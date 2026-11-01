#!/usr/bin/env python3
"""Teclas de PC en lugar de los botones del mando, con el reemplazo de texturas del SDK.

Uso, después de una partida con dump_textures = true en settings.toml:
  python tools\\make_key_icons.py [out\\build\\release\\textures]

Busca en dumps\\ la textura controller_buttons del HUD: 512x64, celdas de 32x32 en el orden de
DATA\\HUD\\shared\\hudart2.xml (nombres de PlayStation, que en Xbox son Y X A B, blanco, negro, gatillos...).
La reconoce por los colores de sus botones (Y amarillo, X azul, A verde, B rojo) y escribe en replacement\\
una imagen 4 veces más grande con el mismo nombre, donde cada celda es la tecla de src/common/controls.cpp.
El SDK la usa en lugar de la original (custom_textures = true). Las celdas sin tecla se quedan como estaban.
También cambia los botones sueltos de 32x32, un círculo de color con la letra blanca: los de la barra de ayuda
de los menús y la pausa ("A Select", "B Back", "X Delete") y los avisos del nivel. Llevan la misma tecla que el HUD.
Con --kenney <carpeta "Keyboard & Mouse\\Double"> usa los dibujos de Kenney Input Prompts (CC0, www.kenney.nl) en
lugar de las teclas dibujadas aquí; el pack se descarga aparte y no va al repositorio.
Necesita Pillow: pip install pillow
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

CELL = 32
SCALE = 4  # la imagen nueva es 4 veces mayor: nítida a 1080p
FONT = r"C:\Windows\Fonts\arialbd.ttf"

# (columna, fila) -> tecla, como src/common/controls.cpp; "mouse:l", "mouse:r" y "mouse:move" se dibujan como un ratón.
# Comprobado sobre la textura volcada: en la Xbox L1 y R1 son los gatillos, L2 y R2 los botones blanco y negro, y la
# fila 1 lleva además los sticks con una flecha (columnas 6 a 13), que hudart2.xml no nombra
KEYS = {
    (0, 0): "SPACE",       # triangle = Y: saltar, levantarse
    (1, 0): "C",           # square = X: agacharse, tumbarse
    (2, 0): "E",           # cross = A: acción, recargar, aceptar
    (3, 0): "Q",           # circle = B: cambiar de arma, volver
    (4, 0): "mouse:r",     # L1 = gatillo izquierdo: apuntar
    (5, 0): "mouse:l",     # R1 = gatillo derecho: disparar
    (6, 0): "H",           # L2 = blanco: botiquín
    (7, 0): "F",           # R2 = negro: adrenalina
    (8, 0): "G",           # cruceta arriba: granada
    (9, 0): "\u2190",      # cruceta izquierda
    (10, 0): "T",          # cruceta abajo: llamar al escuadrón
    (11, 0): "\u2192",     # cruceta derecha
    (12, 0): "Z",          # L3: posicionar al escuadrón
    (13, 0): "V",          # R3: cuerpo a cuerpo
    (14, 0): "mouse:move",  # R3 arriba y abajo: mirar
    (15, 0): "mouse:move",  # R3 izquierda y derecha: mirar
    (0, 1): "TAB",         # select = Back: mapa
    (1, 1): "ESC",         # start: pausa
    (6, 1): "mouse:move",  # stick derecho arriba
    (7, 1): "mouse:move",  # stick derecho izquierda
    (8, 1): "mouse:move",  # stick derecho abajo
    (9, 1): "mouse:move",  # stick derecho derecha
    (10, 1): "W",          # stick izquierdo arriba
    (11, 1): "A",          # stick izquierdo izquierda
    (12, 1): "S",          # stick izquierdo abajo
    (13, 1): "D",          # stick izquierdo derecha
    (14, 1): "WASD",       # L3 arriba y abajo: moverse
    (15, 1): "WASD",       # L3 izquierda y derecha: moverse
}

# cómo reconocer la textura: color medio esperado de algunas celdas
EXPECTED = {(0, 0): "yellow", (1, 0): "blue", (2, 0): "green", (3, 0): "red"}


def dominant(img, col, row, cell=CELL):
    r = g = b = n = 0
    for y in range(row * cell, (row + 1) * cell):
        for x in range(col * cell, (col + 1) * cell):
            pr, pg, pb, pa = img.getpixel((x, y))
            if pa > 128 and max(pr, pg, pb) > 60:
                r, g, b, n = r + pr, g + pg, b + pb, n + 1
    if n < 20:
        return None
    r, g, b = r / n, g / n, b / n
    if r > 1.3 * b and g > 1.3 * b and abs(r - g) < 0.35 * max(r, g):
        return "yellow"
    if g > 1.2 * r and g > 1.2 * b:
        return "green"
    if r > 1.3 * g and r > 1.3 * b:
        return "red"
    if b > 1.2 * r and b > 1.1 * g:
        return "blue"
    return None


def score(img):
    return sum(dominant(img, c, r) == want for (c, r), want in EXPECTED.items())


# los botones sueltos, por su color: la tecla de su celda en controller_buttons
LOOSE = {colour: KEYS[cell] for cell, colour in EXPECTED.items()}

# las teclas de KEYS como dibujos de Kenney Input Prompts; "WASD" se compone con cuatro
KENNEY = {"SPACE": "keyboard_space", "TAB": "keyboard_tab", "ESC": "keyboard_escape", "←": "keyboard_arrow_left",
          "→": "keyboard_arrow_right", "mouse:l": "mouse_left", "mouse:r": "mouse_right",
          "mouse:move": "mouse_move"}


def kenney_icon(folder, label, size):
    """La tecla dibujada por Kenney a size x size, o None si el pack no la tiene."""
    if label == "WASD":
        icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        small = size * 36 // 100
        for key, (x, y) in {"W": (0.5, 0.3), "A": (0.17, 0.7), "S": (0.5, 0.7), "D": (0.83, 0.7)}.items():
            part = kenney_icon(folder, key, small)
            if part is None:
                return None
            icon.alpha_composite(part, (int(x * size - small / 2), int(y * size - small / 2)))
        return icon
    name = KENNEY.get(label, f"keyboard_{label.lower()}")
    path = os.path.join(folder, name + ".png")
    if not os.path.isfile(path):
        return None
    return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)


def place_key(img, x0, y0, label, kenney, s=SCALE):
    """La tecla en la celda de 32 x s píxeles en (x0, y0): de Kenney si hay pack, si no dibujada aquí."""
    size = CELL * s
    icon = kenney_icon(kenney, label, size) if kenney else None
    if icon is not None:
        img.alpha_composite(icon, (x0, y0))
    elif label.startswith("mouse:"):
        draw_mouse(ImageDraw.Draw(img), x0, y0, label.split(":")[1])
    else:
        draw_key(ImageDraw.Draw(img), x0, y0, label, s)


def loose_button(img):
    """El color de un botón suelto (esquinas transparentes y letra blanca en el centro), o None."""
    w, h = img.size
    if w != CELL or h != CELL:
        return None
    if any(img.getpixel(p)[3] > 32 for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))):
        return None
    # la letra: la textura amarilla de 32x32 que no es un botón tiene 1 píxel claro de 256, los botones más de 60
    light = sum(1 for y in range(h // 4, h * 3 // 4) for x in range(w // 4, w * 3 // 4)
                if min(img.getpixel((x, y))[:3]) > 170)
    if light < 30:
        return None
    return dominant(img, 0, 0, w)


def draw_key(draw, x0, y0, label, s=SCALE):
    box = (x0 + 2 * s, y0 + 4 * s, x0 + 30 * s, y0 + 30 * s)
    draw.rounded_rectangle(box, radius=5 * s, fill=(28, 26, 24, 235), outline=(215, 205, 185, 255), width=2 * s)
    draw.line((box[0] + 4 * s, box[1] + 3 * s, box[2] - 4 * s, box[1] + 3 * s), fill=(90, 86, 80, 255), width=s)
    size = {1: 15, 2: 12, 3: 10, 4: 8}.get(len(label), 7) * s
    font = ImageFont.truetype(FONT, size)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2 + s
    draw.text((cx, cy), label, font=font, fill=(240, 232, 215, 255), anchor="mm")


def draw_mouse(draw, x0, y0, which):
    s = SCALE
    body = (x0 + 9 * s, y0 + 3 * s, x0 + 23 * s, y0 + 29 * s)
    draw.rounded_rectangle(body, radius=7 * s, fill=(28, 26, 24, 235), outline=(215, 205, 185, 255), width=2 * s)
    mid = (body[0] + body[2]) / 2
    split = body[1] + 11 * s
    if which in ("l", "r"):
        half = (body[0] + 2 * s, body[1] + 2 * s, mid - s, split) if which == "l" else (mid + s, body[1] + 2 * s, body[2] - 2 * s, split)
        draw.rounded_rectangle(half, radius=4 * s, fill=(225, 120, 40, 255))
    draw.line((mid, body[1] + 2 * s, mid, split), fill=(215, 205, 185, 255), width=s)
    draw.line((body[0] + s, split, body[2] - s, split), fill=(215, 205, 185, 255), width=s)
    if which == "move":
        cy = split + 8 * s
        for dx in (-4, 4):
            draw.ellipse((mid + dx * s - 2 * s, cy - 2 * s, mid + dx * s + 2 * s, cy + 2 * s), fill=(225, 120, 40, 255))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("textures", nargs="?", default=os.path.join("out", "build", "release", "textures"))
    p.add_argument("--kenney", help='carpeta "Keyboard & Mouse\\Double" de Kenney Input Prompts')
    args = p.parse_args()
    if args.kenney and not os.path.isfile(os.path.join(args.kenney, "keyboard_e.png")):
        sys.exit(f"No encuentro keyboard_e.png en {args.kenney}")
    dumps = os.path.join(args.textures, "dumps")
    out_dir = os.path.join(args.textures, "replacement")
    os.makedirs(out_dir, exist_ok=True)

    best, best_score = None, 0
    loose = 0
    for name in sorted(os.listdir(dumps)):
        if not name.endswith(".png"):
            continue
        if name.startswith(f"{CELL}x{CELL}_"):
            img = Image.open(os.path.join(dumps, name)).convert("RGBA")
            colour = loose_button(img)
            if colour in LOOSE:
                big = Image.new("RGBA", (CELL * SCALE, CELL * SCALE), (0, 0, 0, 0))
                place_key(big, 0, 0, LOOSE[colour], args.kenney)
                big.save(os.path.join(out_dir, name))
                print(f"  {name}: botón suelto {colour}, tecla {LOOSE[colour]}")
                loose += 1
            continue
        if not name.startswith("512x64_"):
            continue
        img = Image.open(os.path.join(dumps, name)).convert("RGBA")
        sc = score(img)
        print(f"  {name}: {sc} de {len(EXPECTED)} botones reconocidos")
        if sc > best_score:
            best, best_score = (name, img), sc
    if loose:
        print(f"{loose} botones sueltos escritos en {out_dir}")
    if not best or best_score < 3:
        if loose:
            return
        sys.exit("No encuentro la textura controller_buttons en los volcados: juega hasta que salga un "
                 "\"Press [ ] to...\" con dump_textures = true y vuelve a probar.")

    name, original = best
    w, h = original.size
    big = original.resize((w * SCALE, h * SCALE), Image.LANCZOS)
    draw = ImageDraw.Draw(big)
    for (col, row), key in KEYS.items():
        x0, y0 = col * CELL * SCALE, row * CELL * SCALE
        draw.rectangle((x0, y0, x0 + CELL * SCALE - 1, y0 + CELL * SCALE - 1), fill=(0, 0, 0, 0))
        place_key(big, x0, y0, key, args.kenney)
    path = os.path.join(out_dir, name)
    big.save(path)
    print(f"Teclas escritas en {path} ({w * SCALE}x{h * SCALE})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

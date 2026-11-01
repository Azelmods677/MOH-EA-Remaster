#!/usr/bin/env python3
"""Imágenes del README a partir de capturas del juego (F12) y clips (F11), en out\\build\\release\\screenshots.

Uso:
  python tools\\make_readme_media.py banner <captura> [<captura> ...]   docs\\images\\banner.png y social-preview.png
  python tools\\make_readme_media.py compare <captura> <nombre>          una captura en modo comparación (F9 una vez):
                                                                        las mitades rotuladas "sin efectos" y
                                                                        "remaster", en docs\\images\\<nombre>.webp
  python tools\\make_readme_media.py pair <original> <remaster> <nombre> dos capturas de la misma escena, en modo
                                                                        original (F9 dos veces: sin efectos ni pack)
                                                                        y remaster, lado a lado
  python tools\\make_readme_media.py clip <carpeta clip_...> <nombre>    un GIF de 640 px a 15 imágenes por segundo,
                                                                        en docs\\images\\<nombre>.gif
  python tools\\make_readme_media.py trailer --clips <clip_...> [...] --stills <captura> [...] [--titles "..." ...]
                                                                        un tráiler MP4 1080p con FFmpeg: banner,
                                                                        clips rotulados, capturas con zoom lento y
                                                                        cierre, en out\\trailer.mp4 (para la release:
                                                                        GitHub no reproduce MP4 del repositorio)

Las capturas tienen que ser del juego, y de tu copia: nada del disco va al repositorio.
Necesita Pillow: pip install pillow
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "docs", "images")
TITLE_FONT = r"C:\Windows\Fonts\impact.ttf"
TEXT_FONT = r"C:\Windows\Fonts\arialbd.ttf"
CREAM, RED, AMBER = (240, 230, 210), (178, 34, 34), (230, 150, 60)


def font(path, size):
    return ImageFont.truetype(path, size)


def shadow_text(draw, at, text, fnt, fill, offset=3):
    draw.text((at[0] + offset, at[1] + offset), text, font=fnt, fill=(0, 0, 0, 220))
    draw.text(at, text, font=fnt, fill=fill)


def cover(img, w, h):
    """img recortada al centro para llenar w x h."""
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def collage(shots, w, h):
    """Las capturas en franjas inclinadas, más oscuras a la izquierda, donde va el texto."""
    base = Image.new("RGB", (w, h), (12, 10, 9))
    n = len(shots)
    slant = h // 3
    for i, shot in enumerate(shots):
        x0 = w * (0.35 + 0.65 * i / n)
        x1 = w * (0.35 + 0.65 * (i + 1) / n)
        panel = cover(shot, int(x1 - x0) + slant * 2, h)
        panel = ImageEnhance.Contrast(ImageEnhance.Brightness(panel).enhance(1.35)).enhance(1.15)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon([(x0 + slant, 0), (x1 + slant, 0), (x1, h), (x0, h)], fill=255)
        layer = Image.new("RGB", (w, h))
        layer.paste(panel, (int(x0) - slant // 2, 0))
        base.paste(layer, (0, 0), mask)
        ImageDraw.Draw(base).line([(x0 + slant, 0), (x0, h)], fill=(20, 18, 16), width=6)
    # oscuro a la izquierda para el título
    fade = Image.linear_gradient("L").rotate(90).resize((w, h))
    dark = Image.new("RGB", (w, h), (10, 9, 8))
    base = Image.composite(base, dark, fade.point(lambda v: min(255, int(v * 1.5))))
    return base


def chips(draw, x, y, items, fnt, max_x):
    for item in items:
        tw = draw.textlength(item, font=fnt)
        if x + tw + 28 > max_x:
            break
        draw.rounded_rectangle((x, y, x + tw + 24, y + fnt.size + 16), radius=6, fill=(20, 18, 16, 210),
                               outline=(150, 130, 100, 255), width=2)
        draw.text((x + 12, y + 7), item, font=fnt, fill=CREAM)
        x += tw + 36


def banner(shots, w, h, path, chip_items):
    img = collage(shots, w, h).convert("RGBA")
    draw = ImageDraw.Draw(img)
    s = h / 500
    x = int(60 * s)
    shadow_text(draw, (x, int(70 * s)), "MEDAL OF HONOR", font(TITLE_FONT, int(92 * s)), CREAM, int(4 * s))
    shadow_text(draw, (x, int(165 * s)), "EUROPEAN ASSAULT", font(TITLE_FONT, int(70 * s)), CREAM, int(4 * s))
    badge = font(TITLE_FONT, int(46 * s))
    by = int(262 * s)
    bw = draw.textlength("REMASTER", font=badge)
    draw.rectangle((x, by, x + bw + int(36 * s), by + int(62 * s)), fill=RED)
    draw.text((x + int(18 * s), by + int(4 * s)), "REMASTER", font=badge, fill=CREAM)
    shadow_text(draw, (x + bw + int(56 * s), by + int(12 * s)), "PORT NATIVO PARA PC",
                font(TEXT_FONT, int(32 * s)), CREAM, int(2 * s))
    shadow_text(draw, (x, int(345 * s)), "Xbox original  →  Windows x64  ·  Direct3D 12  ·  sin emulador",
                font(TEXT_FONT, int(24 * s)), (215, 205, 185), int(2 * s))
    chips(draw, x, int(400 * s), chip_items, font(TEXT_FONT, int(20 * s)), w - int(40 * s))
    shadow_text(draw, (w - int(330 * s), h - int(42 * s)), "por AzelModsX677", font(TEXT_FONT, int(24 * s)), AMBER,
                int(2 * s))
    img.convert("RGB").save(path, optimize=True)
    print(f"  {path} ({w}x{h})")


def label(img, text, left):
    draw = ImageDraw.Draw(img)
    fnt = font(TITLE_FONT, max(24, img.height // 18))
    pad = img.height // 30
    tw = draw.textlength(text, font=fnt)
    x = pad if left else img.width - pad - tw
    draw.rectangle((x - 12, pad - 6, x + tw + 12, pad + fnt.size + 12), fill=(15, 13, 12))
    draw.text((x, pad), text, font=fnt, fill=CREAM if left else AMBER)


def save_webp(img, name, width=1600):
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    path = os.path.join(IMAGES, name + ".webp")
    img.save(path, quality=90, method=6)
    print(f"  {path} ({img.width}x{img.height})")


VIDEO_W, VIDEO_H, FPS = 1920, 1080, 30


def fit(img, w, h):
    """img dentro de w x h, centrada sobre negro."""
    scale = min(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), (8, 7, 6))
    canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    return canvas


def caption(img, text):
    """Rótulo abajo a la izquierda, como en los tráileres."""
    img = img.copy()
    draw = ImageDraw.Draw(img)
    fnt = font(TITLE_FONT, 54)
    tw = draw.textlength(text, font=fnt)
    draw.rectangle((60, VIDEO_H - 150, 60 + 14, VIDEO_H - 82), fill=RED)
    shadow_text(draw, (92, VIDEO_H - 156), text, fnt, CREAM, 3)
    return img


def fade(img, k):
    return Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, max(0.0, min(1.0, k)))


def card(lines):
    """Una pantalla de texto centrado: (texto, tamaño, color)."""
    img = Image.new("RGB", (VIDEO_W, VIDEO_H), (10, 9, 8))
    draw = ImageDraw.Draw(img)
    heights = [size * 1.35 for _, size, _ in lines]
    y = (VIDEO_H - sum(heights)) / 2
    for (text, size, color), h in zip(lines, heights):
        fnt = font(TITLE_FONT, size)
        draw.text(((VIDEO_W - draw.textlength(text, font=fnt)) / 2, y), text, font=fnt, fill=color)
        y += h
    return img


SERIF_FONT = r"C:\Windows\Fonts\georgiab.ttf"


def cinema(img):
    """Bandas negras de cine (2,39:1) sobre un fotograma 16:9."""
    img = img.copy()
    bar = round((VIDEO_H - VIDEO_W / 2.39) / 2)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, VIDEO_W, bar), fill=(0, 0, 0))
    draw.rectangle((0, VIDEO_H - bar, VIDEO_W, VIDEO_H), fill=(0, 0, 0))
    return img


def soundtrack(path, seconds, hits):
    """Banda sonora propia, hecha aquí con FFmpeg (sin música del juego): un zumbido grave que respira, viento y un
    golpe de tambor en cada corte."""
    import subprocess
    boom = "+".join(f"gte(t,{h:.2f})*exp(-3.2*max(t-{h:.2f},0))*(0.9*sin(2*PI*46*(t-{h:.2f}))"
                    f"+0.35*sin(2*PI*92*(t-{h:.2f})))" for h in hits) or "0"
    graph = (f"sine=f=55:d={seconds}[a];sine=f=82.41:d={seconds}[b];sine=f=110:d={seconds},volume=0.35[c];"
             f"[a][b][c]amix=inputs=3,tremolo=f=0.2:d=0.5[drone];"
             f"anoisesrc=color=brown:amplitude=0.6:d={seconds},lowpass=f=350[wind];"
             f"aevalsrc='{boom}':d={seconds}:s=44100[hits];"
             f"[drone][wind][hits]amix=inputs=3:weights='1 0.6 2.2',afade=t=in:d=2,"
             f"afade=t=out:st={max(seconds - 3, 0):.2f}:d=3,loudnorm=I=-16[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-filter_complex", graph, "-map", "[out]", "-ar", "44100",
                    path], check=True)


def trailer(clips, stills, titles, out_path):
    import shutil
    import subprocess
    import tempfile

    work = tempfile.mkdtemp(prefix="trailer_")
    count = 0

    def emit(img):  # cada fotograma va a disco al momento: un tráiler en memoria serían gigas
        nonlocal count
        img.save(os.path.join(work, f"{count:05d}.png"), compress_level=1)
        count += 1

    def hold(img, seconds, fade_in=0.4, fade_out=0.4):
        n = round(seconds * FPS)
        for i in range(n):
            t = i / FPS
            k = min(1.0, t / fade_in if fade_in else 1.0, (seconds - t) / fade_out if fade_out else 1.0)
            emit(fade(img, k) if k < 1 else img)

    hits = []  # los cortes, para los golpes de la música

    def cut():
        hits.append(count / FPS)

    # como la intro del juego: negro, "EUROPA, 1942" en letra de época, y el título
    hold(Image.new("RGB", (VIDEO_W, VIDEO_H)), 1.0, 0, 0)
    cut()
    era = Image.new("RGB", (VIDEO_W, VIDEO_H), (6, 5, 4))
    d = ImageDraw.Draw(era)
    for text, y, size in (("EUROPA", 420, 110), ("1942", 560, 110)):
        f = font(SERIF_FONT, size)
        d.text(((VIDEO_W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=(225, 220, 210))
    hold(era, 3.5, 1.2, 1.0)
    cut()
    banner_img = Image.open(os.path.join(IMAGES, "banner.png")).convert("RGB")
    hold(fit(banner_img, VIDEO_W, VIDEO_H), 4.0, 0.8, 0.6)
    cut()
    hold(card([("PORT NATIVO PARA PC", 96, CREAM), ("XBOX ORIGINAL  →  WINDOWS x64  ·  DIRECT3D 12", 48, AMBER),
               ("SIN EMULADOR", 48, AMBER)]), 3.0)
    for i, folder in enumerate(clips):
        cut()
        title = titles[i] if i < len(titles) else ""
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".png"))
        for j, n in enumerate(names):
            shot = cinema(fit(Image.open(os.path.join(folder, n)).convert("RGB"), VIDEO_W, VIDEO_H))
            img = caption(shot, title) if title else shot
            k = min(1.0, (j + 1) / 6, (len(names) - j) / 6)
            for _ in range(FPS // 15):  # los clips van a 15 por segundo
                emit(fade(img, k) if k < 1 else img)
    for path in stills:
        cut()
        still = Image.open(path).convert("RGB")
        base = fit(still, VIDEO_W, VIDEO_H)
        n = round(3.5 * FPS)
        for i in range(n):  # acercamiento lento del 100 % al 106 %
            z = 1 + 0.06 * i / n
            cw, ch = VIDEO_W / z, VIDEO_H / z
            x, y = (VIDEO_W - cw) / 2, (VIDEO_H - ch) / 2
            img = base.crop((round(x), round(y), round(x + cw), round(y + ch))).resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
            k = min(1.0, i / 10, (n - i) / 10)
            emit(fade(img, k) if k < 1 else img)
    cut()
    hold(card([("MEDAL OF HONOR: EUROPEAN ASSAULT", 84, CREAM), ("REMASTER", 120, RED),
               ("por AzelModsX677", 52, AMBER)]), 4.5, 0.6, 1.5)

    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        music = os.path.join(work, "music.wav")
        soundtrack(music, count / FPS, hits)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
                        os.path.join(work, "%05d.png"), "-i", music, "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        out_path], check=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"  {out_path}: {count / FPS:.1f} s, {os.path.getsize(out_path) // 1024} KB")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("banner")
    b.add_argument("shots", nargs="+")
    c = sub.add_parser("compare")
    c.add_argument("shot")
    c.add_argument("name")
    pr = sub.add_parser("pair")
    pr.add_argument("original")
    pr.add_argument("remaster")
    pr.add_argument("name")
    cl = sub.add_parser("clip")
    cl.add_argument("folder")
    cl.add_argument("name")
    cl.add_argument("--width", type=int, default=640)
    tr = sub.add_parser("trailer")
    tr.add_argument("--clips", nargs="*", default=[])
    tr.add_argument("--stills", nargs="*", default=[])
    tr.add_argument("--titles", nargs="*", default=[], help="un rótulo por clip, en orden")
    tr.add_argument("--out", default=os.path.join(ROOT, "out", "trailer.mp4"))
    args = p.parse_args()
    os.makedirs(IMAGES, exist_ok=True)

    if args.cmd == "banner":
        shots = [Image.open(s).convert("RGB") for s in args.shots]
        items = ["FXAA", "BLOOM", "NITIDEZ", "COLOR", "16:9", "TECLADO Y RATÓN", "MODO ASALTO"]
        banner(shots, 1600, 500, os.path.join(IMAGES, "banner.png"), items)
        banner(shots, 1280, 640, os.path.join(IMAGES, "social-preview.png"), items[:5])
    elif args.cmd == "compare":
        img = Image.open(args.shot).convert("RGB")
        label(img, "SIN EFECTOS", True)  # el pack de texturas está en las dos mitades
        label(img, "REMASTER", False)
        save_webp(img, args.name)
    elif args.cmd == "pair":
        a, r = Image.open(args.original).convert("RGB"), Image.open(args.remaster).convert("RGB")
        r = r.resize(a.size, Image.LANCZOS)
        label(a, "ORIGINAL", True)
        label(r, "REMASTER", True)
        gap = a.width // 160
        both = Image.new("RGB", (a.width * 2 + gap, a.height), (15, 13, 12))
        both.paste(a, (0, 0))
        both.paste(r, (a.width + gap, 0))
        save_webp(both, args.name, 2400)
    elif args.cmd == "clip":
        names = sorted(n for n in os.listdir(args.folder) if n.lower().endswith(".png"))
        if not names:
            sys.exit(f"No hay imágenes PNG en {args.folder}")
        frames = []
        for n in names:
            im = Image.open(os.path.join(args.folder, n)).convert("RGB")
            im = im.resize((args.width, round(im.height * args.width / im.width)), Image.LANCZOS)
            frames.append(im.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG))
        path = os.path.join(IMAGES, args.name + ".gif")
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=67, loop=0, optimize=True)
        print(f"  {path}: {len(frames)} imágenes, {os.path.getsize(path) // 1024} KB")
    elif args.cmd == "trailer":
        trailer(args.clips, args.stills, args.titles, args.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

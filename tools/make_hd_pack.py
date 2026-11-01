#!/usr/bin/env python3
"""Pack de texturas HD con IA, hecho en tu PC a partir de las texturas volcadas de tu copia del juego.

Uso, después de jugar con dump_textures = true en settings.toml:
  python tools\\make_hd_pack.py --esrgan <carpeta de realesrgan-ncnn-vulkan.exe> [out\\build\\release\\textures]

Cada textura del mundo (opaca, o con recortes como verjas y hojas) se reescala 4 veces con Real-ESRGAN
(realesrgan-x4plus) y se reduce con Lanczos a su tamaño final: x4 hasta 128 píxeles, x2 por encima, nunca más de
1024. Así la gráfica no se llena de memoria: el SDK carga los PNG sin comprimir y les hace mipmaps.
- Antes de reescalar, la textura se rodea de sus propios bordes opuestos: las que se repiten (suelos, paredes) no
  dejan costuras.
- La transparencia se reescala aparte con Lanczos; si era de recorte (0 o 255), se vuelve a recortar.
- Se saltan las que son sobre todo transparentes (letras, HUD, fuego, humo): la IA las estropea.
- Se saltan las que ya tienen reemplazo fuera de hd\\ (las teclas de make_key_icons.py).
El resultado va a textures\\replacement\\hd\\, con el mismo nombre que el volcado: el SDK lo usa en su lugar.
Nada de esto va al repositorio: son texturas del juego.

Real-ESRGAN: https://github.com/xinntao/Real-ESRGAN (BSD-3), versión ncnn-vulkan (funciona en AMD, NVIDIA e Intel).
Necesita Pillow: pip install pillow
"""
import argparse
import os
import shutil
import subprocess
import sys

from PIL import Image

PAD = 16              # píxeles de borde envueltos antes de reescalar
MAX_SIDE = 1024
MIN_SIDE = 32
TRANSPARENT_SHARE = 0.30  # más transparente que esto: letras, HUD o partículas


def target_scale(w, h):
    scale = 4 if max(w, h) <= 128 else 2
    while scale > 1 and max(w, h) * scale > MAX_SIDE:
        scale //= 2
    return scale


def classify(img):
    """'opaque', 'cutout', 'alpha' o None si no conviene reescalarla."""
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    total = img.width * img.height
    transparent = sum(hist[:128]) / total
    if transparent > TRANSPARENT_SHARE:
        return None
    if sum(hist[:250]) == 0:
        return "opaque"
    binary = (hist[0] + hist[255]) / total
    return "cutout" if binary > 0.98 else "alpha"


def wrap_pad(rgb):
    w, h = rgb.size
    big = Image.new("RGB", (w + 2 * PAD, h + 2 * PAD))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            big.paste(rgb, (PAD + dx * w, PAD + dy * h))
    return big


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("textures", nargs="?", default=os.path.join("out", "build", "release", "textures"))
    p.add_argument("--esrgan", required=True, help="carpeta con realesrgan-ncnn-vulkan.exe y models\\")
    p.add_argument("--work", default=os.path.join("out", "hd_work"))
    p.add_argument("--tile", default="128", help="tamaño de tesela de la IA: menos memoria de vídeo con valores bajos")
    p.add_argument("--limit", type=int, default=0, help="solo las N primeras (para probar)")
    p.add_argument("--max-input", type=int, default=256,
                   help="se saltan las texturas con un lado mayor: las de 512 ya se ven bien y son las más lentas")
    p.add_argument("--finish-only", action="store_true",
                   help="solo termina las que la IA ya ha escrito en <work>\\up, sin volver a lanzarla: el pack a medias "
                        "mientras otra pasada sigue")
    args = p.parse_args()

    textures, esrgan, work = (os.path.abspath(d) for d in (args.textures, args.esrgan, args.work))
    dumps = os.path.join(textures, "dumps")
    replacement = os.path.join(textures, "replacement")
    out_dir = os.path.join(replacement, "hd")
    exe = os.path.join(esrgan, "realesrgan-ncnn-vulkan.exe")
    if not os.path.isfile(exe):
        sys.exit(f"No encuentro {exe}")
    taken = {n for n in os.listdir(replacement) if n.endswith(".png")} if os.path.isdir(replacement) else set()

    src_dir, up_dir = os.path.join(work, "in"), os.path.join(work, "up")
    os.makedirs(out_dir, exist_ok=True)
    if args.finish_only:
        jobs = {}
        for name in sorted(os.listdir(up_dir)):
            img = Image.open(os.path.join(dumps, name)).convert("RGBA")
            jobs[name] = (classify(img), img.size)
        finish(jobs, dumps, up_dir, out_dir)
        return
    for d in (src_dir, up_dir):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    jobs, skipped = {}, 0
    for name in sorted(os.listdir(dumps)):
        if not name.endswith(".png") or name in taken:
            continue
        img = Image.open(os.path.join(dumps, name)).convert("RGBA")
        if min(img.size) < MIN_SIDE or max(img.size) > args.max_input:
            skipped += 1
            continue
        kind = classify(img)
        if not kind:
            skipped += 1
            continue
        jobs[name] = (kind, img.size)
        wrap_pad(img.convert("RGB")).save(os.path.join(src_dir, name))
        if args.limit and len(jobs) >= args.limit:
            break
    print(f"{len(jobs)} texturas para reescalar, {skipped} saltadas (muy pequeñas, grandes o sobre todo transparentes)")
    if not jobs:
        return

    print("Real-ESRGAN x4 (puede tardar varios minutos)...")
    subprocess.run([exe, "-i", src_dir, "-o", up_dir, "-n", "realesrgan-x4plus", "-s", "4", "-t", args.tile, "-f",
                    "png"], check=True, cwd=esrgan)
    finish(jobs, dumps, up_dir, out_dir)


def finish(jobs, dumps, up_dir, out_dir):
    """De la salida x4 de la IA al tamaño final, con su transparencia, en out_dir."""
    done = 0
    for name, (kind, (w, h)) in jobs.items():
        up_path = os.path.join(up_dir, name)
        if not os.path.isfile(up_path):
            print(f"  falta {name}")
            continue
        try:
            up = Image.open(up_path).convert("RGB")
        except OSError:  # la IA aún la está escribiendo (--finish-only con otra pasada en marcha)
            print(f"  aún no se puede leer {name}")
            continue
        up = up.crop((PAD * 4, PAD * 4, PAD * 4 + w * 4, PAD * 4 + h * 4))
        scale = target_scale(w, h)
        size = (w * scale, h * scale)
        rgb = up.resize(size, Image.LANCZOS) if scale != 4 else up
        result = rgb.convert("RGBA")
        if kind != "opaque":
            alpha = Image.open(os.path.join(dumps, name)).convert("RGBA").getchannel("A").resize(size, Image.LANCZOS)
            if kind == "cutout":
                alpha = alpha.point(lambda v: 255 if v >= 128 else 0)
            result.putalpha(alpha)
        result.save(os.path.join(out_dir, name), optimize=False)
        done += 1
    print(f"{done} texturas HD en {out_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

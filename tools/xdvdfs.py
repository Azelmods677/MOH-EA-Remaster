#!/usr/bin/env python3
"""Lector de discos de Xbox original (sistema de archivos XDVDFS).

Uso:
  python xdvdfs.py list    <imagen.iso> [--tsv salida.tsv]
  python xdvdfs.py extract <imagen.iso> <destino> [patrones...]
  python xdvdfs.py xiso    <imagen.iso> <salida.iso>

Acepta imágenes XISO (solo la partición del juego) y redump (el DVD completo).
Los patrones usan comodines estilo glob sobre la ruta, por ejemplo "default.xbe" o "Data/*".
"""
import argparse
import fnmatch
import os
import struct
import sys

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
# Byte donde empieza la partición del juego según el tipo de imagen.
PARTITIONS = [
    ("XISO", 0),
    ("redump XGD1 (Xbox original)", 0x18300000),
    ("redump XGD2 (Xbox 360)", 0xFD90000),
    ("redump XGD3 (Xbox 360)", 0x2080000),
]
ATTR_DIRECTORY = 0x10


def find_partition(f):
    """Devuelve (tipo, offset, sector_raíz, tamaño_raíz) buscando el descriptor de volumen."""
    for kind, base in PARTITIONS:
        # El descriptor de volumen está en el sector 32 de la partición.
        f.seek(base + 32 * SECTOR)
        d = f.read(SECTOR)
        if d[:20] == MAGIC and d[0x7EC:0x800] == MAGIC:
            root_sector, root_size = struct.unpack_from("<II", d, 20)
            return kind, base, root_sector, root_size
    raise SystemExit("No es una imagen de Xbox: no aparece MICROSOFT*XBOX*MEDIA")


def read_directory(f, base, sector, size):
    """Lee una tabla de directorio.

    Cada directorio es un árbol binario ordenado por nombre. Cada entrada tiene:
    izquierda u16, derecha u16 (desplazamientos en grupos de 4 bytes), sector u32,
    tamaño u32, atributos u8, longitud del nombre u8 y el nombre.
    """
    if size == 0:
        return []
    f.seek(base + sector * SECTOR)
    data = f.read(size)
    entries, seen, pending = [], set(), [0]
    while pending:
        off = pending.pop()
        if off in seen or off + 14 > len(data):
            continue
        seen.add(off)
        left, right, start, length, attr, name_len = struct.unpack_from("<HHIIBB", data, off)
        if left == 0xFFFF:  # relleno al final de un sector
            continue
        name = data[off + 14:off + 14 + name_len].decode("latin-1")
        entries.append((name, start, length, attr))
        if left:
            pending.append(left * 4)
        if right:
            pending.append(right * 4)
    return sorted(entries, key=lambda e: e[0].lower())


def walk(f, base, sector, size, prefix=""):
    """Recorre todo el disco y produce (ruta, sector, tamaño, es_directorio)."""
    for name, start, length, attr in read_directory(f, base, sector, size):
        if name in ("", ".", "..") or "/" in name or "\\" in name:
            raise SystemExit(f"Nombre de archivo no válido en el disco: {name!r}")
        path = prefix + name
        is_dir = bool(attr & ATTR_DIRECTORY)
        yield path, start, length, is_dir
        if is_dir:
            yield from walk(f, base, start, length, path + "/")


def copy_range(f, offset, length, out):
    f.seek(offset)
    while length:
        chunk = f.read(min(length, 8 << 20))
        if not chunk:
            raise SystemExit("La imagen se acaba antes de lo esperado (¿descarga incompleta?)")
        out.write(chunk)
        length -= len(chunk)


def cmd_list(args):
    with open(args.image, "rb") as f:
        kind, base, root, root_size = find_partition(f)
        print(f"Imagen: {kind}, partición del juego en 0x{base:X}")
        files = total = 0
        tsv = open(args.tsv, "w", encoding="utf-8") if args.tsv else None
        for path, start, length, is_dir in walk(f, base, root, root_size):
            if tsv:
                tsv.write(f"{path}\t{'dir' if is_dir else length}\n")
            if not is_dir:
                files += 1
                total += length
                if not tsv:
                    print(f"{length:>12}  {path}")
        if tsv:
            tsv.close()
        print(f"{files} archivos, {total / 2**20:.1f} MiB")


def cmd_extract(args):
    dest = os.path.abspath(args.dest)
    with open(args.image, "rb") as f:
        kind, base, root, root_size = find_partition(f)
        print(f"Imagen: {kind}, partición del juego en 0x{base:X}")
        count = 0
        for path, start, length, is_dir in walk(f, base, root, root_size):
            if args.patterns and not any(fnmatch.fnmatch(path.lower(), p.lower()) for p in args.patterns):
                continue
            target = os.path.abspath(os.path.join(dest, *path.split("/")))
            if os.path.commonpath([dest, target]) != dest:
                raise SystemExit(f"Ruta fuera del destino: {path}")
            if is_dir:
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                copy_range(f, base + start * SECTOR, length, out)
            count += 1
            print(f"  {path} ({length} bytes)")
        print(f"{count} archivos extraídos en {dest}")


def cmd_xiso(args):
    with open(args.image, "rb") as f:
        kind, base, _, _ = find_partition(f)
        f.seek(0, os.SEEK_END)
        size = f.tell() - base
        print(f"Imagen: {kind}; copiando {size / 2**30:.2f} GiB desde 0x{base:X}")
        with open(args.out, "wb") as out:
            copy_range(f, base, size, out)
    print(f"XISO escrita en {args.out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list", help="lista los archivos del disco")
    s.add_argument("image")
    s.add_argument("--tsv", help="guarda la lista en un archivo TSV")
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("extract", help="extrae archivos")
    s.add_argument("image")
    s.add_argument("dest")
    s.add_argument("patterns", nargs="*")
    s.set_defaults(fn=cmd_extract)
    s = sub.add_parser("xiso", help="convierte un redump en XISO (para xemu)")
    s.add_argument("image")
    s.add_argument("out")
    s.set_defaults(fn=cmd_xiso)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

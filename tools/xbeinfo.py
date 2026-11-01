#!/usr/bin/env python3
"""Muestra la cabecera de un ejecutable de Xbox original (.xbe).

Uso:
  python xbeinfo.py <default.xbe>

Imprime el certificado (título, región, versión), las secciones de código y datos,
y las librerías del XDK con su número de build, que es lo que decide qué firmas usa el recompilador.
"""
import datetime
import hashlib
import struct
import sys

# Las direcciones de entrada y del thunk del kernel vienen ofuscadas con XOR; la clave cambia entre retail y debug.
ENTRY_KEYS = {"retail": 0xA8FC57AB, "debug": 0x94859D4B}
THUNK_KEYS = {"retail": 0x5B6D40B6, "debug": 0xEFB1F152}
REGIONS = {0x1: "Norteamérica", 0x2: "Japón", 0x4: "resto del mundo", 0x80000000: "fabricación"}
SECTION_FLAGS = {0x1: "escritura", 0x2: "precarga", 0x4: "ejecutable", 0x8: "archivo insertado", 0x10: "head-readonly", 0x20: "tail-readonly"}


def main(path):
    d = open(path, "rb").read()
    if d[:4] != b"XBEH":
        raise SystemExit("No es un XBE: falta la firma XBEH")
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]
    base = u32(0x104)
    at = lambda va: va - base  # dirección virtual -> posición en el archivo (válido para la cabecera)

    def cstr(va):
        o = at(va)
        return d[o:d.index(b"\0", o)].decode("latin-1")

    size_image = u32(0x10C)
    for kind, key in ENTRY_KEYS.items():
        entry = u32(0x128) ^ key
        if base <= entry < base + size_image:
            break
    thunk = u32(0x158) ^ THUNK_KEYS[kind]
    stamp = datetime.datetime.fromtimestamp(u32(0x114), datetime.UTC)

    print(f"Archivo        {path}")
    print(f"SHA-1          {hashlib.sha1(d).hexdigest().upper()}")
    print(f"Tamaño         {len(d)} bytes")
    print(f"Tipo           {kind}")
    print(f"Dirección base 0x{base:08X}")
    print(f"Tamaño imagen  0x{size_image:X} ({size_image / 2**20:.2f} MiB en memoria)")
    print(f"Entrada        0x{entry:08X}")
    print(f"Thunk kernel   0x{thunk:08X}")
    print(f"Compilado      {stamp:%Y-%m-%d %H:%M} UTC")
    print(f"Ruta debug     {cstr(u32(0x14C))}")

    c = at(u32(0x118))
    title_id = u32(c + 0x8)
    name = d[c + 0xC:c + 0xC + 0x50].decode("utf-16-le").split("\0")[0]
    region = u32(c + 0xA0)
    regions = ", ".join(v for k, v in REGIONS.items() if region & k) or "ninguna"
    publisher = bytes([title_id >> 24, (title_id >> 16) & 0xFF]).decode("latin-1")
    print("\nCertificado")
    print(f"  Título       {name}")
    print(f"  Title ID     0x{title_id:08X} ({publisher}-{title_id & 0xFFFF:03d})")
    print(f"  Región       0x{region:X} ({regions})")
    print(f"  Disco        {u32(c + 0xA8)}")
    print(f"  Versión      {u32(c + 0xAC)}")

    print("\nSecciones")
    print(f"  {'nombre':<10} {'dirección':>10} {'tamaño':>10}  atributos")
    for i in range(u32(0x11C)):
        h = at(u32(0x120)) + i * 0x38
        flags, va, vsize, raw, rsize, name_va = struct.unpack_from("<IIIIII", d, h)
        attrs = ", ".join(v for k, v in SECTION_FLAGS.items() if flags & k)
        print(f"  {cstr(name_va):<10} 0x{va:08X} {vsize:>10}  {attrs}")

    print("\nLibrerías del XDK")
    for i in range(u32(0x160)):
        o = at(u32(0x164)) + i * 16
        lib = d[o:o + 8].split(b"\0")[0].decode("latin-1")
        major, minor, build, flags = struct.unpack_from("<HHHH", d, o + 8)
        debug = " (debug)" if flags & 0x8000 else ""
        print(f"  {lib:<9} {major}.{minor}.{build}  QFE {flags & 0x1FFF}{debug}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

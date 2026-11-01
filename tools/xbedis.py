#!/usr/bin/env python3
"""Desensambla código x86 de un .xbe a partir de una dirección, con los nombres de config/game.toml.

Uso:
  python tools\\xbedis.py <default.xbe> <dirección> [instrucciones] [--config config\\game.toml]
  python tools\\xbedis.py <default.xbe> --find <dirección>     Busca el símbolo conocido más cercano por debajo

Las direcciones van en hexadecimal (0x2DC16F o 2DC16F). Necesita capstone: pip install capstone
"""
import argparse
import bisect
import struct
import sys
import tomllib

import capstone


class Xbe:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        u32 = lambda o: struct.unpack_from("<I", self.d, o)[0]
        self.base = u32(0x104)
        self.sections = []
        for i in range(u32(0x11C)):
            h = u32(0x120) - self.base + i * 0x38
            _, va, vsize, raw, rsize, name_va = struct.unpack_from("<IIIIII", self.d, h)
            o = name_va - self.base
            name = self.d[o:self.d.index(b"\0", o)].decode("latin-1")
            self.sections.append((name, va, vsize, raw, rsize))

    def section(self, addr):
        for s in self.sections:
            if s[1] <= addr < s[1] + s[2]:
                return s
        return None

    def read(self, addr, size):
        s = self.section(addr)
        if not s:
            raise SystemExit(f"0x{addr:X} no está en ninguna sección del XBE")
        name, va, vsize, raw, rsize = s
        start = addr - va
        return self.d[raw + start:raw + min(rsize, start + size)]


def load_names(path):
    try:
        cfg = tomllib.load(open(path, "rb"))
    except FileNotFoundError:
        return {}
    names = {}
    for table in ("symbols", "data"):
        for k, v in cfg.get(table, {}).items():
            if isinstance(v, int) and v:
                names[v] = k
    return names


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xbe")
    p.add_argument("addr", nargs="?")
    p.add_argument("count", nargs="?", type=int, default=30)
    p.add_argument("--config", default="config/game.toml")
    p.add_argument("--find")
    args = p.parse_args()
    xbe = Xbe(args.xbe)
    names = load_names(args.config)
    addrs = sorted(names)

    if args.find:
        a = int(args.find, 16)
        i = bisect.bisect_right(addrs, a) - 1
        s = xbe.section(a)
        where = f"sección {s[0]}" if s else "fuera del XBE"
        near = f"{names[addrs[i]]} + 0x{a - addrs[i]:X}" if i >= 0 else "ninguno"
        print(f"0x{a:X}: {where}; símbolo conocido más cercano por debajo: {near}")
        return

    addr = int(args.addr, 16)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for n, ins in enumerate(md.disasm(xbe.read(addr, args.count * 15), addr)):
        if n >= args.count:
            break
        label = f"\n{names[ins.address]}:" if ins.address in names else ""
        if label:
            print(label)
        note = ""
        for op in ins.op_str.replace("[", " ").replace("]", " ").replace(",", " ").split():
            if op.startswith("0x") and int(op, 16) in names:
                note = f"   ; {names[int(op, 16)]}"
        print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<24} {ins.mnemonic} {ins.op_str}{note}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

#!/usr/bin/env python3
"""Busca quién usa una dirección (un texto, una variable) en el código de un .xbe.

Uso:
  python tools\\xberefs.py <default.xbe> 3171E0 302438     direcciones en hexadecimal
  python tools\\xberefs.py <default.xbe> --text "SoldierObject"   busca el texto y luego quién lo usa

Para cada uso imprime la instrucción y la función que la contiene (según out\\xbecalls.json, que crea
tools\\xbecalls.py). Necesita capstone: pip install capstone
"""
import argparse
import bisect
import json
import os
import re
import struct
import sys

import capstone

from xbedis import Xbe


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xbe")
    p.add_argument("addrs", nargs="*")
    p.add_argument("--text")
    args = p.parse_args()
    xbe = Xbe(args.xbe)
    targets = [int(a, 16) for a in args.addrs]
    if args.text:
        for name, va, vsize, raw, rsize in xbe.sections:
            if name in (".rdata", ".data"):
                blob = xbe.d[raw:raw + rsize]
                for m in re.finditer(re.escape(args.text.encode()), blob):
                    start = m.start()
                    while start > 0 and 0x20 <= blob[start - 1] < 0x7F:
                        start -= 1
                    targets.append(va + start)
    starts = []
    if os.path.exists(os.path.join("out", "xbecalls.json")):
        edges = json.load(open(os.path.join("out", "xbecalls.json")))["edges"]
        starts = sorted({t for _, t, j in edges if not j})
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    text = next(s for s in xbe.sections if s[0] == ".text")
    _, va, vsize, raw, rsize = text
    blob = xbe.d[raw:raw + rsize]
    for t in sorted(set(targets)):
        s = xbe.section(t)
        o = s[3] + t - s[1] if s else None
        label = xbe.d[o:o + 70].split(b"\0")[0].decode("latin-1") if o is not None else ""
        print(f"0x{t:06X} {label!r}")
        for m in re.finditer(re.escape(struct.pack("<I", t)), blob):
            # the address can be read from the wrong first byte: prefer the reading that uses it as memory, [0x...],
            # which ends right after it, then any reading that mentions it
            found = None
            for want_memory in (True, False):
                for back in (2, 3, 1, 4):
                    at = va + m.start() - back
                    ins = next(md.disasm(blob[m.start() - back:m.start() + 8], at), None)
                    if not ins or f"0x{t:x}" not in ins.op_str:
                        continue
                    if want_memory and (f"[0x{t:x}]" not in ins.op_str or ins.size != back + 4):
                        continue
                    found = (at, ins)
                    break
                if found:
                    break
            if found:
                at, ins = found
                i = bisect.bisect_right(starts, at) - 1
                func = f"sub_{starts[i]:08X}" if i >= 0 else "?"
                print(f"    {at:08X}  {ins.mnemonic} {ins.op_str:<40} en {func}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

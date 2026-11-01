#!/usr/bin/env python3
"""Divide una sección de código de un .xbe en funciones y busca las que encajan con una descripción.

Uso:
  python tools\\xbefuncs.py <default.xbe> <sección> [--k 0x7FF,0xFFF] [--ret 4] [--len 0x6B] [--calls 0x2DE3D0]

Las funciones se separan por el relleno int3 (0xCC) que el compilador pone entre ellas. Para cada una muestra
la dirección, la longitud, el "ret N" con que vuelve (N = bytes de argumentos en la pila) y si contiene todas
las constantes pedidas con --k. --len acepta un margen del 25 % porque la longitud cambia entre versiones del XDK.
Necesita capstone: pip install capstone
"""
import argparse
import sys

import capstone

from xbedis import Xbe, load_names


def functions(xbe, section):
    name, va, vsize, raw, rsize = next(s for s in xbe.sections if s[0] == section)
    blob = xbe.d[raw:raw + min(vsize, rsize)]
    start, i = 0, 0
    while i < len(blob):
        if blob[i] == 0xCC:
            j = i
            while j < len(blob) and blob[j] == 0xCC:
                j += 1
            if i > start:
                yield va + start, blob[start:i]
            start = i = j
        else:
            i += 1
    if start < len(blob):
        yield va + start, blob[start:]


def describe(md, addr, code):
    rets, consts, calls = set(), set(), set()
    for ins in md.disasm(code, addr):
        if ins.mnemonic == "ret":
            rets.add(int(ins.op_str, 16) if ins.op_str else 0)
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            calls.add(int(ins.op_str, 16))
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM:
                consts.add(op.imm & 0xFFFFFFFF)
            elif op.type == capstone.x86.X86_OP_MEM and op.mem.disp:
                consts.add(op.mem.disp & 0xFFFFFFFF)
    return rets, consts, calls


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xbe")
    p.add_argument("section")
    p.add_argument("--k", default="", help="constantes que debe contener, separadas por comas")
    p.add_argument("--ret", type=int, help="bytes que limpia el ret (ret 4 = un argumento stdcall)")
    p.add_argument("--len", type=lambda s: int(s, 0), help="longitud aproximada")
    p.add_argument("--calls", default="", help="direcciones a las que debe llamar, separadas por comas")
    p.add_argument("--config", default="config/game.toml")
    args = p.parse_args()
    xbe = Xbe(args.xbe)
    names = load_names(args.config)
    want_k = {int(x, 0) for x in args.k.split(",") if x}
    want_calls = {int(x, 0) for x in args.calls.split(",") if x}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    for addr, code in functions(xbe, args.section):
        rets, consts, calls = describe(md, addr, code)
        if want_k - consts or want_calls - calls:
            continue
        if args.ret is not None and args.ret not in rets:
            continue
        if args.len and not (args.len * 0.75 <= len(code) <= args.len * 1.25):
            continue
        label = names.get(addr, "¿?")
        ret = ",".join(f"ret {r}" for r in sorted(rets)) or "sin ret"
        print(f"0x{addr:06X}  len=0x{len(code):X}  {ret:<10} {label}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

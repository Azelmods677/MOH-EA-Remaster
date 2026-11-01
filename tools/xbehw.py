#!/usr/bin/env python3
"""Busca código del .xbe que toca el hardware de la Xbox y al que el juego puede llegar en el port.

Uso:
  python tools\\xbehw.py <default.xbe> [--config config\\game.toml]

En el port no hay GPU, APU ni USB de Xbox: el host sustituye las funciones de config/game.toml [symbols].
El código original que siga tocando el hardware falla. Este script:
  1. desensambla todas las secciones de código y arma el grafo de llamadas directas;
  2. marca como "hardware" las funciones que usan el miniport de la GPU (CDevice + 0x1C28) o direcciones de
     registros (0xFD000000-0xFEFFFFFF);
  3. para cada una, busca un camino desde el código del juego (.text) que no pase por una función del host.
Los caminos que imprime son los crashes en potencia. Las llamadas indirectas (por puntero) no se ven.
Necesita capstone: pip install capstone
"""
import argparse
import bisect
import collections
import sys
import tomllib

import capstone

from xbedis import Xbe

MINIPORT = 0x1C28
# registros de la Xbox: GPU NV2A, APU (audio), AC97, USB, red
HW_RANGES = [(0xFD000000, 0xFE000000, "GPU"), (0xFE800000, 0xFE880000, "APU"), (0xFEC00000, 0xFEC01000, "AC97"),
             (0xFED00000, 0xFED09000, "USB"), (0xFEF00000, 0xFEF00400, "red")]
# con estas instrucciones un valor así es una máscara o una cuenta, no una dirección
NOT_ADDRESS = {"and", "or", "xor", "test", "cmp", "add", "sub", "imul", "adc", "sbb"}
LIBRARY_SECTIONS = {"D3D", "DSOUND", "XGRPH", "XPP"}


def hw_range(v):
    for low, high, what in HW_RANGES:
        if low <= v < high:
            return what
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xbe")
    p.add_argument("--config", default="config/game.toml")
    p.add_argument("--layout", help="layout.toml del XDK (sdk\\xdk\\5849\\layout.toml) para revisar también los campos de CDevice")
    args = p.parse_args()
    xbe = Xbe(args.xbe)
    cfg = tomllib.load(open(args.config, "rb"))
    host = {v: k for k, v in cfg["symbols"].items() if v}
    code_sections = cfg["xbe"].get("code_sections", [".text"] + sorted(LIBRARY_SECTIONS))

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    calls = []          # (instrucción, destino)
    hw = []             # (instrucción, motivo)
    starts = set(host)
    for name, va, vsize, raw, rsize in xbe.sections:
        if name not in code_sections:
            continue
        blob = xbe.d[raw:raw + min(vsize, rsize)]
        off = 0
        while off < len(blob):
            got = False
            for ins in md.disasm(blob[off:], va + off):
                got = True
                off = ins.address + ins.size - va
                if ins.mnemonic == "call" and ins.operands[0].type == capstone.x86.X86_OP_IMM:
                    calls.append((ins.address, ins.operands[0].imm & 0xFFFFFFFF))
                    starts.add(ins.operands[0].imm & 0xFFFFFFFF)
                for op in ins.operands:
                    if op.type == capstone.x86.X86_OP_IMM:
                        if name not in LIBRARY_SECTIONS:
                            continue  # en el código del juego los inmediatos así suelen ser hashes de nombres
                        v = op.imm & 0xFFFFFFFF
                    elif op.type == capstone.x86.X86_OP_MEM:
                        v = op.mem.disp & 0xFFFFFFFF
                    else:
                        continue
                    if v == MINIPORT and name in LIBRARY_SECTIONS:
                        hw.append((ins.address, "miniport (CDevice + 0x1C28)"))
                    elif ins.mnemonic not in NOT_ADDRESS and (what := hw_range(v)):
                        hw.append((ins.address, f"registro {what} 0x{v:08X}"))
            if not got:
                off += 1  # byte que no es una instrucción: saltarlo
    starts = sorted(starts)

    def func_of(a):
        i = bisect.bisect_right(starts, a) - 1
        return starts[i] if i >= 0 else a

    callers = collections.defaultdict(set)
    for at, target in calls:
        callers[target].add(func_of(at))

    text = next(s for s in xbe.sections if s[0] == ".text")
    in_game = lambda a: text[1] <= a < text[1] + text[2] and a not in host

    def path_from_game(f):
        # búsqueda en anchura hacia atrás, sin cruzar funciones del host
        prev, queue = {f: None}, collections.deque([f])
        while queue:
            g = queue.popleft()
            if in_game(g):
                chain = []
                while g is not None:
                    chain.append(g)
                    g = prev[g]
                return chain
            for c in callers[g]:
                if c not in prev and c not in host:
                    prev[c] = g
                    queue.append(c)
        return None

    hw_funcs = collections.defaultdict(set)
    for at, why in hw:
        hw_funcs[func_of(at)].add(why)
    label = lambda a: host.get(a, f"sub_{a:08X}")
    live = 0
    for f in sorted(hw_funcs):
        if f in host:
            continue
        chain = path_from_game(f)
        if not chain:
            continue
        live += 1
        print(f"{label(f)}: {', '.join(sorted(hw_funcs[f]))}")
        print("    " + " -> ".join(label(a) for a in chain))
    print(f"\n{live} funciones de hardware alcanzables desde el juego "
          f"(de {len(hw_funcs)} que tocan hardware; las demás solo las llama código que el host sustituye)")

    if args.layout:
        callees = collections.defaultdict(set)
        for at, target in calls:
            callees[func_of(at)].add(target)
        reach, queue = set(), collections.deque(a for a in starts if in_game(a))
        while queue:
            f = queue.popleft()
            for t in callees[f]:
                if t not in reach and t not in host and not in_game(t):
                    reach.add(t)
                    queue.append(t)
        device_fields(xbe, cfg, md, reach, host, args.layout, label)


# campos de CDevice que el SDK mantiene, con su tamaño cuando es una tabla
FIELD_SIZES = {"CDevice_Transforms": 0x300, "CDevice_Textures": 0x10, "CDevice_Palettes": 0x10,
               "CDevice_Viewport": 0x18, "CDevice_ScreenSpaceOffset": 8, "CDevice_BackBufferScale": 8,
               "CDevice_GammaRamps": 0x600, "CDevice_GammaPending": 8}


def device_fields(xbe, cfg, md, reach, host, layout_path, label):
    """Campos de CDevice que lee el código de D3D alcanzable, que ese código no escribe y que el SDK no mantiene."""
    from xbefuncs import functions
    dev_ptr, dev = cfg["data"]["D3D_pDevice"], cfg["data"]["D3D_Device"]
    known = []
    for k, v in tomllib.load(open(layout_path, "rb"))["layout"].items():
        if k.startswith("CDevice_") and k != "CDevice_Size":
            known.append((v, v + FIELD_SIZES.get(k, 4)))
    is_known = lambda off: any(lo <= off < hi for lo, hi in known)
    reads, writes = collections.defaultdict(set), set()
    R, W = capstone.CS_AC_READ, capstone.CS_AC_WRITE
    for f, code in functions(xbe, "D3D"):
        if f not in reach:
            continue
        regs = set()  # registros que apuntan al dispositivo en este momento
        for ins in md.disasm(code, f):
            for op in ins.operands:
                if op.type != capstone.x86.X86_OP_MEM:
                    continue
                base, disp = op.mem.base, op.mem.disp & 0xFFFFFFFF
                if base in regs and op.mem.index == 0:
                    off = disp
                elif base == 0 and dev <= disp < dev + 0x24A0:
                    off = disp - dev
                else:
                    continue
                if ins.mnemonic == "lea":
                    continue
                if op.access & W:
                    writes.add(off)
                if op.access & R:
                    reads[off].add(f)
            src = ins.operands[1] if len(ins.operands) == 2 else None
            _, written = ins.regs_access()
            new = None
            if ins.mnemonic == "mov" and src is not None:
                if src.type == capstone.x86.X86_OP_MEM and src.mem.base == 0 and src.mem.disp & 0xFFFFFFFF == dev_ptr:
                    new = ins.operands[0].reg
                elif src.type == capstone.x86.X86_OP_IMM and src.imm & 0xFFFFFFFF == dev:
                    new = ins.operands[0].reg
                elif src.type == capstone.x86.X86_OP_REG and src.reg in regs:
                    new = ins.operands[0].reg
            regs -= set(written)
            if ins.mnemonic == "call":
                regs -= {capstone.x86.X86_REG_EAX, capstone.x86.X86_REG_ECX, capstone.x86.X86_REG_EDX}
            if new:
                regs.add(new)
    risky = sorted(off for off in reads if off not in writes and not is_known(off))
    print(f"\nCampos de CDevice que lee el código de D3D alcanzable ({len(reach)} funciones de librería), "
          f"que nadie alcanzable escribe y que el SDK no mantiene: {len(risky)}")
    for off in risky:
        print(f"  +0x{off:04X}  leído en {', '.join(label(a) for a in sorted(reads[off]))}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

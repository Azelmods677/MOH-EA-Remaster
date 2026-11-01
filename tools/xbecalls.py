#!/usr/bin/env python3
"""Grafo de llamadas de un .xbe: quién llama a quién, para seguir un camino por el código.

Uso:
  python tools\\xbecalls.py <default.xbe> --func 17AF0D            función que contiene la dirección
  python tools\\xbecalls.py <default.xbe> --callers 2DED80         quién llama a una función
  python tools\\xbecalls.py <default.xbe> --tree 17AE80 --depth 3  a quién llama (en árbol)
  python tools\\xbecalls.py <default.xbe> --reach 17AE80 --to D3DDevice_  funciones del host alcanzables y por dónde

El grafo (llamadas directas y saltos finales a otra función) se guarda en out\\xbecalls.json la primera vez.
Las funciones empiezan donde las llama alguien o donde config\\game.toml pone un símbolo. Las llamadas por puntero
no se ven. Necesita capstone: pip install capstone
"""
import argparse
import bisect
import collections
import hashlib
import json
import os
import sys
import tomllib

import capstone

from xbedis import Xbe

CACHE = os.path.join("out", "xbecalls.json")


def build(xbe, code_sections):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    edges = []  # (instrucción, destino, es_salto)
    for name, va, vsize, raw, rsize in xbe.sections:
        if name not in code_sections:
            continue
        blob = xbe.d[raw:raw + min(vsize, rsize)]
        off = 0
        while off < len(blob):
            moved = False
            for ins in md.disasm(blob[off:], va + off):
                moved = True
                off = ins.address + ins.size - va
                if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                    edges.append((ins.address, int(ins.op_str, 16), ins.mnemonic == "jmp"))
            if not moved:
                off += 1
    return edges


def load(xbe_path, cfg):
    sha = hashlib.sha1(open(xbe_path, "rb").read()).hexdigest()
    if os.path.exists(CACHE):
        data = json.load(open(CACHE))
        if data.get("sha1") == sha:
            return data["edges"]
    print("construyendo el grafo (una sola vez, ~1 minuto)...", file=sys.stderr)
    xbe = Xbe(xbe_path)
    edges = build(xbe, cfg["xbe"].get("code_sections", [".text"]))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump({"sha1": sha, "edges": edges}, open(CACHE, "w"))
    return edges


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xbe")
    p.add_argument("--config", default="config/game.toml")
    p.add_argument("--func")
    p.add_argument("--callers")
    p.add_argument("--tree")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--reach")
    p.add_argument("--to", default="", help="prefijo de los símbolos del host que interesan (con --reach)")
    args = p.parse_args()
    cfg = tomllib.load(open(args.config, "rb"))
    host = {v: k for k, v in cfg["symbols"].items() if v}
    edges = load(args.xbe, cfg)

    # funciones: destinos de call, más los símbolos; un jmp solo cuenta como llamada si va a un comienzo de función
    starts = sorted({t for _, t, j in edges if not j} | set(host))
    start_set = set(starts)
    func_of = lambda a: starts[bisect.bisect_right(starts, a) - 1] if a >= starts[0] else a
    callees, callers = collections.defaultdict(set), collections.defaultdict(set)
    for at, t, jump in edges:
        if jump and t not in start_set:
            continue  # salto dentro de la misma función
        f = func_of(at)
        if jump and t == f:
            continue
        callees[f].add(t)
        callers[t].add(f)
    label = lambda a: host.get(a, f"sub_{a:08X}")
    h = lambda s: int(s, 16)

    if args.func:
        a = h(args.func)
        print(f"0x{a:X} está en {label(func_of(a))}")
    if args.callers:
        f = h(args.callers)
        for c in sorted(callers[f]):
            print(f"  {label(c)}")
    if args.tree:
        def tree(f, depth, seen, indent):
            for t in sorted(callees[f]):
                mark = "  (host)" if t in host else ""
                print(f"{'  ' * indent}{label(t)}{mark}")
                if depth > 1 and t not in host and t not in seen:
                    seen.add(t)
                    tree(t, depth - 1, seen, indent + 1)
        print(label(h(args.tree)))
        tree(h(args.tree), args.depth, set(), 1)
    if args.reach:
        # búsqueda en anchura sin entrar en funciones del host: primer camino hasta cada símbolo que interesa
        start = h(args.reach)
        prev, queue, found = {start: None}, collections.deque([start]), {}
        while queue:
            f = queue.popleft()
            for t in callees[f]:
                if t in prev:
                    continue
                prev[t] = f
                if t in host:
                    if label(t).startswith(args.to):
                        found[t] = t
                    continue
                queue.append(t)
        for t in sorted(found, key=label):
            chain, g = [], t
            while g is not None:
                chain.append(label(g))
                g = prev[g]
            print(f"{label(t)}:\n    " + " -> ".join(reversed(chain)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

"""Gera notas aleatórias (fictícias) e o resultado da versão Python, para comparar com a versão web.

Uso: python ferramentas/fuzz_paridade.py PASTA [quantidade] [semente]
Depois: node tests/web/fuzz.mjs PASTA
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gerar_exemplos import grupo_ibscbs, nota  # noqa: E402

from auditor_ibs_cbs import auditar, carregar, ler_bytes  # noqa: E402

T = carregar()
CODIGOS = list(T.dados["cclasstrib"])
CSTS = list(T.dados["cst"])


def item_aleatorio(rnd: random.Random):
    if rnd.random() < 0.1:
        return ("PRODUTO", None)
    cclass = rnd.choice(CODIGOS + ["999999"])
    cst = T.cclasstrib(cclass)["cst"] if cclass in T.dados["cclasstrib"] and rnd.random() < 0.7 else rnd.choice(CSTS + ["777"])
    vbc = f"{rnd.randint(1, 500000) / 100:.2f}"
    red = rnd.choice([None, None, "60", "100", "30", "40"])
    sobre = {}
    if rnd.random() < 0.2:
        sobre["vCBS"] = f"{rnd.randint(0, 9999) / 100:.2f}"
    if rnd.random() < 0.1:
        sobre["vIBS"] = f"{rnd.randint(0, 999) / 100:.2f}"
    return (
        "PRODUTO",
        grupo_ibscbs(
            cst,
            cclass,
            vbc,
            p_uf=rnd.choice(["0.10", "0.10", "0.05", "17.70"]),
            p_mun=rnd.choice(["0.00", "0.00", "0.50"]),
            p_cbs=rnd.choice(["0.90", "0.90", "8.80"]),
            red=red,
            sobrescrever=sobre,
            sem_gibscbs=rnd.random() < 0.08,
        ),
    )


def main() -> None:
    pasta = Path(sys.argv[1])
    qtd = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    rnd = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 2026)
    pasta.mkdir(parents=True, exist_ok=True)
    gabarito = {}
    for i in range(qtd):
        itens = [item_aleatorio(rnd) for _ in range(rnd.randint(1, 5))]
        dia = rnd.choice(["2026-01-01", "2026-06-15", "2026-11-20", "2027-03-10", "2025-12-31"])
        total = {"vCBS": "1.00"} if rnd.random() < 0.1 else None
        xml = nota(
            2000 + i,
            itens,
            modelo=rnd.choice([55, 65]),
            crt=rnd.choice(["1", "3", "3", "4"]),
            data=f"{dia}T10:00:00-03:00",
            total_sobrescrever=total,
        )
        nome = f"n{i:04d}.xml"
        (pasta / nome).write_text(xml, encoding="utf-8")
        r = auditar(ler_bytes(xml.encode(), nome), T)
        gabarito[nome] = sorted(([a.codigo, a.gravidade, a.item] for a in r.achados), key=lambda x: (x[0], x[1], x[2] or ""))
    (pasta / "gabarito.json").write_text(json.dumps(gabarito), encoding="utf-8")
    print(f"{qtd} notas em {pasta}")


if __name__ == "__main__":
    main()

"""Gera documentos aleatórios (fictícios) e o resultado da versão Python, para comparar com a versão web.

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

from gerar_exemplos import COMPRA_GOV, CRED_PRES, MONO, TRIB_REGULAR, cte, grupo_ibscbs, nf3e, nfse, nota  # noqa: E402

from auditor_ibs_cbs import auditar, carregar, ler_bytes  # noqa: E402

T = carregar()
CODIGOS = list(T.dados["cclasstrib"])
CSTS = list(T.dados["cst"])
NCMS = ["10063021", "10063011", "02013000", "48201000", "96081000", "00000000", "00", "99999999", "0402", "27160000", ""]
NBSS = ["101011100", "122011000", "122012000", "", "1220"]


def item_aleatorio(rnd: random.Random):
    if rnd.random() < 0.08:
        return None
    cclass = rnd.choice(CODIGOS + ["999999"])
    cst = T.cclasstrib(cclass)["cst"] if cclass in T.dados["cclasstrib"] and rnd.random() < 0.7 else rnd.choice(CSTS + ["777"])
    vbc = f"{rnd.randint(1, 500000) / 100:.2f}"
    sobre = {}
    if rnd.random() < 0.15:
        sobre["vCBS"] = f"{rnd.randint(0, 9999) / 100:.2f}"
    if rnd.random() < 0.08:
        sobre["vIBS"] = f"{rnd.randint(0, 999) / 100:.2f}"
    if rnd.random() < 0.05:
        sobre["vBC"] = rnd.choice(["1,00", "10.5", "abc"])
    if rnd.random() < 0.08:
        sobre["pAliqEfetCBS"] = rnd.choice(["0.5000", "0.3600", "0.0000"])
    if rnd.random() < 0.08:
        sobre["vDifCBS"] = f"{rnd.randint(0, 999) / 100:.2f}"
    return grupo_ibscbs(
        cst,
        cclass,
        vbc,
        p_uf=rnd.choice(["0.10", "0.10", "0.05", "17.70"]),
        p_mun=rnd.choice(["0.00", "0.00", "0.50"]),
        p_cbs=rnd.choice(["0.90", "0.90", "8.80"]),
        red=rnd.choice([None, None, None, "60", "100", "30", "0"]),
        dif=rnd.choice([None, None, None, None, "100", "50"]),
        redutor=rnd.choice([None] * 8 + ["10"]),
        sobrescrever=sobre,
        sem_gibscbs=rnd.random() < 0.06,
        extra_gibscbs=rnd.choice([""] * 12 + [COMPRA_GOV, TRIB_REGULAR]),
        extra_grupo=rnd.choice([""] * 12 + [CRED_PRES]),
        remover=rnd.choice([()] * 15 + [("vIBS",), ("pCBS",)]),
    )


def documento(rnd: random.Random, i: int) -> str:
    tipo = rnd.choices(["nfe", "cte", "nf3e", "nfse"], weights=[70, 10, 10, 10])[0]
    if tipo == "cte":
        return cte(3000 + i, item_aleatorio(rnd), modelo=rnd.choice([57, 67]), crt=rnd.choice(["1", "3"]))
    if tipo == "nf3e":
        itens = [("ENERGIA", item_aleatorio(rnd) or grupo_ibscbs("000", "000001", "10.00")) for _ in range(rnd.randint(1, 3))]
        return nf3e(4000 + i, itens, total_sobrescrever={"vCBS": "1.00"} if rnd.random() < 0.2 else None)
    if tipo == "nfse":
        cclass = rnd.choice(["000001", "200028", "200029", "011003", "999999"])
        cst = T.cclasstrib(cclass)["cst"] if cclass in T.dados["cclasstrib"] else "000"
        sobre = {"vCBS": "1.23"} if rnd.random() < 0.2 else None
        return nfse(
            5000 + i,
            cst,
            cclass,
            rnd.choice(NBSS),
            f"{rnd.randint(100, 900000) / 100:.2f}",
            sobrescrever=sobre,
            autorizada=rnd.random() < 0.8,
        )
    itens = [("PRODUTO", item_aleatorio(rnd), rnd.choice(NCMS)) for _ in range(rnd.randint(1, 5))]
    dia = rnd.choice(["2026-01-01", "2026-06-15", "2026-11-20", "2027-03-10", "2025-12-31"])
    total = {"vCBS": "1.00"} if rnd.random() < 0.1 else None
    xml = nota(
        2000 + i,
        itens,
        modelo=rnd.choice([55, 65]),
        crt=rnd.choice(["1", "3", "3", "4"]),
        data=f"{dia}T10:00:00-03:00",
        total_sobrescrever=total,
        compra_gov=rnd.choice([None] * 9 + ["10.0000"]),
    )
    if rnd.random() < 0.03:
        xml = xml.replace("<imposto></imposto>", f"<imposto>{MONO}</imposto>", 1)
    sorteio = rnd.random()
    if sorteio < 0.01:
        xml = xml.replace("<mod>55</mod>", "<mod>59</mod>")
    elif sorteio < 0.02:
        xml = xml.split("<dhEmi>")[0] + xml.split("</dhEmi>")[1]
    elif sorteio < 0.05 and "<IBSCBSTot>" in xml:
        xml = xml.split("<IBSCBSTot>")[0] + xml.split("</IBSCBSTot>")[1]
    return xml


def main() -> None:
    pasta = Path(sys.argv[1])
    qtd = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    rnd = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 2026)
    pasta.mkdir(parents=True, exist_ok=True)
    gabarito = {}
    for i in range(qtd):
        xml = documento(rnd, i)
        nome = f"n{i:04d}.xml"
        (pasta / nome).write_text(xml, encoding="utf-8", newline="\n")
        r = auditar(ler_bytes(xml.encode(), nome), T)
        gabarito[nome] = sorted(([a.codigo, a.gravidade, a.item] for a in r.achados), key=lambda x: (x[0], x[1], x[2] or ""))
    (pasta / "gabarito.json").write_text(json.dumps(gabarito), encoding="utf-8")
    print(f"{qtd} documentos em {pasta}")


if __name__ == "__main__":
    main()

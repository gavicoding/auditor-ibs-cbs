"""O pacote SQL precisa dar o mesmo resultado do auditor em Python (testado aqui com SQLite)."""

import random
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ferramentas"))

import fuzz_paridade  # noqa: E402
import gerar_sql  # noqa: E402

from auditor_ibs_cbs import XMLInvalido, auditar, carregar, ler_bytes  # noqa: E402

T = carregar()


@pytest.fixture(scope="module")
def banco():
    con = sqlite3.connect(":memory:")
    con.executescript(gerar_sql.tabelas_sql("sqlite", T))
    con.executescript(gerar_sql.auditoria_sql("sqlite"))
    return con


def _comparar(con, documentos):
    con.execute("DELETE FROM ibscbs_auditoria_item")
    esperado = set()
    for k, xml in enumerate(documentos):
        try:
            nota = ler_bytes(xml.encode(), f"d{k}")
        except XMLInvalido:
            continue
        if nota.emissao is None or nota.emissao.year < 2026 or nota.modelo not in (55, 65, 57, 67, 63, 66, 91):
            continue
        r = auditar(nota, T)
        chave = f"d{k}"
        for item in nota.itens:
            if not item.tem_grupo:
                continue
            n = item.numero if nota.por_item else "1"
            con.execute(
                "INSERT INTO ibscbs_auditoria_item VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chave, n, nota.modelo, nota.emissao.isoformat(), item.cst, item.cclasstrib, item.ncm),
            )
            for a in r.achados:
                if a.codigo in gerar_sql.CODIGOS_SQL and (a.item or "1") == n and not (a.campo or "").endswith("Reg"):
                    esperado.add((chave, n, a.codigo))
    obtido = {(c, i, cod) for c, i, cod, _, _ in con.execute("SELECT * FROM ibscbs_auditoria_resultado")}
    return obtido, esperado


def test_exemplos(banco):
    docs = [p.read_text(encoding="utf-8") for p in sorted((RAIZ / "exemplos").glob("*.xml"))]
    obtido, esperado = _comparar(banco, docs)
    assert obtido == esperado and esperado


def test_documentos_aleatorios(banco):
    rnd = random.Random(2026)
    docs = [fuzz_paridade.documento(rnd, i) for i in range(800)]
    obtido, esperado = _comparar(banco, docs)
    assert obtido == esperado, (sorted(obtido - esperado)[:5], sorted(esperado - obtido)[:5])
    assert len(esperado) > 300

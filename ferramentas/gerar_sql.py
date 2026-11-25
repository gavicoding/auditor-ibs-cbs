"""Gera o pacote SQL (SQL Server, PostgreSQL, MySQL e SQLite) a partir das mesmas tabelas oficiais.

Para cada dialeto, em sql/<dialeto>/:
  01_tabelas.sql   cria as tabelas ibscbs_* e carrega CST, cClassTrib, documentos, reduções,
                   NCM aplicáveis (com exceções) e a tabela NCM
  02_auditoria.sql cria a tabela de entrada ibscbs_auditoria_item e a view ibscbs_auditoria_resultado,
                   que confere cada item: CST e cClassTrib (existência, vigência, par, documento) e
                   NCM x cClassTrib, com os mesmos códigos AIC e de rejeição do auditor
Com --exemplos, também gera sql/exemplos/<dialeto>.sql (itens dos XMLs de exemplo) e
sql/exemplos/esperado.csv (resultado da versão Python), usados no CI para provar que o SQL dá o
mesmo resultado.

Uso: python ferramentas/gerar_sql.py [--exemplos]
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from auditor_ibs_cbs import XMLInvalido, auditar, carregar, ler_bytes  # noqa: E402
from auditor_ibs_cbs.tabelas import EXIGEM_NCM_SEMPRE  # noqa: E402

DESTINO = RAIZ / "sql"
DIALETOS = ("sqlserver", "postgresql", "mysql", "sqlite")
CODIGOS_SQL = {"AIC-011", "AIC-013", "AIC-014", "AIC-015", "AIC-016", "AIC-017", "AIC-018"}


_UNICODE = False  # SQL Server: literais N'...' para preservar acentos


def _s(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return ("N'" if _UNICODE else "'") + str(v).replace("'", "''") + "'"


def _concat(d: str, a: str, b: str) -> str:
    return {"sqlserver": f"{a} + {b}", "mysql": f"CONCAT({a}, {b})"}.get(d, f"{a} || {b}")


def _texto(d: str, n: int) -> str:
    return f"NVARCHAR({n})" if d == "sqlserver" else f"VARCHAR({n})"


def _lotes(d: str, tabela: str, colunas: str, linhas: list[str], tamanho: int = 500) -> str:
    saida = []
    for i in range(0, len(linhas), tamanho):
        saida.append(f"INSERT INTO {tabela} ({colunas}) VALUES\n  " + ",\n  ".join(linhas[i : i + tamanho]) + ";")
    return "\n".join(saida)


def tabelas_sql(d: str, t) -> str:
    tx = lambda n: _texto(d, n)  # noqa: E731
    dados = t.dados
    partes = [
        f"-- auditor-ibs-cbs: tabelas oficiais do IBS/CBS (base {t.versao}), dialeto {d}.",
        "-- Fonte: calculadora pública da Receita Federal (licença MIT). Projeto independente, não oficial.",
        "-- Gerado por ferramentas/gerar_sql.py; não edite à mão.",
        "",
        f"CREATE TABLE ibscbs_versao (base {tx(10)} NOT NULL, data_base CHAR(10) NOT NULL, fonte {tx(200)} NOT NULL);",
        f"CREATE TABLE ibscbs_cst (cst CHAR(3) NOT NULL PRIMARY KEY, descricao {tx(300)} NOT NULL, inicio CHAR(10), fim CHAR(10),"
        " exige_gibscbs SMALLINT NOT NULL, exige_gred SMALLINT NOT NULL, exige_gdif SMALLINT NOT NULL);",
        f"CREATE TABLE ibscbs_cclasstrib (cclasstrib CHAR(6) NOT NULL PRIMARY KEY, cst CHAR(3) NOT NULL, descricao {tx(600)} NOT NULL,"
        f" tipo_aliquota {tx(60)}, inicio CHAR(10), fim CHAR(10));",
        "CREATE TABLE ibscbs_cclasstrib_documento (cclasstrib CHAR(6) NOT NULL, modelo SMALLINT NOT NULL, inicio CHAR(10), fim CHAR(10));",
        f"CREATE TABLE ibscbs_cclasstrib_reducao (cclasstrib CHAR(6) NOT NULL, tributo {tx(10)} NOT NULL, percentual DECIMAL(7,4) NOT NULL,"
        " inicio CHAR(10), fim CHAR(10));",
        "CREATE TABLE ibscbs_cclasstrib_ncm (id INT NOT NULL PRIMARY KEY, cclasstrib CHAR(6) NOT NULL, prefixo VARCHAR(8) NOT NULL,"
        " inicio CHAR(10), fim CHAR(10));",
        "CREATE TABLE ibscbs_cclasstrib_ncm_excecao (ncm_id INT NOT NULL, prefixo VARCHAR(8) NOT NULL, inicio CHAR(10), fim CHAR(10));",
        f"CREATE TABLE ibscbs_ncm (ncm CHAR(8) NOT NULL PRIMARY KEY, descricao {tx(1000)} NOT NULL, inicio CHAR(10), fim CHAR(10));",
        "CREATE INDEX ix_ibscbs_doc ON ibscbs_cclasstrib_documento (cclasstrib, modelo);",
        "CREATE INDEX ix_ibscbs_ncm ON ibscbs_cclasstrib_ncm (cclasstrib);",
        "",
        f"INSERT INTO ibscbs_versao (base, data_base, fonte) VALUES ({_s(t.fonte['versao_base'])}, {_s(t.fonte['data_base'])}, {_s(t.fonte['url'])});",
    ]
    partes.append(
        _lotes(
            d,
            "ibscbs_cst",
            "cst, descricao, inicio, fim, exige_gibscbs, exige_gred, exige_gdif",
            [
                f"({_s(k)}, {_s(v['descricao'])}, {_s(v['inicio'])}, {_s(v['fim'])}, {_s(v['grupos']['gIBSCBS'])}, {_s(v['grupos']['gRed'])}, {_s(v['grupos']['gDif'])})"
                for k, v in dados["cst"].items()
            ],
        )
    )
    cl, docs, reds, ncms, excs = [], [], [], [], []
    nid = 0
    for k, v in dados["cclasstrib"].items():
        cl.append(f"({_s(k)}, {_s(v['cst'])}, {_s(v['descricao'])}, {_s(v['tipo_aliquota'])}, {_s(v['inicio'])}, {_s(v['fim'])})")
        docs += [f"({_s(k)}, {x['modelo']}, {_s(x['inicio'])}, {_s(x['fim'])})" for x in v["documentos"]]
        reds += [f"({_s(k)}, {_s(x['tributo'])}, {x['percentual']}, {_s(x['inicio'])}, {_s(x['fim'])})" for x in v["reducao"]]
        for n in v.get("ncm", []):
            nid += 1
            ncms.append(f"({nid}, {_s(k)}, {_s(n['codigo'])}, {_s(n['inicio'])}, {_s(n['fim'])})")
            excs += [f"({nid}, {_s(e['codigo'])}, {_s(e['inicio'])}, {_s(e['fim'])})" for e in n.get("excecoes", [])]
    partes.append(_lotes(d, "ibscbs_cclasstrib", "cclasstrib, cst, descricao, tipo_aliquota, inicio, fim", cl))
    partes.append(_lotes(d, "ibscbs_cclasstrib_documento", "cclasstrib, modelo, inicio, fim", docs))
    partes.append(_lotes(d, "ibscbs_cclasstrib_reducao", "cclasstrib, tributo, percentual, inicio, fim", reds))
    partes.append(_lotes(d, "ibscbs_cclasstrib_ncm", "id, cclasstrib, prefixo, inicio, fim", ncms))
    if excs:
        partes.append(_lotes(d, "ibscbs_cclasstrib_ncm_excecao", "ncm_id, prefixo, inicio, fim", excs))
    from auditor_ibs_cbs.tabelas import _carregar_ncm

    tabela_ncm = _carregar_ncm(None)
    partes.append(_lotes(d, "ibscbs_ncm", "ncm, descricao, inicio, fim", [f"({_s(k)}, {_s(v[0])}, {_s(v[1])}, {_s(v[2])})" for k, v in tabela_ncm.items()]))
    return "\n".join(partes) + "\n"


def auditoria_sql(d: str) -> str:
    tx = lambda n: _texto(d, n)  # noqa: E731
    vig = lambda a: f"({a}.inicio IS NULL OR {a}.inicio <= i.data_emissao) AND ({a}.fim IS NULL OR {a}.fim >= i.data_emissao)"  # noqa: E731
    casa_n = f"i.ncm LIKE {_concat(d, 'n.prefixo', chr(39) + '%' + chr(39))}"
    casa_e = f"i.ncm LIKE {_concat(d, 'e.prefixo', chr(39) + '%' + chr(39))}"
    sempre = ", ".join(_s(c) for c in sorted(EXIGEM_NCM_SEMPRE))
    tem_lista = f"EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND {vig('n')})"
    ncm_invalido = "(i.ncm IS NULL OR LENGTH(i.ncm) <> 8 OR i.ncm IN ('00', '00000000'))"
    if d == "sqlserver":
        ncm_invalido = ncm_invalido.replace("LENGTH(", "LEN(")
    aplicavel = (
        f"(EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND {casa_n} AND {vig('n')})"
        f" AND (NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n JOIN ibscbs_cclasstrib_ncm_excecao e ON e.ncm_id = n.id"
        f" WHERE n.cclasstrib = i.cclasstrib AND {casa_n} AND {vig('n')} AND {casa_e} AND {vig('e')})"
        f" OR EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm n WHERE n.cclasstrib = i.cclasstrib AND {casa_n} AND {vig('n')}"
        f" AND (NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm_excecao e WHERE e.ncm_id = n.id)"
        f" OR EXISTS (SELECT 1 FROM ibscbs_cclasstrib_ncm_excecao e WHERE e.ncm_id = n.id AND NOT ({vig('e')}))))))"
    )
    regras = [
        ("AIC-011", "1020", "CST do IBS/CBS inexistente", "NOT EXISTS (SELECT 1 FROM ibscbs_cst s WHERE s.cst = i.cst)"),
        ("AIC-012", None, "CST fora da vigência", f"EXISTS (SELECT 1 FROM ibscbs_cst s WHERE s.cst = i.cst AND NOT ({vig('s')}))"),
        ("AIC-013", "1023", "cClassTrib inexistente", "NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib)"),
        ("AIC-014", None, "cClassTrib fora da vigência", f"EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib AND NOT ({vig('c')}))"),
        (
            "AIC-015",
            "1024",
            "cClassTrib não pertence ao CST",
            "i.cst IS NOT NULL AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib AND c.cst <> i.cst)",
        ),
        (
            "AIC-016",
            "1025",
            "cClassTrib não permitido neste documento",
            "EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib)"
            f" AND NOT EXISTS (SELECT 1 FROM ibscbs_cclasstrib_documento x WHERE x.cclasstrib = i.cclasstrib AND x.modelo = i.modelo AND {vig('x')})",
        ),
        (
            "AIC-017",
            None,
            "NCM obrigatório para este cClassTrib",
            f"i.modelo IN (55, 65) AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib)"
            f" AND ({tem_lista} OR i.cclasstrib IN ({sempre})) AND {ncm_invalido}",
        ),
        (
            "AIC-018",
            None,
            "NCM não pode usar este cClassTrib",
            f"i.modelo IN (55, 65) AND EXISTS (SELECT 1 FROM ibscbs_cclasstrib c WHERE c.cclasstrib = i.cclasstrib)"
            f" AND {tem_lista} AND NOT {ncm_invalido} AND NOT {aplicavel}",
        ),
    ]
    selects = [
        f"SELECT i.chave, i.item, '{cod}' AS codigo, {_s(rej) if rej else 'NULL'} AS rejeicao, {_s(msg)} AS problema\n  FROM ibscbs_auditoria_item i\n  WHERE {cond}"
        for cod, rej, msg, cond in regras
    ]
    return (
        f"-- auditor-ibs-cbs: conferência dentro do banco (dialeto {d}).\n"
        "-- 1) Carregue os itens das suas notas em ibscbs_auditoria_item (um registro por item com grupo IBS/CBS).\n"
        "-- 2) SELECT * FROM ibscbs_auditoria_resultado ORDER BY chave, item, codigo;\n"
        "-- Datas no formato AAAA-MM-DD. Os códigos AIC e de rejeição são os mesmos do auditor (NT 2025.002-RTC v1.53).\n\n"
        f"CREATE TABLE ibscbs_auditoria_item (chave {tx(60)} NOT NULL, item {tx(10)} NOT NULL, modelo SMALLINT NOT NULL,"
        " data_emissao CHAR(10) NOT NULL, cst CHAR(3), cclasstrib CHAR(6), ncm VARCHAR(8));\n"
        + ("GO\n" if d == "sqlserver" else "")
        + "\nCREATE VIEW ibscbs_auditoria_resultado AS\n"
        + "\nUNION ALL\n".join(selects)
        + ";\n"
        + ("GO\n" if d == "sqlserver" else "")
    )


def exemplos(t) -> tuple[dict[str, str], str]:
    itens, esperado = [], []
    for p in sorted((RAIZ / "exemplos").glob("*.xml")):
        try:
            nota = ler_bytes(p.read_bytes(), p.name)
        except XMLInvalido:
            continue
        if nota.emissao is None or nota.modelo not in (55, 65, 57, 67, 63, 66, 91) or nota.emissao.year < 2026:
            continue
        r = auditar(nota, t)
        chave = nota.chave or p.stem
        for item in nota.itens:
            if not item.tem_grupo:
                continue
            n = item.numero if nota.por_item else "1"
            itens.append((chave, n, nota.modelo, nota.emissao.isoformat(), item.cst, item.cclasstrib, item.ncm))
            for a in r.achados:
                if a.codigo in CODIGOS_SQL and (a.item or "1") == n and not a.campo.endswith("Reg"):
                    esperado.append((chave, n, a.codigo))
    por_dialeto = {}
    for d in DIALETOS:
        linhas = [f"({_s(c)}, {_s(i)}, {m}, {_s(dt)}, {_s(cst)}, {_s(cl)}, {_s(ncm)})" for c, i, m, dt, cst, cl, ncm in itens]
        por_dialeto[d] = _lotes(d, "ibscbs_auditoria_item", "chave, item, modelo, data_emissao, cst, cclasstrib, ncm", linhas) + "\n"
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    for linha in sorted(set(esperado)):
        w.writerow(linha)
    return por_dialeto, out.getvalue()


def main(argv: list[str]) -> int:
    global _UNICODE
    t = carregar()
    for d in DIALETOS:
        _UNICODE = d == "sqlserver"
        pasta = DESTINO / d
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "01_tabelas.sql").write_text(tabelas_sql(d, t), encoding="utf-8", newline="\n")
        (pasta / "02_auditoria.sql").write_text(auditoria_sql(d), encoding="utf-8", newline="\n")
    _UNICODE = False
    if "--exemplos" in argv:
        pasta = DESTINO / "exemplos"
        pasta.mkdir(parents=True, exist_ok=True)
        itens, esperado = exemplos(t)
        for d, sql in itens.items():
            (pasta / f"{d}.sql").write_text(sql, encoding="utf-8", newline="\n")
        (pasta / "esperado.csv").write_text(esperado, encoding="utf-8", newline="\n")
    print(json.dumps({"dialetos": list(DIALETOS), "base": t.versao}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

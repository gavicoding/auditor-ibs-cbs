"""Gera src/auditor_ibs_cbs/dados/tabelas-rtc.json a partir do repositório público da
calculadora da Receita Federal (https://github.com/ReceitaFederal/calculadora-rtc-regime-regular,
licença MIT).

O script só lê os arquivos SQL de migração (pasta flyway/sql) e os aplica num SQLite em
memória, na mesma ordem que o Flyway usa. Nenhum código Java do repositório é executado.

Uso:
    git clone --depth 1 --filter=blob:none --sparse https://github.com/ReceitaFederal/calculadora-rtc-regime-regular rtc
    git -C rtc sparse-checkout set flyway LICENSE
    python ferramentas/exportar_tabelas.py rtc
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

DADOS = Path(__file__).resolve().parent.parent / "src" / "auditor_ibs_cbs" / "dados"
DESTINO = DADOS / "tabelas-rtc.json"
DESTINO_NCM = DADOS / "ncm.json"
FONTE_URL = "https://github.com/ReceitaFederal/calculadora-rtc-regime-regular"
TRIBUTOS_IBS_CBS = (2, 3, 4)  # CBS, IBSUF, IBSMun (1 = Imposto Seletivo, fora do escopo)


def montar_banco(repo: Path) -> sqlite3.Connection:
    sql_dir = repo / "flyway" / "sql"
    criacao = sql_dir / "criacao"
    versoes = sorted(
        (sql_dir / "manutencao").glob("V*.sql"),
        key=lambda p: int(re.match(r"V(\d+)", p.name).group(1)),
    )
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.executescript((criacao / "beforeMigrate.sql").read_text(encoding="utf-8"))
    con.executescript((criacao / "B0001__sistema_tributario_completo.sql").read_text(encoding="utf-8"))
    for arquivo in versoes:
        # Algumas migrações recriam tabelas; a checagem de chave estrangeira é feita no fim.
        con.execute("PRAGMA foreign_keys = OFF")
        con.executescript("BEGIN;\n" + arquivo.read_text(encoding="utf-8") + "\nCOMMIT;")
    con.executescript((criacao / "afterMigrate.sql").read_text(encoding="utf-8"))
    problemas = con.execute("PRAGMA foreign_key_check").fetchall()
    if problemas:
        raise SystemExit(f"Banco montado com {len(problemas)} problemas de chave estrangeira; abortando.")
    return con


def commit_da_fonte(repo: Path) -> str | None:
    try:
        saida = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%H"], capture_output=True, text=True, check=True)
        return saida.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def exportar(con: sqlite3.Connection, repo: Path) -> dict:
    con.row_factory = sqlite3.Row
    versao = con.execute("SELECT VRBD_VERSAO_BASE_DADO, VRBD_DATA, VRBD_DESCRICAO FROM VERSAO_BASE_DADO ORDER BY VRBD_ID DESC LIMIT 1").fetchone()
    filtro = f"SELECT TRST_SITR_ID FROM TRIBUTO_SITUACAO_TRIBUTARIA WHERE TRST_TBTO_ID IN {TRIBUTOS_IBS_CBS}"

    cst = {}
    for r in con.execute(f"SELECT * FROM SITUACAO_TRIBUTARIA WHERE SITR_ID IN ({filtro}) ORDER BY SITR_CD"):
        cst[r["SITR_CD"]] = {
            "descricao": r["SITR_DESCRICAO"],
            "inicio": r["SITR_INICIO_VIGENCIA"],
            "fim": r["SITR_FIM_VIGENCIA"],
            "grupos": {
                "gIBSCBS": bool(r["SITR_IND_GIBSCBS"]),
                "gIBSCBSMono": bool(r["SITR_IND_GIBSCBSMONO"]),
                "gRed": bool(r["SITR_IND_GRED"]),
                "gDif": bool(r["SITR_IND_GDIF"]),
                "gTransfCred": bool(r["SITR_IND_GTRANSFCRED"]),
                "gCredPresIBSZFM": bool(r["SITR_IND_GCREDPRESIBSZFM"]),
                "gAjusteCompet": bool(r["SITR_IND_GAJUSTECOMPET"]),
            },
        }

    modelos = {r["TPDF_ID"]: r["TPDF_TIPO"] for r in con.execute("SELECT TPDF_ID, TPDF_TIPO FROM TIPO_DFE")}
    tributos = {r["TBTO_ID"]: r["TBTO_SIGLA"] for r in con.execute("SELECT TBTO_ID, TBTO_SIGLA FROM TRIBUTO")}

    cclass = {}
    anexos_usados: set[int] = set()
    consulta = f"""
        SELECT c.*, s.SITR_CD FROM CLASSIFICACAO_TRIBUTARIA c
        JOIN SITUACAO_TRIBUTARIA s ON s.SITR_ID = c.CLTR_SITR_ID
        WHERE c.CLTR_SITR_ID IN ({filtro}) ORDER BY c.CLTR_CD
    """
    for r in con.execute(consulta):
        dfe = [
            {"modelo": modelos[d["TDCL_TPDF_ID"]], "inicio": d["TDCL_INICIO_VIGENCIA"], "fim": d["TDCL_FIM_VIGENCIA"]}
            for d in con.execute("SELECT * FROM TIPO_DFE_CLASSIFICACAO WHERE TDCL_CLTR_ID = ? ORDER BY TDCL_TPDF_ID", (r["CLTR_ID"],))
        ]
        reducao = [
            {
                "tributo": tributos[p["PERE_TBTO_ID"]],
                "percentual": p["PERE_VALOR"],
                "inicio": p["PERE_INICIO_VIGENCIA"],
                "fim": p["PERE_FIM_VIGENCIA"],
            }
            for p in con.execute(
                "SELECT * FROM PERCENTUAL_REDUCAO WHERE PERE_CLTR_ID = ? ORDER BY PERE_TBTO_ID, PERE_INICIO_VIGENCIA",
                (r["CLTR_ID"],),
            )
        ]
        nomenclatura = {}
        for tipo, tab, exc, pre_n, pre_e in (
            ("ncm", "NCM_APLICAVEL", "EXCECAO_NCM_APLICAVEL", "NCMA", "ENCM"),
            ("nbs", "NBS_APLICAVEL", "EXCECAO_NBS_APLICAVEL", "NBSA", "ENBS"),
        ):
            lista = []
            for a in con.execute(f"SELECT * FROM {tab} WHERE {pre_n}_CLTR_ID = ? ORDER BY {pre_n}_{tipo.upper()}_CD", (r["CLTR_ID"],)):
                excecoes = [
                    {
                        "codigo": e[f"{pre_e}_{tipo.upper()}_CD"],
                        "inicio": e[f"{pre_e}_INICIO_VIGENCIA"],
                        "fim": e[f"{pre_e}_FIM_VIGENCIA"],
                    }
                    for e in con.execute(f"SELECT * FROM {exc} WHERE {pre_e}_{pre_n}_ID = ?", (a[f"{pre_n}_ID"],))
                ]
                entrada = {
                    "codigo": a[f"{pre_n}_{tipo.upper()}_CD"],
                    "anexo": a[f"{pre_n}_ANXO_ID"],
                    "inicio": a[f"{pre_n}_INICIO_VIGENCIA"],
                    "fim": a[f"{pre_n}_FIM_VIGENCIA"],
                }
                if excecoes:
                    entrada["excecoes"] = excecoes
                lista.append(entrada)
                if entrada["anexo"] is not None:
                    anexos_usados.add(entrada["anexo"])
            nomenclatura[tipo] = lista
        cclass[r["CLTR_CD"]] = {
            "cst": r["SITR_CD"],
            "descricao": r["CLTR_DESCRICAO"],
            "tipo_aliquota": r["CLTR_TIPO_ALIQUOTA"],
            "inicio": r["CLTR_INICIO_VIGENCIA"],
            "fim": r["CLTR_FIM_VIGENCIA"],
            "documentos": dfe,
            "reducao": reducao,
            "nomenclatura": r["CLTR_NOMENCLATURA"],
            "indicadores": {
                "gEstornoCred": bool(r["CLTR_IND_GESTORNOCRED"]),
                "gCredPresOper": bool(r["CLTR_IND_GCREDPRESOPER"]),
                "gMonoPadrao": bool(r["CLTR_IND_GMONOPADRAO"]),
                "gMonoReten": bool(r["CLTR_IND_GMONORETEN"]),
                "gMonoRet": bool(r["CLTR_IND_GMONORET"]),
                "gMonoDif": bool(r["CLTR_IND_GMONODIF"]),
            },
            "ncm": nomenclatura["ncm"],
            "nbs": nomenclatura["nbs"],
        }

    aliquotas = [
        {
            "tributo": tributos[r["ALRE_TBTO_ID"]],
            "percentual": r["ALRE_VALOR"],
            "inicio": r["ALRE_INICIO_VIGENCIA"],
            "fim": r["ALRE_FIM_VIGENCIA"],
        }
        for r in con.execute("SELECT * FROM ALIQUOTA_REFERENCIA ORDER BY ALRE_TBTO_ID, ALRE_INICIO_VIGENCIA")
    ]

    anexos = {}
    for a in con.execute("SELECT * FROM ANEXO ORDER BY ANXO_ID"):
        if a["ANXO_ID"] in anexos_usados:
            anexos[str(a["ANXO_ID"])] = {"anexo": a["ANXO_NUMERO"], "item": a["ANXO_NUMERO_ITEM"], "texto": a["ANXO_TEXTO_ITEM"]}

    tipos_dfe = {str(r["TPDF_TIPO"]): r["TPDF_SIGLA"] for r in con.execute("SELECT TPDF_TIPO, TPDF_SIGLA FROM TIPO_DFE ORDER BY TPDF_TIPO")}

    return {
        "fonte": {
            "projeto": "Calculadora de Tributos da Reforma Tributária (regime regular)",
            "autor": "Receita Federal do Brasil",
            "url": FONTE_URL,
            "licenca": "MIT",
            "commit": commit_da_fonte(repo),
            "versao_base": versao["VRBD_VERSAO_BASE_DADO"],
            "data_base": versao["VRBD_DATA"][:10],
            "descricao_base": versao["VRBD_DESCRICAO"],
        },
        "aviso": "Dados extraídos do repositório público da Receita Federal (licença MIT). Este arquivo não é oficial.",
        "cst": cst,
        "cclasstrib": cclass,
        "aliquota_referencia": aliquotas,
        "anexos": anexos,
        "tipos_documento": tipos_dfe,
    }


def exportar_ncm(con: sqlite3.Connection) -> dict:
    """NCMs de 8 dígitos (com descrição e vigência), para conferir se o NCM do item existe."""
    con.row_factory = sqlite3.Row
    return {
        r["NCM_CD"]: [r["NCM_DESCRICAO"], r["NCM_INICIO_VIGENCIA"], r["NCM_FIM_VIGENCIA"]]
        for r in con.execute("SELECT * FROM NCM WHERE LENGTH(NCM_CD) = 8 ORDER BY NCM_CD")
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    repo = Path(argv[1])
    con = montar_banco(repo)
    dados = exportar(con, repo)
    ncm = exportar_ncm(con)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    DESTINO_NCM.write_text(json.dumps({"fonte": dados["fonte"], "ncm": ncm}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        f"{DESTINO.name}: base {dados['fonte']['versao_base']} ({dados['fonte']['data_base']}), "
        f"{len(dados['cst'])} CST, {len(dados['cclasstrib'])} cClassTrib, {len(ncm)} NCM"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

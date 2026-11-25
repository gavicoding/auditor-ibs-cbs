"""Saídas do auditor: texto, JSON, CSV, Markdown, HTML e o resumo consolidado do lote.

Os relatórios mostram chave, número, item e o problema. Não incluem dados do destinatário.
"""

from __future__ import annotations

import csv
import html
import io
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal

from .regras import Resultado

ROTULO = {"erro": "ERRO", "atencao": "ATENÇÃO", "info": "INFO", "ok": "OK"}


def _brl(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resumo(resultados: list[Resultado]) -> dict:
    situacoes = Counter(r.situacao for r in resultados)
    problemas = [(r, a) for r in resultados for a in r.achados if a.gravidade != "info"]
    codigos = Counter(a.codigo for _, a in problemas)
    titulos = {a.codigo: a.titulo for _, a in problemas}
    por_tipo = Counter(r.tipo or "?" for r in resultados)

    # problemas por emitente, por cClassTrib e por NCM (itens com pelo menos um problema)
    por_emitente: Counter = Counter()
    for r in resultados:
        if r.situacao != "ok":
            por_emitente[r.emitente or "?"] += 1
    itens_com_problema = {(id(r), a.item) for r, a in problemas if a.item}
    por_cclass: Counter = Counter()
    por_ncm: Counter = Counter()
    for r in resultados:
        for linha in r.linhas:
            if (id(r), linha["item"]) in itens_com_problema:
                por_cclass[linha["cclasstrib"] or "(sem)"] += 1
                if linha["ncm"]:
                    por_ncm[linha["ncm"]] += 1

    # valores por cClassTrib (todas as notas lidas)
    valores: dict[str, dict] = defaultdict(lambda: {"itens": 0, "base": Decimal(0), "ibs": Decimal(0), "cbs": Decimal(0)})
    for r in resultados:
        for linha in r.linhas:
            if not linha["cclasstrib"]:
                continue
            v = valores[linha["cclasstrib"]]
            v["itens"] += 1
            for k in ("base", "ibs", "cbs"):
                if linha[k] is not None:
                    v[k] += linha[k]

    return {
        "notas": len(resultados),
        "ok": situacoes.get("ok", 0),
        "com_atencao": situacoes.get("atencao", 0),
        "com_erro": situacoes.get("erro", 0),
        "por_tipo": dict(por_tipo),
        "problemas_mais_comuns": [[c, n, titulos[c]] for c, n in codigos.most_common(15)],
        "itens_com_problema_por_cclasstrib": por_cclass.most_common(15),
        "itens_com_problema_por_ncm": por_ncm.most_common(15),
        "documentos_com_problema_por_emitente": por_emitente.most_common(15),
        "valores_por_cclasstrib": {
            k: {"itens": v["itens"], "base": str(v["base"]), "ibs": str(v["ibs"]), "cbs": str(v["cbs"])} for k, v in sorted(valores.items())
        },
    }


def _linhas(resultados: Iterable[Resultado], incluir_info: bool):
    for r in resultados:
        for a in r.achados:
            if a.gravidade == "info" and not incluir_info:
                continue
            yield r, a


def _ident(r: Resultado) -> str:
    tipo = r.tipo or "Documento"
    return f"{tipo} {r.numero or '?'} série {r.serie or '?'}" + (f"  chave {r.chave}" if r.chave else "")


def texto(resultados: list[Resultado], versao_tabelas: str, incluir_info: bool = False) -> str:
    out = io.StringIO()
    for r in resultados:
        achados = [a for a in r.achados if incluir_info or a.gravidade != "info"]
        if not achados:
            continue
        out.write(f"\n[{ROTULO[r.situacao]}] {_ident(r)}\n  arquivo: {r.origem}\n")
        for a in achados:
            onde = f"item {a.item}: " if a.item else ""
            out.write(f"  - {ROTULO[a.gravidade]:<8}{a.codigo}  {onde}{a.titulo}\n")
            out.write(f"      {a.explicacao}\n")
            out.write(f"      Como corrigir: {a.como_corrigir}\n")
    s = resumo(resultados)
    out.write(f"\nResumo: {s['notas']} documento(s) | {s['ok']} ok | {s['com_atencao']} com atenção | {s['com_erro']} com erro\n")
    if s["problemas_mais_comuns"]:
        out.write("Problemas mais comuns:\n")
        for codigo, n, titulo in s["problemas_mais_comuns"][:8]:
            out.write(f"  {n:>6}  {codigo}  {titulo}\n")
    if s["itens_com_problema_por_cclasstrib"]:
        out.write("cClassTrib com mais itens problemáticos: " + ", ".join(f"{c} ({n})" for c, n in s["itens_com_problema_por_cclasstrib"][:5]) + "\n")
    out.write(f"Tabelas oficiais usadas: base {versao_tabelas}\n")
    return out.getvalue()


def json_(resultados: list[Resultado], fonte: dict) -> str:
    return json.dumps(
        {"tabelas": fonte, "resumo": resumo(resultados), "documentos": [r.como_dict() for r in resultados]},
        ensure_ascii=False,
        indent=2,
    )


def _celula(v) -> str:
    """Neutraliza fórmulas ao abrir no Excel (CSV injection)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def csv_(resultados: list[Resultado], incluir_info: bool = False) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(
        [
            "arquivo",
            "documento",
            "chave",
            "numero",
            "serie",
            "emissao",
            "emitente",
            "item",
            "gravidade",
            "codigo",
            "problema",
            "explicacao",
            "como_corrigir",
            "campo",
        ]
    )
    for r, a in _linhas(resultados, incluir_info):
        w.writerow(
            [
                _celula(x)
                for x in (
                    r.origem,
                    r.tipo,
                    r.chave,
                    r.numero,
                    r.serie,
                    r.emissao,
                    r.emitente,
                    a.item,
                    a.gravidade,
                    a.codigo,
                    a.titulo,
                    a.explicacao,
                    a.como_corrigir,
                    a.campo,
                )
            ]
        )
    return "﻿" + out.getvalue()


def resumo_csv(resultados: list[Resultado]) -> str:
    """Planilha de valores por cClassTrib (base, IBS e CBS somados), para conferência do contador."""
    s = resumo(resultados)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(["cclasstrib", "itens", "base_calculo", "ibs", "cbs", "itens_com_problema"])
    problemas = dict(s["itens_com_problema_por_cclasstrib"])
    for c, v in s["valores_por_cclasstrib"].items():
        w.writerow(
            [
                c,
                v["itens"],
                v["base"].replace(".", ","),
                v["ibs"].replace(".", ","),
                v["cbs"].replace(".", ","),
                problemas.get(c, 0),
            ]
        )
    return "﻿" + out.getvalue()


def markdown(resultados: list[Resultado], versao_tabelas: str, incluir_info: bool = False) -> str:
    s = resumo(resultados)
    linhas = [
        "## Auditoria IBS/CBS",
        "",
        f"**{s['notas']}** documento(s): **{s['ok']}** ok, **{s['com_atencao']}** com atenção, **{s['com_erro']}** com erro. "
        f"Tabelas oficiais: base {versao_tabelas}.",
        "",
    ]
    if s["problemas_mais_comuns"]:
        linhas += ["### Problemas mais comuns", "", "| Código | Problema | Ocorrências |", "| :--- | :--- | ---: |"]
        linhas += [f"| {c} | {t.replace('|', '/')} | {n} |" for c, n, t in s["problemas_mais_comuns"]]
        linhas.append("")
    linhas += ["### Detalhes", "", "| Documento | Item | Gravidade | Código | Problema |", "| :--- | :--- | :--- | :--- | :--- |"]
    for r, a in _linhas(resultados, incluir_info):
        problema = a.titulo.replace("|", "/")
        linhas.append(f"| {r.tipo or ''} {r.numero or '?'}/{r.serie or '?'} | {a.item or '-'} | {ROTULO[a.gravidade]} | {a.codigo} | {problema} |")
    return "\n".join(linhas) + "\n"


def html_(resultados: list[Resultado], versao_tabelas: str, incluir_info: bool = False) -> str:
    s = resumo(resultados)
    e = html.escape
    linhas = []
    for r, a in _linhas(resultados, incluir_info):
        linhas.append(
            f'<tr class="{a.gravidade}"><td>{e(r.tipo or "")} {e(r.numero or "?")}/{e(r.serie or "?")}<br><small>{e(r.chave or r.origem)}</small></td>'
            f"<td>{e(a.item or '-')}</td><td><b>{ROTULO[a.gravidade]}</b><br><small>{a.codigo}</small></td>"
            f"<td><b>{e(a.titulo)}</b><br>{e(a.explicacao)}<br><i>Como corrigir:</i> {e(a.como_corrigir)}</td></tr>"
        )
    corpo = "\n".join(linhas) or '<tr><td colspan="4">Nenhum problema encontrado.</td></tr>'

    def tabela(titulo: str, cab: list[str], dados: list[list]) -> str:
        if not dados:
            return ""
        th = "".join(f"<th>{e(c)}</th>" for c in cab)
        trs = "".join("<tr>" + "".join(f"<td>{e(str(x))}</td>" for x in linha) + "</tr>" for linha in dados)
        return f"<h2>{e(titulo)}</h2><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"

    valores = [
        [c, v["itens"], "R$ " + _brl(Decimal(v["base"])), "R$ " + _brl(Decimal(v["ibs"])), "R$ " + _brl(Decimal(v["cbs"]))]
        for c, v in s["valores_por_cclasstrib"].items()
    ]
    blocos = (
        tabela("Problemas mais comuns", ["Código", "Problema", "Ocorrências"], [[c, t, n] for c, n, t in s["problemas_mais_comuns"]])
        + tabela(
            "Itens com problema por cClassTrib",
            ["cClassTrib", "Itens"],
            [list(x) for x in s["itens_com_problema_por_cclasstrib"]],
        )
        + tabela("Itens com problema por NCM", ["NCM", "Itens"], [list(x) for x in s["itens_com_problema_por_ncm"]])
        + tabela(
            "Documentos com problema por emitente (CNPJ)",
            ["Emitente", "Documentos"],
            [list(x) for x in s["documentos_com_problema_por_emitente"]],
        )
        + tabela("Valores por cClassTrib", ["cClassTrib", "Itens", "Base de cálculo", "IBS", "CBS"], valores)
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auditoria IBS/CBS</title>
<style>
:root{{--bg:#fff;--tx:#1f2328;--mu:#59636e;--bd:#d1d9e0;--er:#cf222e;--at:#9a6700;--in:#0969da}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--tx:#e6edf3;--mu:#9198a1;--bd:#3d444d;--er:#ff7b72;--at:#d29922;--in:#58a6ff}}}}
body{{background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:24px 16px}}
table{{border-collapse:collapse;width:100%;margin-bottom:24px}}td,th{{border-bottom:1px solid var(--bd);padding:8px;text-align:left;vertical-align:top}}
h2{{font-size:18px;margin-top:28px}}small,.mu{{color:var(--mu)}}tr.erro td:nth-child(3){{color:var(--er)}}tr.atencao td:nth-child(3){{color:var(--at)}}tr.info td:nth-child(3){{color:var(--in)}}
</style></head><body>
<h1>Auditoria IBS/CBS</h1>
<p><b>{s["notas"]}</b> documento(s): <b>{s["ok"]}</b> ok, <b>{s["com_atencao"]}</b> com atenção, <b>{s["com_erro"]}</b> com erro.</p>
<p class="mu">Tabelas oficiais da calculadora da Receita Federal, base {e(versao_tabelas)}. Relatório gerado pelo auditor-ibs-cbs
(projeto independente, não oficial). Não substitui a validação da SEFAZ nem a orientação do seu contador.</p>
{blocos}
<h2>Detalhes</h2>
<table><thead><tr><th>Documento</th><th>Item</th><th>Gravidade</th><th>Problema</th></tr></thead><tbody>
{corpo}
</tbody></table></body></html>
"""

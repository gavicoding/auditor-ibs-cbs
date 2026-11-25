"""Saídas do auditor: texto, JSON, CSV, Markdown e HTML.

Os relatórios mostram chave, número, item e o problema. Não incluem dados do destinatário.
"""

from __future__ import annotations

import csv
import html
import io
import json
from collections import Counter
from collections.abc import Iterable

from .regras import Resultado

ROTULO = {"erro": "ERRO", "atencao": "ATENÇÃO", "info": "INFO", "ok": "OK"}


def resumo(resultados: list[Resultado]) -> dict:
    situacoes = Counter(r.situacao for r in resultados)
    codigos = Counter(a.codigo for r in resultados for a in r.achados if a.gravidade != "info")
    return {
        "notas": len(resultados),
        "ok": situacoes.get("ok", 0),
        "com_atencao": situacoes.get("atencao", 0),
        "com_erro": situacoes.get("erro", 0),
        "problemas_mais_comuns": codigos.most_common(10),
    }


def _linhas(resultados: Iterable[Resultado], incluir_info: bool):
    for r in resultados:
        for a in r.achados:
            if a.gravidade == "info" and not incluir_info:
                continue
            yield r, a


def texto(resultados: list[Resultado], versao_tabelas: str, incluir_info: bool = False) -> str:
    out = io.StringIO()
    for r in resultados:
        achados = [a for a in r.achados if incluir_info or a.gravidade != "info"]
        if not achados:
            continue
        ident = f"NF {r.numero or '?'} série {r.serie or '?'}" + (f"  chave {r.chave}" if r.chave else "")
        out.write(f"\n[{ROTULO[r.situacao]}] {ident}\n  arquivo: {r.origem}\n")
        for a in achados:
            onde = f"item {a.item}: " if a.item else ""
            out.write(f"  - {ROTULO[a.gravidade]:<8}{a.codigo}  {onde}{a.titulo}\n")
            out.write(f"      {a.explicacao}\n")
            out.write(f"      Como corrigir: {a.como_corrigir}\n")
    s = resumo(resultados)
    out.write(f"\nResumo: {s['notas']} nota(s) | {s['ok']} ok | {s['com_atencao']} com atenção | {s['com_erro']} com erro\n")
    if s["problemas_mais_comuns"]:
        out.write("Problemas mais comuns: " + ", ".join(f"{c} ({n})" for c, n in s["problemas_mais_comuns"]) + "\n")
    out.write(f"Tabelas oficiais usadas: base {versao_tabelas}\n")
    return out.getvalue()


def json_(resultados: list[Resultado], fonte: dict) -> str:
    return json.dumps(
        {"tabelas": fonte, "resumo": resumo(resultados), "notas": [r.como_dict() for r in resultados]},
        ensure_ascii=False,
        indent=2,
    )


def csv_(resultados: list[Resultado], incluir_info: bool = False) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(
        [
            "arquivo",
            "chave",
            "numero",
            "serie",
            "emissao",
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
                r.origem,
                r.chave,
                r.numero,
                r.serie,
                r.emissao,
                a.item,
                a.gravidade,
                a.codigo,
                a.titulo,
                a.explicacao,
                a.como_corrigir,
                a.campo,
            ]
        )
    return out.getvalue()


def markdown(resultados: list[Resultado], versao_tabelas: str, incluir_info: bool = False) -> str:
    s = resumo(resultados)
    linhas = [
        "## Auditoria IBS/CBS",
        "",
        f"**{s['notas']}** nota(s): **{s['ok']}** ok, **{s['com_atencao']}** com atenção, **{s['com_erro']}** com erro. "
        f"Tabelas oficiais: base {versao_tabelas}.",
        "",
        "| Nota | Item | Gravidade | Código | Problema |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for r, a in _linhas(resultados, incluir_info):
        problema = a.titulo.replace("|", "/")
        linhas.append(
            f"| {r.numero or '?'}/{r.serie or '?'} | {a.item or '-'} | {ROTULO[a.gravidade]} | {a.codigo} | {problema} |"
        )
    return "\n".join(linhas) + "\n"


def html_(resultados: list[Resultado], versao_tabelas: str, incluir_info: bool = False) -> str:
    s = resumo(resultados)
    e = html.escape
    linhas = []
    for r, a in _linhas(resultados, incluir_info):
        linhas.append(
            f'<tr class="{a.gravidade}"><td>{e(r.numero or "?")}/{e(r.serie or "?")}<br><small>{e(r.chave or "")}</small></td>'
            f"<td>{e(a.item or '-')}</td><td><b>{ROTULO[a.gravidade]}</b><br><small>{a.codigo}</small></td>"
            f"<td><b>{e(a.titulo)}</b><br>{e(a.explicacao)}<br><i>Como corrigir:</i> {e(a.como_corrigir)}</td></tr>"
        )
    corpo = "\n".join(linhas) or '<tr><td colspan="4">Nenhum problema encontrado.</td></tr>'
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auditoria IBS/CBS</title>
<style>
:root{{--bg:#fff;--tx:#1f2328;--mu:#59636e;--bd:#d1d9e0;--er:#cf222e;--at:#9a6700;--in:#0969da}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--tx:#e6edf3;--mu:#9198a1;--bd:#3d444d;--er:#ff7b72;--at:#d29922;--in:#58a6ff}}}}
body{{background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:24px 16px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid var(--bd);padding:8px;text-align:left;vertical-align:top}}
small,.mu{{color:var(--mu)}}tr.erro td:nth-child(3){{color:var(--er)}}tr.atencao td:nth-child(3){{color:var(--at)}}tr.info td:nth-child(3){{color:var(--in)}}
</style></head><body>
<h1>Auditoria IBS/CBS</h1>
<p><b>{s["notas"]}</b> nota(s): <b>{s["ok"]}</b> ok, <b>{s["com_atencao"]}</b> com atenção, <b>{s["com_erro"]}</b> com erro.</p>
<p class="mu">Tabelas oficiais da calculadora da Receita Federal, base {e(versao_tabelas)}. Relatório gerado pelo auditor-ibs-cbs
(projeto independente, não oficial). Não substitui a validação da SEFAZ nem a orientação do seu contador.</p>
<table><thead><tr><th>Nota</th><th>Item</th><th>Gravidade</th><th>Problema</th></tr></thead><tbody>
{corpo}
</tbody></table></body></html>
"""

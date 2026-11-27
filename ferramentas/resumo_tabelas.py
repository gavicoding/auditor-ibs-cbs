"""Resume o que mudou nas tabelas oficiais em relação ao último commit.

Usado pelo workflow diário de atualização: o resumo vai no corpo do pull request e, com
--changelog, a versão nova da base é registrada no topo do CHANGELOG.md.

Uso:
    python ferramentas/resumo_tabelas.py               # imprime o resumo em Markdown
    python ferramentas/resumo_tabelas.py --changelog   # idem, e registra a versão no CHANGELOG.md
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TABELAS = "src/auditor_ibs_cbs/dados/tabelas-rtc.json"
NCM = "src/auditor_ibs_cbs/dados/ncm.json"
CHANGELOG = RAIZ / "CHANGELOG.md"
LIMITE = 40  # itens listados por tabela no corpo do PR


def _anterior(caminho: str) -> dict:
    saida = subprocess.run(["git", "show", f"HEAD:{caminho}"], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    return json.loads(saida.stdout) if saida.returncode == 0 else {}


def _atual(caminho: str) -> dict:
    return json.loads((RAIZ / caminho).read_text(encoding="utf-8"))


def comparar(antes: dict, depois: dict) -> tuple[list[str], list[str], list[str]]:
    """Chaves novas, removidas e alteradas entre dois dicionários."""
    novos = sorted(set(depois) - set(antes))
    removidos = sorted(set(antes) - set(depois))
    alterados = sorted(k for k in set(antes) & set(depois) if antes[k] != depois[k])
    return novos, removidos, alterados


def _campos(a: dict, b: dict) -> str:
    return ", ".join(sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))


def _curto(texto: str, limite: int = 90) -> str:
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + "…"


def _aliquotas(lista: list[dict]) -> set[tuple]:
    return {(a["tributo"], a["percentual"], a["inicio"], a["fim"]) for a in lista}


def _versao(fonte: dict) -> str:
    return f"{fonte.get('versao_base', '?')} de {fonte.get('data_base', '?')}" if fonte else "nenhuma"


def montar(antes: dict, depois: dict, ncm_antes: dict, ncm_depois: dict) -> tuple[str, str]:
    """Devolve (resumo em Markdown para o PR, linha curta para o CHANGELOG)."""
    fa, fd = antes.get("fonte", {}), depois.get("fonte", {})
    cst = comparar(antes.get("cst", {}), depois.get("cst", {}))
    cclass = comparar(antes.get("cclasstrib", {}), depois.get("cclasstrib", {}))
    ncm = comparar(ncm_antes.get("ncm", {}), ncm_depois.get("ncm", {}))
    al_a, al_d = _aliquotas(antes.get("aliquota_referencia", [])), _aliquotas(depois.get("aliquota_referencia", []))
    aliq = (sorted(al_d - al_a), sorted(al_a - al_d), [])

    linhas = [
        f"- **Base anterior:** {_versao(fa)}",
        f"- **Base nova:** {_versao(fd)}" + (f" ({_curto(fd['descricao_base'])})" if fd.get("descricao_base") else ""),
        f"- **Fonte:** [{fd.get('url', 'calculadora oficial')}]({fd.get('url', '')})" + (f", commit `{fd['commit'][:12]}`" if fd.get("commit") else ""),
        "",
        "| Tabela | Novos | Removidos | Alterados |",
        "|---|---|---|---|",
    ]
    nomes = (("CST", cst), ("cClassTrib", cclass), ("Alíquotas de referência", aliq), ("NCM", ncm))
    for nome, (n, r, a) in nomes:
        linhas.append(f"| {nome} | {len(n)} | {len(r)} | {len(a)} |")

    def detalhar(titulo: str, dados: tuple, antes_d: dict, depois_d: dict, descrever) -> None:
        n, r, a = dados
        if not (n or r or a):
            return
        linhas.extend(["", f"### {titulo}", ""])
        entradas = [f"- novo `{k}`: {descrever(depois_d[k])}" for k in n]
        entradas += [f"- removido `{k}`: {descrever(antes_d[k])}" for k in r]
        entradas += [f"- alterado `{k}`: {_campos(antes_d[k], depois_d[k])}" for k in a]
        linhas.extend(entradas[:LIMITE])
        if len(entradas) > LIMITE:
            linhas.append(f"- … e mais {len(entradas) - LIMITE}")

    detalhar("CST", cst, antes.get("cst", {}), depois.get("cst", {}), lambda v: _curto(v["descricao"]))
    detalhar(
        "cClassTrib",
        cclass,
        antes.get("cclasstrib", {}),
        depois.get("cclasstrib", {}),
        lambda v: f"{_curto(v['descricao'])} (CST {v['cst']})",
    )
    if aliq[0] or aliq[1]:
        linhas.extend(["", "### Alíquotas de referência", ""])
        linhas += [f"- nova: {t} {p}% de {i} a {f or 'sem fim'}" for t, p, i, f in aliq[0]]
        linhas += [f"- removida: {t} {p}% de {i} a {f or 'sem fim'}" for t, p, i, f in aliq[1]]
    if any(ncm):
        linhas.extend(["", "### NCM", "", f"{len(ncm[0])} novos, {len(ncm[1])} removidos e {len(ncm[2])} alterados (descrição ou vigência)."])

    partes = [
        f"{nome}: " + ", ".join(f"{len(x)} {rot}" for x, rot in zip(d, ("novos", "removidos", "alterados"), strict=True) if x) for nome, d in nomes if any(d)
    ]
    curto = "; ".join(partes) if partes else "só metadados da base mudaram"
    return "\n".join(linhas), curto


def registrar_changelog(depois: dict, curto: str) -> None:
    fonte = depois["fonte"]
    titulo = f"## Tabelas oficiais: base {fonte['versao_base']} de {fonte['data_base']}"
    texto = CHANGELOG.read_text(encoding="utf-8")
    if titulo in texto:
        return
    entrada = f"{titulo}\n\nAtualização automática a partir da calculadora oficial da Receita Federal. {curto}.\n\n"
    cabecalho = "# Mudanças\n\n"
    texto = cabecalho + entrada + texto[len(cabecalho) :] if texto.startswith(cabecalho) else entrada + texto
    CHANGELOG.write_text(texto, encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    depois = _atual(TABELAS)
    resumo, curto = montar(_anterior(TABELAS), depois, _anterior(NCM), _atual(NCM))
    if "--changelog" in argv:
        registrar_changelog(depois, curto)
    print(resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Vigia as publicações do Portal da NF-e ligadas à reforma tributária (IBS, CBS, IS, NT 2025.002...).

Lê a página pública de documentos, filtra o que interessa e compara com a lista já conhecida
(``vigia/publicacoes-conhecidas.json``). Imprime em JSON as publicações novas, para o workflow
abrir uma issue de revisão. Regra fiscal nova exige revisão humana: nada é aplicado sozinho.

Uso:
    python ferramentas/vigiar_publicacoes.py            # imprime as novas (lista JSON)
    python ferramentas/vigiar_publicacoes.py --atualizar # grava a lista atual como conhecida
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://dfe-portal.svrs.rs.gov.br/NFE/Documentos"
CONHECIDAS = Path(__file__).resolve().parent.parent / "vigia" / "publicacoes-conhecidas.json"
INTERESSE = re.compile(r"RTC|IBS|CBS|Imposto Seletivo|Reforma Tribut|2025\.00[2-9]|cClassTrib|LC 214", re.I)
LIMITE = 5 * 1024 * 1024


def baixar() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "auditor-ibs-cbs (verificador de publicacoes)"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - URL fixa do portal oficial
        return resp.read(LIMITE).decode("utf-8", "replace")


def _limpar(texto: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", texto)).split())


def extrair(pagina: str) -> list[dict]:
    publicacoes = []
    for artigo in re.findall(r"<article[^>]*>(.*?)</article>", pagina, re.S):
        titulo = re.search(r"<h2[^>]*>(.*?)</h2>", artigo, re.S)
        if not titulo:
            continue
        data = re.search(r'datetime="\s*([^"]+?)\s*"', artigo)
        arquivo = re.search(r"download_arquivo_estatico\([^)]*?'([^']+)'\)", artigo)
        descricao = re.search(r"</header>(.*)", artigo, re.S)
        item = {
            "data": data.group(1) if data else "",
            "titulo": _limpar(titulo.group(1)),
            "arquivo": arquivo.group(1) if arquivo else "",
            "descricao": _limpar(descricao.group(1))[:500] if descricao else "",
        }
        if INTERESSE.search(item["titulo"] + " " + item["descricao"] + " " + item["arquivo"]):
            publicacoes.append(item)
    return publicacoes


def chave(p: dict) -> str:
    return f"{p['data']}|{p['titulo']}|{p['arquivo']}"


def main(argv: list[str]) -> int:
    atuais = extrair(baixar())
    if not atuais:
        print("Nenhuma publicação encontrada: a página pode ter mudado de formato.", file=sys.stderr)
        return 2
    if "--atualizar" in argv:
        CONHECIDAS.parent.mkdir(exist_ok=True)
        CONHECIDAS.write_text(json.dumps(sorted(atuais, key=chave), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(atuais)} publicações registradas como conhecidas")
        return 0
    conhecidas = {chave(p) for p in json.loads(CONHECIDAS.read_text(encoding="utf-8"))}
    novas = [p for p in atuais if chave(p) not in conhecidas]
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(novas, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

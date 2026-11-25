"""Compara os esquemas XSD embutidos com os da calculadora oficial e informa a versão dela.

Uso: python ferramentas/vigiar_calculadora.py CAMINHO_DO_CLONE
Imprime JSON: {"versao": "...", "xsd_diferentes": [...], "xsd_novos": [...]}.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EMBUTIDOS = RAIZ / "src" / "auditor_ibs_cbs" / "dados" / "xsd"
PASTAS = {"nfe": "nfe", "cte": "cte", "bpe": "bpe", "nfse": "nfse"}


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main(argv: list[str]) -> int:
    repo = Path(argv[1])
    pom = (repo / "pom.xml").read_text(encoding="utf-8") if (repo / "pom.xml").exists() else ""
    m = re.search(r"<artifactId>[^<]*calculadora[^<]*</artifactId>\s*<version>([^<]+)</version>", pom) or re.search(r"<version>([^<]+)</version>", pom)
    diferentes, novos = [], []
    for local, remoto in PASTAS.items():
        origem = repo / "src" / "main" / "resources" / "xml" / remoto / "originais"
        if not origem.exists():
            continue
        for arq in sorted(origem.glob("*.xsd")):
            meu = EMBUTIDOS / local / arq.name
            if not meu.exists():
                novos.append(f"{local}/{arq.name}")
            elif _hash(meu) != _hash(arq):
                diferentes.append(f"{local}/{arq.name}")
    print(json.dumps({"versao": m.group(1) if m else "?", "xsd_diferentes": diferentes, "xsd_novos": novos}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

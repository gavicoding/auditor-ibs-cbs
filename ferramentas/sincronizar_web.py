"""Copia as tabelas e os exemplos para docs/ (a página web usa os mesmos arquivos do pacote Python)."""

import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"


def main() -> None:
    for nome in ("tabelas-rtc.json", "ncm.json"):
        shutil.copyfile(RAIZ / "src/auditor_ibs_cbs/dados" / nome, DOCS / nome)
    pasta = DOCS / "exemplos"
    pasta.mkdir(exist_ok=True)
    for antigo in pasta.glob("*.xml"):
        antigo.unlink()
    nomes = []
    for xml in sorted((RAIZ / "exemplos").glob("*.xml")):
        shutil.copyfile(xml, pasta / xml.name)
        nomes.append(xml.name)
    (pasta / "lista.json").write_text(json.dumps(nomes, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("docs/ sincronizado")


if __name__ == "__main__":
    main()

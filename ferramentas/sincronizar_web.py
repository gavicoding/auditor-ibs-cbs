"""Copia as tabelas e os exemplos para docs/ (a página web usa os mesmos arquivos do pacote Python)."""

import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"


def main() -> None:
    shutil.copyfile(RAIZ / "src/auditor_ibs_cbs/dados/tabelas-rtc.json", DOCS / "tabelas-rtc.json")
    (DOCS / "exemplos").mkdir(exist_ok=True)
    for xml in sorted((RAIZ / "exemplos").glob("*.xml")):
        shutil.copyfile(xml, DOCS / "exemplos" / xml.name)
    print("docs/ sincronizado")


if __name__ == "__main__":
    main()

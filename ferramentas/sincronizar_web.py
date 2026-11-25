"""Copia as tabelas e os exemplos para docs/ (a página web usa os mesmos arquivos do pacote Python)."""

import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"


def main() -> None:
    for nome in ("tabelas-rtc.json", "ncm.json"):
        shutil.copyfile(RAIZ / "src/auditor_ibs_cbs/dados" / nome, DOCS / nome)
    import sys

    sys.path.insert(0, str(RAIZ / "src"))
    from auditor_ibs_cbs import nt

    catalogo = {
        "versao": nt.VERSAO_NT,
        "regras": {k: list(v) for k, v in nt.REGRAS.items()},
        "por_tributo": nt.POR_TRIBUTO,
        "totais": nt.TOTAIS,
        "cclass_debito_credito": {k: [sorted(a), sorted(b)] for k, (a, b) in nt.CCLASS_DEBITO_CREDITO.items()},
        "debito_exige": nt.DEBITO_EXIGE,
        "credito_exige": nt.CREDITO_EXIGE,
        "aliquotas_lei": {str(k): v for k, v in nt.ALIQUOTAS_LEI.items()},
    }
    (DOCS / "nt.json").write_text(json.dumps(catalogo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
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

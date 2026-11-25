"""Regera tests/esperado.json a partir da versão Python (revise o diff antes de commitar!).

O gabarito é usado pelos testes das duas versões (Python e web).
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from auditor_ibs_cbs import XMLInvalido, auditar, carregar, ler_bytes  # noqa: E402


def main() -> None:
    t = carregar()
    saida = {}
    for p in sorted((RAIZ / "exemplos").glob("*.xml")):
        try:
            r = auditar(ler_bytes(p.read_bytes(), p.name), t)
            saida[p.name] = {
                "achados": sorted(([a.codigo, a.gravidade, a.item, a.rejeicao] for a in r.achados), key=lambda x: (x[0], x[1], x[2] or "", x[3] or ""))
            }
        except XMLInvalido:
            saida[p.name] = {"ilegivel": True}
    (RAIZ / "tests" / "esperado.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(saida)} exemplos no gabarito")


if __name__ == "__main__":
    main()

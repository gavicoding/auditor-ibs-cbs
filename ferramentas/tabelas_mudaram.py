"""Sai com código 0 se os DADOS das tabelas mudaram em relação ao último commit (ignora o hash de origem).

Usado pelo workflow diário: um commit novo no repositório da Receita sem mudança de dados
não deve gerar pull request.
"""

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVOS = ("src/auditor_ibs_cbs/dados/tabelas-rtc.json", "src/auditor_ibs_cbs/dados/ncm.json")


def sem_commit(texto: str) -> dict:
    dados = json.loads(texto)
    dados.get("fonte", {}).pop("commit", None)
    return dados


def main() -> int:
    for arquivo in ARQUIVOS:
        antes = subprocess.run(["git", "show", f"HEAD:{arquivo}"], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        if antes.returncode != 0:
            return 0  # arquivo novo
        agora = (RAIZ / arquivo).read_text(encoding="utf-8")
        if sem_commit(antes.stdout) != sem_commit(agora):
            print(f"mudou: {arquivo}")
            return 0
    print("Tabelas já estão atualizadas (só o commit de origem mudou, ou nada mudou).")
    return 1


if __name__ == "__main__":
    sys.exit(main())

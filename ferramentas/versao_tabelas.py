"""Imprime a versão da base de tabelas embutida (usado pelo workflow de atualização)."""

import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "src" / "auditor_ibs_cbs" / "dados" / "tabelas-rtc.json"
fonte = json.loads(ARQUIVO.read_text(encoding="utf-8"))["fonte"]
print(f"{fonte['versao_base']} de {fonte['data_base']}")

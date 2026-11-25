"""Tabelas oficiais de CST e cClassTrib do IBS/CBS.

Os dados vêm do repositório público da calculadora da Receita Federal (licença MIT) e são
gerados por ``ferramentas/exportar_tabelas.py``. Veja ``fonte`` para a versão usada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any


def _vigente(inicio: str | None, fim: str | None, dia: date) -> bool:
    if inicio and dia < date.fromisoformat(inicio):
        return False
    if fim and dia > date.fromisoformat(fim):
        return False
    return True


@dataclass(frozen=True)
class Tabelas:
    dados: dict[str, Any]

    @property
    def fonte(self) -> dict[str, Any]:
        return self.dados["fonte"]

    @property
    def versao(self) -> str:
        f = self.fonte
        return f"{f['versao_base']} ({f['data_base']})"

    def cst(self, codigo: str) -> dict[str, Any] | None:
        return self.dados["cst"].get(codigo)

    def cclasstrib(self, codigo: str) -> dict[str, Any] | None:
        return self.dados["cclasstrib"].get(codigo)

    @staticmethod
    def vigente(registro: dict[str, Any], dia: date) -> bool:
        return _vigente(registro.get("inicio"), registro.get("fim"), dia)

    def permitido_no_modelo(self, codigo: str, modelo: int, dia: date) -> bool:
        reg = self.cclasstrib(codigo)
        if not reg:
            return False
        return any(d["modelo"] == modelo and _vigente(d["inicio"], d["fim"], dia) for d in reg["documentos"])

    def reducao(self, codigo: str, tributo: str, dia: date) -> float | None:
        """Percentual de redução oficial do cClassTrib para o tributo (CBS, IBSUF, IBSMun) na data."""
        reg = self.cclasstrib(codigo)
        if not reg:
            return None
        for r in reg["reducao"]:
            if r["tributo"] == tributo and _vigente(r["inicio"], r["fim"], dia):
                return r["percentual"]
        return None

    def aliquota_referencia(self, tributo: str, dia: date) -> float | None:
        for a in self.dados["aliquota_referencia"]:
            if a["tributo"] == tributo and _vigente(a["inicio"], a["fim"], dia):
                return a["percentual"]
        return None


@lru_cache(maxsize=4)
def carregar(caminho: str | None = None) -> Tabelas:
    """Carrega as tabelas embutidas no pacote, ou um JSON alternativo (mesmo formato)."""
    if caminho:
        texto = Path(caminho).read_text(encoding="utf-8")
    else:
        texto = resources.files("auditor_ibs_cbs").joinpath("dados/tabelas-rtc.json").read_text(encoding="utf-8")
    return Tabelas(json.loads(texto))

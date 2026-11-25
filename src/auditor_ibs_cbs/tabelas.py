"""Tabelas oficiais de CST, cClassTrib, NCM/NBS aplicáveis e NCM do IBS/CBS.

Os dados vêm do repositório público da calculadora da Receita Federal (licença MIT) e são
gerados por ``ferramentas/exportar_tabelas.py``. Veja ``fonte`` para a versão usada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

# cClassTrib que exigem NCM em NF-e/NFC-e mesmo sem lista própria (regra da calculadora oficial)
EXIGEM_NCM_SEMPRE = frozenset({"200038", "515001"})


def _vigente(inicio: str | None, fim: str | None, dia: date) -> bool:
    if inicio and dia < date.fromisoformat(inicio):
        return False
    if fim and dia > date.fromisoformat(fim):
        return False
    return True


@dataclass(frozen=True)
class Tabelas:
    dados: dict[str, Any]
    caminho_ncm: str | None = field(default=None, compare=False)

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

    def nome_documento(self, modelo: int) -> str:
        return self.dados.get("tipos_documento", {}).get(str(modelo), f"modelo {modelo}")

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

    # --- NCM / NBS aplicáveis -------------------------------------------------------------

    def tem_lista(self, codigo: str, tipo: str, dia: date) -> bool:
        """O cClassTrib só vale para alguns NCMs (tipo='ncm') ou NBSs (tipo='nbs') na data?"""
        reg = self.cclasstrib(codigo)
        return bool(reg) and any(_vigente(n["inicio"], n["fim"], dia) for n in reg.get(tipo, []))

    def aplicavel(self, codigo: str, tipo: str, valor: str, dia: date) -> bool:
        """Mesma regra da calculadora oficial: casa por prefixo e respeita as exceções vigentes."""
        reg = self.cclasstrib(codigo)
        if not reg:
            return False
        casam = [n for n in reg.get(tipo, []) if valor.startswith(n["codigo"]) and _vigente(n["inicio"], n["fim"], dia)]
        if not casam:
            return False
        tem_excecao = any(valor.startswith(e["codigo"]) and _vigente(e["inicio"], e["fim"], dia) for n in casam for e in n.get("excecoes", []))
        if not tem_excecao:
            return True
        return any(not n.get("excecoes") or any(not _vigente(e["inicio"], e["fim"], dia) for e in n["excecoes"]) for n in casam)

    def anexos_do_cclasstrib(self, codigo: str, tipo: str, dia: date) -> list[str]:
        """Itens de anexo da LC 214/2025 ligados ao cClassTrib (ex.: 'Anexo I, item 1')."""
        reg = self.cclasstrib(codigo) or {}
        vistos: list[str] = []
        for n in reg.get(tipo, []):
            a = self.dados.get("anexos", {}).get(str(n.get("anexo")))
            if a and _vigente(n["inicio"], n["fim"], dia):
                rotulo = f"Anexo {a['anexo']}, item {a['item']}"
                if rotulo not in vistos:
                    vistos.append(rotulo)
        return vistos

    # --- tabela NCM (carregada só quando precisa) --------------------------------------------

    def ncm(self, codigo: str) -> list | None:
        """[descrição, início, fim] do NCM de 8 dígitos, ou None se não existe."""
        return _carregar_ncm(self.caminho_ncm).get(codigo)


@lru_cache(maxsize=2)
def _carregar_ncm(caminho: str | None) -> dict[str, list]:
    if caminho:
        texto = Path(caminho).read_text(encoding="utf-8")
    else:
        texto = resources.files("auditor_ibs_cbs").joinpath("dados/ncm.json").read_text(encoding="utf-8")
    return json.loads(texto)["ncm"]


@lru_cache(maxsize=4)
def carregar(caminho: str | None = None, caminho_ncm: str | None = None) -> Tabelas:
    """Carrega as tabelas: o arquivo indicado, a cópia baixada por ``atualizar`` (se for mais nova)
    ou as embutidas no pacote."""
    if caminho:
        return Tabelas(json.loads(Path(caminho).read_text(encoding="utf-8")), caminho_ncm)
    embutidas = json.loads(resources.files("auditor_ibs_cbs").joinpath("dados/tabelas-rtc.json").read_text(encoding="utf-8"))
    from .atualizacao import copia_do_usuario, numero_versao

    copia = copia_do_usuario()
    if copia and caminho_ncm is None:
        baixadas = json.loads(Path(copia[0]).read_text(encoding="utf-8"))
        if numero_versao(baixadas["fonte"]) > numero_versao(embutidas["fonte"]):
            return Tabelas(baixadas, copia[1])
    return Tabelas(embutidas, caminho_ncm)

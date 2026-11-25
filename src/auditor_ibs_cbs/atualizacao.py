"""Atualização das tabelas oficiais sem reinstalar o pacote.

``auditor-ibs-cbs atualizar`` baixa as tabelas publicadas neste repositório (que acompanham a
calculadora da Receita Federal) para uma pasta do usuário. ``carregar()`` passa a usar essa cópia
quando ela é mais nova que a embutida no pacote. Os arquivos são validados antes de serem gravados.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/gavicoding/auditor-ibs-cbs/main/src/auditor_ibs_cbs/dados/"
ARQUIVOS = ("tabelas-rtc.json", "ncm.json")
LIMITE = 10 * 1024 * 1024
FONTE_OFICIAL = "https://github.com/ReceitaFederal/calculadora-rtc-regime-regular"


def pasta_usuario() -> Path:
    return Path(os.environ.get("AUDITOR_IBS_CBS_DADOS") or Path.home() / ".auditor-ibs-cbs")


def numero_versao(fonte: dict) -> int:
    """'V0073' -> 73 (0 se não der para ler)."""
    texto = str(fonte.get("versao_base", ""))
    digitos = "".join(ch for ch in texto if ch.isdigit())
    return int(digitos) if digitos else 0


def validar(nome: str, dados: dict) -> None:
    fonte = dados.get("fonte") or {}
    if fonte.get("url") != FONTE_OFICIAL:
        raise ValueError(f"{nome}: fonte inesperada")
    if nome == "tabelas-rtc.json" and not (dados.get("cst") and dados.get("cclasstrib")):
        raise ValueError(f"{nome}: tabelas vazias")
    if nome == "ncm.json" and not dados.get("ncm"):
        raise ValueError(f"{nome}: tabela NCM vazia")


def baixar(base: str = BASE) -> dict:
    """Baixa, valida e grava as tabelas na pasta do usuário. Devolve a fonte das novas tabelas."""
    destino = pasta_usuario()
    novos = {}
    for nome in ARQUIVOS:
        req = urllib.request.Request(base + nome, headers={"User-Agent": "auditor-ibs-cbs"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - URL fixa do repositório
            bruto = resp.read(LIMITE + 1)
        if len(bruto) > LIMITE:
            raise ValueError(f"{nome}: arquivo maior que o esperado")
        dados = json.loads(bruto.decode("utf-8"))
        validar(nome, dados)
        novos[nome] = bruto
    destino.mkdir(parents=True, exist_ok=True)
    for nome, bruto in novos.items():  # só grava depois de validar os dois
        (destino / nome).write_bytes(bruto)
    return json.loads(novos["tabelas-rtc.json"])["fonte"]


def copia_do_usuario() -> tuple[str, str] | None:
    """Caminhos (tabelas, ncm) da cópia do usuário, se existir e for válida."""
    pasta = pasta_usuario()
    tabelas, ncm = pasta / "tabelas-rtc.json", pasta / "ncm.json"
    if not (tabelas.exists() and ncm.exists()):
        return None
    try:
        validar("tabelas-rtc.json", json.loads(tabelas.read_text(encoding="utf-8")))
    except (ValueError, json.JSONDecodeError):
        return None
    return str(tabelas), str(ncm)

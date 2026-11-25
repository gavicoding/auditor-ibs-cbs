"""Validação opcional contra o leiaute oficial (XSD) dos documentos.

Usa a biblioteca ``xmlschema`` (instale com ``pip install "auditor-ibs-cbs[xsd]"``). Os esquemas
são os que acompanham a calculadora pública da Receita Federal (pasta ``dados/xsd``).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import lru_cache
from importlib import resources

# elemento raiz (sem namespace) -> (pasta, arquivo do esquema)
ESQUEMAS = {
    "NFe": ("nfe", "nfe_v4.00.xsd"),
    "CTe": ("cte", "cte_v4.00.xsd"),
    "CTeOS": ("cte", "cteOS_v4.00.xsd"),
    "BPe": ("bpe", "bpeTiposBasico_v1.00.xsd"),
    "NFSe": ("nfse", "tiposComplexos_v1.01.xsd"),
    "DPS": ("nfse", "tiposComplexos_v1.01.xsd"),
}
MAX_ERROS = 5


class XSDIndisponivel(RuntimeError):
    """A biblioteca xmlschema não está instalada."""


@lru_cache(maxsize=8)
def _esquema(pasta: str, arquivo: str):
    try:
        import xmlschema
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise XSDIndisponivel('instale com: pip install "auditor-ibs-cbs[xsd]"') from erro
    caminho = resources.files("auditor_ibs_cbs").joinpath(f"dados/xsd/{pasta}/{arquivo}")
    with resources.as_file(caminho) as arquivo_local:
        return xmlschema.XMLSchema(str(arquivo_local))


def validar(conteudo: bytes) -> list[str] | None:
    """Erros de leiaute do documento (lista vazia = válido). None = tipo sem esquema disponível.

    O conteúdo já deve ter passado pela checagem de segurança do leitor (sem DOCTYPE/ENTITY).
    """
    raiz = ET.fromstring(conteudo)
    for nome, (pasta, arquivo) in ESQUEMAS.items():
        alvo = raiz if raiz.tag.rsplit("}", 1)[-1] == nome else next((el for el in raiz.iter() if el.tag.rsplit("}", 1)[-1] == nome), None)
        if alvo is None:
            continue
        esquema = _esquema(pasta, arquivo)
        erros = []
        for erro in esquema.iter_errors(alvo):
            caminho = (erro.path or "").replace("{http://www.portalfiscal.inf.br/nfe}", "")
            erros.append(f"{caminho}: {erro.reason}"[:300])
            if len(erros) >= MAX_ERROS:
                break
        return erros
    return None

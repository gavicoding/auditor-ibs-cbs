"""Leitura segura de XMLs de NF-e (modelo 55) e NFC-e (modelo 65).

- Funciona com ou sem namespace, e com ``nfeProc`` ou ``NFe`` na raiz.
- Recusa XML com DOCTYPE/ENTITY (proteção contra XXE e "billion laughs").
- Lê arquivos soltos, pastas (recursivo) e arquivos .zip sem extrair nada para o disco.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

TAMANHO_MAXIMO = 20 * 1024 * 1024  # 20 MB por XML
MAX_ARQUIVOS_ZIP = 200_000


class XMLInvalido(ValueError):
    """O conteúdo não é um XML de NF-e/NFC-e que possa ser lido com segurança."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sem_namespace(raiz: ET.Element) -> ET.Element:
    for el in raiz.iter():
        el.tag = _local(el.tag)
    return raiz


def _texto(el: ET.Element | None, caminho: str) -> str | None:
    if el is None:
        return None
    achado = el.find(caminho)
    if achado is None or achado.text is None:
        return None
    return achado.text.strip()


def _decimal(el: ET.Element | None, caminho: str) -> Decimal | None:
    valor = _texto(el, caminho)
    if valor is None or valor == "":
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


@dataclass
class Tributo:
    """Um dos três blocos do gIBSCBS: gIBSUF, gIBSMun ou gCBS."""

    aliquota: Decimal | None
    valor: Decimal | None
    reducao: Decimal | None = None  # gRed/pRedAliq
    aliquota_efetiva: Decimal | None = None  # gRed/pAliqEfet
    tem_diferimento: bool = False  # gDif
    tem_devolucao: bool = False  # gDevTrib


@dataclass
class Item:
    numero: str
    descricao: str
    tem_grupo: bool  # imposto/IBSCBS presente
    cst: str | None = None
    cclasstrib: str | None = None
    grupos: set[str] = field(default_factory=set)  # subgrupos presentes em IBSCBS
    base: Decimal | None = None  # gIBSCBS/vBC
    ibs_uf: Tributo | None = None
    ibs_mun: Tributo | None = None
    cbs: Tributo | None = None
    valor_ibs: Decimal | None = None  # gIBSCBS/vIBS


@dataclass
class Totais:
    presente: bool
    base: Decimal | None = None
    ibs_uf: Decimal | None = None
    ibs_mun: Decimal | None = None
    ibs: Decimal | None = None
    cbs: Decimal | None = None


@dataclass
class Nota:
    origem: str
    chave: str | None
    modelo: int | None
    numero: str | None
    serie: str | None
    emissao: date | None
    crt: str | None
    cnpj_emitente: str | None
    itens: list[Item]
    totais: Totais


def _tributo(grupo: ET.Element | None, prefixo: str) -> Tributo | None:
    if grupo is None:
        return None
    red = grupo.find("gRed")
    return Tributo(
        aliquota=_decimal(grupo, f"p{prefixo}"),
        valor=_decimal(grupo, f"v{prefixo}"),
        reducao=_decimal(red, "pRedAliq"),
        aliquota_efetiva=_decimal(red, "pAliqEfet"),
        tem_diferimento=grupo.find("gDif") is not None,
        tem_devolucao=grupo.find("gDevTrib") is not None,
    )


def _item(det: ET.Element) -> Item:
    numero = det.get("nItem") or "?"
    descricao = _texto(det, "prod/xProd") or ""
    grupo = det.find("imposto/IBSCBS")
    if grupo is None:
        return Item(numero=numero, descricao=descricao, tem_grupo=False)
    item = Item(
        numero=numero,
        descricao=descricao,
        tem_grupo=True,
        cst=_texto(grupo, "CST"),
        cclasstrib=_texto(grupo, "cClassTrib"),
        grupos={filho.tag for filho in grupo if filho.tag.startswith("g")},
    )
    g = grupo.find("gIBSCBS")
    if g is not None:
        item.base = _decimal(g, "vBC")
        item.ibs_uf = _tributo(g.find("gIBSUF"), "IBSUF")
        item.ibs_mun = _tributo(g.find("gIBSMun"), "IBSMun")
        item.cbs = _tributo(g.find("gCBS"), "CBS")
        item.valor_ibs = _decimal(g, "vIBS")
    return item


def _data(texto: str | None) -> date | None:
    if not texto or len(texto) < 10:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        return None


def ler_bytes(conteudo: bytes, origem: str) -> Nota:
    if len(conteudo) > TAMANHO_MAXIMO:
        raise XMLInvalido("arquivo maior que 20 MB")
    inicio = conteudo[:4096].upper()
    if b"<!DOCTYPE" in inicio or b"<!ENTITY" in conteudo.upper():
        raise XMLInvalido("XML com DOCTYPE/ENTITY foi recusado por segurança")
    try:
        raiz = _sem_namespace(ET.fromstring(conteudo))
    except ET.ParseError as erro:
        raise XMLInvalido(f"XML mal formado ({erro})") from None

    inf = raiz if raiz.tag == "infNFe" else raiz.find(".//infNFe")
    if inf is None:
        raise XMLInvalido("não é um XML de NF-e/NFC-e (infNFe não encontrado)")

    ide = inf.find("ide")
    modelo_txt = _texto(ide, "mod")
    chave = (inf.get("Id") or "").removeprefix("NFe") or _texto(raiz, ".//protNFe/infProt/chNFe")
    tot = inf.find("total/IBSCBSTot")
    totais = Totais(presente=tot is not None)
    if tot is not None:
        totais.base = _decimal(tot, "vBCIBSCBS")
        totais.ibs_uf = _decimal(tot, "gIBS/gIBSUF/vIBSUF")
        totais.ibs_mun = _decimal(tot, "gIBS/gIBSMun/vIBSMun")
        totais.ibs = _decimal(tot, "gIBS/vIBS")
        totais.cbs = _decimal(tot, "gCBS/vCBS")

    return Nota(
        origem=origem,
        chave=chave or None,
        modelo=int(modelo_txt) if modelo_txt and modelo_txt.isdigit() else None,
        numero=_texto(ide, "nNF"),
        serie=_texto(ide, "serie"),
        emissao=_data(_texto(ide, "dhEmi") or _texto(ide, "dEmi")),
        crt=_texto(inf, "emit/CRT"),
        cnpj_emitente=_texto(inf, "emit/CNPJ"),
        itens=[_item(det) for det in inf.findall("det")],
        totais=totais,
    )


def ler_arquivo(caminho: str | Path) -> Nota:
    caminho = Path(caminho)
    if caminho.stat().st_size > TAMANHO_MAXIMO:
        raise XMLInvalido("arquivo maior que 20 MB")
    return ler_bytes(caminho.read_bytes(), str(caminho))


def percorrer(entradas: list[str | Path]) -> Iterator[tuple[str, bytes | Exception]]:
    """Gera (origem, conteúdo) para cada XML encontrado em arquivos, pastas e .zip."""
    for entrada in entradas:
        caminho = Path(entrada)
        if caminho.is_dir():
            arquivos = sorted(p for p in caminho.rglob("*") if p.is_file() and p.suffix.lower() in (".xml", ".zip"))
            yield from percorrer(arquivos)
        elif caminho.suffix.lower() == ".zip":
            yield from _percorrer_zip(caminho)
        elif caminho.is_file():
            try:
                if caminho.stat().st_size > TAMANHO_MAXIMO:
                    raise XMLInvalido("arquivo maior que 20 MB")
                yield str(caminho), caminho.read_bytes()
            except (OSError, XMLInvalido) as erro:
                yield str(caminho), erro
        else:
            yield str(caminho), FileNotFoundError(f"não encontrado: {caminho}")


def _percorrer_zip(caminho: Path) -> Iterator[tuple[str, bytes | Exception]]:
    try:
        with zipfile.ZipFile(caminho) as arquivo_zip:
            membros = [m for m in arquivo_zip.infolist() if not m.is_dir() and m.filename.lower().endswith(".xml")]
            if len(membros) > MAX_ARQUIVOS_ZIP:
                yield str(caminho), XMLInvalido(f"zip com mais de {MAX_ARQUIVOS_ZIP} arquivos")
                return
            for membro in membros:
                origem = f"{caminho}!{membro.filename}"
                if membro.file_size > TAMANHO_MAXIMO:
                    yield origem, XMLInvalido("arquivo maior que 20 MB")
                    continue
                with arquivo_zip.open(membro) as f:
                    dados = f.read(TAMANHO_MAXIMO + 1)
                if len(dados) > TAMANHO_MAXIMO:
                    yield origem, XMLInvalido("arquivo maior que 20 MB")
                    continue
                yield origem, dados
    except (OSError, zipfile.BadZipFile) as erro:
        yield str(caminho), XMLInvalido(f"zip inválido ({erro})")

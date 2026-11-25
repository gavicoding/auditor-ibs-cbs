"""Leitura segura de documentos fiscais eletrônicos com o grupo IBS/CBS.

Documentos suportados: NF-e (55), NFC-e (65), CT-e (57), CT-e OS (67), BP-e (63), NF3-e (66) e
NFS-e nacional (DPS ou NFS-e autorizada).

- Funciona com ou sem namespace e com ou sem o envelope de protocolo (nfeProc, cteProc...).
- Recusa XML com DOCTYPE/ENTITY (proteção contra XXE e "billion laughs").
- Lê arquivos soltos, pastas (recursivo) e arquivos .zip sem extrair nada para o disco.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

TAMANHO_MAXIMO = 20 * 1024 * 1024  # 20 MB por XML
MAX_ARQUIVOS_ZIP = 200_000

# raiz de informação -> (sigla, modelo padrão, caminho do número)
RAIZES = {
    "infNFe": ("NF-e", 55, "ide/nNF"),
    "infCte": ("CT-e", 57, "ide/nCT"),
    "infBPe": ("BP-e", 63, "ide/nBP"),
    "infNF3e": ("NF3-e", 66, "ide/nNF"),
    "infNFSe": ("NFS-e", 91, "nNFSe"),
    "infDPS": ("NFS-e", 91, "nDPS"),
}
SIGLAS = {55: "NF-e", 65: "NFC-e", 57: "CT-e", 67: "CT-e OS", 63: "BP-e", 66: "NF3-e", 91: "NFS-e"}


class XMLInvalido(ValueError):
    """O conteúdo não é um documento fiscal que possa ser lido com segurança."""


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


NUMERO = re.compile(r"-?\d+(\.\d+)?")


def _numero(texto: str | None) -> Decimal | None:
    """Só aceita o formato do leiaute (dígitos, ponto decimal opcional); o resto vira None."""
    if not texto or not NUMERO.fullmatch(texto):
        return None
    try:
        return Decimal(texto)
    except InvalidOperation:  # pragma: no cover - a regex já garante o formato
        return None


def _decimal(el: ET.Element | None, caminho: str) -> Decimal | None:
    return _numero(_texto(el, caminho))


@dataclass
class Tributo:
    """Um dos três blocos do IBS/CBS: IBS estadual (UF), IBS municipal (Mun) ou CBS."""

    aliquota: Decimal | None
    valor: Decimal | None
    reducao: Decimal | None = None  # gRed/pRedAliq
    aliquota_efetiva: Decimal | None = None  # gRed/pAliqEfet
    tem_diferimento: bool = False  # gDif
    p_dif: Decimal | None = None
    v_dif: Decimal | None = None
    tem_devolucao: bool = False  # gDevTrib
    v_dev: Decimal | None = None


@dataclass
class Campo:
    """Um valor do grupo IBS/CBS, guardado para conferir o formato exigido pelo leiaute."""

    caminho: str
    nome: str
    valor: str


@dataclass
class Item:
    numero: str
    descricao: str
    tem_grupo: bool  # grupo IBSCBS presente
    ncm: str | None = None
    nbs: str | None = None
    cst: str | None = None
    cclasstrib: str | None = None
    grupos: set[str] = field(default_factory=set)  # subgrupos presentes em IBSCBS
    base: Decimal | None = None  # vBC
    ibs_uf: Tributo | None = None
    ibs_mun: Tributo | None = None
    cbs: Tributo | None = None
    valor_ibs: Decimal | None = None  # vIBS
    especiais: dict[str, dict[str, Decimal | str | None]] = field(default_factory=dict)
    faltando: list[str] = field(default_factory=list)  # campos obrigatórios ausentes no grupo
    campos: list[Campo] = field(default_factory=list)


@dataclass
class Totais:
    presente: bool
    valores: dict[str, Decimal | None] = field(default_factory=dict)
    campos: list[Campo] = field(default_factory=list)


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
    tipo: str | None = None  # sigla: NF-e, NFC-e, CT-e...
    redutor_compra_gov: Decimal | None = None  # gCompraGov/pRedutor
    por_item: bool = True  # NF-e, NFC-e e NF3-e têm itens; CT-e, BP-e e NFS-e têm um grupo só


# ----------------------------------------------------------------------------- grupos TCIBS (DFe)

OBRIGATORIOS_GIBSCBS = (
    "vBC",
    "gIBSUF/pIBSUF",
    "gIBSUF/vIBSUF",
    "gIBSMun/pIBSMun",
    "gIBSMun/vIBSMun",
    "vIBS",
    "gCBS/pCBS",
    "gCBS/vCBS",
)
NUMERICOS = ("v", "p", "q", "adRem")  # campos numéricos do grupo IBS/CBS
OBRIGATORIOS_SUB = {"gRed": ("pRedAliq", "pAliqEfet"), "gDif": ("pDif", "vDif"), "gDevTrib": ("vDevTrib",)}


def _campos(el: ET.Element, prefixo: str) -> list[Campo]:
    saida = []
    for filho in el.iter():
        if filho is el or len(filho):
            continue
        saida.append(Campo(prefixo, filho.tag, (filho.text or "").strip()))
    return saida


def _tributo(grupo: ET.Element | None, prefixo: str, item: Item, nome_grupo: str) -> Tributo | None:
    if grupo is None:
        return None
    red = grupo.find("gRed")
    dif = grupo.find("gDif")
    dev = grupo.find("gDevTrib")
    for sub, el in (("gRed", red), ("gDif", dif), ("gDevTrib", dev)):
        if el is not None:
            for obrig in OBRIGATORIOS_SUB[sub]:
                if el.find(obrig) is None:
                    item.faltando.append(f"{nome_grupo}/{sub}/{obrig}")
    return Tributo(
        aliquota=_decimal(grupo, f"p{prefixo}"),
        valor=_decimal(grupo, f"v{prefixo}"),
        reducao=_decimal(red, "pRedAliq"),
        aliquota_efetiva=_decimal(red, "pAliqEfet"),
        tem_diferimento=dif is not None,
        p_dif=_decimal(dif, "pDif"),
        v_dif=_decimal(dif, "vDif"),
        tem_devolucao=dev is not None,
        v_dev=_decimal(dev, "vDevTrib"),
    )


def _valores(el: ET.Element | None) -> dict[str, Decimal | str | None]:
    """Todos os valores-folha de um grupo, pelo caminho relativo (ex.: 'gIBSCredPres/vCredPres')."""
    if el is None:
        return {}
    saida: dict[str, Decimal | str | None] = {}

    def visitar(no: ET.Element, prefixo: str) -> None:
        for filho in no:
            caminho = f"{prefixo}{filho.tag}"
            if len(filho):
                visitar(filho, caminho + "/")
            else:
                texto = (filho.text or "").strip()
                if filho.tag.startswith(NUMERICOS):
                    saida[caminho] = _numero(texto)
                else:
                    saida[caminho] = texto

    visitar(el, "")
    return saida


def _grupo_dfe(grupo: ET.Element | None, numero: str, descricao: str, ncm: str | None) -> Item:
    if grupo is None:
        return Item(numero=numero, descricao=descricao, tem_grupo=False, ncm=ncm)
    item = Item(
        numero=numero,
        descricao=descricao,
        tem_grupo=True,
        ncm=ncm,
        cst=_texto(grupo, "CST"),
        cclasstrib=_texto(grupo, "cClassTrib"),
        grupos={filho.tag for filho in grupo if filho.tag.startswith("g")},
        campos=_campos(grupo, "IBSCBS"),
    )
    g = grupo.find("gIBSCBS")
    if g is not None:
        for obrig in OBRIGATORIOS_GIBSCBS:
            if g.find(obrig) is None:
                item.faltando.append(f"gIBSCBS/{obrig}")
        item.base = _decimal(g, "vBC")
        item.ibs_uf = _tributo(g.find("gIBSUF"), "IBSUF", item, "gIBSUF")
        item.ibs_mun = _tributo(g.find("gIBSMun"), "IBSMun", item, "gIBSMun")
        item.cbs = _tributo(g.find("gCBS"), "CBS", item, "gCBS")
        item.valor_ibs = _decimal(g, "vIBS")
        for nome in ("gTribRegular", "gTribCompraGov"):
            if g.find(nome) is not None:
                item.especiais[nome] = _valores(g.find(nome))
    for nome in ("gIBSCBSMono", "gTransfCred", "gAjusteCompet", "gEstornoCred", "gCredPresOper", "gCredPresIBSZFM"):
        if grupo.find(nome) is not None:
            item.especiais[nome] = _valores(grupo.find(nome))
    return item


def _totais(tot: ET.Element | None) -> Totais:
    if tot is None:
        return Totais(presente=False)
    return Totais(presente=True, valores=_valores(tot), campos=_campos(tot, "IBSCBSTot"))


# ----------------------------------------------------------------------------- NFS-e nacional


def _nfse(raiz: ET.Element, origem: str) -> Nota:
    inf_nfse = raiz if raiz.tag == "infNFSe" else raiz.find(".//infNFSe")
    inf_dps = raiz if raiz.tag == "infDPS" else raiz.find(".//infDPS")
    if inf_dps is None:
        raise XMLInvalido("NFS-e sem o DPS (infDPS), onde ficam o CST e o cClassTrib")
    trib = inf_dps.find("IBSCBS/valores/trib/gIBSCBS")
    nbs = _texto(inf_dps, "serv/cServ/cNBS")
    descricao = _texto(inf_dps, "serv/cServ/xDescServ") or ""
    item = Item(numero="1", descricao=descricao[:120], tem_grupo=trib is not None, nbs=nbs)
    if trib is not None:
        item.cst = _texto(trib, "CST")
        item.cclasstrib = _texto(trib, "cClassTrib")
        item.grupos = {f.tag for f in trib if f.tag.startswith("g")}
        item.campos = _campos(trib, "IBSCBS/valores/trib/gIBSCBS")
        if trib.find("gTribRegular") is not None:
            item.especiais["gTribRegular"] = _valores(trib.find("gTribRegular"))
    dif = trib.find("gDif") if trib is not None else None
    calc = inf_nfse.find("IBSCBS") if inf_nfse is not None else None
    redutor = None
    if calc is not None:
        v = calc.find("valores")
        tot = calc.find("totCIBS")
        redutor = _decimal(calc, "pRedutor")
        item.base = _decimal(v, "vBC")

        def trib_nfse(sigla: str, grupo: str, tot_valor: str, tot_dif: str, p_dif: str) -> Tributo:
            g = v.find(grupo) if v is not None else None
            return Tributo(
                aliquota=_decimal(g, f"p{sigla}"),
                valor=_decimal(tot, tot_valor),
                reducao=_decimal(g, f"pRedAliq{sigla[3:] if sigla != 'CBS' else 'CBS'}"),
                aliquota_efetiva=_decimal(g, f"pAliqEfet{sigla[3:] if sigla != 'CBS' else 'CBS'}"),
                tem_diferimento=dif is not None,
                p_dif=_decimal(dif, p_dif),
                v_dif=_decimal(tot, tot_dif),
            )

        item.ibs_uf = trib_nfse("IBSUF", "uf", "gIBS/gIBSUFTot/vIBSUF", "gIBS/gIBSUFTot/vDifUF", "pDifUF")
        item.ibs_mun = trib_nfse("IBSMun", "mun", "gIBS/gIBSMunTot/vIBSMun", "gIBS/gIBSMunTot/vDifMun", "pDifMun")
        item.cbs = trib_nfse("CBS", "fed", "gCBS/vCBS", "gCBS/vDifCBS", "pDifCBS")
        item.valor_ibs = _decimal(tot, "gIBS/vIBSTot")
        item.grupos.add("gIBSCBS")
        item.campos += _campos(calc, "infNFSe/IBSCBS")
    emissao = _texto(inf_dps, "dhEmi")
    return Nota(
        origem=origem,
        chave=((inf_nfse.get("Id") or "").removeprefix("NFS") if inf_nfse is not None else None) or None,
        modelo=91,
        tipo="NFS-e",
        numero=_texto(inf_nfse, "nNFSe") or _texto(inf_dps, "nDPS"),
        serie=_texto(inf_dps, "serie"),
        emissao=_data(emissao),
        crt=None,
        cnpj_emitente=_texto(inf_dps, "prest/CNPJ"),
        itens=[item],
        totais=Totais(presente=False),
        redutor_compra_gov=redutor,
        por_item=False,
    )


# ----------------------------------------------------------------------------- entrada


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
    if b"<!DOCTYPE" in conteudo[:4096].upper() or b"<!ENTITY" in conteudo.upper():
        raise XMLInvalido("XML com DOCTYPE/ENTITY foi recusado por segurança")
    try:
        raiz = _sem_namespace(ET.fromstring(conteudo))
    except ET.ParseError as erro:
        raise XMLInvalido(f"XML mal formado ({erro})") from None

    inf = None
    for tag in RAIZES:
        inf = raiz if raiz.tag == tag else raiz.find(f".//{tag}")
        if inf is not None:
            break
    if inf is None:
        raise XMLInvalido("não é um documento fiscal suportado (NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e ou NFS-e)")
    if inf.tag in ("infNFSe", "infDPS"):
        return _nfse(raiz, origem)

    sigla, modelo_padrao, caminho_numero = RAIZES[inf.tag]
    ide = inf.find("ide")
    modelo_txt = _texto(ide, "mod")
    modelo = int(modelo_txt) if modelo_txt and modelo_txt.isdigit() else modelo_padrao
    chave = (inf.get("Id") or "")[-44:] or None
    if not chave:
        for tag in ("chNFe", "chCTe", "chBPe", "chNF3e"):
            prot = raiz.find(f".//{tag}")
            if prot is not None and prot.text:
                chave = prot.text.strip()
                break

    itens: list[Item] = []
    totais = Totais(presente=False)
    por_item = True
    if inf.tag == "infNFe":
        for det in inf.findall("det"):
            itens.append(_grupo_dfe(det.find("imposto/IBSCBS"), det.get("nItem") or "?", _texto(det, "prod/xProd") or "", _texto(det, "prod/NCM")))
        totais = _totais(inf.find("total/IBSCBSTot"))
    elif inf.tag == "infNF3e":
        for det in inf.findall("NFdet/det"):
            for di in det.findall("detItem"):
                numero = det.get("nItem") or di.get("nItem") or "?"
                itens.append(_grupo_dfe(di.find("imposto/IBSCBS"), numero, _texto(di, "prod/xProd") or "", None))
        totais = _totais(inf.find("total/IBSCBSTot"))
    else:  # CT-e, CT-e OS, BP-e: um grupo para o documento todo
        itens.append(_grupo_dfe(inf.find("imp/IBSCBS"), "1", "", None))
        por_item = False

    return Nota(
        origem=origem,
        chave=chave,
        modelo=modelo,
        tipo=SIGLAS.get(modelo, sigla),
        numero=_texto(inf, caminho_numero),
        serie=_texto(ide, "serie"),
        emissao=_data(_texto(ide, "dhEmi") or _texto(ide, "dEmi")),
        crt=_texto(inf, "emit/CRT"),
        cnpj_emitente=_texto(inf, "emit/CNPJ"),
        itens=itens,
        totais=totais,
        redutor_compra_gov=_decimal(ide, "gCompraGov/pRedutor"),
        por_item=por_item,
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

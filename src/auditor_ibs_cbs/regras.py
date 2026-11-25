"""Regras de auditoria do IBS/CBS em documentos fiscais eletrônicos.

Gravidades:
- ``erro``: o documento contradiz a tabela oficial ou uma regra de validação em produção (tende a ser
  rejeitado ou fica errado perante o fisco);
- ``atencao``: algo não bate e merece conferência, ou a regra oficial ainda é "implementação futura";
- ``info``: observação, não indica problema.

Para NF-e e NFC-e, cada achado ligado a uma regra da NT 2025.002-RTC traz o código de rejeição, a regra,
a página e se a regra já vale em produção (veja ``nt.py``). As fórmulas e tolerâncias são as da NT:
valores do item com tolerância de R$ 0,01; totais iguais à soma dos itens, sem tolerância; alíquota
efetiva com 4 casas e arredondamento na última casa.
As mensagens não substituem a validação da SEFAZ nem orientação contábil.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from . import nt
from .leitor import Campo, Item, Nota, Tributo
from .tabelas import EXIGEM_NCM_SEMPRE, Tabelas

TOLERANCIA = Decimal("0.01")
TOLERANCIA_COMPRA_GOV = Decimal("0.04")
CENTAVO = Decimal("0.01")
DEZ_MILESIMO = Decimal("0.0001")
ZERO = Decimal(0)
INICIO_REFORMA = date(2026, 1, 1)
MODELOS_SUPORTADOS = {55, 65, 57, 67, 63, 66, 91}
NCM_ZERO = {"00", "00000000"}
TRIBUTOS = (("IBSUF", "IBS estadual"), ("IBSMun", "IBS municipal"), ("CBS", "CBS"))

# grupo do IBSCBS -> (cStat se exigido e ausente, cStat se indevido) na NF-e/NFC-e
GRUPOS_POR_INDICADOR = {
    "gIBSCBS": ("1022", "1021"),
    "gIBSCBSMono": ("1116", "1151"),
    "gTransfCred": ("1132", "1131"),
    "gCredPresIBSZFM": ("1135", None),
    "gAjusteCompet": ("1170", None),
}

# Formatos do leiaute (DFeTiposBasicos_v1.00.xsd)
FORMATOS_DFE = (
    (("CST", "CSTReg"), re.compile(r"\d{3}"), "3 dígitos"),
    (("cClassTrib", "cClassTribReg"), re.compile(r"\d{6}"), "6 dígitos"),
    (("cCredPres",), re.compile(r"\d{2}"), "2 dígitos"),
    (("q",), re.compile(r"0|0\.[0-9]{4}|[1-9][0-9]{0,10}(\.[0-9]{4})?"), "número com 4 casas decimais"),
    (("p", "adRem"), re.compile(r"0|0\.[0-9]{2,4}|[1-9][0-9]{0,2}(\.[0-9]{2,4})?"), "percentual com 2 a 4 casas decimais (ex.: 0.90)"),
    (("v",), re.compile(r"0|0\.[0-9]{2}|[1-9][0-9]{0,12}(\.[0-9]{2})?"), "valor com 2 casas decimais (ex.: 10.50)"),
)
FORMATOS_NFSE = (
    (("CST", "CSTReg"), re.compile(r"\d{3}"), "3 dígitos"),
    (("cClassTrib", "cClassTribReg"), re.compile(r"\d{6}"), "6 dígitos"),
    (("v",), re.compile(r"0|0\.[0-9]{2}|[1-9][0-9]{0,14}(\.[0-9]{2})?"), "valor com 2 casas decimais (ex.: 10.50)"),
)


@dataclass
class Achado:
    codigo: str
    gravidade: str  # erro | atencao | info
    titulo: str
    explicacao: str
    como_corrigir: str
    item: str | None = None
    campo: str | None = None
    rejeicao: str | None = None  # cStat da SEFAZ (NF-e/NFC-e)
    regra_nt: str | None = None
    pagina_nt: int | None = None
    em_producao: bool | None = None

    def como_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Resultado:
    origem: str
    chave: str | None = None
    modelo: int | None = None
    tipo: str | None = None
    numero: str | None = None
    serie: str | None = None
    emissao: str | None = None
    emitente: str | None = None
    itens: int = 0
    achados: list[Achado] = field(default_factory=list)
    linhas: list[dict] = field(default_factory=list)  # um resumo por item, para os relatórios consolidados

    @property
    def situacao(self) -> str:
        gravidades = {a.gravidade for a in self.achados}
        if "erro" in gravidades:
            return "erro"
        if "atencao" in gravidades:
            return "atencao"
        return "ok"

    def como_dict(self) -> dict:
        return {
            "origem": self.origem,
            "chave": self.chave,
            "modelo": self.modelo,
            "tipo": self.tipo,
            "numero": self.numero,
            "serie": self.serie,
            "emissao": self.emissao,
            "emitente": self.emitente,
            "itens": self.itens,
            "situacao": self.situacao,
            "achados": [a.como_dict() for a in self.achados],
        }


# ----------------------------------------------------------------------------- utilidades


def _brl(valor: Decimal | None) -> str:
    if valor is None:
        return "?"
    texto = f"{valor:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(valor: Decimal | float | None) -> str:
    if valor is None:
        return "?"
    texto = f"{Decimal(str(valor)).normalize():f}"
    return texto.replace(".", ",") + "%"


def arredondar(valor: Decimal, casas: Decimal = CENTAVO) -> Decimal:
    """Arredondamento bancário (HALF_EVEN), o mesmo modo da calculadora oficial."""
    return valor.quantize(casas, rounding=ROUND_HALF_EVEN)


def _dec(v) -> Decimal | None:
    if v is None or isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _data_br(dia: date) -> str:
    return f"{dia:%d/%m/%Y}"


def _resumir(texto: str, limite: int = 80) -> str:
    """Descrição de NCM legível: sem tags, sem os traços de hierarquia e cortada em palavra inteira."""
    texto = re.sub(r"<[^>]*>", "", texto).lstrip("- ").strip()
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0].rstrip(",;:") + "…"


class _Coletor:
    """Junta os achados e liga cada um à regra da NT quando o documento é NF-e/NFC-e."""

    def __init__(self, nota: Nota):
        self.nfe = nota.modelo in (55, 65)
        self.lista: list[Achado] = []

    def add(self, codigo, gravidade, titulo, explicacao, corrigir, item=None, campo=None, cstat: str | None = None) -> None:
        a = Achado(codigo, gravidade, titulo, explicacao, corrigir, item=item, campo=campo)
        ref = nt.referencia(cstat) if (cstat and self.nfe) else None
        if ref:
            a.rejeicao, a.regra_nt, a.pagina_nt, a.em_producao = ref["rejeicao"], ref["regra_nt"], ref["pagina_nt"], ref["em_producao"]
            if not a.em_producao and a.gravidade == "erro":
                a.gravidade = "atencao"  # a SEFAZ ainda não rejeita em produção: vira aviso antecipado
        self.lista.append(a)


# ----------------------------------------------------------------------------- auditoria


def auditar(nota: Nota, tabelas: Tabelas) -> Resultado:
    r = Resultado(
        origem=nota.origem,
        chave=nota.chave,
        modelo=nota.modelo,
        tipo=nota.tipo,
        numero=nota.numero,
        serie=nota.serie,
        emissao=nota.emissao.isoformat() if nota.emissao else None,
        emitente=nota.cnpj_emitente,
        itens=len(nota.itens),
    )
    c = _Coletor(nota)
    if nota.modelo not in MODELOS_SUPORTADOS:
        c.add(
            "AIC-002", "info", "Documento fora do escopo", f"O modelo {nota.modelo} não é um documento suportado; o arquivo não foi auditado.", "Nada a fazer."
        )
    elif nota.emissao is None:
        c.add(
            "AIC-003",
            "erro",
            "Data de emissão ausente",
            "Sem a data de emissão (dhEmi) não dá para saber quais tabelas valiam no dia.",
            "Confira se o arquivo é o XML completo do documento.",
            campo="dhEmi",
        )
    elif nota.emissao < INICIO_REFORMA:
        c.add(
            "AIC-004",
            "info",
            "Documento anterior à reforma",
            "O documento foi emitido antes de 01/01/2026, quando o grupo IBS/CBS ainda não existia.",
            "Nada a fazer.",
        )
    else:
        _auditar_cabecalho(nota, c)
        for item in nota.itens:
            _auditar_item(item, nota, tabelas, c)
            r.linhas.append(
                {
                    "item": item.numero,
                    "cst": item.cst,
                    "cclasstrib": item.cclasstrib,
                    "ncm": item.ncm,
                    "nbs": item.nbs,
                    "base": item.base,
                    "ibs": item.valor_ibs,
                    "cbs": item.cbs.valor if item.cbs else None,
                }
            )
        if nota.por_item:
            _auditar_totais(nota, c)
    r.achados = c.lista
    return r


def _ref_item(nota: Nota, item: Item) -> str | None:
    return item.numero if nota.por_item else None


def _auditar_cabecalho(nota: Nota, c: _Coletor) -> None:
    if nota.modelo == 65 and nota.tem_compra_gov:
        c.add(
            "AIC-044",
            "erro",
            "NFC-e com compra governamental",
            "A NFC-e não pode ter o grupo de compras governamentais (gCompraGov).",
            "Use NF-e (modelo 55) para compras governamentais.",
            campo="ide/gCompraGov",
            cstat="1006",
        )


def _auditar_item(item: Item, nota: Nota, t: Tabelas, c: _Coletor) -> None:
    dia = nota.emissao
    n = _ref_item(nota, item)
    nfe = nota.modelo in (55, 65)
    nfse = nota.modelo == 91

    if not item.tem_grupo:
        onde = "O item não tem" if nota.por_item else "O documento não tem"
        excecao = None
        if nfe and nota.fin_nfe in ("2", "4"):
            excecao = "Notas de devolução ou complementares que referenciam notas anteriores a 2027 são exceção a essa regra."
        elif nfe and item.cprod_anp:
            excecao = "Combustíveis da tabela de tributação monofásica são exceção a essa regra; confira se o produto está nela."
        if excecao:
            c.add(
                "AIC-010",
                "info",
                "Grupo IBS/CBS não informado",
                f"{onde} o grupo IBSCBS. {excecao}",
                "Nada a fazer, se o caso se encaixa na exceção.",
                item=n,
                campo="IBSCBS",
            )
        elif nota.crt == "3":
            c.add(
                "AIC-010",
                "erro" if nfe else "atencao",
                "Grupo IBS/CBS não informado",
                f"{onde} o grupo IBSCBS. Emitentes do regime normal (CRT 3) devem informar IBS e CBS.",
                "Configure no sistema emissor o CST e o cClassTrib para gerar o grupo IBSCBS.",
                item=n,
                campo="IBSCBS",
                cstat="1115",
            )
        else:
            regime = "Para o Simples Nacional e o MEI (CRT 1, 2 ou 4)" if nota.crt in ("1", "2", "4") else "Para este emitente"
            c.add(
                "AIC-010",
                "info",
                "Grupo IBS/CBS não informado",
                f"{onde} o grupo IBSCBS. {regime}, a obrigatoriedade segue um cronograma próprio da NT 2025.002.",
                "Confira na versão vigente da nota técnica a partir de quando o seu regime precisa informar.",
                item=n,
                campo="IBSCBS",
            )
        if nfe and item.ncm:
            _conferir_ncm_existe(item, t, dia, n, c)
        return

    _conferir_formatos(item.campos, nfse, n, c)
    for campo in item.faltando:
        c.add(
            "AIC-051",
            "erro",
            "Campo obrigatório ausente",
            f"O campo {campo} é obrigatório no grupo IBS/CBS e não foi informado.",
            "Gere o grupo completo; o leiaute da NT 2025.002 lista os campos obrigatórios.",
            item=n,
            campo=campo,
        )

    cst = t.cst(item.cst or "")
    _conferir_codigos(item.cst, item.cclasstrib, nota, t, n, "", c)
    cl = t.cclasstrib(item.cclasstrib or "")

    if nfe:
        _conferir_ncm(item, cl, t, dia, n, c)
        _conferir_debito_credito(item, nota, n, c)
    if nfse and cl:
        _conferir_nbs(item, t, dia, c)

    # grupos exigidos ou vedados pelo CST
    if cst is not None and not nfse:
        grupos = GRUPOS_POR_INDICADOR if nfe else {"gIBSCBS": (None, None)}
        for grupo, (cod_ausente, cod_indevido) in grupos.items():
            exigido = cst["grupos"].get(grupo, False)
            presente = grupo in item.grupos
            if exigido and not presente and not (grupo == "gIBSCBS" and nota.tp_nf_debito == "07"):
                c.add(
                    "AIC-020",
                    "erro",
                    f"Grupo {grupo} ausente",
                    f"O CST {item.cst} ({cst['descricao']}) exige o grupo {grupo}, que não foi informado.",
                    f"Gere o grupo {grupo} ou confira se o CST está certo.",
                    item=n,
                    campo=f"IBSCBS/{grupo}",
                    cstat=cod_ausente,
                )
            elif presente and not exigido:
                c.add(
                    "AIC-021",
                    "erro" if (nfe and cod_indevido) else "atencao",
                    f"Grupo {grupo} informado indevidamente",
                    f"O grupo {grupo} foi informado, mas o CST {item.cst} ({cst['descricao']}) não o permite.",
                    "Confira se o CST está certo para esta operação.",
                    item=n,
                    campo=f"IBSCBS/{grupo}",
                    cstat=cod_indevido,
                )

    if nfe and cl:
        _conferir_estorno(item, cl, nota, n, c)
    if "gIBSCBS" in item.grupos:
        _auditar_valores(item, nota, t, cst, n, c)
    _auditar_especiais(item, nota, t, n, c)


def _conferir_formatos(campos: list[Campo], nfse: bool, n: str | None, c: _Coletor) -> None:
    formatos = FORMATOS_NFSE if nfse else FORMATOS_DFE
    total = 0
    for campo in campos:
        for prefixos, regex, descricao in formatos:
            exato = prefixos[0][0].isupper() or prefixos[0].startswith("c")
            casa = campo.nome in prefixos if exato else campo.nome.startswith(prefixos)
            if not casa:
                continue
            if not regex.fullmatch(campo.valor):
                c.add(
                    "AIC-050",
                    "erro",
                    f"Formato inválido em {campo.nome}",
                    f"O campo {campo.nome} tem o valor '{campo.valor[:30]}', mas o leiaute exige {descricao}.",
                    "Corrija a formatação no sistema emissor (ponto como separador decimal, sem separador de milhar).",
                    item=n,
                    campo=f"{campo.caminho}/{campo.nome}",
                )
                total += 1
            break
        if total >= 5:
            break


def _conferir_codigos(cst_cod, cl_cod, nota: Nota, t: Tabelas, n, sufixo: str, c: _Coletor) -> None:
    """CST e cClassTrib (sufixo 'Reg' para o grupo de tributação regular)."""
    dia = nota.emissao
    doc = t.nome_documento(nota.modelo)
    reg = bool(sufixo)
    rotulo = " da tributação regular" if reg else ""
    cst = t.cst(cst_cod or "")
    if cst is None:
        c.add(
            "AIC-011",
            "erro",
            f"CST{rotulo} inexistente",
            f"O CST '{cst_cod}' não existe na tabela oficial ({t.versao}).",
            "Use um dos CSTs da tabela oficial; o comando 'consultar' lista os códigos.",
            item=n,
            campo=f"CST{sufixo}",
            cstat="1066" if reg else "1020",
        )
    elif not t.vigente(cst, dia):
        c.add(
            "AIC-012",
            "erro",
            f"CST{rotulo} fora da vigência",
            f"O CST {cst_cod} não valia em {_data_br(dia)} (vigência {cst['inicio']} a {cst['fim'] or 'atual'}).",
            "Use um CST vigente na data de emissão.",
            item=n,
            campo=f"CST{sufixo}",
        )
    cl = t.cclasstrib(cl_cod or "")
    if cl is None:
        c.add(
            "AIC-013",
            "erro",
            f"cClassTrib{rotulo} inexistente",
            f"O código de classificação tributária '{cl_cod}' não existe na tabela oficial ({t.versao}).",
            "Corrija o cClassTrib; use 'consultar' para ver os códigos de cada CST.",
            item=n,
            campo=f"cClassTrib{sufixo}",
            cstat="1067" if reg else "1023",
        )
        return
    if not t.vigente(cl, dia):
        c.add(
            "AIC-014",
            "erro",
            f"cClassTrib{rotulo} fora da vigência",
            f"O cClassTrib {cl_cod} não valia em {_data_br(dia)} (vigência {cl['inicio']} a {cl['fim'] or 'atual'}).",
            "Troque pelo código que substituiu este na tabela vigente.",
            item=n,
            campo=f"cClassTrib{sufixo}",
        )
    if cst_cod and cl["cst"] != cst_cod:
        c.add(
            "AIC-015",
            "atencao" if reg else "erro",
            f"cClassTrib{rotulo} não pertence ao CST",
            f"O cClassTrib {cl_cod} ({cl['descricao']}) é do CST {cl['cst']}, mas foi informado o CST {cst_cod}.",
            f"Use o CST {cl['cst']} ou escolha um cClassTrib do CST {cst_cod}.",
            item=n,
            campo=f"CST{sufixo}",
            cstat=None if reg else "1024",
        )
    if not reg and not t.permitido_no_modelo(cl_cod, nota.modelo, dia):
        c.add(
            "AIC-016",
            "erro",
            f"cClassTrib não permitido em {doc}",
            f"Pela tabela oficial, o cClassTrib {cl_cod} ({cl['descricao']}) não pode ser usado em {doc} na data de emissão.",
            f"Escolha um cClassTrib previsto para {doc}.",
            item=n,
            campo="cClassTrib",
            cstat="1025",
        )


def _conferir_debito_credito(item: Item, nota: Nota, n, c: _Coletor) -> None:
    """UB14-60, UB14-70 e UB14-80: cClassTrib x tipo de nota de débito/crédito (só NF-e)."""
    if nota.modelo != 55 or not item.cclasstrib:
        return
    cod = item.cclasstrib
    deb, cred = nota.tp_nf_debito, nota.tp_nf_credito
    if cod in nt.CCLASS_DEBITO_CREDITO:
        aceita_deb, aceita_cred = nt.CCLASS_DEBITO_CREDITO[cod]
        if not ((deb and deb in aceita_deb) or (cred and cred in aceita_cred)):
            exige = " ou ".join([f"nota de débito tipo {d}" for d in sorted(aceita_deb)] + [f"nota de crédito tipo {x}" for x in sorted(aceita_cred)])
            c.add(
                "AIC-046",
                "erro",
                "cClassTrib incompatível com o tipo da nota",
                f"O cClassTrib {cod} só pode ser usado em {exige}.",
                "Confira a finalidade da nota e o tipo de nota de débito ou crédito.",
                item=n,
                campo="ide/tpNFDebito",
                cstat="1202",
            )
    if deb in nt.DEBITO_EXIGE and cod != nt.DEBITO_EXIGE[deb]:
        c.add(
            "AIC-046",
            "erro",
            "cClassTrib incompatível com a nota de débito",
            f"Na nota de débito tipo {deb}, os itens devem usar o cClassTrib {nt.DEBITO_EXIGE[deb]}, mas este usa {cod}.",
            "Ajuste o cClassTrib ou o tipo da nota de débito.",
            item=n,
            campo="IBSCBS/cClassTrib",
            cstat="1200",
        )
    if cred in nt.CREDITO_EXIGE and cod != nt.CREDITO_EXIGE[cred]:
        c.add(
            "AIC-046",
            "erro",
            "cClassTrib incompatível com a nota de crédito",
            f"Na nota de crédito tipo {cred}, os itens devem usar o cClassTrib {nt.CREDITO_EXIGE[cred]}, mas este usa {cod}.",
            "Ajuste o cClassTrib ou o tipo da nota de crédito.",
            item=n,
            campo="IBSCBS/cClassTrib",
            cstat="1201",
        )


def _conferir_estorno(item: Item, cl: dict, nota: Nota, n, c: _Coletor) -> None:
    """UB116-10/20: grupo de estorno de crédito conforme o indicador do cClassTrib."""
    exige = cl.get("indicadores", {}).get("gEstornoCred", False) or nota.tp_nf_debito == "07"
    presente = "gEstornoCred" in item.grupos
    if presente and not exige:
        c.add(
            "AIC-047",
            "erro",
            "Grupo de estorno de crédito informado indevidamente",
            f"O cClassTrib {item.cclasstrib} não permite o grupo gEstornoCred.",
            "Retire o grupo gEstornoCred ou confira o cClassTrib.",
            item=n,
            campo="IBSCBS/gEstornoCred",
            cstat="1172",
        )
    elif exige and not presente:
        c.add(
            "AIC-047",
            "erro",
            "Grupo de estorno de crédito não informado",
            f"O cClassTrib {item.cclasstrib} (ou a nota de débito por perda em estoque) exige o grupo gEstornoCred.",
            "Gere o grupo gEstornoCred com os valores estornados.",
            item=n,
            campo="IBSCBS/gEstornoCred",
            cstat="1173",
        )


def _conferir_ncm_existe(item: Item, t: Tabelas, dia: date, n, c: _Coletor) -> None:
    ncm = item.ncm or ""
    if len(ncm) != 8 or ncm in NCM_ZERO:
        return
    registro = t.ncm(ncm)
    if registro is None or not (registro[1] <= dia.isoformat() <= registro[2]):
        motivo = "não existe na tabela NCM" if registro is None else f"não estava vigente em {_data_br(dia)}"
        c.add(
            "AIC-019",
            "atencao",
            "NCM inexistente ou fora da vigência",
            f"O NCM {ncm} {motivo}.",
            "Confira a classificação fiscal do produto na tabela NCM vigente.",
            item=n,
            campo="prod/NCM",
        )


def _conferir_ncm(item: Item, cl: dict | None, t: Tabelas, dia: date, n, c: _Coletor) -> None:
    _conferir_ncm_existe(item, t, dia, n, c)
    if cl is None:
        return
    codigo = item.cclasstrib
    tem_lista = t.tem_lista(codigo, "ncm", dia)
    if not tem_lista and codigo not in EXIGEM_NCM_SEMPRE:
        return
    ncm = item.ncm or ""
    anexos = t.anexos_do_cclasstrib(codigo, "ncm", dia)
    onde = f" ({', '.join(anexos[:3])}{'…' if len(anexos) > 3 else ''} da LC 214/2025)" if anexos else ""
    if len(ncm) != 8 or ncm in NCM_ZERO:
        c.add(
            "AIC-017",
            "erro",
            "NCM obrigatório para este cClassTrib",
            f"O cClassTrib {codigo} ({cl['descricao']}) exige o NCM completo de 8 dígitos do produto, mas o item informa '{ncm or 'nada'}'.",
            "Informe o NCM correto do produto no cadastro.",
            item=n,
            campo="prod/NCM",
        )
    elif tem_lista and not t.aplicavel(codigo, "ncm", ncm, dia):
        descricao = t.ncm(ncm)
        produto = f" ({_resumir(descricao[0])})" if descricao else ""
        possiveis = [x for x in t.dados["cclasstrib"] if x != codigo and t.tem_lista(x, "ncm", dia) and t.aplicavel(x, "ncm", ncm, dia)]
        dica = (
            f" Para este NCM, os cClassTrib com lista que se aplicam são: {', '.join(possiveis[:5])}."
            if possiveis
            else " Nenhum cClassTrib com lista se aplica a este NCM; use o da tributação comum (ex.: 000001)."
        )
        c.add(
            "AIC-018",
            "erro",
            "NCM não pode usar este cClassTrib",
            f"O cClassTrib {codigo} ({cl['descricao']}) só vale para os produtos listados na lei{onde}. O NCM {ncm}{produto} não está nessa lista, então o tratamento (como a redução) não se aplica.",
            "Confira o NCM e o cClassTrib do produto." + dica,
            item=n,
            campo="IBSCBS/cClassTrib",
        )


def _conferir_nbs(item: Item, t: Tabelas, dia: date, c: _Coletor) -> None:
    codigo = item.cclasstrib
    if not t.tem_lista(codigo, "nbs", dia):
        return
    cl = t.cclasstrib(codigo)
    nbs = item.nbs or ""
    if len(nbs) != 9:
        c.add(
            "AIC-024",
            "erro",
            "NBS obrigatório para este cClassTrib",
            f"O cClassTrib {codigo} ({cl['descricao']}) exige o código NBS completo (9 dígitos) do serviço, mas a NFS-e informa '{nbs or 'nada'}'.",
            "Informe o NBS do serviço (cServ/cNBS).",
            campo="serv/cServ/cNBS",
        )
    elif not t.aplicavel(codigo, "nbs", nbs, dia):
        c.add(
            "AIC-025",
            "erro",
            "NBS não pode usar este cClassTrib",
            f"O cClassTrib {codigo} ({cl['descricao']}) só vale para os serviços listados na lei. O NBS {nbs} não está nessa lista.",
            "Confira o NBS e o cClassTrib do serviço.",
            campo="IBSCBS/cClassTrib",
        )


# ----------------------------------------------------------------------------- valores


def _auditar_valores(item: Item, nota: Nota, t: Tabelas, cst: dict | None, n, c: _Coletor) -> None:
    dia = nota.emissao
    nfe = nota.modelo in (55, 65)
    nfse = nota.modelo == 91
    preve_reducao = bool(cst and cst["grupos"].get("gRed"))
    preve_dif = bool(cst and cst["grupos"].get("gDif"))
    blocos = (("IBSUF", "IBS estadual", item.ibs_uf), ("IBSMun", "IBS municipal", item.ibs_mun), ("CBS", "CBS", item.cbs))

    for sigla, nome, trib in blocos:
        if trib is None:
            continue
        # diferimento (UB22, UB40, UB59)
        if cst is not None and not nfse:
            if trib.tem_diferimento and not preve_dif:
                c.add(
                    "AIC-026",
                    "erro",
                    f"Diferimento não permitido ({nome})",
                    f"Foi informado diferimento (gDif) no {nome}, mas o CST {item.cst} ({cst['descricao']}) não permite.",
                    "Retire o gDif ou use um CST com diferimento (ex.: 510, 515).",
                    item=n,
                    campo=f"g{sigla}/gDif",
                    cstat=nt.POR_TRIBUTO["dif_indevido"][sigla],
                )
            elif preve_dif and not trib.tem_diferimento:
                c.add(
                    "AIC-026",
                    "erro",
                    f"Diferimento não informado ({nome})",
                    f"O CST {item.cst} ({cst['descricao']}) exige o grupo de diferimento (gDif) no {nome}.",
                    "Gere o grupo gDif com o percentual diferido ou confira o CST.",
                    item=n,
                    campo=f"g{sigla}/gDif",
                    cstat=nt.POR_TRIBUTO["dif_ausente"][sigla],
                )
        # devolução de tributos (UB24, UB43, UB62, UB62a, UB63)
        if nfe and trib.tem_devolucao:
            if sigla == "IBSUF":
                c.add(
                    "AIC-028",
                    "erro",
                    "Devolução do IBS estadual informada indevidamente",
                    "O grupo gDevTrib não pode ser informado no IBS estadual.",
                    "Retire o grupo gDevTrib do IBS estadual.",
                    item=n,
                    campo="gIBSUF/gDevTrib",
                    cstat="1111",
                )
            elif sigla == "IBSMun":
                c.add(
                    "AIC-028",
                    "erro",
                    "Devolução do IBS municipal informada indevidamente",
                    "O grupo gDevTrib não pode ser informado no IBS municipal.",
                    "Retire o grupo gDevTrib do IBS municipal.",
                    item=n,
                    campo="gIBSMun/gDevTrib",
                    cstat="1112",
                )
            elif nota.modelo == 65:
                c.add(
                    "AIC-028",
                    "erro",
                    "Devolução da CBS informada indevidamente",
                    "A NFC-e não pode ter o grupo de devolução da CBS (gDevTrib).",
                    "Retire o grupo gDevTrib da CBS.",
                    item=n,
                    campo="gCBS/gDevTrib",
                    cstat="1187",
                )
            elif trib.p_dev is None:
                c.add(
                    "AIC-028",
                    "erro",
                    "Percentual de devolução da CBS não informado",
                    "O grupo de devolução da CBS exige o percentual devolvido (pDevTrib).",
                    "Informe o pDevTrib.",
                    item=n,
                    campo="gCBS/gDevTrib/pDevTrib",
                    cstat="1188",
                )
            else:
                aliq = trib.aliquota_efetiva if trib.aliquota_efetiva is not None else trib.aliquota
                if item.base is not None and aliq is not None and trib.v_dev is not None:
                    esperado = item.base * aliq / 100 * trib.p_dev / 100
                    if abs(esperado - trib.v_dev) > TOLERANCIA:
                        c.add(
                            "AIC-028",
                            "erro",
                            "Valor da CBS devolvida não confere",
                            f"Base R$ {_brl(item.base)} x {_pct(aliq)} x {_pct(trib.p_dev)} devolvido = R$ {_brl(arredondar(esperado))}, mas foi informado R$ {_brl(trib.v_dev)}.",
                            "O valor devolvido é base x alíquota x percentual devolvido.",
                            item=n,
                            campo="gCBS/gDevTrib/vDevTrib",
                            cstat="1189",
                        )
        # redução de alíquota (UB26/27, UB45/46, UB64/65)
        tem_red = trib.reducao is not None or trib.aliquota_efetiva is not None
        if cst is not None and not nfse:
            excecao_gov = nota.tem_compra_gov and (trib.reducao or ZERO) == 0
            if tem_red and not preve_reducao and not excecao_gov and (nfe or (trib.reducao or ZERO) != 0):
                c.add(
                    "AIC-022",
                    "erro" if nfe else "atencao",
                    f"Redução de alíquota não permitida ({nome})",
                    f"Foi informada redução (gRed) no {nome}, mas o CST {item.cst} não permite redução.",
                    "Retire o gRed ou use um CST com redução (ex.: 200). Em compra governamental, o gRed vai com pRedAliq igual a zero.",
                    item=n,
                    campo=f"g{sigla}/gRed",
                    cstat=nt.POR_TRIBUTO["red_indevido"][sigla],
                )
            if nfe and not tem_red and (preve_reducao or nota.tem_compra_gov):
                motivo = "o CST exige redução" if preve_reducao else "a nota é de compra governamental"
                c.add(
                    "AIC-027",
                    "erro",
                    f"Grupo de redução não informado ({nome})",
                    f"O grupo gRed do {nome} é obrigatório porque {motivo}.",
                    "Gere o grupo gRed com o percentual de redução e a alíquota efetiva.",
                    item=n,
                    campo=f"g{sigla}/gRed",
                    cstat=nt.POR_TRIBUTO["red_ausente"][sigla],
                )
        oficial = t.reducao(item.cclasstrib or "", sigla, dia) if item.cclasstrib else None
        if trib.reducao is not None and oficial is not None and preve_reducao and Decimal(str(oficial)) != trib.reducao:
            c.add(
                "AIC-023",
                "erro" if nfe else "atencao",
                f"Percentual de redução diferente do oficial ({nome})",
                f"Foi informada redução de {_pct(trib.reducao)}, mas a tabela oficial do cClassTrib {item.cclasstrib} prevê {_pct(oficial)}.",
                "Use o percentual de redução oficial do cClassTrib.",
                item=n,
                campo=f"g{sigla}/gRed/pRedAliq",
                cstat=nt.POR_TRIBUTO["p_red"][sigla],
            )
        elif nfe and trib.reducao is not None and not preve_reducao and nota.tem_compra_gov and trib.reducao != 0:
            c.add(
                "AIC-023",
                "erro",
                f"Percentual de redução não permitido ({nome})",
                f"O CST {item.cst} não permite redução; em compra governamental o pRedAliq deve ser zero, mas foi informado {_pct(trib.reducao)}.",
                "Informe pRedAliq igual a zero.",
                item=n,
                campo=f"g{sigla}/gRed/pRedAliq",
                cstat=nt.POR_TRIBUTO["p_red"][sigla],
            )
        _conferir_aliquota_efetiva(trib, sigla, nome, nota, n, c)
        _conferir_valor(item, trib, sigla, nome, nota, n, c)

    # vIBS (UB54a-10)
    if item.valor_ibs is not None and item.ibs_uf and item.ibs_mun and None not in (item.ibs_uf.valor, item.ibs_mun.valor):
        soma = item.ibs_uf.valor + item.ibs_mun.valor
        cred = _dec(item.especiais.get("gCredPresOper", {}).get("gIBSCredPres/vCredPres"))
        aceitos = [soma] + ([soma - cred] if cred is not None else [])
        if all(abs(v - item.valor_ibs) > TOLERANCIA for v in aceitos):
            c.add(
                "AIC-031",
                "erro",
                "IBS total diferente da soma",
                f"O IBS total é R$ {_brl(item.valor_ibs)}, mas IBS estadual + municipal dá R$ {_brl(soma)}.",
                "O vIBS deve ser vIBSUF + vIBSMun (menos o crédito presumido, quando o código manda deduzir).",
                item=n,
                campo="vIBS",
                cstat="1150",
            )

    _conferir_aliquotas(item, nota, t, n, c)
    if nfe and item.composicao is not None and item.base is not None:
        _conferir_base(item, n, c)


def _conferir_aliquotas(item: Item, nota: Nota, t: Tabelas, n, c: _Coletor) -> None:
    dia = nota.emissao
    nfe = nota.modelo in (55, 65)
    blocos = (("CBS", "CBS", item.cbs), ("IBSUF", "IBS estadual", item.ibs_uf), ("IBSMun", "IBS municipal", item.ibs_mun))
    if nfe:
        # UB18-10, UB37-10, UB56-10: alíquotas fixadas na lei para 2025 a 2028
        lei = nt.ALIQUOTAS_LEI.get(dia.year, {})
        regular = "gTribRegular" in item.especiais
        for sigla, nome, trib in blocos:
            if trib is None or trib.aliquota is None or sigla not in lei:
                continue
            if nota.fin_nfe == "4" or nota.tp_nf_credito in ("03", "04", "06"):
                continue
            if sigla == "CBS" and trib.tem_alczfm:
                continue
            esperado = ZERO if regular else Decimal(lei[sigla])
            if trib.aliquota != esperado:
                motivo = "com tributação regular informada, ela deve ser zero" if regular else f"a lei fixa {_pct(esperado)} para {dia.year}"
                c.add(
                    "AIC-032",
                    "erro",
                    f"Alíquota do {nome} inválida",
                    f"Foi informada alíquota de {_pct(trib.aliquota)}, mas {motivo}.",
                    "Corrija a alíquota no sistema emissor (as reduções vão no grupo gRed, não na alíquota).",
                    item=n,
                    campo=f"p{sigla}",
                    cstat=nt.POR_TRIBUTO["aliquota"][sigla],
                )
        return
    cl = t.cclasstrib(item.cclasstrib or "")
    for sigla, nome, trib in blocos:
        if trib is None or trib.aliquota is None or trib.reducao is not None or nota.redutor_compra_gov is not None:
            continue
        ref = t.aliquota_referencia(sigla, dia)
        if ref is not None and cl and cl.get("tipo_aliquota") == "Padrão" and trib.aliquota != Decimal(str(ref)):
            c.add(
                "AIC-032",
                "info",
                f"Alíquota diferente da referência ({nome})",
                f"A alíquota informada é {_pct(trib.aliquota)}; a de referência para {dia.year} é {_pct(ref)}.",
                "Se não houver motivo específico (regime, benefício), confira a alíquota configurada.",
                item=n,
                campo=f"p{sigla}",
            )


def _conferir_base(item: Item, n, c: _Coletor) -> None:
    """UB16-10 (implementação futura): base do IBS/CBS a partir dos valores do item."""
    v = item.composicao
    soma = v["vProd"] + v["vFrete"] + v["vSeg"] + v["vOutro"] + v["vII"] + v["vIS"]
    soma -= v["vDesc"] + v["vPIS"] + v["vCOFINS"] + v["vICMS"] + v["vICMSUFDest"] + v["vFCP"] + v["vFCPUFDest"] + v["vICMSMono"] + v["vISSQN"]
    if abs(soma - item.base) > TOLERANCIA:
        c.add(
            "AIC-029",
            "erro",
            "Base de cálculo diferente da composição prevista",
            f"A base do IBS/CBS é R$ {_brl(item.base)}, mas a composição da NT (produto + frete + seguro + outras + II + IS "
            f"- desconto - PIS - COFINS - ICMS - FCP - ICMS monofásico - ISSQN) dá R$ {_brl(soma)}. A SEFAZ ainda não rejeita por isso, "
            "mas a regra já está publicada.",
            "Confira se o sistema monta a base como a NT descreve; vale corrigir antes de a regra entrar em produção.",
            item=n,
            campo="gIBSCBS/vBC",
            cstat="1104",
        )


def _aliquota_publicada(trib: Tributo, nota: Nota) -> Decimal | None:
    """A alíquota que multiplica a base: a efetiva, quando houver o grupo de redução."""
    if trib.aliquota_efetiva is not None:
        return trib.aliquota_efetiva
    if nota.redutor_compra_gov is not None:
        return None  # sem a alíquota efetiva não dá para conferir sem risco de alarme falso
    return trib.aliquota


def _conferir_aliquota_efetiva(trib: Tributo, sigla: str, nome: str, nota: Nota, n, c: _Coletor) -> None:
    if trib.aliquota is None or trib.aliquota_efetiva is None:
        return
    reducao = trib.reducao or ZERO
    redutor = nota.redutor_compra_gov or ZERO
    exata = trib.aliquota * (1 - reducao / 100) * (1 - redutor / 100)
    nfse = nota.modelo == 91
    esperada = arredondar(exata, CENTAVO if nfse else DEZ_MILESIMO)
    tolerancia = CENTAVO if nfse else ZERO
    if abs(esperada - trib.aliquota_efetiva) > tolerancia:
        c.add(
            "AIC-033",
            "erro" if nota.modelo in (55, 65) else "atencao",
            f"Alíquota efetiva não confere ({nome})",
            f"Com alíquota {_pct(trib.aliquota)}, redução {_pct(reducao)}"
            + (f" e redutor de compra governamental {_pct(redutor)}" if redutor else "")
            + f", a alíquota efetiva seria {_pct(esperada)}, mas foi informada {_pct(trib.aliquota_efetiva)}.",
            "A alíquota efetiva é alíquota x (1 - redução) x (1 - redutor), com 4 casas decimais.",
            item=n,
            campo=f"pAliqEfet ({sigla})",
            cstat=nt.POR_TRIBUTO["aliq_efet"][sigla],
        )


def _conferir_valor(item: Item, trib: Tributo, sigla: str, nome: str, nota: Nota, n, c: _Coletor) -> None:
    """UB35/54/67: v = vBC x alíquota - vDif - vDevTrib (tolerância de R$ 0,01). UB23/42/61: vDif."""
    if item.base is None or trib.valor is None:
        return
    nfe = nota.modelo in (55, 65)
    if trib.tem_devolucao and not nfe:
        return
    aliquota = _aliquota_publicada(trib, nota)
    if aliquota is None:
        return
    bruto = item.base * aliquota / Decimal(100)
    if trib.tem_diferimento:
        if trib.p_dif is None:
            return
        v_dif = bruto * trib.p_dif / Decimal(100)
        if trib.v_dif is not None and abs(v_dif - trib.v_dif) > TOLERANCIA:
            c.add(
                "AIC-034",
                "erro" if nfe else "atencao",
                f"Valor diferido do {nome} não confere",
                f"Base R$ {_brl(item.base)} x {_pct(aliquota)} x {_pct(trib.p_dif)} diferido = R$ {_brl(arredondar(v_dif))}, mas foi informado R$ {_brl(trib.v_dif)}.",
                "O valor diferido é base x alíquota x percentual de diferimento.",
                item=n,
                campo=f"vDif ({sigla})",
                cstat=nt.POR_TRIBUTO["v_dif"][sigla],
            )
    deducoes = (trib.v_dif or ZERO if trib.tem_diferimento else ZERO) + (trib.v_dev or ZERO if trib.tem_devolucao else ZERO)
    devido = bruto - deducoes
    if abs(devido - trib.valor) > TOLERANCIA:
        conta = f"Base R$ {_brl(item.base)} x {_pct(aliquota)} = R$ {_brl(arredondar(bruto))}"
        if deducoes:
            conta += f", menos diferido/devolvido (R$ {_brl(deducoes)}), dá R$ {_brl(arredondar(devido))}"
        c.add(
            "AIC-030",
            "erro" if nfe else "atencao",
            f"Valor do {nome} não bate com base x alíquota",
            f"{conta}, mas foi informado R$ {_brl(trib.valor)}.",
            "Confira a base de cálculo e a alíquota; a calculadora oficial da Receita ajuda a conferir.",
            item=n,
            campo=f"v{sigla}",
            cstat=nt.POR_TRIBUTO["valor"][sigla],
        )


def _diferenca(esperado: Decimal, informado: Decimal | None, tolerancia: Decimal = TOLERANCIA) -> bool:
    return informado is not None and abs(esperado - informado) > tolerancia


def _auditar_especiais(item: Item, nota: Nota, t: Tabelas, n, c: _Coletor) -> None:
    esp = item.especiais
    nfe = nota.modelo in (55, 65)

    # crédito presumido
    cred = esp.get("gCredPresOper")
    if cred:
        if nota.modelo == 65:
            c.add(
                "AIC-045",
                "erro",
                "Crédito presumido não permitido na NFC-e",
                "A NFC-e não pode ter o grupo de crédito presumido da operação (gCredPresOper).",
                "Retire o grupo gCredPresOper.",
                item=n,
                campo="IBSCBS/gCredPresOper",
                cstat="1049",
            )
        base = _dec(cred.get("vBCCredPres"))
        for g, nome in (("gIBSCredPres", "IBS"), ("gCBSCredPres", "CBS")):
            p = _dec(cred.get(f"{g}/pCredPres"))
            v = _dec(cred.get(f"{g}/vCredPres", cred.get(f"{g}/vCredPresCondSus")))
            if base is not None and p is not None and v is not None and _diferenca(base * p / 100, v):
                c.add(
                    "AIC-035",
                    "atencao",
                    f"Crédito presumido de {nome} não confere",
                    f"Base R$ {_brl(base)} x {_pct(p)} = R$ {_brl(arredondar(base * p / 100))}, mas foi informado R$ {_brl(v)}.",
                    "O crédito presumido é a base do crédito x o percentual.",
                    item=n,
                    campo=f"gCredPresOper/{g}",
                )
    if "gCredPresIBSZFM" in item.grupos and nota.modelo == 65:
        c.add(
            "AIC-045",
            "erro",
            "Crédito presumido da ZFM não permitido na NFC-e",
            "A NFC-e não pode ter o grupo gCredPresIBSZFM.",
            "Retire o grupo gCredPresIBSZFM.",
            item=n,
            campo="IBSCBS/gCredPresIBSZFM",
            cstat="1138",
        )
    if nota.modelo == 55:
        if "gCredPresIBSZFM" in item.grupos and nota.tp_nf_credito != "02":
            c.add(
                "AIC-045",
                "erro",
                "Crédito presumido da ZFM fora da nota de crédito tipo 02",
                "O grupo gCredPresIBSZFM só cabe na nota de crédito tipo 02 (apropriação de crédito presumido de IBS na ZFM).",
                "Confira o tipo da nota de crédito.",
                item=n,
                campo="IBSCBS/gCredPresIBSZFM",
                cstat="1158",
            )
        elif "gCredPresIBSZFM" not in item.grupos and nota.tp_nf_credito == "02" and item.tem_grupo:
            c.add(
                "AIC-045",
                "erro",
                "Nota de crédito tipo 02 sem crédito presumido da ZFM",
                "A nota de crédito tipo 02 exige o grupo gCredPresIBSZFM.",
                "Gere o grupo gCredPresIBSZFM.",
                item=n,
                campo="IBSCBS/gCredPresIBSZFM",
                cstat="1159",
            )

    # transferência de crédito
    transf = esp.get("gTransfCred")
    if transf is not None and nota.modelo == 55:
        if nota.fin_nfe != "6":
            c.add(
                "AIC-048",
                "erro",
                "Transferência de crédito fora da nota de débito",
                "O grupo gTransfCred só pode ser usado em nota de débito (finNFe = 6).",
                "Confira a finalidade da nota.",
                item=n,
                campo="ide/finNFe",
                cstat="1133",
            )
        if (_dec(transf.get("vIBS")) or ZERO) <= 0 and (_dec(transf.get("vCBS")) or ZERO) <= 0:
            c.add(
                "AIC-048",
                "erro",
                "Transferência de crédito sem valor",
                "Na transferência de crédito, o valor do IBS ou da CBS deve ser maior que zero.",
                "Informe os valores transferidos.",
                item=n,
                campo="gTransfCred",
                cstat="1129",
            )

    # compra governamental (UB82a)
    gov = esp.get("gTribCompraGov")
    if nota.modelo == 55:
        if nota.tem_compra_gov and gov is None and "gIBSCBS" in item.grupos:
            c.add(
                "AIC-036",
                "erro",
                "Composição da compra governamental não informada",
                "A nota é de compra governamental, mas o item não tem o grupo gTribCompraGov.",
                "Gere o grupo gTribCompraGov com as alíquotas e valores sem o redutor.",
                item=n,
                campo="gIBSCBS/gTribCompraGov",
                cstat="1141",
            )
        elif gov is not None and not nota.tem_compra_gov:
            c.add(
                "AIC-036",
                "erro",
                "Composição da compra governamental informada indevidamente",
                "O item tem o grupo gTribCompraGov, mas a nota não é de compra governamental (sem gCompraGov).",
                "Retire o grupo gTribCompraGov ou informe o gCompraGov.",
                item=n,
                campo="gIBSCBS/gTribCompraGov",
                cstat="1144",
            )
    if gov and item.base is not None:
        trib_gov = sum((_dec(gov.get(f"vTrib{s}")) or ZERO) for s, _ in TRIBUTOS)
        trib_item = sum(((x.valor or ZERO) if x else ZERO) for x in (item.ibs_uf, item.ibs_mun, item.cbs))
        if nfe and abs(trib_gov - trib_item) > TOLERANCIA_COMPRA_GOV:
            c.add(
                "AIC-036",
                "erro",
                "Soma da compra governamental divergente",
                f"A soma de vTribIBSUF + vTribIBSMun + vTribCBS (R$ {_brl(trib_gov)}) difere de vIBSUF + vIBSMun + vCBS (R$ {_brl(trib_item)}) em mais de R$ 0,04.",
                "Os valores do gTribCompraGov devem somar o mesmo que os tributos do item.",
                item=n,
                campo="gTribCompraGov",
                cstat="1142",
            )
        for s, nome in TRIBUTOS:
            p, v = _dec(gov.get(f"pAliq{s}")), _dec(gov.get(f"vTrib{s}"))
            if p is not None and v is not None and _diferenca(item.base * p / 100, v):
                c.add(
                    "AIC-036",
                    "atencao",
                    f"Tributo da compra governamental não confere ({nome})",
                    f"Base R$ {_brl(item.base)} x {_pct(p)} = R$ {_brl(arredondar(item.base * p / 100))}, mas foi informado R$ {_brl(v)}.",
                    "Confira a alíquota da compra governamental.",
                    item=n,
                    campo=f"gTribCompraGov/vTrib{s}",
                )

    # tributação regular (UB69, UB70, UB72)
    reg = esp.get("gTribRegular")
    if reg:
        _conferir_codigos(reg.get("CSTReg"), reg.get("cClassTribReg"), nota, t, n, "Reg", c)
        if item.base is not None:
            for s, nome in TRIBUTOS:
                p, v = _dec(reg.get(f"pAliqEfetReg{s}")), _dec(reg.get(f"vTribReg{s}"))
                if p is not None and v is not None and _diferenca(item.base * p / 100, v):
                    c.add(
                        "AIC-037",
                        "erro" if nfe else "atencao",
                        f"Tributação regular não confere ({nome})",
                        f"Base R$ {_brl(item.base)} x {_pct(p)} = R$ {_brl(arredondar(item.base * p / 100))}, mas foi informado R$ {_brl(v)}.",
                        "Confira a alíquota efetiva da tributação regular.",
                        item=n,
                        campo=f"gTribRegular/vTribReg{s}",
                        cstat=nt.POR_TRIBUTO["trib_regular"][s],
                    )


# ----------------------------------------------------------------------------- totais


def _soma(valores) -> Decimal:
    return sum((v for v in valores if v is not None), ZERO)


def _auditar_totais(nota: Nota, c: _Coletor) -> None:
    nfe = nota.modelo in (55, 65)
    itens = [i for i in nota.itens if i.tem_grupo]
    tot = nota.totais
    if not itens:
        if nfe and tot.presente:
            c.add(
                "AIC-042",
                "erro",
                "Totais de IBS/CBS informados indevidamente",
                "O documento tem o grupo IBSCBSTot, mas nenhum item tem IBS/CBS.",
                "Retire o grupo IBSCBSTot ou gere o IBS/CBS dos itens.",
                campo="total/IBSCBSTot",
                cstat="1118",
            )
        return
    if not tot.presente:
        if nfe or any(i.grupos & {"gIBSCBS", "gIBSCBSMono", "gEstornoCred"} for i in itens):
            c.add(
                "AIC-040",
                "erro",
                "Totais de IBS/CBS ausentes",
                "Há itens com IBS/CBS, mas o documento não tem o grupo de totais IBSCBSTot.",
                "Gere o grupo IBSCBSTot com a soma dos itens.",
                campo="total/IBSCBSTot",
                cstat="1119",
            )
        return

    def esp(i: Item, grupo: str, chave: str):
        return _dec(i.especiais.get(grupo, {}).get(chave))

    contas = {
        "vBCIBSCBS": ("base de cálculo", lambda i: i.base),
        "gIBS/gIBSUF/vIBSUF": ("IBS estadual", lambda i: i.ibs_uf.valor if i.ibs_uf else None),
        "gIBS/gIBSUF/vDif": ("IBS estadual diferido", lambda i: i.ibs_uf.v_dif if i.ibs_uf else None),
        "gIBS/gIBSUF/vDevTrib": ("IBS estadual devolvido", lambda i: i.ibs_uf.v_dev if i.ibs_uf else None),
        "gIBS/gIBSMun/vIBSMun": ("IBS municipal", lambda i: i.ibs_mun.valor if i.ibs_mun else None),
        "gIBS/gIBSMun/vDif": ("IBS municipal diferido", lambda i: i.ibs_mun.v_dif if i.ibs_mun else None),
        "gIBS/gIBSMun/vDevTrib": ("IBS municipal devolvido", lambda i: i.ibs_mun.v_dev if i.ibs_mun else None),
        "gIBS/vIBS": ("IBS", lambda i: i.valor_ibs),
        "gIBS/vCredPres": ("crédito presumido de IBS", lambda i: esp(i, "gCredPresOper", "gIBSCredPres/vCredPres")),
        "gIBS/vCredPresCondSus": ("crédito presumido de IBS em condição suspensiva", lambda i: esp(i, "gCredPresOper", "gIBSCredPres/vCredPresCondSus")),
        "gCBS/vCBS": ("CBS", lambda i: i.cbs.valor if i.cbs else None),
        "gCBS/vDif": ("CBS diferida", lambda i: i.cbs.v_dif if i.cbs else None),
        "gCBS/vDevTrib": ("CBS devolvida", lambda i: i.cbs.v_dev if i.cbs else None),
        "gCBS/vCredPres": ("crédito presumido de CBS", lambda i: esp(i, "gCredPresOper", "gCBSCredPres/vCredPres")),
        "gCBS/vCredPresCondSus": ("crédito presumido de CBS em condição suspensiva", lambda i: esp(i, "gCredPresOper", "gCBSCredPres/vCredPresCondSus")),
        "gMono/vIBSMono": ("IBS monofásico", lambda i: esp(i, "gIBSCBSMono", "gMonoPadrao/vIBSMono")),
        "gMono/vCBSMono": ("CBS monofásica", lambda i: esp(i, "gIBSCBSMono", "gMonoPadrao/vCBSMono")),
        "gMono/vIBSMonoReten": ("IBS monofásico retido", lambda i: esp(i, "gIBSCBSMono", "gMonoReten/vIBSMonoReten")),
        "gMono/vCBSMonoReten": ("CBS monofásica retida", lambda i: esp(i, "gIBSCBSMono", "gMonoReten/vCBSMonoReten")),
        "gMono/vIBSMonoRet": ("IBS monofásico cobrado antes", lambda i: esp(i, "gIBSCBSMono", "gMonoRet/vIBSMonoRet")),
        "gMono/vCBSMonoRet": ("CBS monofásica cobrada antes", lambda i: esp(i, "gIBSCBSMono", "gMonoRet/vCBSMonoRet")),
        "gEstornoCred/vIBSEstCred": ("estorno de crédito de IBS", lambda i: esp(i, "gEstornoCred", "vIBSEstCred")),
        "gEstornoCred/vCBSEstCred": ("estorno de crédito de CBS", lambda i: esp(i, "gEstornoCred", "vCBSEstCred")),
    }
    _conferir_formatos(tot.campos, False, None, c)
    tolerancia = ZERO if nfe else TOLERANCIA  # NT 2025.002: total = soma dos itens, sem tolerância
    for caminho, (nome, valor) in contas.items():
        informado = _dec(tot.valores.get(caminho))
        if informado is None:
            continue
        calculado = _soma(valor(i) for i in itens)
        if abs(informado - calculado) > tolerancia:
            c.add(
                "AIC-041",
                "erro",
                f"Total de {nome} diferente da soma dos itens",
                f"O total informa R$ {_brl(informado)}, mas a soma dos itens dá R$ {_brl(calculado)}"
                + (". A NT exige igualdade exata, sem tolerância de centavo." if nfe else "."),
                "Some os valores já arredondados de cada item; não recalcule o total sobre a base inteira.",
                campo=f"IBSCBSTot/{caminho}",
                cstat=nt.TOTAIS.get(caminho),
            )

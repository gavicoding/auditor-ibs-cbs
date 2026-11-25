"""Regras de auditoria do IBS/CBS em documentos fiscais eletrônicos.

Gravidades:
- ``erro``: o dado contradiz a tabela oficial ou o leiaute (a nota tende a ser rejeitada ou fica
  errada perante o fisco);
- ``atencao``: algo não bate e merece conferência (valor, percentual, grupo inesperado);
- ``info``: observação, não indica problema.

As fórmulas seguem a calculadora pública da Receita Federal (arredondamento HALF_EVEN, valor =
arred2(vBC x alíquota publicada / 100), diferimento vDif = arred2(vBC x alíquota / 100 x pDif / 100)).
As mensagens não substituem a validação da SEFAZ nem orientação contábil.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from .leitor import Campo, Item, Nota, Tributo
from .tabelas import EXIGEM_NCM_SEMPRE, Tabelas

TOLERANCIA = Decimal("0.01")
CENTAVO = Decimal("0.01")
DEZ_MILESIMO = Decimal("0.0001")
INICIO_REFORMA = date(2026, 1, 1)
MODELOS_SUPORTADOS = {55, 65, 57, 67, 63, 66, 91}
NCM_ZERO = {"00", "00000000"}

GRUPOS_POR_INDICADOR = ("gIBSCBS", "gIBSCBSMono", "gTransfCred", "gCredPresIBSZFM", "gAjusteCompet")

# Formatos do leiaute (DFeTiposBasicos_v1.00.xsd)
FORMATOS_DFE = (
    (("CST", "CSTReg"), re.compile(r"\d{3}"), "3 dígitos"),
    (("cClassTrib", "cClassTribReg"), re.compile(r"\d{6}"), "6 dígitos"),
    (("cCredPres",), re.compile(r"\d{2}"), "2 dígitos"),
    (("q",), re.compile(r"0|0\.[0-9]{4}|[1-9][0-9]{0,10}(\.[0-9]{4})?"), "número com 4 casas decimais"),
    (
        ("p", "adRem"),
        re.compile(r"0|0\.[0-9]{2,4}|[1-9][0-9]{0,2}(\.[0-9]{2,4})?"),
        "percentual com 2 a 4 casas decimais (ex.: 0.90)",
    ),
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


def _resumir(texto: str, limite: int = 80) -> str:
    """Descrição de NCM legível: sem tags, sem os traços de hierarquia e cortada em palavra inteira."""
    texto = re.sub(r"<[^>]*>", "", texto).lstrip("- ").strip()
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _data_br(dia: date) -> str:
    return f"{dia:%d/%m/%Y}"


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
    if nota.modelo not in MODELOS_SUPORTADOS:
        r.achados.append(
            Achado(
                "AIC-002",
                "info",
                "Documento fora do escopo",
                f"O modelo {nota.modelo} não é um documento suportado; o arquivo não foi auditado.",
                "Nada a fazer.",
            )
        )
        return r
    if nota.emissao is None:
        r.achados.append(
            Achado(
                "AIC-003",
                "erro",
                "Data de emissão ausente",
                "Sem a data de emissão (dhEmi) não dá para saber quais tabelas valiam no dia.",
                "Confira se o arquivo é o XML completo do documento.",
                campo="dhEmi",
            )
        )
        return r
    if nota.emissao < INICIO_REFORMA:
        r.achados.append(
            Achado(
                "AIC-004",
                "info",
                "Documento anterior à reforma",
                "O documento foi emitido antes de 01/01/2026, quando o grupo IBS/CBS ainda não existia.",
                "Nada a fazer.",
            )
        )
        return r

    for item in nota.itens:
        r.achados.extend(_auditar_item(item, nota, tabelas))
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
        r.achados.extend(_auditar_totais(nota))
    return r


def _ref_item(nota: Nota, item: Item) -> str | None:
    return item.numero if nota.por_item else None


def _auditar_item(item: Item, nota: Nota, t: Tabelas) -> list[Achado]:
    achados: list[Achado] = []
    dia = nota.emissao
    n = _ref_item(nota, item)
    nfe = nota.modelo in (55, 65)
    nfse = nota.modelo == 91

    if not item.tem_grupo:
        onde = "O item não tem" if nota.por_item else "O documento não tem"
        if nota.crt == "3":
            achados.append(
                Achado(
                    "AIC-010",
                    "erro",
                    "Grupo IBS/CBS não informado",
                    f"{onde} o grupo IBSCBS. Pela NT 2025.002, emitentes do regime normal (CRT 3) devem informar "
                    "IBS e CBS. A rejeição automática (1115) segue o cronograma da versão vigente da nota técnica.",
                    "Configure no sistema emissor o CST e o cClassTrib para gerar o grupo IBSCBS.",
                    item=n,
                    campo="IBSCBS",
                )
            )
        else:
            regime = "Para o Simples Nacional e o MEI (CRT 1, 2 ou 4)" if nota.crt in ("1", "2", "4") else "Para este emitente"
            achados.append(
                Achado(
                    "AIC-010",
                    "info",
                    "Grupo IBS/CBS não informado",
                    f"{onde} o grupo IBSCBS. {regime}, a obrigatoriedade segue um cronograma próprio da NT 2025.002.",
                    "Confira na versão vigente da nota técnica a partir de quando o seu regime precisa informar.",
                    item=n,
                    campo="IBSCBS",
                )
            )
        if nfe and item.ncm:
            achados.extend(_conferir_ncm_existe(item, t, dia, n))
        return achados

    achados.extend(_conferir_formatos(item.campos, nfse, n))
    for campo in item.faltando:
        achados.append(
            Achado(
                "AIC-051",
                "erro",
                "Campo obrigatório ausente",
                f"O campo {campo} é obrigatório no grupo IBS/CBS e não foi informado.",
                "Gere o grupo completo; o leiaute da NT 2025.002 lista os campos obrigatórios.",
                item=n,
                campo=campo,
            )
        )

    # --- CST e cClassTrib ---
    cst = t.cst(item.cst or "")
    achados.extend(_conferir_codigos(item.cst, item.cclasstrib, nota, t, n, sufixo=""))
    cl = t.cclasstrib(item.cclasstrib or "")

    # --- NCM / NBS ---
    if nfe:
        achados.extend(_conferir_ncm(item, cl, t, dia, n))
    if nfse and cl:
        achados.extend(_conferir_nbs(item, t, dia))

    # --- grupos exigidos pelo CST ---
    if cst is not None and not nfse:
        grupos = GRUPOS_POR_INDICADOR if nfe else ("gIBSCBS",)
        for grupo in grupos:
            exigido = cst["grupos"].get(grupo, False)
            presente = grupo in item.grupos
            if exigido and not presente:
                achados.append(
                    Achado(
                        "AIC-020",
                        "erro",
                        f"Grupo {grupo} ausente",
                        f"O CST {item.cst} ({cst['descricao']}) exige o grupo {grupo}, que não foi informado.",
                        f"Gere o grupo {grupo} ou confira se o CST está certo.",
                        item=n,
                        campo=f"IBSCBS/{grupo}",
                    )
                )
            elif presente and not exigido:
                achados.append(
                    Achado(
                        "AIC-021",
                        "atencao",
                        f"Grupo {grupo} inesperado",
                        f"O grupo {grupo} foi informado, mas o CST {item.cst} ({cst['descricao']}) não o prevê.",
                        "Confira se o CST está certo para esta operação.",
                        item=n,
                        campo=f"IBSCBS/{grupo}",
                    )
                )

    if "gIBSCBS" in item.grupos:
        achados.extend(_auditar_valores(item, nota, t, cst, n))
    achados.extend(_auditar_especiais(item, nota, t, n))
    return achados


def _conferir_formatos(campos: list[Campo], nfse: bool, n: str | None) -> list[Achado]:
    achados = []
    formatos = FORMATOS_NFSE if nfse else FORMATOS_DFE
    for campo in campos:
        for prefixos, regex, descricao in formatos:
            casa = campo.nome in prefixos if prefixos[0][0].isupper() or prefixos[0].startswith("c") else campo.nome.startswith(prefixos)
            if not casa:
                continue
            if not regex.fullmatch(campo.valor):
                achados.append(
                    Achado(
                        "AIC-050",
                        "erro",
                        f"Formato inválido em {campo.nome}",
                        f"O campo {campo.nome} tem o valor '{campo.valor[:30]}', mas o leiaute exige {descricao}.",
                        "Corrija a formatação no sistema emissor (ponto como separador decimal, sem separador de milhar).",
                        item=n,
                        campo=f"{campo.caminho}/{campo.nome}",
                    )
                )
            break
        if len(achados) >= 5:
            break
    return achados


def _conferir_codigos(cst_cod: str | None, cl_cod: str | None, nota: Nota, t: Tabelas, n: str | None, sufixo: str) -> list[Achado]:
    """CST e cClassTrib (sufixo 'Reg' para o grupo de tributação regular)."""
    achados: list[Achado] = []
    dia = nota.emissao
    doc = t.nome_documento(nota.modelo)
    rotulo = " da tributação regular" if sufixo else ""
    cst = t.cst(cst_cod or "")
    if cst is None:
        achados.append(
            Achado(
                "AIC-011",
                "erro",
                f"CST{rotulo} inexistente",
                f"O CST '{cst_cod}' não existe na tabela oficial ({t.versao}).",
                "Use um dos CSTs da tabela oficial; o comando 'consultar' lista os códigos.",
                item=n,
                campo=f"CST{sufixo}",
            )
        )
    elif not t.vigente(cst, dia):
        achados.append(
            Achado(
                "AIC-012",
                "erro",
                f"CST{rotulo} fora da vigência",
                f"O CST {cst_cod} não valia em {_data_br(dia)} (vigência {cst['inicio']} a {cst['fim'] or 'atual'}).",
                "Use um CST vigente na data de emissão.",
                item=n,
                campo=f"CST{sufixo}",
            )
        )
    cl = t.cclasstrib(cl_cod or "")
    if cl is None:
        achados.append(
            Achado(
                "AIC-013",
                "erro",
                f"cClassTrib{rotulo} inexistente",
                f"O código de classificação tributária '{cl_cod}' não existe na tabela oficial ({t.versao}).",
                "Corrija o cClassTrib; use 'consultar' para ver os códigos de cada CST.",
                item=n,
                campo=f"cClassTrib{sufixo}",
            )
        )
        return achados
    if not t.vigente(cl, dia):
        achados.append(
            Achado(
                "AIC-014",
                "erro",
                f"cClassTrib{rotulo} fora da vigência",
                f"O cClassTrib {cl_cod} não valia em {_data_br(dia)} (vigência {cl['inicio']} a {cl['fim'] or 'atual'}).",
                "Troque pelo código que substituiu este na tabela vigente.",
                item=n,
                campo=f"cClassTrib{sufixo}",
            )
        )
    if cst_cod and cl["cst"] != cst_cod:
        achados.append(
            Achado(
                "AIC-015",
                "erro",
                f"cClassTrib{rotulo} não pertence ao CST",
                f"O cClassTrib {cl_cod} ({cl['descricao']}) é do CST {cl['cst']}, mas foi informado o CST {cst_cod}.",
                f"Use o CST {cl['cst']} ou escolha um cClassTrib do CST {cst_cod}.",
                item=n,
                campo=f"CST{sufixo}",
            )
        )
    if not sufixo and not t.permitido_no_modelo(cl_cod, nota.modelo, dia):
        achados.append(
            Achado(
                "AIC-016",
                "erro",
                f"cClassTrib não permitido em {doc}",
                f"Pela tabela oficial, o cClassTrib {cl_cod} ({cl['descricao']}) não pode ser usado em {doc} na data de emissão.",
                f"Escolha um cClassTrib previsto para {doc}.",
                item=n,
                campo="cClassTrib",
            )
        )
    return achados


def _conferir_ncm_existe(item: Item, t: Tabelas, dia: date, n: str | None) -> list[Achado]:
    ncm = item.ncm or ""
    if len(ncm) != 8 or ncm in NCM_ZERO:
        return []
    registro = t.ncm(ncm)
    if registro is None or not (registro[1] <= dia.isoformat() <= registro[2]):
        motivo = "não existe na tabela NCM" if registro is None else f"não estava vigente em {_data_br(dia)}"
        return [
            Achado(
                "AIC-019",
                "atencao",
                "NCM inexistente ou fora da vigência",
                f"O NCM {ncm} {motivo}.",
                "Confira a classificação fiscal do produto na tabela NCM vigente.",
                item=n,
                campo="prod/NCM",
            )
        ]
    return []


def _conferir_ncm(item: Item, cl: dict | None, t: Tabelas, dia: date, n: str | None) -> list[Achado]:
    achados = _conferir_ncm_existe(item, t, dia, n)
    if cl is None:
        return achados
    codigo = item.cclasstrib
    tem_lista = t.tem_lista(codigo, "ncm", dia)
    if not tem_lista and codigo not in EXIGEM_NCM_SEMPRE:
        return achados
    ncm = item.ncm or ""
    anexos = t.anexos_do_cclasstrib(codigo, "ncm", dia)
    onde = f" ({', '.join(anexos[:3])}{'…' if len(anexos) > 3 else ''} da LC 214/2025)" if anexos else ""
    if len(ncm) != 8 or ncm in NCM_ZERO:
        achados.append(
            Achado(
                "AIC-017",
                "erro",
                "NCM obrigatório para este cClassTrib",
                f"O cClassTrib {codigo} ({cl['descricao']}) exige o NCM completo de 8 dígitos do produto, mas o item informa '{ncm or 'nada'}'.",
                "Informe o NCM correto do produto no cadastro.",
                item=n,
                campo="prod/NCM",
            )
        )
    elif tem_lista and not t.aplicavel(codigo, "ncm", ncm, dia):
        descricao = t.ncm(ncm)
        produto = f" ({_resumir(descricao[0])})" if descricao else ""
        achados.append(
            Achado(
                "AIC-018",
                "erro",
                "NCM não pode usar este cClassTrib",
                f"O cClassTrib {codigo} ({cl['descricao']}) só vale para os produtos listados na lei{onde}. "
                f"O NCM {ncm}{produto} não está nessa lista, então o tratamento (como a redução) não se aplica.",
                "Confira o NCM e o cClassTrib do produto; se o produto não está no anexo, use o cClassTrib da tributação comum.",
                item=n,
                campo="IBSCBS/cClassTrib",
            )
        )
    return achados


def _conferir_nbs(item: Item, t: Tabelas, dia: date) -> list[Achado]:
    codigo = item.cclasstrib
    if not t.tem_lista(codigo, "nbs", dia):
        return []
    cl = t.cclasstrib(codigo)
    nbs = item.nbs or ""
    if len(nbs) != 9:
        return [
            Achado(
                "AIC-024",
                "erro",
                "NBS obrigatório para este cClassTrib",
                f"O cClassTrib {codigo} ({cl['descricao']}) exige o código NBS completo (9 dígitos) do serviço, mas a NFS-e informa '{nbs or 'nada'}'.",
                "Informe o NBS do serviço (cServ/cNBS).",
                campo="serv/cServ/cNBS",
            )
        ]
    if not t.aplicavel(codigo, "nbs", nbs, dia):
        return [
            Achado(
                "AIC-025",
                "erro",
                "NBS não pode usar este cClassTrib",
                f"O cClassTrib {codigo} ({cl['descricao']}) só vale para os serviços listados na lei. O NBS {nbs} não está nessa lista.",
                "Confira o NBS e o cClassTrib do serviço.",
                campo="IBSCBS/cClassTrib",
            )
        ]
    return []


# ----------------------------------------------------------------------------- valores


def _auditar_valores(item: Item, nota: Nota, t: Tabelas, cst: dict | None, n: str | None) -> list[Achado]:
    achados: list[Achado] = []
    dia = nota.emissao
    preve_reducao = bool(cst and cst["grupos"].get("gRed"))
    preve_dif = bool(cst and cst["grupos"].get("gDif"))
    nfse = nota.modelo == 91
    blocos = (("IBSUF", "IBS estadual", item.ibs_uf), ("IBSMun", "IBS municipal", item.ibs_mun), ("CBS", "CBS", item.cbs))

    tem_dif = any(trib and trib.tem_diferimento for _, _, trib in blocos)
    if cst is not None and tem_dif and not preve_dif:
        achados.append(
            Achado(
                "AIC-026",
                "atencao",
                "Diferimento inesperado",
                f"Foi informado diferimento (gDif), mas o CST {item.cst} ({cst['descricao']}) não prevê diferimento.",
                "Operações com diferimento usam CSTs como 510 ou 515.",
                item=n,
                campo="gDif",
            )
        )
    elif cst is not None and preve_dif and not tem_dif and not nfse:
        achados.append(
            Achado(
                "AIC-026",
                "atencao",
                "Diferimento não informado",
                f"O CST {item.cst} ({cst['descricao']}) prevê diferimento, mas nenhum grupo gDif foi informado.",
                "Confira se o CST está certo ou gere o grupo gDif com o percentual diferido.",
                item=n,
                campo="gDif",
            )
        )

    for sigla, nome, trib in blocos:
        if trib is None:
            continue
        tem_red = trib.reducao is not None or (trib.aliquota_efetiva is not None and not nfse)
        if cst is not None and tem_red and not preve_reducao and (trib.reducao or Decimal(0)) != 0:
            achados.append(
                Achado(
                    "AIC-022",
                    "atencao",
                    f"Redução de alíquota inesperada ({nome})",
                    f"Foi informada redução (gRed) no {nome}, mas o CST {item.cst} não prevê redução.",
                    "Confira o CST: operações com redução usam CSTs como 200 ou 515.",
                    item=n,
                    campo=f"g{sigla}/gRed",
                )
            )
        oficial = t.reducao(item.cclasstrib or "", sigla, dia) if item.cclasstrib else None
        if trib.reducao is not None and oficial is not None and Decimal(str(oficial)) != trib.reducao:
            achados.append(
                Achado(
                    "AIC-023",
                    "atencao",
                    f"Percentual de redução diferente do oficial ({nome})",
                    f"Foi informada redução de {_pct(trib.reducao)}, mas a tabela oficial do cClassTrib {item.cclasstrib} prevê {_pct(oficial)}.",
                    "Confira o cClassTrib e o percentual de redução configurados.",
                    item=n,
                    campo=f"g{sigla}/gRed/pRedAliq",
                )
            )
        achados.extend(_conferir_aliquota_efetiva(trib, sigla, nome, nota, n))
        achados.extend(_conferir_valor(item, trib, sigla, nome, nota, n))

    if item.valor_ibs is not None and item.ibs_uf and item.ibs_mun and None not in (item.ibs_uf.valor, item.ibs_mun.valor):
        soma = item.ibs_uf.valor + item.ibs_mun.valor
        if abs(soma - item.valor_ibs) > TOLERANCIA:
            achados.append(
                Achado(
                    "AIC-031",
                    "erro",
                    "IBS total diferente da soma",
                    f"O IBS total é R$ {_brl(item.valor_ibs)}, mas IBS estadual + municipal dá R$ {_brl(soma)}.",
                    "O IBS total deve ser a soma do IBS estadual e do municipal.",
                    item=n,
                    campo="vIBS",
                )
            )

    cl = t.cclasstrib(item.cclasstrib or "")
    for sigla, nome, trib in (
        ("CBS", "CBS", item.cbs),
        ("IBSUF", "IBS estadual", item.ibs_uf),
        ("IBSMun", "IBS municipal", item.ibs_mun),
    ):
        if trib is None or trib.aliquota is None or trib.reducao is not None or nota.redutor_compra_gov is not None:
            continue
        ref = t.aliquota_referencia(sigla, dia)
        if ref is not None and cl and cl.get("tipo_aliquota") == "Padrão" and trib.aliquota != Decimal(str(ref)):
            achados.append(
                Achado(
                    "AIC-032",
                    "info",
                    f"Alíquota diferente da referência ({nome})",
                    f"A alíquota informada é {_pct(trib.aliquota)}; a de referência para {dia.year} é {_pct(ref)}.",
                    "Se não houver motivo específico (regime, benefício), confira a alíquota configurada.",
                    item=n,
                    campo=f"p{sigla}",
                )
            )
    return achados


def _aliquota_publicada(trib: Tributo, nota: Nota) -> Decimal | None:
    """A alíquota que multiplica a base, como a calculadora publica (efetiva, quando houver)."""
    if trib.aliquota_efetiva is not None:
        return trib.aliquota_efetiva
    if nota.redutor_compra_gov is not None:
        return None  # sem a alíquota efetiva publicada, não dá para conferir sem risco de alarme falso
    return trib.aliquota


def _conferir_aliquota_efetiva(trib: Tributo, sigla: str, nome: str, nota: Nota, n: str | None) -> list[Achado]:
    if trib.aliquota is None or trib.aliquota_efetiva is None:
        return []
    reducao = trib.reducao or Decimal(0)
    redutor = nota.redutor_compra_gov or Decimal(0)
    exata = trib.aliquota * (1 - reducao / 100) * (1 - redutor / 100)
    nfse = nota.modelo == 91
    esperada = arredondar(exata, CENTAVO if nfse else DEZ_MILESIMO)
    tolerancia = CENTAVO if nfse else DEZ_MILESIMO
    if abs(esperada - trib.aliquota_efetiva) > tolerancia:
        return [
            Achado(
                "AIC-033",
                "atencao",
                f"Alíquota efetiva não confere ({nome})",
                f"Com alíquota {_pct(trib.aliquota)}, redução {_pct(reducao)}"
                + (f" e redutor de compra governamental {_pct(redutor)}" if redutor else "")
                + f", a alíquota efetiva seria {_pct(esperada)}, mas foi informada {_pct(trib.aliquota_efetiva)}.",
                "A alíquota efetiva é alíquota x (1 - redução) x (1 - redutor); confira os percentuais.",
                item=n,
                campo=f"pAliqEfet ({sigla})",
            )
        ]
    return []


def _conferir_valor(item: Item, trib: Tributo, sigla: str, nome: str, nota: Nota, n: str | None) -> list[Achado]:
    if item.base is None or trib.valor is None:
        return []
    if trib.tem_devolucao:
        return []  # a devolução (gDevTrib) não tem fórmula publicada na calculadora; não recalculamos
    aliquota = _aliquota_publicada(trib, nota)
    if aliquota is None:
        return []
    calculado = arredondar(item.base * aliquota / Decimal(100))
    achados = []
    devido = calculado
    if trib.tem_diferimento:
        if trib.p_dif is None:
            return []
        v_dif = arredondar(item.base * aliquota / Decimal(100) * trib.p_dif / Decimal(100))
        devido = calculado - v_dif
        if trib.v_dif is not None and abs(v_dif - trib.v_dif) > TOLERANCIA:
            achados.append(
                Achado(
                    "AIC-034",
                    "atencao",
                    f"Valor diferido do {nome} não confere",
                    f"Base R$ {_brl(item.base)} x {_pct(aliquota)} x {_pct(trib.p_dif)} diferido = R$ {_brl(v_dif)}, mas foi informado R$ {_brl(trib.v_dif)}.",
                    "O valor diferido é base x alíquota x percentual de diferimento.",
                    item=n,
                    campo=f"vDif ({sigla})",
                )
            )
    if abs(devido - trib.valor) > TOLERANCIA:
        conta = f"Base R$ {_brl(item.base)} x {_pct(aliquota)} = R$ {_brl(calculado)}"
        if trib.tem_diferimento:
            conta += f", menos o diferido, dá R$ {_brl(devido)}"
        achados.append(
            Achado(
                "AIC-030",
                "atencao",
                f"Valor do {nome} não bate com base x alíquota",
                f"{conta}, mas foi informado R$ {_brl(trib.valor)}.",
                "Confira a base de cálculo e a alíquota; a calculadora oficial da Receita ajuda a conferir.",
                item=n,
                campo=f"v{sigla}",
            )
        )
    return achados


def _diferenca(esperado: Decimal, informado: Decimal | None) -> bool:
    return informado is not None and abs(esperado - informado) > TOLERANCIA


def _auditar_especiais(item: Item, nota: Nota, t: Tabelas, n: str | None) -> list[Achado]:
    achados: list[Achado] = []
    esp = item.especiais

    # crédito presumido: vCredPres = vBCCredPres x pCredPres
    cred = esp.get("gCredPresOper")
    if cred:
        base = _dec(cred.get("vBCCredPres"))
        for g, nome in (("gIBSCredPres", "IBS"), ("gCBSCredPres", "CBS")):
            p = _dec(cred.get(f"{g}/pCredPres"))
            v = _dec(cred.get(f"{g}/vCredPres", cred.get(f"{g}/vCredPresCondSus")))
            if base is not None and p is not None and v is not None:
                esperado = arredondar(base * p / 100)
                if _diferenca(esperado, v):
                    achados.append(
                        Achado(
                            "AIC-035",
                            "atencao",
                            f"Crédito presumido de {nome} não confere",
                            f"Base R$ {_brl(base)} x {_pct(p)} = R$ {_brl(esperado)}, mas foi informado R$ {_brl(v)}.",
                            "O crédito presumido é a base do crédito x o percentual.",
                            item=n,
                            campo=f"gCredPresOper/{g}",
                        )
                    )

    # compra governamental: vTrib = vBC x pAliq
    gov = esp.get("gTribCompraGov")
    if gov and item.base is not None:
        for s, nome in (("IBSUF", "IBS estadual"), ("IBSMun", "IBS municipal"), ("CBS", "CBS")):
            p, v = _dec(gov.get(f"pAliq{s}")), _dec(gov.get(f"vTrib{s}"))
            if p is not None and v is not None:
                esperado = arredondar(item.base * p / 100)
                if _diferenca(esperado, v):
                    achados.append(
                        Achado(
                            "AIC-036",
                            "atencao",
                            f"Tributo da compra governamental não confere ({nome})",
                            f"Base R$ {_brl(item.base)} x {_pct(p)} = R$ {_brl(esperado)}, mas foi informado R$ {_brl(v)}.",
                            "Confira a alíquota da compra governamental.",
                            item=n,
                            campo=f"gTribCompraGov/vTrib{s}",
                        )
                    )

    # tributação regular (operações com tributação que difere da regular)
    reg = esp.get("gTribRegular")
    if reg:
        achados.extend(_conferir_codigos(reg.get("CSTReg"), reg.get("cClassTribReg"), nota, t, n, sufixo="Reg"))
        if item.base is not None:
            for s, nome in (("IBSUF", "IBS estadual"), ("IBSMun", "IBS municipal"), ("CBS", "CBS")):
                p, v = _dec(reg.get(f"pAliqEfetReg{s}")), _dec(reg.get(f"vTribReg{s}"))
                if p is not None and v is not None:
                    esperado = arredondar(item.base * p / 100)
                    if _diferenca(esperado, v):
                        achados.append(
                            Achado(
                                "AIC-037",
                                "atencao",
                                f"Tributação regular não confere ({nome})",
                                f"Base R$ {_brl(item.base)} x {_pct(p)} = R$ {_brl(esperado)}, mas foi informado R$ {_brl(v)}.",
                                "Confira a alíquota efetiva da tributação regular.",
                                item=n,
                                campo=f"gTribRegular/vTribReg{s}",
                            )
                        )

    # monofásico: valor = quantidade x alíquota ad rem
    mono = esp.get("gIBSCBSMono")
    if mono:
        for grupo, q, pares in (
            ("gMonoPadrao", "qBCMono", (("adRemIBS", "vIBSMono"), ("adRemCBS", "vCBSMono"))),
            ("gMonoReten", "qBCMonoReten", (("adRemIBSReten", "vIBSMonoReten"), ("adRemCBSReten", "vCBSMonoReten"))),
            ("gMonoRet", "qBCMonoRet", (("adRemIBSRet", "vIBSMonoRet"), ("adRemCBSRet", "vCBSMonoRet"))),
        ):
            qtd = _dec(mono.get(f"{grupo}/{q}"))
            for ad, val in pares:
                a, v = _dec(mono.get(f"{grupo}/{ad}")), _dec(mono.get(f"{grupo}/{val}"))
                if qtd is not None and a is not None and v is not None:
                    esperado = arredondar(qtd * a)
                    if _diferenca(esperado, v):
                        achados.append(
                            Achado(
                                "AIC-038",
                                "atencao",
                                f"Valor monofásico não confere ({val})",
                                f"Quantidade {qtd.normalize():f} x R$ {a.normalize():f} = R$ {_brl(esperado)}, mas foi informado R$ {_brl(v)}.",
                                "Na tributação monofásica o valor é a quantidade x a alíquota ad rem.",
                                item=n,
                                campo=f"gIBSCBSMono/{grupo}/{val}",
                            )
                        )
    return achados


# ----------------------------------------------------------------------------- totais


def _soma(valores) -> Decimal:
    return sum((v for v in valores if v is not None), Decimal(0))


def _auditar_totais(nota: Nota) -> list[Achado]:
    itens = [i for i in nota.itens if i.tem_grupo]
    com_valores = [i for i in itens if i.grupos & {"gIBSCBS", "gIBSCBSMono", "gEstornoCred"}]
    if not com_valores:
        return []
    tot = nota.totais
    if not tot.presente:
        return [
            Achado(
                "AIC-040",
                "erro",
                "Totais de IBS/CBS ausentes",
                "Há itens com IBS/CBS, mas o documento não tem o grupo de totais IBSCBSTot.",
                "Gere o grupo IBSCBSTot com a soma dos itens.",
                campo="total/IBSCBSTot",
            )
        ]

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
        "gIBS/vCredPresCondSus": (
            "crédito presumido de IBS em condição suspensiva",
            lambda i: esp(i, "gCredPresOper", "gIBSCredPres/vCredPresCondSus"),
        ),
        "gCBS/vCBS": ("CBS", lambda i: i.cbs.valor if i.cbs else None),
        "gCBS/vDif": ("CBS diferida", lambda i: i.cbs.v_dif if i.cbs else None),
        "gCBS/vDevTrib": ("CBS devolvida", lambda i: i.cbs.v_dev if i.cbs else None),
        "gCBS/vCredPres": ("crédito presumido de CBS", lambda i: esp(i, "gCredPresOper", "gCBSCredPres/vCredPres")),
        "gCBS/vCredPresCondSus": (
            "crédito presumido de CBS em condição suspensiva",
            lambda i: esp(i, "gCredPresOper", "gCBSCredPres/vCredPresCondSus"),
        ),
        "gMono/vIBSMono": ("IBS monofásico", lambda i: esp(i, "gIBSCBSMono", "gMonoPadrao/vIBSMono")),
        "gMono/vCBSMono": ("CBS monofásica", lambda i: esp(i, "gIBSCBSMono", "gMonoPadrao/vCBSMono")),
        "gMono/vIBSMonoReten": ("IBS monofásico retido", lambda i: esp(i, "gIBSCBSMono", "gMonoReten/vIBSMonoReten")),
        "gMono/vCBSMonoReten": ("CBS monofásica retida", lambda i: esp(i, "gIBSCBSMono", "gMonoReten/vCBSMonoReten")),
        "gMono/vIBSMonoRet": ("IBS monofásico cobrado antes", lambda i: esp(i, "gIBSCBSMono", "gMonoRet/vIBSMonoRet")),
        "gMono/vCBSMonoRet": ("CBS monofásica cobrada antes", lambda i: esp(i, "gIBSCBSMono", "gMonoRet/vCBSMonoRet")),
        "gEstornoCred/vIBSEstCred": ("estorno de crédito de IBS", lambda i: esp(i, "gEstornoCred", "vIBSEstCred")),
        "gEstornoCred/vCBSEstCred": ("estorno de crédito de CBS", lambda i: esp(i, "gEstornoCred", "vCBSEstCred")),
    }
    achados = _conferir_formatos(tot.campos, False, None)
    for caminho, (nome, valor) in contas.items():
        informado = _dec(tot.valores.get(caminho))
        if informado is None:
            continue
        calculado = _soma(valor(i) for i in itens)
        if abs(informado - calculado) > TOLERANCIA:
            achados.append(
                Achado(
                    "AIC-041",
                    "erro",
                    f"Total de {nome} diferente da soma dos itens",
                    f"O total informa R$ {_brl(informado)}, mas a soma dos itens dá R$ {_brl(calculado)}.",
                    "O total do documento deve ser a soma dos valores dos itens.",
                    campo=f"IBSCBSTot/{caminho}",
                )
            )
    return achados

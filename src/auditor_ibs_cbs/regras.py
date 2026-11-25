"""Regras de auditoria do grupo IBS/CBS em NF-e e NFC-e.

Gravidades:
- ``erro``: o dado contradiz a tabela oficial ou a estrutura exigida (a nota tende a ser rejeitada
  ou fica errada perante o fisco);
- ``atencao``: algo não bate e merece conferência (valor, percentual de redução, grupo inesperado);
- ``info``: observação, não indica problema.

As mensagens não substituem a validação da SEFAZ nem orientação contábil.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from .leitor import Item, Nota, Tributo
from .tabelas import Tabelas

TOLERANCIA = Decimal("0.01")
CENTAVO = Decimal("0.01")
INICIO_REFORMA = date(2026, 1, 1)
MODELOS = {55: "NF-e", 65: "NFC-e"}

# Grupos do IBSCBS que dependem do CST (indicadores da tabela de CST)
GRUPOS_POR_INDICADOR = ("gIBSCBS", "gIBSCBSMono", "gTransfCred", "gCredPresIBSZFM", "gAjusteCompet")


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
    numero: str | None = None
    serie: str | None = None
    emissao: str | None = None
    itens: int = 0
    achados: list[Achado] = field(default_factory=list)

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
            "numero": self.numero,
            "serie": self.serie,
            "emissao": self.emissao,
            "itens": self.itens,
            "situacao": self.situacao,
            "achados": [a.como_dict() for a in self.achados],
        }


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


def arredondar(valor: Decimal) -> Decimal:
    """Duas casas, arredondamento bancário (o mesmo modo HALF_EVEN da calculadora oficial)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_EVEN)


def auditar(nota: Nota, tabelas: Tabelas) -> Resultado:
    r = Resultado(
        origem=nota.origem,
        chave=nota.chave,
        modelo=nota.modelo,
        numero=nota.numero,
        serie=nota.serie,
        emissao=nota.emissao.isoformat() if nota.emissao else None,
        itens=len(nota.itens),
    )
    if nota.modelo not in MODELOS:
        r.achados.append(
            Achado(
                "AIC-002",
                "info",
                "Documento fora do escopo",
                f"O modelo {nota.modelo} não é NF-e (55) nem NFC-e (65); o arquivo não foi auditado.",
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
                "Confira se o arquivo é o XML completo da nota.",
                campo="ide/dhEmi",
            )
        )
        return r
    if nota.emissao < INICIO_REFORMA:
        r.achados.append(
            Achado(
                "AIC-004",
                "info",
                "Nota anterior à reforma",
                "A nota foi emitida antes de 01/01/2026, quando o grupo IBS/CBS ainda não existia.",
                "Nada a fazer.",
            )
        )
        return r

    for item in nota.itens:
        r.achados.extend(_auditar_item(item, nota, tabelas))
    r.achados.extend(_auditar_totais(nota))
    return r


def _auditar_item(item: Item, nota: Nota, t: Tabelas) -> list[Achado]:
    achados: list[Achado] = []
    dia = nota.emissao
    n = item.numero
    modelo = MODELOS[nota.modelo]

    if not item.tem_grupo:
        if nota.crt == "3":
            achados.append(
                Achado(
                    "AIC-010",
                    "erro",
                    "Grupo IBS/CBS não informado",
                    "O item não tem o grupo IBSCBS. Pela NT 2025.002, emitentes do regime normal (CRT 3) "
                    "devem informar IBS e CBS em todos os itens. A rejeição automática (1115) segue o "
                    "cronograma da versão vigente da nota técnica.",
                    "Configure no sistema emissor o CST e o cClassTrib do produto para gerar o grupo IBSCBS.",
                    item=n,
                    campo="det/imposto/IBSCBS",
                )
            )
        else:
            achados.append(
                Achado(
                    "AIC-010",
                    "info",
                    "Grupo IBS/CBS não informado",
                    "O item não tem o grupo IBSCBS. Para o Simples Nacional e o MEI (CRT 1, 2 ou 4) a "
                    "obrigatoriedade segue um cronograma próprio da NT 2025.002.",
                    "Confira na versão vigente da nota técnica a partir de quando o seu regime precisa informar.",
                    item=n,
                    campo="det/imposto/IBSCBS",
                )
            )
        return achados

    # --- CST ---
    cst = t.cst(item.cst or "")
    if cst is None:
        achados.append(
            Achado(
                "AIC-011",
                "erro",
                "CST do IBS/CBS inexistente",
                f"O CST '{item.cst}' não existe na tabela oficial ({t.versao}).",
                "Use um dos CSTs da tabela oficial; o comando 'consultar' lista os códigos.",
                item=n,
                campo="IBSCBS/CST",
            )
        )
    elif not t.vigente(cst, dia):
        achados.append(
            Achado(
                "AIC-012",
                "erro",
                "CST fora da vigência",
                f"O CST {item.cst} não valia em {dia:%d/%m/%Y} (vigência {cst['inicio']} a {cst['fim'] or 'atual'}).",
                "Use um CST vigente na data de emissão.",
                item=n,
                campo="IBSCBS/CST",
            )
        )

    # --- cClassTrib ---
    cl = t.cclasstrib(item.cclasstrib or "")
    if cl is None:
        achados.append(
            Achado(
                "AIC-013",
                "erro",
                "cClassTrib inexistente",
                f"O código de classificação tributária '{item.cclasstrib}' não existe na tabela oficial ({t.versao}).",
                "Corrija o cClassTrib do produto; use 'consultar' para ver os códigos de cada CST.",
                item=n,
                campo="IBSCBS/cClassTrib",
            )
        )
    else:
        if not t.vigente(cl, dia):
            achados.append(
                Achado(
                    "AIC-014",
                    "erro",
                    "cClassTrib fora da vigência",
                    f"O cClassTrib {item.cclasstrib} não valia em {dia:%d/%m/%Y} "
                    f"(vigência {cl['inicio']} a {cl['fim'] or 'atual'}).",
                    "Troque pelo código que substituiu este na tabela vigente.",
                    item=n,
                    campo="IBSCBS/cClassTrib",
                )
            )
        if item.cst and cl["cst"] != item.cst:
            achados.append(
                Achado(
                    "AIC-015",
                    "erro",
                    "cClassTrib não pertence ao CST",
                    f"O cClassTrib {item.cclasstrib} ({cl['descricao']}) é do CST {cl['cst']}, "
                    f"mas o item informa CST {item.cst}.",
                    f"Use o CST {cl['cst']} ou escolha um cClassTrib do CST {item.cst}.",
                    item=n,
                    campo="IBSCBS/CST",
                )
            )
        if not t.permitido_no_modelo(item.cclasstrib, nota.modelo, dia):
            achados.append(
                Achado(
                    "AIC-016",
                    "erro",
                    f"cClassTrib não permitido em {modelo}",
                    f"Pela tabela oficial, o cClassTrib {item.cclasstrib} ({cl['descricao']}) não pode ser "
                    f"usado em {modelo} na data de emissão.",
                    f"Escolha um cClassTrib previsto para {modelo}.",
                    item=n,
                    campo="IBSCBS/cClassTrib",
                )
            )

    # --- grupos exigidos pelo CST ---
    if cst is not None:
        for grupo in GRUPOS_POR_INDICADOR:
            exigido = cst["grupos"].get(grupo, False)
            presente = grupo in item.grupos
            if exigido and not presente:
                achados.append(
                    Achado(
                        "AIC-020",
                        "erro",
                        f"Grupo {grupo} ausente",
                        f"O CST {item.cst} ({cst['descricao']}) exige o grupo {grupo}, que não está no item.",
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
                        f"O item traz o grupo {grupo}, que o CST {item.cst} ({cst['descricao']}) não prevê.",
                        "Confira se o CST está certo para esta operação.",
                        item=n,
                        campo=f"IBSCBS/{grupo}",
                    )
                )

    # --- valores ---
    if "gIBSCBS" in item.grupos:
        achados.extend(_auditar_valores(item, nota, t, cst))
    return achados


def _auditar_valores(item: Item, nota: Nota, t: Tabelas, cst: dict | None) -> list[Achado]:
    achados: list[Achado] = []
    n = item.numero
    dia = nota.emissao
    preve_reducao = bool(cst and cst["grupos"].get("gRed"))

    for sigla, nome, trib in (
        ("IBSUF", "IBS estadual", item.ibs_uf),
        ("IBSMun", "IBS municipal", item.ibs_mun),
        ("CBS", "CBS", item.cbs),
    ):
        if trib is None:
            continue
        tem_red = trib.reducao is not None or trib.aliquota_efetiva is not None
        if cst is not None and tem_red and not preve_reducao:
            achados.append(
                Achado(
                    "AIC-022",
                    "atencao",
                    f"Redução de alíquota inesperada ({nome})",
                    f"O item informa redução (gRed) no {nome}, mas o CST {item.cst} não prevê redução.",
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
                    f"O item informa redução de {_pct(trib.reducao)}, mas a tabela oficial do cClassTrib "
                    f"{item.cclasstrib} prevê {_pct(oficial)}.",
                    "Confira o cClassTrib e o percentual de redução configurados para o produto.",
                    item=n,
                    campo=f"g{sigla}/gRed/pRedAliq",
                )
            )
        achados.extend(_conferir_valor(item, trib, sigla, nome))

    # vIBS = vIBSUF + vIBSMun
    if item.valor_ibs is not None and item.ibs_uf and item.ibs_mun and None not in (item.ibs_uf.valor, item.ibs_mun.valor):
        soma = item.ibs_uf.valor + item.ibs_mun.valor
        if abs(soma - item.valor_ibs) > TOLERANCIA:
            achados.append(
                Achado(
                    "AIC-031",
                    "erro",
                    "IBS total diferente da soma",
                    f"vIBS é R$ {_brl(item.valor_ibs)}, mas IBS estadual + municipal dá R$ {_brl(soma)}.",
                    "O vIBS do item deve ser a soma de vIBSUF e vIBSMun.",
                    item=n,
                    campo="gIBSCBS/vIBS",
                )
            )

    # alíquota de referência (só observação)
    for sigla, nome, trib in (
        ("CBS", "CBS", item.cbs),
        ("IBSUF", "IBS estadual", item.ibs_uf),
        ("IBSMun", "IBS municipal", item.ibs_mun),
    ):
        if trib is None or trib.aliquota is None or trib.reducao is not None:
            continue
        ref = t.aliquota_referencia(sigla, dia)
        cl = t.cclasstrib(item.cclasstrib or "")
        if ref is not None and cl and cl.get("tipo_aliquota") == "Padrão" and trib.aliquota != Decimal(str(ref)):
            achados.append(
                Achado(
                    "AIC-032",
                    "info",
                    f"Alíquota diferente da referência ({nome})",
                    f"A alíquota informada é {_pct(trib.aliquota)}; a de referência para {dia.year} é {_pct(ref)}.",
                    "Se não houver motivo específico (regime, benefício), confira a alíquota configurada.",
                    item=n,
                    campo=f"g{sigla}/p{sigla}",
                )
            )
    return achados


def _conferir_valor(item: Item, trib: Tributo, sigla: str, nome: str) -> list[Achado]:
    if item.base is None or trib.valor is None or trib.aliquota is None:
        return []
    if trib.tem_diferimento or trib.tem_devolucao:
        return []  # diferimento e devolução mudam a conta; não conferimos para não gerar alarme falso
    aliquota = trib.aliquota_efetiva if trib.aliquota_efetiva is not None else trib.aliquota
    esperado = arredondar(item.base * aliquota / Decimal(100))
    if abs(esperado - trib.valor) > TOLERANCIA:
        return [
            Achado(
                "AIC-030",
                "atencao",
                f"Valor do {nome} não bate com base x alíquota",
                f"Base R$ {_brl(item.base)} x {_pct(aliquota)} = R$ {_brl(esperado)}, mas o item informa R$ {_brl(trib.valor)}.",
                "Confira a base de cálculo e a alíquota; a calculadora oficial da Receita ajuda a conferir.",
                item=item.numero,
                campo=f"g{sigla}/v{sigla}",
            )
        ]
    return []


def _auditar_totais(nota: Nota) -> list[Achado]:
    itens = [i for i in nota.itens if "gIBSCBS" in i.grupos]
    if not itens:
        return []
    tot = nota.totais
    if not tot.presente:
        return [
            Achado(
                "AIC-040",
                "erro",
                "Totais de IBS/CBS ausentes",
                "Há itens com IBS/CBS, mas a nota não tem o grupo total/IBSCBSTot.",
                "Gere o grupo IBSCBSTot com a soma dos itens.",
                campo="total/IBSCBSTot",
            )
        ]

    def soma(valores):
        vs = [v for v in valores if v is not None]
        return sum(vs, Decimal(0)) if vs else None

    contas = (
        ("vBCIBSCBS", "base de cálculo", tot.base, soma(i.base for i in itens)),
        ("gIBSUF/vIBSUF", "IBS estadual", tot.ibs_uf, soma(i.ibs_uf.valor for i in itens if i.ibs_uf)),
        ("gIBSMun/vIBSMun", "IBS municipal", tot.ibs_mun, soma(i.ibs_mun.valor for i in itens if i.ibs_mun)),
        ("gIBS/vIBS", "IBS", tot.ibs, soma(i.valor_ibs for i in itens)),
        ("gCBS/vCBS", "CBS", tot.cbs, soma(i.cbs.valor for i in itens if i.cbs)),
    )
    achados = []
    for campo, nome, informado, calculado in contas:
        if informado is None or calculado is None:
            continue
        if abs(informado - calculado) > TOLERANCIA:
            achados.append(
                Achado(
                    "AIC-041",
                    "erro",
                    f"Total de {nome} diferente da soma dos itens",
                    f"O total informa R$ {_brl(informado)}, mas a soma dos itens dá R$ {_brl(calculado)}.",
                    "O total da nota deve ser a soma dos valores dos itens.",
                    campo=f"IBSCBSTot/{campo}",
                )
            )
    return achados

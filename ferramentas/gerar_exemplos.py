"""Gera XMLs 100% fictícios em exemplos/ (um por situação que o auditor confere).

Empresas, CNPJs, produtos e valores são inventados. Os XMLs têm só os campos que o auditor lê;
não são documentos completos nem têm assinatura.

Uso: python ferramentas/gerar_exemplos.py
"""

from __future__ import annotations

import re
import zipfile
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "exemplos"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_BPE = "http://www.portalfiscal.inf.br/bpe"
NS_NF3E = "http://www.portalfiscal.inf.br/nf3e"
NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
CNPJ = "11222333000181"  # CNPJ de exemplo, fictício
DATA = "2026-11-20T10:15:00-03:00"


def dv_chave(chave43: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(chave43)))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def chave(modelo: int, numero: int, ano_mes: str = "2611") -> str:
    base = f"35{ano_mes}{CNPJ}{modelo:02d}001{numero:09d}1{numero:08d}"
    return base + dv_chave(base)


def q(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def q4(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))


def grupo_ibscbs(
    cst,
    cclass,
    vbc,
    p_uf="0.10",
    p_mun="0.00",
    p_cbs="0.90",
    red=None,
    sobrescrever=None,
    sem_gibscbs=False,
    dif=None,
    redutor=None,
    extra_gibscbs="",
    extra_grupo="",
    remover=(),
    dev=None,
):
    """Grupo IBSCBS de um item, com os valores calculados como a calculadora oficial faz.

    sobrescrever: força valores (ex.: {"vCBS": "2.00"}) para simular erros.
    dif: percentual de diferimento (gera gDif). redutor: redutor de compra governamental.
    """
    vbc = Decimal(vbc)
    s = sobrescrever or {}

    def bloco(tag, p):
        p = Decimal(p)
        efet = p * (1 - Decimal(red or 0) / 100) * (1 - Decimal(redutor or 0) / 100)
        efet_txt = s.get(f"pAliqEfet{tag}", q4(efet))
        calculado = (vbc * Decimal(efet_txt) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        gred = f"<gRed><pRedAliq>{q4(Decimal(red or 0))}</pRedAliq><pAliqEfet>{efet_txt}</pAliqEfet></gRed>" if (red is not None or redutor is not None) else ""
        gdif, vdif, gdev, vdev = "", Decimal(0), "", Decimal(0)
        if dev is not None and tag == "CBS":
            vdev = (vbc * Decimal(efet_txt) / 100 * Decimal(dev) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            vdev = Decimal(s.get("vDevTrib", q(vdev)))
            gdev = f"<gDevTrib><pDevTrib>{q4(Decimal(dev))}</pDevTrib><vDevTrib>{q(vdev)}</vDevTrib></gDevTrib>"
        if dif is not None:
            vdif = (vbc * Decimal(efet_txt) / 100 * Decimal(dif) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            vdif = Decimal(s.get(f"vDif{tag}", q(vdif)))
            gdif = f"<gDif><pDif>{q4(Decimal(dif))}</pDif><vDif>{q(vdif)}</vDif></gDif>"
        v = s.get(f"v{tag}", q(calculado - vdif - vdev))
        p_txt = s.get(f"p{tag}", q4(p))
        return f"<g{tag}><p{tag}>{p_txt}</p{tag}>{gdif}{gdev}{gred}<v{tag}>{v}</v{tag}></g{tag}>", Decimal(v), vdif

    uf_xml, v_uf, d_uf = bloco("IBSUF", p_uf)
    mun_xml, v_mun, d_mun = bloco("IBSMun", p_mun)
    cbs_xml, v_cbs, d_cbs = bloco("CBS", p_cbs)
    v_ibs = Decimal(s.get("vIBS", q(v_uf + v_mun)))
    vbc_txt = s.get("vBC", q(vbc))
    corpo = ""
    if not sem_gibscbs:
        corpo = f"<gIBSCBS><vBC>{vbc_txt}</vBC>{uf_xml}{mun_xml}<vIBS>{q(v_ibs)}</vIBS>{cbs_xml}{extra_gibscbs}</gIBSCBS>"
    for tag in remover:
        corpo = re.sub(f"<{tag}>.*?</{tag}>", "", corpo, count=1)
    xml = f"<IBSCBS><CST>{cst}</CST><cClassTrib>{cclass}</cClassTrib>{corpo}{extra_grupo}</IBSCBS>"
    valores = {
        "vBC": vbc,
        "vIBSUF": v_uf,
        "vIBSMun": v_mun,
        "vIBS": v_ibs,
        "vCBS": v_cbs,
        "difUF": d_uf,
        "difMun": d_mun,
        "difCBS": d_cbs,
    }
    return xml, {**valores, "tem": not sem_gibscbs}


def _total(soma: dict, t_extra: dict, extra_xml: str = "") -> str:
    t = {k: q(v) for k, v in soma.items()}
    t.update(t_extra)
    return (
        f"<IBSCBSTot><vBCIBSCBS>{t['vBC']}</vBCIBSCBS><gIBS><gIBSUF><vDif>{t['difUF']}</vDif><vDevTrib>0.00</vDevTrib>"
        f"<vIBSUF>{t['vIBSUF']}</vIBSUF></gIBSUF><gIBSMun><vDif>{t['difMun']}</vDif><vDevTrib>0.00</vDevTrib>"
        f"<vIBSMun>{t['vIBSMun']}</vIBSMun></gIBSMun><vIBS>{t['vIBS']}</vIBS><vCredPres>{t.get('credIBS', '0.00')}</vCredPres>"
        f"<vCredPresCondSus>0.00</vCredPresCondSus></gIBS><gCBS><vDif>{t['difCBS']}</vDif><vDevTrib>0.00</vDevTrib>"
        f"<vCBS>{t['vCBS']}</vCBS><vCredPres>{t.get('credCBS', '0.00')}</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus></gCBS>{extra_xml}</IBSCBSTot>"
    )


def _somar(itens):
    chaves = ("vBC", "vIBSUF", "vIBSMun", "vIBS", "vCBS", "difUF", "difMun", "difCBS")
    soma = {k: Decimal(0) for k in chaves}
    tem = False
    for grupo in itens:
        if grupo and grupo[1]["tem"]:
            tem = True
            for k in chaves:
                soma[k] += grupo[1][k]
    return soma, tem


def nota(
    numero,
    itens,
    modelo=55,
    crt="3",
    data=DATA,
    total_sobrescrever=None,
    ano_mes="2611",
    compra_gov=None,
    total_extra="",
    forcar_total=False,
    fin_nfe=None,
    tp_debito=None,
    tp_credito=None,
):
    """itens: lista de (descrição, grupo_ibscbs ou None, NCM) ou (descrição, grupo, NCM, prod_extra, imposto_extra)."""
    ch = chave(modelo, numero, ano_mes)
    dets = []
    for i, it in enumerate(itens, start=1):
        produto, grupo, ncm = it[:3]
        prod_extra, imposto_extra = (it[3], it[4]) if len(it) > 3 else ("", "")
        xml = grupo[0] if grupo else ""
        dets.append(
            f'<det nItem="{i}"><prod><cProd>{i:04d}</cProd><xProd>{produto}</xProd><NCM>{ncm}</NCM>{prod_extra}</prod>'
            f"<imposto>{imposto_extra}{xml}</imposto></det>"
        )
    soma, tem = _somar([it[1] for it in itens])
    total = _total(soma, total_sobrescrever or {}, total_extra) if (tem or forcar_total) else ""
    gov = f"<gCompraGov><tpEnteGov>1</tpEnteGov><pRedutor>{compra_gov}</pRedutor><tpOperGov>1</tpOperGov></gCompraGov>" if compra_gov else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<nfeProc xmlns="{NS_NFE}" versao="4.00"><NFe><infNFe Id="NFe{ch}" versao="4.00">'
        f"<ide><cUF>35</cUF><mod>{modelo}</mod><serie>1</serie><nNF>{numero}</nNF><dhEmi>{data}</dhEmi>"
        f"{f'<finNFe>{fin_nfe}</finNFe>' if fin_nfe else ''}{f'<tpNFDebito>{tp_debito}</tpNFDebito>' if tp_debito else ''}"
        f"{f'<tpNFCredito>{tp_credito}</tpNFCredito>' if tp_credito else ''}{gov}</ide>"
        f"<emit><CNPJ>{CNPJ}</CNPJ><xNome>EMPRESA FICTICIA EXEMPLO LTDA</xNome><CRT>{crt}</CRT></emit>"
        f"{''.join(dets)}<total>{total}</total></infNFe></NFe></nfeProc>\n"
    )


def cte(numero, grupo, modelo=57, crt="3"):
    ch = chave(modelo, numero)
    raiz, inf = ("cteOSProc", "CTeOS") if modelo == 67 else ("cteProc", "CTe")
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<{raiz} xmlns="{NS_CTE}" versao="4.00"><{inf}><infCte Id="CTe{ch}" versao="4.00">'
        f"<ide><cUF>35</cUF><mod>{modelo}</mod><serie>1</serie><nCT>{numero}</nCT><dhEmi>{DATA}</dhEmi></ide>"
        f"<emit><CNPJ>{CNPJ}</CNPJ><xNome>TRANSPORTADORA FICTICIA LTDA</xNome><CRT>{crt}</CRT></emit>"
        f"<imp>{grupo[0] if grupo else ''}</imp></infCte></{inf}></{raiz}>\n"
    )


def bpe(numero, grupo, crt="3"):
    ch = chave(63, numero)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<bpeProc xmlns="{NS_BPE}" versao="1.00"><BPe><infBPe Id="BPe{ch}" versao="1.00">'
        f"<ide><cUF>35</cUF><mod>63</mod><serie>1</serie><nBP>{numero}</nBP><dhEmi>{DATA}</dhEmi></ide>"
        f"<emit><CNPJ>{CNPJ}</CNPJ><xNome>VIACAO FICTICIA LTDA</xNome><CRT>{crt}</CRT></emit>"
        f"<imp>{grupo[0] if grupo else ''}</imp></infBPe></BPe></bpeProc>\n"
    )


def nf3e(numero, itens, total_sobrescrever=None):
    ch = chave(66, numero)
    dets = "".join(
        f'<det nItem="{i}"><detItem><prod><cProd>{i}</cProd><xProd>{d}</xProd></prod><imposto>{g[0]}</imposto></detItem></det>'
        for i, (d, g) in enumerate(itens, start=1)
    )
    soma, _ = _somar([g for _, g in itens])
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<nf3eProc xmlns="{NS_NF3E}" versao="1.00"><NF3e><infNF3e Id="NF3e{ch}" versao="1.00">'
        f"<ide><cUF>35</cUF><mod>66</mod><serie>1</serie><nNF>{numero}</nNF><dhEmi>{DATA}</dhEmi></ide>"
        f"<emit><CNPJ>{CNPJ}</CNPJ><xNome>DISTRIBUIDORA FICTICIA LTDA</xNome><CRT>3</CRT></emit>"
        f"<NFdet>{dets}</NFdet><total>{_total(soma, total_sobrescrever or {})}</total></infNF3e></NF3e></nf3eProc>\n"
    )


def nfse(numero, cst, cclass, nbs, vbc, sobrescrever=None, autorizada=True):
    """NFS-e nacional: DPS (CST, cClassTrib, NBS) e, se autorizada, o bloco calculado."""
    s = sobrescrever or {}
    vbc = Decimal(vbc)
    p = {"UF": Decimal("0.10"), "Mun": Decimal("0.00"), "CBS": Decimal("0.90")}
    v = {k: Decimal(s.get(f"v{k}", q(vbc * a / 100))) for k, a in p.items()}
    dps = (
        f"<DPS><infDPS><dhEmi>{DATA}</dhEmi><serie>900</serie><nDPS>{numero}</nDPS><prest><CNPJ>{CNPJ}</CNPJ></prest>"
        f"<serv><cServ><cTribNac>010101</cTribNac><xDescServ>SERVICO FICTICIO DE EXEMPLO</xDescServ><cNBS>{nbs}</cNBS></cServ></serv>"
        f"<IBSCBS><finNFSe>0</finNFSe><cIndOp>100301</cIndOp><indDest>0</indDest><valores><trib><gIBSCBS>"
        f"<CST>{cst}</CST><cClassTrib>{cclass}</cClassTrib></gIBSCBS></trib></valores></IBSCBS></infDPS></DPS>"
    )
    calc = ""
    if autorizada:
        calc = (
            f"<IBSCBS><cLocalidadeIncid>3550308</cLocalidadeIncid><xLocalidadeIncid>Sao Paulo</xLocalidadeIncid>"
            f"<valores><vBC>{q(vbc)}</vBC><uf><pIBSUF>0.10</pIBSUF><pAliqEfetUF>0.10</pAliqEfetUF></uf>"
            f"<mun><pIBSMun>0.00</pIBSMun><pAliqEfetMun>0.00</pAliqEfetMun></mun><fed><pCBS>0.90</pCBS><pAliqEfetCBS>0.90</pAliqEfetCBS></fed></valores>"
            f"<totCIBS><vTotNF>{q(vbc)}</vTotNF><gIBS><vIBSTot>{q(v['UF'] + v['Mun'])}</vIBSTot><gIBSUFTot><vIBSUF>{q(v['UF'])}</vIBSUF></gIBSUFTot>"
            f"<gIBSMunTot><vIBSMun>{q(v['Mun'])}</vIBSMun></gIBSMunTot></gIBS><gCBS><vCBS>{q(v['CBS'])}</vCBS></gCBS></totCIBS></IBSCBS>"
        )
    if autorizada:
        corpo = f'<NFSe xmlns="{NS_NFSE}"><infNFSe Id="NFS3550308{numero:041d}"><nNFSe>{numero}</nNFSe>{calc}{dps}</infNFSe></NFSe>'
    else:
        corpo = dps.replace("<DPS>", f'<DPS xmlns="{NS_NFSE}">', 1)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{corpo}\n'


CANETA, CADERNO, ARROZ, ENERGIA, PECA, GASOLINA = "96081000", "48201000", "10063021", "27160000", "87089990", "27101259"

CRED_PRES = (
    "<gCredPresOper><vBCCredPres>100.00</vBCCredPres><cCredPres>01</cCredPres>"
    "<gIBSCredPres><pCredPres>10.0000</pCredPres><vCredPres>5.00</vCredPres></gIBSCredPres></gCredPresOper>"
)
COMPRA_GOV = (
    "<gTribCompraGov><pAliqIBSUF>0.1000</pAliqIBSUF><vTribIBSUF>0.10</vTribIBSUF><pAliqIBSMun>0.0000</pAliqIBSMun>"
    "<vTribIBSMun>0.00</vTribIBSMun><pAliqCBS>0.9000</pAliqCBS><vTribCBS>1.00</vTribCBS></gTribCompraGov>"
)
TRIB_REGULAR = (
    "<gTribRegular><CSTReg>000</CSTReg><cClassTribReg>200003</cClassTribReg><pAliqEfetRegIBSUF>0.1000</pAliqEfetRegIBSUF>"
    "<vTribRegIBSUF>0.10</vTribRegIBSUF><pAliqEfetRegIBSMun>0.0000</pAliqEfetRegIBSMun><vTribRegIBSMun>0.00</vTribRegIBSMun>"
    "<pAliqEfetRegCBS>0.9000</pAliqEfetRegCBS><vTribRegCBS>0.90</vTribRegCBS></gTribRegular>"
)


def mono_grupo(v_ibs: str = "100.00", v_cbs: str = "50.00", tot_ibs: str | None = None) -> str:
    """Grupo monofásico de 100 litros com ad rem de R$ 1,00 (IBS) e R$ 0,50 (CBS)."""
    return (
        "<IBSCBS><CST>620</CST><cClassTrib>620001</cClassTrib><gIBSCBSMono><gMonoPadrao><qBCMono>100.0000</qBCMono>"
        f"<adRemIBS>1.0000</adRemIBS><adRemCBS>0.5000</adRemCBS><vIBSMono>{v_ibs}</vIBSMono><vCBSMono>{v_cbs}</vCBSMono></gMonoPadrao>"
        f"<vTotIBSMonoItem>{tot_ibs or v_ibs}</vTotIBSMonoItem><vTotCBSMonoItem>{v_cbs}</vTotCBSMonoItem></gIBSCBSMono></IBSCBS>"
    )


MONO = mono_grupo()


def mono_nota(numero: int = 1026, v_ibs: str = "100.00", tot_ibs: str | None = None):
    corpo = nota(numero, [("GASOLINA FICTICIA", None, GASOLINA)])
    corpo = corpo.replace("<imposto></imposto>", f"<imposto>{mono_grupo(v_ibs, tot_ibs=tot_ibs)}</imposto>")
    tot = (
        f"<IBSCBSTot><vBCIBSCBS>0.00</vBCIBSCBS><gMono><vIBSMono>{v_ibs}</vIBSMono><vCBSMono>50.00</vCBSMono>"
        "<vIBSMonoReten>0.00</vIBSMonoReten><vCBSMonoReten>0.00</vCBSMonoReten><vIBSMonoRet>0.00</vIBSMonoRet><vCBSMonoRet>0.00</vCBSMonoRet></gMono></IBSCBSTot>"
    )
    return corpo.replace("<total></total>", f"<total>{tot}</total>")


EXEMPLOS = {
    "01-correta.xml": nota(
        1001,
        [
            ("CANETA AZUL", grupo_ibscbs("000", "000001", "150.00"), CANETA),
            ("CADERNO 96 FOLHAS", grupo_ibscbs("000", "000001", "37.90"), CADERNO),
        ],
    ),
    "02-sem-grupo-regime-normal.xml": nota(1002, [("CANETA AZUL", None, CANETA)]),
    "03-sem-grupo-simples-nacional.xml": nota(1003, [("CANETA AZUL", None, CANETA)], crt="1"),
    "04-cclasstrib-de-outro-cst.xml": nota(1004, [("ARROZ 5KG", grupo_ibscbs("000", "200003", "29.90"), ARROZ)]),
    "05-cclasstrib-inexistente.xml": nota(1005, [("CANETA AZUL", grupo_ibscbs("000", "999999", "10.00"), CANETA)]),
    "06-cclasstrib-nao-permitido-nfce.xml": nota(1006, [("PECA AUTOMOTIVA", grupo_ibscbs("000", "000003", "80.00"), PECA)], modelo=65),
    "07-valores-errados.xml": nota(
        1007,
        [("MOCHILA", grupo_ibscbs("000", "000001", "200.00", sobrescrever={"vCBS": "2.00", "vIBS": "0.50"}), "42029200")],
        total_sobrescrever={"vBC": "210.00"},
    ),
    "08-reducao-diferente-da-oficial.xml": nota(1008, [("ARROZ 5KG", grupo_ibscbs("200", "200003", "29.90", red="60"), ARROZ)]),
    "09-grupo-gibscbs-ausente.xml": nota(1009, [("CANETA AZUL", grupo_ibscbs("000", "000001", "10.00", sem_gibscbs=True), CANETA)]),
    "10-reducao-correta-cesta-basica.xml": nota(1010, [("ARROZ 1KG", grupo_ibscbs("200", "200003", "8.50", red="100"), ARROZ)]),
    "11-antes-da-reforma.xml": nota(1011, [("CANETA AZUL", None, CANETA)], data="2025-12-15T09:00:00-03:00", ano_mes="2512"),
    "12-cclasstrib-encerrado.xml": nota(1012, [("SERVICO EXEMPLO", grupo_ibscbs("220", "220001", "50.00"), "00")]),
    "13-xml-com-doctype.xml": '<?xml version="1.0"?>\n<!DOCTYPE x [<!ENTITY a "aaaa">]>\n<nfeProc>&a;</nfeProc>\n',
    "14-nao-e-documento-fiscal.xml": '<?xml version="1.0"?>\n<pedido><numero>1</numero></pedido>\n',
    "15-ncm-fora-da-lista-cesta-basica.xml": nota(1015, [("CADERNO 96 FOLHAS", grupo_ibscbs("200", "200003", "37.90", red="100"), CADERNO)]),
    "16-ncm-zerado-com-cclasstrib-de-lista.xml": nota(1016, [("ARROZ 5KG", grupo_ibscbs("200", "200003", "29.90", red="100"), "00000000")]),
    "17-ncm-inexistente.xml": nota(1017, [("PRODUTO GENERICO", grupo_ibscbs("000", "000001", "10.00"), "99999999")]),
    "18-formato-invalido.xml": nota(
        1018,
        [("CANETA AZUL", grupo_ibscbs("000", "000001", "1500.00", sobrescrever={"vBC": "1,500.00", "pIBSUF": "0.1"}), CANETA)],
    ),
    "19-campo-obrigatorio-ausente.xml": nota(1019, [("CANETA AZUL", grupo_ibscbs("000", "000001", "10.00", remover=("vIBS",)), CANETA)]),
    "20-diferimento-valor-errado.xml": nota(
        1020,
        [("ENERGIA ELETRICA", grupo_ibscbs("510", "510001", "1000.00", dif="100", sobrescrever={"vDifCBS": "5.00"}), ENERGIA)],
    ),
    "21-diferimento-correto.xml": nota(1021, [("ENERGIA ELETRICA", grupo_ibscbs("510", "510001", "1000.00", dif="100"), ENERGIA)]),
    "22-aliquota-efetiva-errada.xml": nota(
        1022, [("ARROZ 5KG", grupo_ibscbs("200", "200003", "29.90", red="100", sobrescrever={"pAliqEfetCBS": "0.5000"}), ARROZ)]
    ),
    "23-credito-presumido-errado.xml": nota(
        1023,
        [("PECA AUTOMOTIVA", grupo_ibscbs("000", "000003", "100.00", extra_grupo=CRED_PRES), PECA)],
        total_sobrescrever={"credIBS": "5.00"},
    ),
    "24-compra-governamental-errada.xml": nota(
        1024,
        [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00", red="0", redutor="10", extra_gibscbs=COMPRA_GOV), CANETA)],
        compra_gov="10.0000",
    ),
    "25-tributacao-regular-par-errado.xml": nota(1025, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00", extra_gibscbs=TRIB_REGULAR), CANETA)]),
    "26-monofasico.xml": mono_nota(),
    "27-total-diferido-errado.xml": nota(
        1027,
        [("ENERGIA ELETRICA", grupo_ibscbs("510", "510001", "1000.00", dif="100"), ENERGIA)],
        total_sobrescrever={"difCBS": "1.00"},
    ),
    "28-cte-correto.xml": cte(2001, grupo_ibscbs("000", "000001", "500.00")),
    "29-cte-cclasstrib-nao-permitido.xml": cte(2002, grupo_ibscbs("200", "200003", "500.00", red="100")),
    "30-cte-os-correto.xml": cte(2003, grupo_ibscbs("000", "000001", "300.00"), modelo=67),
    "31-bpe-sem-grupo.xml": bpe(3001, None),
    "32-nf3e-total-errado.xml": nf3e(
        4001,
        [("ENERGIA", grupo_ibscbs("000", "000001", "250.00")), ("ILUMINACAO", grupo_ibscbs("000", "000001", "30.00"))],
        total_sobrescrever={"vCBS": "9.99"},
    ),
    "33-nfse-correta.xml": nfse(5001, "000", "000001", "101011100", "1000.00"),
    "34-nfse-nbs-fora-da-lista.xml": nfse(5002, "200", "200028", "101011100", "1000.00"),
    "35-nfse-valor-errado.xml": nfse(5003, "000", "000001", "101011100", "1000.00", sobrescrever={"vCBS": "8.00"}),
    "36-dps-sem-nbs-obrigatorio.xml": nfse(5004, "200", "200028", "", "1000.00", autorizada=False),
}
_caneta = [("CANETA AZUL", grupo_ibscbs("000", "000001", "150.00"), CANETA)]
EXEMPLOS["37-modelo-nao-suportado.xml"] = nota(1037, _caneta, modelo=59)
EXEMPLOS["38-sem-data-de-emissao.xml"] = nota(1038, _caneta).replace(f"<dhEmi>{DATA}</dhEmi>", "")
EXEMPLOS["39-sem-totais.xml"] = nota(1039, _caneta).split("<total>")[0] + "<total></total></infNFe></NFe></nfeProc>\n"

# Regras da NT 2025.002-RTC v1.53
_PROD_100 = "<vProd>100.00</vProd><vDesc>10.00</vDesc>"
_ICMS_18 = "<ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>90.00</vBC><pICMS>20.00</pICMS><vICMS>18.00</vICMS></ICMS00></ICMS>"
EXEMPLOS["40-reducao-nao-permitida.xml"] = nota(1040, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00", red="10"), CANETA)])
EXEMPLOS["41-reducao-ausente-cst-200.xml"] = nota(1041, [("ARROZ 5KG", grupo_ibscbs("200", "200003", "29.90"), ARROZ)])
EXEMPLOS["42-devolucao-cbs-valor-errado.xml"] = nota(
    1042, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00", dev="100", sobrescrever={"vDevTrib": "0.50"}), CANETA)]
)
EXEMPLOS["43-base-calculo-divergente.xml"] = nota(1043, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00"), CANETA, _PROD_100, _ICMS_18)])
EXEMPLOS["44-base-calculo-correta.xml"] = nota(1044, [("CANETA AZUL", grupo_ibscbs("000", "000001", "72.00"), CANETA, _PROD_100, _ICMS_18)])
EXEMPLOS["45-totais-sem-itens-com-ibscbs.xml"] = nota(1045, [("CANETA AZUL", None, CANETA)], forcar_total=True)
EXEMPLOS["46-nfce-com-compra-governamental.xml"] = nota(
    1046, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00", red="0", redutor="10"), CANETA)], modelo=65, compra_gov="10.0000"
)
EXEMPLOS["47-nota-debito-cclasstrib-incompativel.xml"] = nota(
    1047, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00"), CANETA)], fin_nfe="6", tp_debito="07"
)
EXEMPLOS["48-estorno-informado-indevidamente.xml"] = nota(
    1048,
    [
        (
            "CANETA AZUL",
            grupo_ibscbs("000", "000001", "100.00", extra_grupo="<gEstornoCred><vIBSEstCred>0.10</vIBSEstCred><vCBSEstCred>0.90</vCBSEstCred></gEstornoCred>"),
            CANETA,
        )
    ],
)
EXEMPLOS["49-transferencia-fora-nota-debito.xml"] = nota(
    1049,
    [
        (
            "TRANSFERENCIA",
            ("<IBSCBS><CST>800</CST><cClassTrib>800001</cClassTrib><gTransfCred><vIBS>0.00</vIBS><vCBS>0.00</vCBS></gTransfCred></IBSCBS>", {"tem": False}),
            "00",
        )
    ],
)
EXEMPLOS["50-diferimento-nao-permitido.xml"] = nota(1050, [("CANETA AZUL", grupo_ibscbs("000", "000001", "100.00", dif="100"), CANETA)])
# 100 litros x R$ 1,00 de IBS ad rem = R$ 100,00, mas a nota informa R$ 90,00 (e o total do item, R$ 95,00)
EXEMPLOS["51-monofasico-valor-errado.xml"] = mono_nota(1051, v_ibs="90.00", tot_ibs="95.00")


def main() -> None:
    PASTA.mkdir(exist_ok=True)
    for antigo in PASTA.glob("*.xml"):
        antigo.unlink()
    for nome, conteudo in EXEMPLOS.items():
        (PASTA / nome).write_text(conteudo, encoding="utf-8", newline="\n")
    with zipfile.ZipFile(PASTA / "lote-exemplo.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for nome in ("01-correta.xml", "04-cclasstrib-de-outro-cst.xml", "07-valores-errados.xml"):
            info = zipfile.ZipInfo(f"lote/{nome}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, EXEMPLOS[nome])
    print(f"{len(EXEMPLOS)} XMLs e lote-exemplo.zip em {PASTA}")


if __name__ == "__main__":
    main()

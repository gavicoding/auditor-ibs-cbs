"""Gera XMLs 100% fictícios em exemplos/ (um por situação que o auditor confere).

Empresas, CNPJs, produtos e valores são inventados. Os XMLs têm só os campos que o auditor lê;
não são notas completas nem têm assinatura.

Uso: python ferramentas/gerar_exemplos.py
"""

from __future__ import annotations

import zipfile
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "exemplos"
NS = "http://www.portalfiscal.inf.br/nfe"
CNPJ = "11222333000181"  # CNPJ de exemplo, fictício


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


def grupo_ibscbs(cst, cclass, vbc, p_uf="0.10", p_mun="0.00", p_cbs="0.90", red=None, sobrescrever=None, sem_gibscbs=False):
    vbc = Decimal(vbc)
    s = sobrescrever or {}

    def bloco(tag, p):
        p = Decimal(p)
        efet = p * (1 - Decimal(red) / 100) if red is not None else p
        v = s.get(f"v{tag}", q(vbc * efet / 100))
        gred = f"<gRed><pRedAliq>{Decimal(red):.4f}</pRedAliq><pAliqEfet>{efet:.4f}</pAliqEfet></gRed>" if red is not None else ""
        return f"<g{tag}><p{tag}>{p:.4f}</p{tag}>{gred}<v{tag}>{v}</v{tag}></g{tag}>", Decimal(v)

    uf_xml, v_uf = bloco("IBSUF", p_uf)
    mun_xml, v_mun = bloco("IBSMun", p_mun)
    cbs_xml, v_cbs = bloco("CBS", p_cbs)
    v_ibs = Decimal(s.get("vIBS", q(v_uf + v_mun)))
    if sem_gibscbs:
        corpo = ""
    else:
        corpo = f"<gIBSCBS><vBC>{q(vbc)}</vBC>{uf_xml}{mun_xml}<vIBS>{q(v_ibs)}</vIBS>{cbs_xml}</gIBSCBS>"
    xml = f"<IBSCBS><CST>{cst}</CST><cClassTrib>{cclass}</cClassTrib>{corpo}</IBSCBS>"
    return xml, {"vBC": vbc, "vIBSUF": v_uf, "vIBSMun": v_mun, "vIBS": v_ibs, "vCBS": v_cbs, "tem": not sem_gibscbs}


def nota(numero, itens, modelo=55, crt="3", data="2026-11-20T10:15:00-03:00", total_sobrescrever=None, ano_mes="2611"):
    ch = chave(modelo, numero, ano_mes)
    dets, soma = [], {k: Decimal(0) for k in ("vBC", "vIBSUF", "vIBSMun", "vIBS", "vCBS")}
    tem_grupo = False
    for i, (produto, grupo) in enumerate(itens, start=1):
        if grupo:
            xml, val = grupo
            if val["tem"]:
                tem_grupo = True
                for k in soma:
                    soma[k] += val[k]
        else:
            xml = ""
        dets.append(f'<det nItem="{i}"><prod><cProd>{i:04d}</cProd><xProd>{produto}</xProd></prod><imposto>{xml}</imposto></det>')
    t = {k: q(v) for k, v in soma.items()}
    t.update(total_sobrescrever or {})
    total = ""
    if tem_grupo:
        total = (
            f"<IBSCBSTot><vBCIBSCBS>{t['vBC']}</vBCIBSCBS><gIBS><gIBSUF><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib>"
            f"<vIBSUF>{t['vIBSUF']}</vIBSUF></gIBSUF><gIBSMun><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib>"
            f"<vIBSMun>{t['vIBSMun']}</vIBSMun></gIBSMun><vIBS>{t['vIBS']}</vIBS><vCredPres>0.00</vCredPres>"
            f"<vCredPresCondSus>0.00</vCredPresCondSus></gIBS><gCBS><vDif>0.00</vDif><vDevTrib>0.00</vDevTrib>"
            f"<vCBS>{t['vCBS']}</vCBS><vCredPres>0.00</vCredPres><vCredPresCondSus>0.00</vCredPresCondSus></gCBS></IBSCBSTot>"
        )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<nfeProc xmlns="{NS}" versao="4.00"><NFe><infNFe Id="NFe{ch}" versao="4.00">'
        f"<ide><cUF>35</cUF><mod>{modelo}</mod><serie>1</serie><nNF>{numero}</nNF><dhEmi>{data}</dhEmi></ide>"
        f"<emit><CNPJ>{CNPJ}</CNPJ><xNome>EMPRESA FICTICIA EXEMPLO LTDA</xNome><CRT>{crt}</CRT></emit>"
        f"{''.join(dets)}<total>{total}</total></infNFe></NFe></nfeProc>\n"
    )


EXEMPLOS = {
    "01-correta.xml": nota(
        1001,
        [("CANETA AZUL", grupo_ibscbs("000", "000001", "150.00")), ("CADERNO 96 FOLHAS", grupo_ibscbs("000", "000001", "37.90"))],
    ),
    "02-sem-grupo-regime-normal.xml": nota(1002, [("CANETA AZUL", None)]),
    "03-sem-grupo-simples-nacional.xml": nota(1003, [("CANETA AZUL", None)], crt="1"),
    "04-cclasstrib-de-outro-cst.xml": nota(1004, [("ARROZ 5KG", grupo_ibscbs("000", "200003", "29.90"))]),
    "05-cclasstrib-inexistente.xml": nota(1005, [("CANETA AZUL", grupo_ibscbs("000", "999999", "10.00"))]),
    "06-cclasstrib-nao-permitido-nfce.xml": nota(1006, [("PECA AUTOMOTIVA", grupo_ibscbs("000", "000003", "80.00"))], modelo=65),
    "07-valores-errados.xml": nota(
        1007,
        [("MOCHILA", grupo_ibscbs("000", "000001", "200.00", sobrescrever={"vCBS": "2.00", "vIBS": "0.50"}))],
        total_sobrescrever={"vBC": "210.00"},
    ),
    "08-reducao-diferente-da-oficial.xml": nota(1008, [("ARROZ 5KG", grupo_ibscbs("200", "200003", "29.90", red="60"))]),
    "09-grupo-gibscbs-ausente.xml": nota(1009, [("CANETA AZUL", grupo_ibscbs("000", "000001", "10.00", sem_gibscbs=True))]),
    "10-reducao-correta-cesta-basica.xml": nota(1010, [("FEIJAO 1KG", grupo_ibscbs("200", "200003", "8.50", red="100"))]),
    "11-antes-da-reforma.xml": nota(1011, [("CANETA AZUL", None)], data="2025-12-15T09:00:00-03:00", ano_mes="2512"),
    "12-cclasstrib-encerrado.xml": nota(1012, [("SERVICO EXEMPLO", grupo_ibscbs("220", "220001", "50.00"))]),
    "13-xml-com-doctype.xml": '<?xml version="1.0"?>\n<!DOCTYPE x [<!ENTITY a "aaaa">]>\n<nfeProc>&a;</nfeProc>\n',
    "14-nao-e-nfe.xml": '<?xml version="1.0"?>\n<pedido><numero>1</numero></pedido>\n',
}


def main() -> None:
    PASTA.mkdir(exist_ok=True)
    for nome, conteudo in EXEMPLOS.items():
        (PASTA / nome).write_text(conteudo, encoding="utf-8")
    with zipfile.ZipFile(PASTA / "lote-exemplo.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for nome in ("01-correta.xml", "04-cclasstrib-de-outro-cst.xml", "07-valores-errados.xml"):
            z.writestr(f"lote/{nome}", EXEMPLOS[nome])
    print(f"{len(EXEMPLOS)} XMLs e lote-exemplo.zip em {PASTA}")


if __name__ == "__main__":
    main()

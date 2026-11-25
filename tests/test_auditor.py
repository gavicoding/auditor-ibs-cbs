import copy
import json
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from auditor_ibs_cbs import XMLInvalido, auditar, carregar, ler_bytes
from auditor_ibs_cbs.cli import main
from auditor_ibs_cbs.leitor import TAMANHO_MAXIMO, percorrer
from auditor_ibs_cbs.regras import arredondar
from auditor_ibs_cbs.relatorio import csv_, resumo
from auditor_ibs_cbs.tabelas import Tabelas

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLOS = RAIZ / "exemplos"
ESPERADO = json.loads((Path(__file__).parent / "esperado.json").read_text(encoding="utf-8"))
T = carregar()
TOTAL_XML = len(list(EXEMPLOS.glob("*.xml")))


def ler(nome: str):
    return ler_bytes((EXEMPLOS / nome).read_bytes(), nome)


def codigos(nome: str, tabelas=T) -> list[list]:
    r = auditar(ler(nome), tabelas)
    return sorted(([a.codigo, a.gravidade, a.item, a.rejeicao] for a in r.achados), key=lambda x: (x[0], x[1], x[2] or "", x[3] or ""))


@pytest.mark.parametrize("nome", sorted(k for k in ESPERADO if not ESPERADO[k].get("ilegivel")))
def test_exemplos_batem_com_o_esperado(nome):
    assert codigos(nome) == ESPERADO[nome]["achados"]


@pytest.mark.parametrize("nome", sorted(k for k in ESPERADO if ESPERADO[k].get("ilegivel")))
def test_exemplos_ilegiveis_sao_recusados(nome):
    with pytest.raises(XMLInvalido):
        ler(nome)


def test_gabarito_cobre_todos_os_exemplos():
    assert sorted(ESPERADO) == sorted(p.name for p in EXEMPLOS.glob("*.xml"))


@pytest.mark.parametrize(
    "nome",
    [
        "01-correta.xml",
        "10-reducao-correta-cesta-basica.xml",
        "21-diferimento-correto.xml",
        "28-cte-correto.xml",
        "30-cte-os-correto.xml",
        "33-nfse-correta.xml",
    ],
)
def test_documentos_corretos_nao_tem_achados(nome):
    assert codigos(nome) == []


def test_tipos_de_documento_reconhecidos():
    tipos = {
        ler(n).tipo
        for n in (
            "01-correta.xml",
            "06-cclasstrib-nao-permitido-nfce.xml",
            "28-cte-correto.xml",
            "30-cte-os-correto.xml",
            "31-bpe-sem-grupo.xml",
            "32-nf3e-total-errado.xml",
            "33-nfse-correta.xml",
        )
    }
    assert tipos == {"NF-e", "NFC-e", "CT-e", "CT-e OS", "BP-e", "NF3-e", "NFS-e"}


# ---------- tabelas ----------


def test_tabelas_tem_fonte_e_versao():
    assert T.fonte["licenca"] == "MIT"
    assert T.fonte["url"].startswith("https://github.com/ReceitaFederal/")
    assert T.fonte["versao_base"].startswith("V")


def test_todo_cclasstrib_aponta_para_um_cst_existente():
    for codigo, reg in T.dados["cclasstrib"].items():
        assert len(codigo) == 6 and codigo.isdigit()
        assert T.cst(reg["cst"]) is not None, codigo


def test_aliquotas_de_referencia_2026():
    dia = date(2026, 6, 1)
    assert T.aliquota_referencia("CBS", dia) == 0.9
    assert T.aliquota_referencia("IBSUF", dia) == 0.1
    assert T.aliquota_referencia("IBSMun", dia) == 0.0


def test_reducao_oficial_cesta_basica():
    assert T.reducao("200003", "CBS", date(2026, 6, 1)) == 100.0


def test_ncm_aplicavel_por_prefixo_e_com_excecao():
    dia = date(2026, 6, 1)
    assert T.tem_lista("200003", "ncm", dia)
    assert T.aplicavel("200003", "ncm", "10063021", dia)  # arroz
    assert T.aplicavel("200003", "ncm", "02071100", dia)  # frango, coberto pelo prefixo 0207
    assert not T.aplicavel("200003", "ncm", "02074300", dia)  # exceção oficial dentro do 0207
    assert not T.aplicavel("200003", "ncm", "48201000", dia)  # caderno
    assert not T.tem_lista("000001", "ncm", dia)


def test_anexos_e_tabela_ncm():
    dia = date(2026, 6, 1)
    assert any(a.startswith("Anexo I,") for a in T.anexos_do_cclasstrib("200003", "ncm", dia))
    assert T.ncm("10063021") is not None
    assert T.ncm("99999999") is None


def test_cst_fora_da_vigencia_com_tabela_modificada():
    dados = copy.deepcopy(T.dados)
    dados["cst"]["000"]["fim"] = "2026-06-30"
    tabela = Tabelas(dados)
    assert ["AIC-012", "erro", "1", None] in codigos("01-correta.xml", tabela)


# ---------- cálculo ----------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("0.125", "0.12"), ("0.135", "0.14"), ("1.005", "1.00"), ("2.675", "2.68"), ("10", "10.00")],
)
def test_arredondamento_bancario(valor, esperado):
    assert arredondar(Decimal(valor)) == Decimal(esperado)


def test_diferenca_de_um_centavo_e_tolerada():
    xml = (EXEMPLOS / "01-correta.xml").read_text(encoding="utf-8").replace("<vCBS>1.35</vCBS>", "<vCBS>1.36</vCBS>", 1)
    r = auditar(ler_bytes(xml.encode(), "x"), T)
    assert "AIC-030" not in {a.codigo for a in r.achados}


def test_numero_fora_do_formato_nao_vira_valor():
    xml = (EXEMPLOS / "01-correta.xml").read_text(encoding="utf-8").replace("<vBC>150.00</vBC>", "<vBC>1_50.00</vBC>", 1)
    nota = ler_bytes(xml.encode(), "x")
    assert nota.itens[0].base is None


# ---------- segurança e leitura ----------


def test_recusa_entity_mesmo_sem_doctype_no_inicio():
    with pytest.raises(XMLInvalido):
        ler_bytes(b"<a>" + b" " * 5000 + b'<!ENTITY x "y"></a>', "x")


def test_recusa_arquivo_grande():
    with pytest.raises(XMLInvalido):
        ler_bytes(b"<a>" + b"x" * (TAMANHO_MAXIMO + 1) + b"</a>", "x")


def test_xml_mal_formado():
    with pytest.raises(XMLInvalido):
        ler_bytes(b"<nfeProc><NFe>", "x")


def test_funciona_sem_namespace_e_sem_nfeproc():
    xml = (EXEMPLOS / "01-correta.xml").read_text(encoding="utf-8")
    xml = xml.replace(' xmlns="http://www.portalfiscal.inf.br/nfe"', "")
    inicio = xml.index("<NFe>")
    fim = xml.index("</NFe>") + len("</NFe>")
    nota = ler_bytes(xml[inicio:fim].encode(), "x")
    assert nota.modelo == 55 and len(nota.itens) == 2


def test_zip_e_pasta():
    origem = [o for o, _ in percorrer([EXEMPLOS / "lote-exemplo.zip"])]
    assert len(origem) == 3 and all("!lote/" in o for o in origem)
    assert sum(1 for _ in percorrer([EXEMPLOS])) == TOTAL_XML + 3


def test_zip_ignora_o_que_nao_e_xml(tmp_path):
    z = tmp_path / "misto.zip"
    with zipfile.ZipFile(z, "w") as arq:
        arq.writestr("leia.txt", "oi")
        arq.writestr("nota.xml", (EXEMPLOS / "01-correta.xml").read_text(encoding="utf-8"))
    assert [o.split("!")[1] for o, _ in percorrer([z])] == ["nota.xml"]


def test_relatorio_nao_inclui_dados_do_destinatario():
    xml = (EXEMPLOS / "02-sem-grupo-regime-normal.xml").read_text(encoding="utf-8")
    xml = xml.replace("</emit>", "</emit><dest><CPF>12345678909</CPF><xNome>MARIA FICTICIA</xNome></dest>")
    r = auditar(ler_bytes(xml.encode(), "x"), T)
    texto = json.dumps(r.como_dict(), ensure_ascii=False) + csv_([r])
    assert "12345678909" not in texto and "MARIA" not in texto


def test_csv_neutraliza_formulas():
    r = auditar(ler_bytes((EXEMPLOS / "02-sem-grupo-regime-normal.xml").read_bytes(), "=HYPERLINK(1).xml"), T)
    saida = csv_([r])
    assert "\n'=HYPERLINK(1).xml;" in saida
    assert "\n=HYPERLINK" not in saida


# ---------- resumo ----------


def test_resumo_consolidado():
    resultados = []
    for p in sorted(EXEMPLOS.glob("*.xml")):
        try:
            resultados.append(auditar(ler_bytes(p.read_bytes(), p.name), T))
        except XMLInvalido:
            pass
    s = resumo(resultados)
    assert s["notas"] == len(resultados)
    assert s["ok"] + s["com_atencao"] + s["com_erro"] == s["notas"]
    assert {"NF-e", "NFC-e", "CT-e", "CT-e OS", "BP-e", "NF3-e", "NFS-e"} <= set(s["por_tipo"])
    assert "200003" in dict(s["itens_com_problema_por_cclasstrib"])
    assert Decimal(s["valores_por_cclasstrib"]["000001"]["base"]) > 0


# ---------- XSD (opcional) ----------


def test_xsd_aponta_erros_de_leiaute():
    pytest.importorskip("xmlschema")
    from auditor_ibs_cbs.xsd import validar

    erros = validar((EXEMPLOS / "01-correta.xml").read_bytes())
    assert erros  # o exemplo é propositalmente incompleto (só os campos que o auditor lê)
    assert validar(b"<pedido/>") is None


# ---------- linha de comando ----------


def test_cli_codigo_de_saida():
    assert main(["auditar", str(EXEMPLOS / "01-correta.xml"), "--falhar-em", "erro"]) == 0
    assert main(["auditar", str(EXEMPLOS / "08-reducao-diferente-da-oficial.xml"), "--falhar-em", "erro"]) == 1
    # sem o grupo IBS/CBS é atenção: a rejeição 1115 ainda é "implementação futura" em produção
    assert main(["auditar", str(EXEMPLOS / "02-sem-grupo-regime-normal.xml"), "--falhar-em", "erro"]) == 0
    assert main(["auditar", str(EXEMPLOS / "02-sem-grupo-regime-normal.xml"), "--falhar-em", "atencao"]) == 1


def test_achado_traz_a_regra_oficial():
    r = auditar(ler((EXEMPLOS / "07-valores-errados.xml").name), T)
    total = next(a for a in r.achados if a.codigo == "AIC-041")
    assert (total.rejeicao, total.regra_nt, total.pagina_nt, total.em_producao) == ("1076", "W35-10", 71, True)
    aviso = auditar(ler("02-sem-grupo-regime-normal.xml"), T).achados[0]
    assert (aviso.rejeicao, aviso.em_producao, aviso.gravidade) == ("1115", False, "atencao")


def test_total_exige_igualdade_exata():
    xml = (EXEMPLOS / "01-correta.xml").read_text(encoding="utf-8").replace("<vCBS>1.69</vCBS><vCredPres>", "<vCBS>1.70</vCBS><vCredPres>")
    r = auditar(ler_bytes(xml.encode(), "x"), T)
    assert any(a.codigo == "AIC-041" and a.rejeicao == "1091" for a in r.achados)


@pytest.mark.parametrize("formato", ["texto", "json", "csv", "md", "html", "resumo-csv"])
def test_cli_formatos(tmp_path, formato):
    saida = tmp_path / f"r.{formato}"
    assert main(["auditar", str(EXEMPLOS), "-f", formato, "-o", str(saida)]) == 0
    conteudo = saida.read_text(encoding="utf-8")
    if formato == "resumo-csv":
        assert "200003" in conteudo and "base_calculo" in conteudo
        return
    assert "AIC-015" in conteudo
    if formato == "json":
        dados = json.loads(conteudo)
        assert dados["resumo"]["notas"] == TOTAL_XML + 3
        assert dados["tabelas"]["licenca"] == "MIT"


def test_cli_xsd(capsys):
    pytest.importorskip("xmlschema")
    assert main(["auditar", str(EXEMPLOS / "01-correta.xml"), "--xsd"]) == 0
    assert "AIC-052" in capsys.readouterr().out


def test_cli_consultar(capsys):
    assert main(["consultar", "200003"]) == 0
    saida = capsys.readouterr().out
    assert "CST 200" in saida and "Anexo I" in saida
    assert main(["consultar", "011"]) == 0
    assert "011001" in capsys.readouterr().out
    assert main(["consultar", "10063021"]) == 0
    assert "200003" in capsys.readouterr().out
    assert main(["consultar", "123456"]) == 1


def test_cli_sem_xml(tmp_path):
    assert main(["auditar", str(tmp_path)]) == 2


def test_datas_das_tabelas_sem_hora():
    """Datas com hora (ex.: '2026-01-01 00:00:00') fariam o NCM não valer no primeiro dia."""
    from auditor_ibs_cbs.tabelas import _carregar_ncm

    assert all(len(v[1]) == 10 and len(v[2]) == 10 for v in _carregar_ncm(None).values())

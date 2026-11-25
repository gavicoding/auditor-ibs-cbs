import io
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

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLOS = RAIZ / "exemplos"
ESPERADO = json.loads((Path(__file__).parent / "esperado.json").read_text(encoding="utf-8"))
T = carregar()


def codigos(nome: str) -> list[list]:
    nota = ler_bytes((EXEMPLOS / nome).read_bytes(), nome)
    r = auditar(nota, T)
    return sorted(([a.codigo, a.gravidade, a.item] for a in r.achados), key=lambda x: (x[0], x[1], x[2] or ""))


@pytest.mark.parametrize("nome", sorted(k for k in ESPERADO if not ESPERADO[k].get("ilegivel")))
def test_exemplos_batem_com_o_esperado(nome):
    assert codigos(nome) == ESPERADO[nome]["achados"]


@pytest.mark.parametrize("nome", sorted(k for k in ESPERADO if ESPERADO[k].get("ilegivel")))
def test_exemplos_ilegiveis_sao_recusados(nome):
    with pytest.raises(XMLInvalido):
        ler_bytes((EXEMPLOS / nome).read_bytes(), nome)


def test_nota_correta_nao_tem_achados():
    assert codigos("01-correta.xml") == []


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


def test_zip_e_pasta(tmp_path):
    origem = [o for o, _ in percorrer([EXEMPLOS / "lote-exemplo.zip"])]
    assert len(origem) == 3 and all("!lote/" in o for o in origem)
    assert sum(1 for _ in percorrer([EXEMPLOS])) == 14 + 3


def test_zip_ignora_o_que_nao_e_xml(tmp_path):
    z = tmp_path / "misto.zip"
    with zipfile.ZipFile(z, "w") as arq:
        arq.writestr("leia.txt", "oi")
        arq.writestr("nota.xml", (EXEMPLOS / "01-correta.xml").read_text(encoding="utf-8"))
    assert [o.split("!")[1] for o, _ in percorrer([z])] == ["nota.xml"]


def test_relatorio_nao_inclui_dados_do_destinatario():
    xml = (EXEMPLOS / "02-sem-grupo-regime-normal.xml").read_text(encoding="utf-8")
    xml = xml.replace("</emit>", "</emit><dest><CPF>12345678909</CPF><xNome>MARIA FICTICIA</xNome></dest>")
    arquivo = io.BytesIO()
    r = auditar(ler_bytes(xml.encode(), "x"), T)
    texto = json.dumps(r.como_dict(), ensure_ascii=False)
    assert "12345678909" not in texto and "MARIA" not in texto
    arquivo.close()


# ---------- linha de comando ----------


def test_cli_codigo_de_saida(capsys):
    assert main(["auditar", str(EXEMPLOS / "01-correta.xml"), "--falhar-em", "erro"]) == 0
    assert main(["auditar", str(EXEMPLOS / "02-sem-grupo-regime-normal.xml"), "--falhar-em", "erro"]) == 1
    assert main(["auditar", str(EXEMPLOS / "08-reducao-diferente-da-oficial.xml"), "--falhar-em", "erro"]) == 0
    assert main(["auditar", str(EXEMPLOS / "08-reducao-diferente-da-oficial.xml"), "--falhar-em", "atencao"]) == 1


@pytest.mark.parametrize("formato", ["texto", "json", "csv", "md", "html"])
def test_cli_formatos(tmp_path, formato):
    saida = tmp_path / f"r.{formato}"
    assert main(["auditar", str(EXEMPLOS), "-f", formato, "-o", str(saida)]) == 0
    conteudo = saida.read_text(encoding="utf-8")
    assert "AIC-015" in conteudo
    if formato == "json":
        dados = json.loads(conteudo)
        assert dados["resumo"]["notas"] == 17
        assert dados["tabelas"]["licenca"] == "MIT"


def test_cli_consultar(capsys):
    assert main(["consultar", "200003"]) == 0
    assert "CST 200" in capsys.readouterr().out
    assert main(["consultar", "011"]) == 0
    assert "011001" in capsys.readouterr().out
    assert main(["consultar", "123456"]) == 1


def test_cli_sem_xml(tmp_path):
    assert main(["auditar", str(tmp_path)]) == 2

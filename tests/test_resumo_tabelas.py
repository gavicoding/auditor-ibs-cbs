import copy
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("resumo_tabelas", RAIZ / "ferramentas" / "resumo_tabelas.py")
resumo_tabelas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(resumo_tabelas)


def _base():
    return {
        "fonte": {"versao_base": "V0001", "data_base": "2026-01-01", "url": "https://exemplo.test/rtc"},
        "cst": {"000": {"descricao": "Tributação integral", "inicio": "2026-01-01", "fim": None}},
        "cclasstrib": {"000001": {"cst": "000", "descricao": "Situações tributadas integralmente", "fim": None}},
        "aliquota_referencia": [{"tributo": "CBS", "percentual": 0.9, "inicio": "2026-01-01", "fim": None}],
    }


def test_resumo_lista_novos_removidos_alterados_e_aliquotas():
    antes, depois = _base(), _base()
    depois["fonte"].update(versao_base="V0002", data_base="2026-02-01")
    depois["cclasstrib"]["000001"]["fim"] = "2026-12-31"
    depois["cclasstrib"]["200099"] = {"cst": "200", "descricao": "Redução fictícia", "fim": None}
    depois["aliquota_referencia"].append({"tributo": "CBS", "percentual": 8.8, "inicio": "2027-01-01", "fim": None})
    texto, curto = resumo_tabelas.montar(antes, depois, {"ncm": {"01": 1}}, {"ncm": {"01": 1, "02": 2}})
    assert "V0001 de 2026-01-01" in texto and "V0002 de 2026-02-01" in texto
    assert "| cClassTrib | 1 | 0 | 1 |" in texto
    assert "- novo `200099`: Redução fictícia (CST 200)" in texto
    assert "- alterado `000001`: fim" in texto
    assert "- nova: CBS 8.8% de 2027-01-01 a sem fim" in texto
    assert curto == "cClassTrib: 1 novos, 1 alterados; Alíquotas de referência: 1 novos; NCM: 1 novos"


def test_resumo_sem_mudanca_de_dados():
    texto, curto = resumo_tabelas.montar(_base(), copy.deepcopy(_base()), {}, {})
    assert curto == "só metadados da base mudaram"
    assert "| CST | 0 | 0 | 0 |" in texto


def test_changelog_registra_versao_uma_vez(tmp_path, monkeypatch):
    arquivo = tmp_path / "CHANGELOG.md"
    arquivo.write_text("# Mudanças\n\n## 1.0.0\n\nPrimeira versão.\n", encoding="utf-8")
    monkeypatch.setattr(resumo_tabelas, "CHANGELOG", arquivo)
    depois = _base()
    resumo_tabelas.registrar_changelog(depois, "cClassTrib: 1 novos")
    resumo_tabelas.registrar_changelog(depois, "cClassTrib: 1 novos")
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.count("## Tabelas oficiais: base V0001 de 2026-01-01") == 1
    assert texto.index("Tabelas oficiais") < texto.index("## 1.0.0")

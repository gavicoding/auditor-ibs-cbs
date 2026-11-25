"""API HTTP local e atualização das tabelas."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from auditor_ibs_cbs import atualizacao, carregar
from auditor_ibs_cbs.servidor import criar_handler

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLOS = RAIZ / "exemplos"
DADOS = RAIZ / "src" / "auditor_ibs_cbs" / "dados"


@pytest.fixture(scope="module")
def api():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), criar_handler(carregar()))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


def _get(url):
    with urllib.request.urlopen(url) as r:
        return json.load(r)


def _post(url, dados):
    with urllib.request.urlopen(urllib.request.Request(url, data=dados, method="POST")) as r:
        return json.load(r)


def test_saude(api):
    d = _get(api + "/saude")
    assert d["ok"] and d["tabelas"]["licenca"] == "MIT"


def test_auditar_xml_e_zip(api):
    d = _post(api + "/auditar", (EXEMPLOS / "07-valores-errados.xml").read_bytes())
    assert {a["rejeicao"] for a in d["documentos"][0]["achados"]} == {"1069", "1150", "1076"}
    z = _post(api + "/auditar", (EXEMPLOS / "lote-exemplo.zip").read_bytes())
    assert z["resumo"]["notas"] == 3


def test_consultar(api):
    assert "200003" in _get(api + "/consultar/10063021")["cclasstrib_com_lista"]
    assert _get(api + "/consultar/200003")["cst"] == "200"


def test_rotas_invalidas(api):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(api + "/nada")
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(api + "/auditar", b"")
    assert e.value.code == 413


def test_atualizar_de_fonte_local(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDITOR_IBS_CBS_DADOS", str(tmp_path / "cache"))
    fonte = tmp_path / "fonte"
    fonte.mkdir()
    tabelas = json.loads((DADOS / "tabelas-rtc.json").read_text(encoding="utf-8"))
    tabelas["fonte"]["versao_base"] = "V9999"
    (fonte / "tabelas-rtc.json").write_text(json.dumps(tabelas), encoding="utf-8")
    (fonte / "ncm.json").write_text((DADOS / "ncm.json").read_text(encoding="utf-8"), encoding="utf-8")
    nova = atualizacao.baixar(fonte.as_uri() + "/")
    assert nova["versao_base"] == "V9999"
    carregar.cache_clear()
    try:
        assert carregar().fonte["versao_base"] == "V9999"  # a cópia mais nova passa a ser usada
    finally:
        carregar.cache_clear()


def test_atualizar_recusa_fonte_desconhecida(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDITOR_IBS_CBS_DADOS", str(tmp_path / "cache"))
    fonte = tmp_path / "fonte"
    fonte.mkdir()
    tabelas = json.loads((DADOS / "tabelas-rtc.json").read_text(encoding="utf-8"))
    tabelas["fonte"]["url"] = "https://exemplo.invalido/tabelas"
    (fonte / "tabelas-rtc.json").write_text(json.dumps(tabelas), encoding="utf-8")
    (fonte / "ncm.json").write_text((DADOS / "ncm.json").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError):
        atualizacao.baixar(fonte.as_uri() + "/")
    assert not (tmp_path / "cache").exists()  # nada é gravado se a validação falhar

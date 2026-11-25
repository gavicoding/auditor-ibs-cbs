"""API HTTP local: deixa qualquer sistema (Delphi, C#, Java, PHP, Node...) usar o auditor.

``auditor-ibs-cbs servir`` sobe um servidor só com a biblioteca padrão do Python:

- ``GET  /saude``               situação e versão das tabelas
- ``POST /auditar``             corpo = um XML (ou um .zip com XMLs); responde JSON
- ``GET  /consultar/<codigo>``  CST (3), cClassTrib (6) ou NCM (8 dígitos)

Por padrão escuta só em 127.0.0.1 (a própria máquina). Os XMLs ficam só na memória do processo:
nada é gravado em disco nem enviado para fora.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, relatorio
from .leitor import TAMANHO_MAXIMO, XMLInvalido, ler_bytes, percorrer
from .regras import Achado, Resultado, auditar
from .tabelas import Tabelas, carregar

LIMITE_CORPO = 200 * 1024 * 1024  # um .zip grande de XMLs


def _consultar(t: Tabelas, codigo: str) -> tuple[int, dict]:
    if len(codigo) == 3 and t.cst(codigo):
        reg = dict(t.cst(codigo))
        reg["cclasstrib"] = [c for c, r in t.dados["cclasstrib"].items() if r["cst"] == codigo]
        return 200, {"tipo": "CST", "codigo": codigo, **reg}
    if len(codigo) == 6 and t.cclasstrib(codigo):
        return 200, {"tipo": "cClassTrib", "codigo": codigo, **t.cclasstrib(codigo)}
    if len(codigo) == 8 and codigo.isdigit():
        hoje = date.today()
        aceitam = [c for c in t.dados["cclasstrib"] if t.tem_lista(c, "ncm", hoje) and t.aplicavel(c, "ncm", codigo, hoje)]
        registro = t.ncm(codigo)
        return (200 if registro else 404), {"tipo": "NCM", "codigo": codigo, "descricao": registro[0] if registro else None, "cclasstrib_com_lista": aceitam}
    return 404, {"erro": f"código '{codigo}' não encontrado"}


def criar_handler(tabelas: Tabelas):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"auditor-ibs-cbs/{__version__}"

        def log_message(self, *args) -> None:  # não registra nada (os dados podem ser sensíveis)
            return

        def _json(self, status: int, corpo: dict) -> None:
            dados = json.dumps(corpo, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/saude":
                self._json(200, {"ok": True, "versao": __version__, "tabelas": tabelas.fonte})
            elif self.path.startswith("/consultar/"):
                self._json(*_consultar(tabelas, self.path.rsplit("/", 1)[-1].strip()))
            else:
                self._json(404, {"erro": "rota inexistente", "rotas": ["GET /saude", "POST /auditar", "GET /consultar/<codigo>"]})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/auditar":
                self._json(404, {"erro": "rota inexistente"})
                return
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho <= 0 or tamanho > LIMITE_CORPO:
                self._json(413, {"erro": "envie um XML ou .zip de até 200 MB no corpo da requisição"})
                return
            corpo = self.rfile.read(tamanho)
            resultados = []
            if corpo[:2] == b"PK":  # .zip
                with tempfile.TemporaryDirectory() as pasta:
                    arq = Path(pasta) / "lote.zip"
                    arq.write_bytes(corpo)
                    entradas = list(percorrer([arq]))
                for origem, conteudo in entradas:
                    resultados.append(_auditar(origem.split("!", 1)[-1], conteudo, tabelas))
            else:
                if len(corpo) > TAMANHO_MAXIMO:
                    self._json(413, {"erro": "XML maior que 20 MB"})
                    return
                resultados.append(_auditar("documento.xml", corpo, tabelas))
            self._json(200, {"resumo": relatorio.resumo(resultados), "documentos": [r.como_dict() for r in resultados]})

    return Handler


def _auditar(origem: str, conteudo, tabelas: Tabelas) -> Resultado:
    if isinstance(conteudo, Exception):
        erro = conteudo
    else:
        try:
            return auditar(ler_bytes(conteudo, origem), tabelas)
        except XMLInvalido as e:
            erro = e
    r = Resultado(origem=origem)
    r.achados.append(Achado("AIC-001", "erro", "Arquivo não pôde ser lido", str(erro), "Confira se é o XML do documento fiscal, completo e sem alterações."))
    return r


def servir(host: str = "127.0.0.1", porta: int = 8080) -> None:
    tabelas = carregar()
    servidor = ThreadingHTTPServer((host, porta), criar_handler(tabelas))
    print(f"auditor-ibs-cbs ouvindo em http://{host}:{porta}  (tabelas {tabelas.versao})")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()

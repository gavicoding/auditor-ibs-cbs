"""Linha de comando: ``auditor-ibs-cbs``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, relatorio
from .leitor import XMLInvalido, ler_bytes, percorrer
from .regras import Achado, Resultado, auditar
from .tabelas import carregar

AJUDA = """Exemplos:
  auditor-ibs-cbs auditar notas/                 confere todos os XMLs da pasta (e de arquivos .zip)
  auditor-ibs-cbs auditar notas/ -f html -o relatorio.html
  auditor-ibs-cbs auditar notas/ --falhar-em erro   código de saída 1 se houver erro (bom para CI)
  auditor-ibs-cbs consultar 200003               explica um cClassTrib
  auditor-ibs-cbs consultar 011                  explica um CST e lista seus cClassTrib
  auditor-ibs-cbs tabelas                        mostra a versão das tabelas oficiais usadas
"""


def _auditar(args: argparse.Namespace) -> int:
    tabelas = carregar(args.tabelas)
    resultados: list[Resultado] = []
    for origem, conteudo in percorrer(args.entradas):
        if isinstance(conteudo, Exception):
            resultados.append(_falha(origem, conteudo))
            continue
        try:
            nota = ler_bytes(conteudo, origem)
        except XMLInvalido as erro:
            resultados.append(_falha(origem, erro))
            continue
        resultados.append(auditar(nota, tabelas))

    if not resultados:
        print("Nenhum XML encontrado.", file=sys.stderr)
        return 2

    formato = args.formato
    if formato == "texto":
        saida = relatorio.texto(resultados, tabelas.versao, args.info)
    elif formato == "json":
        saida = relatorio.json_(resultados, tabelas.fonte)
    elif formato == "csv":
        saida = relatorio.csv_(resultados, args.info)
    elif formato == "md":
        saida = relatorio.markdown(resultados, tabelas.versao, args.info)
    else:
        saida = relatorio.html_(resultados, tabelas.versao, args.info)

    if args.saida:
        Path(args.saida).write_text(saida, encoding="utf-8")
        s = relatorio.resumo(resultados)
        print(f"{s['notas']} nota(s): {s['ok']} ok, {s['com_atencao']} com atenção, {s['com_erro']} com erro -> {args.saida}")
    else:
        sys.stdout.write(saida)

    gravidades = {a.gravidade for r in resultados for a in r.achados}
    if args.falhar_em == "erro" and "erro" in gravidades:
        return 1
    if args.falhar_em == "atencao" and gravidades & {"erro", "atencao"}:
        return 1
    return 0


def _falha(origem: str, erro: Exception) -> Resultado:
    r = Resultado(origem=origem)
    r.achados.append(
        Achado(
            "AIC-001",
            "erro",
            "Arquivo não pôde ser lido",
            str(erro),
            "Confira se é o XML da NF-e/NFC-e, completo e sem alterações.",
        )
    )
    return r


def _consultar(args: argparse.Namespace) -> int:
    t = carregar(args.tabelas)
    codigo = args.codigo.strip()
    if len(codigo) == 3 and t.cst(codigo):
        c = t.cst(codigo)
        grupos = ", ".join(g for g, sim in c["grupos"].items() if sim) or "nenhum"
        print(f"CST {codigo}: {c['descricao']}")
        print(f"  vigência: {c['inicio']} a {c['fim'] or 'atual'} | grupos exigidos: {grupos}")
        print("  cClassTrib deste CST:")
        for cod, reg in t.dados["cclasstrib"].items():
            if reg["cst"] == codigo:
                print(f"    {cod}  {reg['descricao']}")
        return 0
    reg = t.cclasstrib(codigo)
    if reg:
        modelos = sorted({d["modelo"] for d in reg["documentos"]})
        print(f"cClassTrib {codigo}: {reg['descricao']}")
        print(f"  CST {reg['cst']} ({t.cst(reg['cst'])['descricao']})")
        print(f"  tipo de alíquota: {reg['tipo_aliquota']} | vigência: {reg['inicio']} a {reg['fim'] or 'atual'}")
        print(f"  documentos (modelos): {', '.join(map(str, modelos))}  (55 = NF-e, 65 = NFC-e)")
        reducoes = {r["tributo"]: r["percentual"] for r in reg["reducao"] if r["percentual"]}
        if reducoes:
            print("  redução: " + ", ".join(f"{k} {v:g}%" for k, v in reducoes.items()))
        return 0
    print(f"Código '{codigo}' não encontrado na tabela {t.versao}.", file=sys.stderr)
    return 1


def _tabelas(args: argparse.Namespace) -> int:
    t = carregar(args.tabelas)
    f = t.fonte
    print(f"Fonte: {f['projeto']} ({f['autor']}, licença {f['licenca']})")
    print(f"       {f['url']}" + (f" @ {f['commit'][:7]}" if f.get("commit") else ""))
    print(f"Base:  {f['versao_base']} de {f['data_base']} - {f['descricao_base']}")
    print(f"       {len(t.dados['cst'])} CST e {len(t.dados['cclasstrib'])} cClassTrib de IBS/CBS")
    return 0


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(
        prog="auditor-ibs-cbs",
        description="Confere o IBS/CBS (reforma tributária) de XMLs de NF-e e NFC-e contra as tabelas oficiais.",
        epilog=AJUDA,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--tabelas", help="usar outro arquivo de tabelas (JSON no mesmo formato)")
    sub = p.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("auditar", help="confere XMLs, pastas ou arquivos .zip")
    a.add_argument("entradas", nargs="+", help="arquivos .xml, pastas ou .zip")
    a.add_argument("-f", "--formato", choices=["texto", "json", "csv", "md", "html"], default="texto")
    a.add_argument("-o", "--saida", help="gravar o relatório neste arquivo")
    a.add_argument("--info", action="store_true", help="mostrar também as observações (gravidade info)")
    a.add_argument("--falhar-em", choices=["nunca", "erro", "atencao"], default="nunca", help="quando devolver código de saída 1")
    a.set_defaults(func=_auditar)

    c = sub.add_parser("consultar", help="explica um CST (3 dígitos) ou cClassTrib (6 dígitos)")
    c.add_argument("codigo")
    c.set_defaults(func=_consultar)

    t = sub.add_parser("tabelas", help="mostra a versão das tabelas oficiais usadas")
    t.set_defaults(func=_tabelas)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

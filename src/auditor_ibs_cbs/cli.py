"""Linha de comando: ``auditor-ibs-cbs``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__, relatorio
from .leitor import XMLInvalido, ler_bytes, percorrer
from .regras import Achado, Resultado, auditar
from .tabelas import carregar

AJUDA = """Exemplos:
  auditor-ibs-cbs auditar notas/                 confere todos os XMLs da pasta (e de arquivos .zip)
  auditor-ibs-cbs auditar notas/ -f html -o relatorio.html
  auditor-ibs-cbs auditar notas/ -f resumo-csv -o valores.csv   base, IBS e CBS por cClassTrib
  auditor-ibs-cbs auditar notas/ --xsd           também valida o leiaute oficial (pip install "auditor-ibs-cbs[xsd]")
  auditor-ibs-cbs auditar notas/ --falhar-em erro   código de saída 1 se houver erro (bom para CI)
  auditor-ibs-cbs consultar 200003               explica um cClassTrib (e para quais NCMs ele vale)
  auditor-ibs-cbs consultar 011                  explica um CST e lista seus cClassTrib
  auditor-ibs-cbs consultar 10063021             NCM: descrição e cClassTrib com lista que aceitam o produto
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
        resultado = auditar(nota, tabelas)
        if args.xsd:
            resultado.achados.extend(_xsd(conteudo))
        resultados.append(resultado)

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
    elif formato == "resumo-csv":
        saida = relatorio.resumo_csv(resultados)
    else:
        saida = relatorio.html_(resultados, tabelas.versao, args.info)

    if args.saida:
        Path(args.saida).write_text(saida, encoding="utf-8")
        s = relatorio.resumo(resultados)
        print(f"{s['notas']} documento(s): {s['ok']} ok, {s['com_atencao']} com atenção, {s['com_erro']} com erro -> {args.saida}")
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
            "Confira se é o XML do documento fiscal, completo e sem alterações.",
        )
    )
    return r


def _xsd(conteudo: bytes) -> list[Achado]:
    from .xsd import XSDIndisponivel, validar

    try:
        erros = validar(conteudo)
    except XSDIndisponivel as erro:
        raise SystemExit(f"--xsd: {erro}") from None
    if erros is None:
        return [
            Achado(
                "AIC-053",
                "info",
                "Leiaute não validado",
                "Não há esquema XSD disponível para este tipo de documento.",
                "Nada a fazer.",
            )
        ]
    return [
        Achado(
            "AIC-052",
            "erro",
            "XML fora do leiaute oficial (XSD)",
            erro,
            "Corrija o campo indicado; o XML precisa seguir o esquema oficial do documento.",
        )
        for erro in erros
    ]


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
    if len(codigo) == 8 and codigo.isdigit():
        return _consultar_ncm(t, codigo)
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
        for tipo in ("ncm", "nbs"):
            vigentes = [n for n in reg.get(tipo, []) if not n["fim"]]
            if vigentes:
                anexos = t.anexos_do_cclasstrib(codigo, tipo, date.today())
                print(
                    f"  só vale para {len(vigentes)} código(s) {tipo.upper()}: "
                    + ", ".join(n["codigo"] for n in vigentes[:12])
                    + (" …" if len(vigentes) > 12 else "")
                )
                if anexos:
                    print("  base legal: " + "; ".join(anexos[:6]) + (" …" if len(anexos) > 6 else "") + " (LC 214/2025)")
        return 0
    print(f"Código '{codigo}' não encontrado na tabela {t.versao}.", file=sys.stderr)
    return 1


def _consultar_ncm(t, ncm: str) -> int:
    registro = t.ncm(ncm)
    hoje = date.today()
    if registro:
        print(f"NCM {ncm}: {registro[0]}")
        print(f"  vigência: {registro[1]} a {registro[2]}")
    else:
        print(f"NCM {ncm}: não encontrado na tabela NCM ({t.versao}).")
    aceitam = [c for c in t.dados["cclasstrib"] if t.tem_lista(c, "ncm", hoje) and t.aplicavel(c, "ncm", ncm, hoje)]
    if aceitam:
        print("  cClassTrib com lista de produtos que aceitam este NCM:")
        for c in aceitam:
            reg = t.cclasstrib(c)
            reducoes = {r["tributo"]: r["percentual"] for r in reg["reducao"] if r["percentual"]}
            red = f" | redução {max(reducoes.values()):g}%" if reducoes else ""
            print(f"    {c}  CST {reg['cst']}  {reg['descricao']}{red}")
    else:
        print("  Nenhum cClassTrib com lista específica aceita este NCM; ele segue os códigos sem lista (ex.: 000001).")
    return 0 if registro else 1


def _tabelas(args: argparse.Namespace) -> int:
    t = carregar(args.tabelas)
    f = t.fonte
    print(f"Fonte: {f['projeto']} ({f['autor']}, licença {f['licenca']})")
    print(f"       {f['url']}" + (f" @ {f['commit'][:7]}" if f.get("commit") else ""))
    print(f"Base:  {f['versao_base']} de {f['data_base']} - {f['descricao_base']}")
    print(f"       {len(t.dados['cst'])} CST e {len(t.dados['cclasstrib'])} cClassTrib de IBS/CBS, {len(t.dados.get('anexos', {}))} itens de anexo")
    return 0


def _atualizar(args: argparse.Namespace) -> int:
    from .atualizacao import baixar, pasta_usuario
    from .tabelas import carregar as _carregar

    antes = _carregar().versao
    try:
        fonte = baixar()
    except Exception as erro:  # rede, JSON inválido, fonte inesperada
        print(f"Não foi possível atualizar: {erro}", file=sys.stderr)
        return 1
    _carregar.cache_clear()
    print(f"Tabelas baixadas para {pasta_usuario()}: base {fonte['versao_base']} de {fonte['data_base']} (em uso antes: {antes}).")
    print(f"Em uso agora: {_carregar().versao}")
    return 0


def _servir(args: argparse.Namespace) -> int:
    from .servidor import servir

    servir(args.host, args.porta)
    return 0


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(
        prog="auditor-ibs-cbs",
        description="Confere o IBS/CBS (reforma tributária) de NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e e NFS-e contra as tabelas oficiais.",
        epilog=AJUDA,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--tabelas", help="usar outro arquivo de tabelas (JSON no mesmo formato)")
    sub = p.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("auditar", help="confere XMLs, pastas ou arquivos .zip")
    a.add_argument("entradas", nargs="+", help="arquivos .xml, pastas ou .zip")
    a.add_argument("-f", "--formato", choices=["texto", "json", "csv", "md", "html", "resumo-csv"], default="texto")
    a.add_argument("-o", "--saida", help="gravar o relatório neste arquivo")
    a.add_argument("--info", action="store_true", help="mostrar também as observações (gravidade info)")
    a.add_argument("--xsd", action="store_true", help='validar também o leiaute oficial (requer: pip install "auditor-ibs-cbs[xsd]")')
    a.add_argument("--falhar-em", choices=["nunca", "erro", "atencao"], default="nunca", help="quando devolver código de saída 1")
    a.set_defaults(func=_auditar)

    c = sub.add_parser("consultar", help="explica um CST (3 dígitos), cClassTrib (6 dígitos) ou NCM (8 dígitos)")
    c.add_argument("codigo")
    c.set_defaults(func=_consultar)

    t = sub.add_parser("tabelas", help="mostra a versão das tabelas oficiais usadas")
    t.set_defaults(func=_tabelas)

    u = sub.add_parser("atualizar", help="baixa as tabelas oficiais mais recentes (sem reinstalar)")
    u.set_defaults(func=_atualizar)

    s = sub.add_parser("servir", help="sobe uma API HTTP local para outros sistemas usarem o auditor")
    s.add_argument("--host", default="127.0.0.1", help="endereço (padrão: só esta máquina)")
    s.add_argument("--porta", type=int, default=8080)
    s.set_defaults(func=_servir)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

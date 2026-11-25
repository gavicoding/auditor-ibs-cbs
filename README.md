**🇧🇷 Português** | [🇺🇸 English](README.en.md)

# Auditor IBS/CBS: confira suas NF-e e NFC-e para a reforma tributária

[![CI](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml/badge.svg)](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml)
[![Usar no navegador](https://img.shields.io/badge/usar%20no%20navegador-gr%C3%A1tis-1a7f5a)](https://gavicoding.github.io/auditor-ibs-cbs/)
![Python](https://img.shields.io/badge/python-3.10%20a%203.13-blue)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-0-brightgreen)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

Desde 2026 as notas fiscais precisam trazer o **grupo do IBS e da CBS** em cada item, com o **CST** e o **cClassTrib** certos. Errar o par de códigos, usar um código que já saiu da tabela ou mandar valores que não batem faz a nota ser rejeitada ou ficar errada perante o fisco.

O **Auditor IBS/CBS** lê os XMLs das suas notas, uma ou milhares de uma vez, e diz **o que está errado, em qual item e como corrigir**, em português simples. A conferência usa as **tabelas oficiais** de CST e cClassTrib publicadas pela Receita Federal.

👉 **[Usar agora no navegador](https://gavicoding.github.io/auditor-ibs-cbs/)**: arraste os XMLs ou um .zip. **Nada sai do seu computador**; tudo é processado no próprio navegador.

---

## Para quem é

- **Contadores e analistas fiscais** que precisam conferir as notas emitidas pelos clientes antes de o problema virar rejeição ou autuação.
- **Desenvolvedores de ERP e emissores** que querem um teste automático para o grupo IBS/CBS (dá para rodar no CI).
- **Empresas** que querem saber se o sistema delas já está gerando as notas do jeito certo.

## O que você ganha

- **Encontra o problema antes da SEFAZ:** confere a pasta inteira de uma vez, inclusive dentro de arquivos .zip.
- **Explicação que dá para entender:** cada problema vem com o motivo e com o que fazer.
- **Tabelas sempre atualizadas:** uma rotina semanal compara com o repositório público da Receita e atualiza quando sai tabela nova.
- **Sem instalar nada (no navegador)** ou **sem dependências (em Python)**.
- **Privacidade:** o relatório não inclui dados do destinatário, e a versão web não envia nada para servidor nenhum.

---

## O que é conferido

| Código | Gravidade | O que significa |
| :--- | :--- | :--- |
| `AIC-010` | erro (regime normal) / info (Simples) | Item sem o grupo IBS/CBS |
| `AIC-011` / `AIC-012` | erro | CST inexistente ou fora da vigência na data da nota |
| `AIC-013` / `AIC-014` | erro | cClassTrib inexistente ou fora da vigência |
| `AIC-015` | erro | cClassTrib não pertence ao CST informado |
| `AIC-016` | erro | cClassTrib não pode ser usado em NF-e (ou em NFC-e) |
| `AIC-020` / `AIC-021` | erro / atenção | Grupo exigido pelo CST está faltando, ou veio um grupo que o CST não prevê |
| `AIC-022` / `AIC-023` | atenção | Redução de alíquota sem previsão no CST, ou percentual diferente do oficial |
| `AIC-030` | atenção | Valor do tributo diferente de base × alíquota (tolerância de R$ 0,01) |
| `AIC-031` | erro | vIBS diferente de vIBSUF + vIBSMun |
| `AIC-032` | info | Alíquota diferente da alíquota de referência do ano |
| `AIC-040` / `AIC-041` | erro | Totais da nota ausentes ou diferentes da soma dos itens |
| `AIC-001` | erro | Arquivo ilegível (ou recusado por segurança) |

As regras do par CST × cClassTrib e do tipo de documento são as mesmas que a calculadora oficial aplica. Os valores são conferidos com arredondamento bancário (`HALF_EVEN`), também como na calculadora oficial. Itens com diferimento ou devolução de tributo não têm o valor recalculado, para não gerar alarme falso.

---

## Linha de comando

Requer Python 3.10 ou mais novo. Não há dependências.

```bash
pip install git+https://github.com/gavicoding/auditor-ibs-cbs.git
```

```bash
# Conferir uma pasta (procura XMLs em subpastas e dentro de arquivos .zip)
auditor-ibs-cbs auditar notas/

# Relatório em HTML para mandar ao cliente, ou planilha CSV
auditor-ibs-cbs auditar notas/ -f html -o relatorio.html
auditor-ibs-cbs auditar notas/ -f csv -o problemas.csv

# No CI do seu ERP: falha se alguma nota de teste tiver erro
auditor-ibs-cbs auditar testes/notas-geradas/ --falhar-em erro

# O que significa este código?
auditor-ibs-cbs consultar 200003
auditor-ibs-cbs consultar 011

# Qual versão das tabelas oficiais está sendo usada?
auditor-ibs-cbs tabelas
```

Exemplo de saída (com as notas fictícias da pasta [`exemplos/`](exemplos/)):

```text
[ERRO] NF 1004 série 1  chave 35261111222333000181550010000010041000010040
  arquivo: exemplos/04-cclasstrib-de-outro-cst.xml
  - ERRO    AIC-015  item 1: cClassTrib não pertence ao CST
      O cClassTrib 200003 (Vendas de produtos destinados à alimentação humana (Anexo I)) é do CST 200, mas o item informa CST 000.
      Como corrigir: Use o CST 200 ou escolha um cClassTrib do CST 000.

Resumo: 17 nota(s) | 5 ok | 1 com atenção | 11 com erro
Tabelas oficiais usadas: base V0073 (2026-11-09)
```

Formatos: `texto` (padrão), `json`, `csv`, `md` e `html`. Use `--info` para ver também as observações.

## Como biblioteca

```python
from auditor_ibs_cbs import auditar, carregar, ler_arquivo

tabelas = carregar()
resultado = auditar(ler_arquivo("nota.xml"), tabelas)
for achado in resultado.achados:
    print(achado.codigo, achado.gravidade, achado.item, achado.titulo)
```

---

## De onde vêm as tabelas

As tabelas de CST, cClassTrib, vínculo com cada tipo de documento, percentuais de redução e alíquotas de referência são extraídas do repositório público da **[Calculadora de Tributos da Receita Federal](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular)** (licença MIT). O script [`ferramentas/exportar_tabelas.py`](ferramentas/exportar_tabelas.py) só lê os arquivos SQL de migração daquele repositório e gera o arquivo [`tabelas-rtc.json`](src/auditor_ibs_cbs/dados/tabelas-rtc.json), com a versão da base e o commit de origem.

Toda semana, o workflow [`atualizar-tabelas`](.github/workflows/atualizar-tabelas.yml) refaz a extração e abre um pull request quando a Receita publica uma base nova.

Para cálculos completos (base de cálculo, alíquotas por município, geração do grupo do XML), use a própria calculadora oficial. Este projeto é um **complemento** a ela: confere notas já emitidas, em lote, e explica o problema.

## Avisos

- **Projeto independente e não oficial.** Não tem relação com a Receita Federal, o Serpro ou as SEFAZ.
- O resultado ajuda a encontrar problemas, mas **não substitui a validação da SEFAZ nem a orientação do seu contador**. As regras mudam com novas versões da NT 2025.002; confira sempre a versão vigente.
- Os XMLs da pasta `exemplos/` são **fictícios** (empresa, CNPJ, produtos e valores inventados).

## Contribuir

Achou um falso alarme, um caso que não é conferido ou uma explicação confusa? [Abra uma issue](https://github.com/gavicoding/auditor-ibs-cbs/issues/new/choose). Pull requests são bem-vindos; veja o [guia de contribuição](CONTRIBUTING.md). **Nunca anexe XMLs reais**: eles têm dados de clientes. Monte um exemplo fictício com [`ferramentas/gerar_exemplos.py`](ferramentas/gerar_exemplos.py).

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest                                   # testes da versão Python
node --test tests/web/paridade.test.mjs  # mesma bateria na versão web
python ferramentas/fuzz_paridade.py /tmp/fuzz 500 && node tests/web/fuzz.mjs /tmp/fuzz   # Python x web em notas aleatórias
```

A versão web ([`docs/auditor.js`](docs/auditor.js)) e a versão Python ([`src/auditor_ibs_cbs/regras.py`](src/auditor_ibs_cbs/regras.py)) seguem as mesmas regras e são conferidas pelo mesmo gabarito ([`tests/esperado.json`](tests/esperado.json)) e por um teste com notas aleatórias a cada mudança.

## Licença

[MIT](LICENSE). As tabelas derivadas da calculadora da Receita Federal seguem a licença MIT original; veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

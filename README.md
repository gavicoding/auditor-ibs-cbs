**🇧🇷 Português** | [🇺🇸 English](README.en.md)

# Auditor IBS/CBS: confira suas notas fiscais para a reforma tributária

[![CI](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml/badge.svg)](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml)
[![Usar no navegador](https://img.shields.io/badge/usar%20no%20navegador-gr%C3%A1tis-1a7f5a)](https://gavicoding.github.io/auditor-ibs-cbs/)
![Python](https://img.shields.io/badge/python-3.10%20a%203.13-blue)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-0-brightgreen)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

Desde 2026 os documentos fiscais precisam trazer o **grupo do IBS e da CBS**, com o **CST** e o **cClassTrib** certos. Errar o par de códigos, usar um código que já saiu da tabela, aplicar a redução da cesta básica num produto que não está na lista da lei ou mandar valores que não batem faz a nota ser rejeitada ou ficar errada perante o fisco.

O **Auditor IBS/CBS** lê os XMLs, um ou milhares de uma vez, e diz **o que está errado, em qual item e como corrigir**, em português simples. A conferência usa as **tabelas oficiais** publicadas pela Receita Federal: CST, cClassTrib, produtos (NCM) e serviços (NBS) que cada código aceita, anexos da LC 214/2025 e alíquotas de referência.

👉 **[Usar agora no navegador](https://gavicoding.github.io/auditor-ibs-cbs/)**: arraste os XMLs ou um .zip. **Nada sai do seu computador**; tudo é processado no próprio navegador.

**Documentos suportados:** NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e e NFS-e nacional (DPS ou NFS-e autorizada).

---

## Para quem é

- **Contadores e analistas fiscais** que precisam conferir as notas emitidas pelos clientes antes de o problema virar rejeição ou autuação.
- **Desenvolvedores de ERP e emissores** que querem um teste automático para o grupo IBS/CBS (dá para rodar no CI).
- **Empresas** que querem saber se o sistema delas já está gerando os documentos do jeito certo.

## O que você ganha

- **Encontra o problema antes da SEFAZ:** confere a pasta inteira de uma vez, inclusive dentro de arquivos .zip.
- **Explicação que dá para entender:** cada problema vem com o motivo, a base legal quando houver (ex.: "Anexo I, item 1 da LC 214/2025") e o que fazer.
- **Pega o erro mais caro:** produto usando um cClassTrib com redução (cesta básica, saúde, insumos agropecuários…) sem estar na lista da lei.
- **Resumo do lote:** problemas mais comuns, itens com problema por cClassTrib e por NCM, documentos por emitente e base, IBS e CBS somados por cClassTrib, com planilhas para o contador.
- **"Qual código meu produto pode usar?":** consulte o NCM e veja quais cClassTrib com benefício aceitam aquele produto.
- **Tabelas sempre atualizadas:** uma rotina semanal compara com o repositório público da Receita e atualiza quando sai base nova.
- **Privacidade:** o relatório não inclui dados do destinatário, e a versão web não envia nada para servidor nenhum.

---

## O que é conferido

| Código | Gravidade | O que significa |
| :--- | :--- | :--- |
| `AIC-010` | erro (regime normal) / info (Simples) | Item ou documento sem o grupo IBS/CBS |
| `AIC-011` / `AIC-012` | erro | CST inexistente ou fora da vigência na data do documento |
| `AIC-013` / `AIC-014` | erro | cClassTrib inexistente ou fora da vigência |
| `AIC-015` | erro | cClassTrib não pertence ao CST informado (também na tributação regular) |
| `AIC-016` | erro | cClassTrib não pode ser usado naquele tipo de documento |
| `AIC-017` / `AIC-018` | erro | NCM ausente quando o cClassTrib exige, ou produto (NCM) fora da lista do cClassTrib, respeitando as exceções oficiais |
| `AIC-019` | atenção | NCM inexistente ou fora da vigência na tabela NCM |
| `AIC-024` / `AIC-025` | erro | NFS-e: NBS ausente quando exigido, ou serviço (NBS) fora da lista do cClassTrib |
| `AIC-020` / `AIC-021` | erro / atenção | Grupo exigido pelo CST está faltando, ou veio um grupo que o CST não prevê |
| `AIC-022` / `AIC-023` | atenção | Redução sem previsão no CST, ou percentual diferente do oficial do cClassTrib |
| `AIC-026` | atenção | Diferimento informado sem o CST prever (ou o contrário) |
| `AIC-030` | atenção | Valor do tributo diferente de base × alíquota (considerando diferimento) |
| `AIC-031` | erro | IBS total diferente de IBS estadual + municipal |
| `AIC-032` | info | Alíquota diferente da alíquota de referência do ano |
| `AIC-033` | atenção | Alíquota efetiva diferente de alíquota × (1 − redução) × (1 − redutor de compra governamental) |
| `AIC-034` | atenção | Valor diferido diferente de base × alíquota × percentual diferido |
| `AIC-035` | atenção | Crédito presumido diferente de base do crédito × percentual |
| `AIC-036` | atenção | Tributo da compra governamental que não confere |
| `AIC-037` | atenção | Tributação regular que não confere |
| `AIC-038` | atenção | Monofásico: valor diferente de quantidade × alíquota ad rem |
| `AIC-040` / `AIC-041` | erro | Totais do documento ausentes ou diferentes da soma dos itens (inclusive diferido, devolvido, crédito presumido, monofásico e estorno) |
| `AIC-050` / `AIC-051` | erro | Campo fora do formato do leiaute, ou campo obrigatório ausente no grupo |
| `AIC-052` | erro | Com `--xsd`: documento fora do esquema oficial (XSD) |
| `AIC-001` a `AIC-004` | erro / info | Arquivo ilegível ou recusado por segurança, modelo não suportado, sem data, anterior à reforma |

**Como as regras foram feitas:** a vinculação CST × cClassTrib, cClassTrib × documento e NCM/NBS × cClassTrib (por prefixo e com exceções) segue a mesma lógica da calculadora oficial da Receita. Os valores usam as fórmulas publicadas pela calculadora: valor = arred2(base × alíquota publicada ÷ 100), diferimento = arred2(base × alíquota ÷ 100 × pDif ÷ 100), com arredondamento bancário (`HALF_EVEN`) e tolerância de R$ 0,01. Quando a calculadora não publica fórmula (devolução de tributo), o valor não é recalculado, para não gerar alarme falso.

---

## Linha de comando

Requer Python 3.10 ou mais novo. Não há dependências.

```bash
pip install git+https://github.com/gavicoding/auditor-ibs-cbs.git
```

```bash
# Conferir uma pasta (procura XMLs em subpastas e dentro de arquivos .zip)
auditor-ibs-cbs auditar notas/

# Relatório em HTML (com o resumo do lote) para mandar ao cliente, ou planilhas CSV
auditor-ibs-cbs auditar notas/ -f html -o relatorio.html
auditor-ibs-cbs auditar notas/ -f csv -o problemas.csv
auditor-ibs-cbs auditar notas/ -f resumo-csv -o valores-por-cclasstrib.csv

# Também validar o leiaute oficial (XSD); instale o extra opcional
pip install "auditor-ibs-cbs[xsd] @ git+https://github.com/gavicoding/auditor-ibs-cbs.git"
auditor-ibs-cbs auditar notas/ --xsd

# No CI do seu ERP: falha se algum documento de teste tiver erro
auditor-ibs-cbs auditar testes/notas-geradas/ --falhar-em erro

# Consultas
auditor-ibs-cbs consultar 200003     # o que é este cClassTrib e para quais NCMs vale
auditor-ibs-cbs consultar 011        # este CST e seus cClassTrib
auditor-ibs-cbs consultar 10063021   # este NCM: descrição e quais cClassTrib com benefício aceitam o produto
auditor-ibs-cbs tabelas              # versão das tabelas oficiais em uso
```

Exemplo de saída (com os documentos fictícios da pasta [`exemplos/`](exemplos/)):

```text
[ERRO] NF-e 1015 série 1  chave 35261111222333000181550010000010151000010150
  arquivo: exemplos/15-ncm-fora-da-lista-cesta-basica.xml
  - ERRO    AIC-018  item 1: NCM não pode usar este cClassTrib
      O cClassTrib 200003 (Vendas de produtos destinados à alimentação humana (Anexo I)) só vale para os produtos
      listados na lei (Anexo I, item 19, Anexo I, item 20, Anexo I, item 2… da LC 214/2025). O NCM 48201000 (Livros
      de registro e de contabilidade, blocos de notas, de encomendas, de…) não está nessa lista, então o tratamento
      (como a redução) não se aplica.
      Como corrigir: Confira o NCM e o cClassTrib do produto; se o produto não está no anexo, use o cClassTrib da tributação comum.
```

Formatos: `texto` (padrão), `json`, `csv`, `md`, `html` e `resumo-csv`. Use `--info` para ver também as observações.

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

Tudo é extraído do repositório público da **[Calculadora de Tributos da Receita Federal](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular)** (licença MIT):
- CST e cClassTrib, com vigência e documentos permitidos;
- NCM e NBS aplicáveis a cada cClassTrib, com as exceções;
- textos dos anexos da LC 214/2025;
- percentuais de redução e alíquotas de referência;
- tabela NCM;
- esquemas XSD dos documentos.

O script [`ferramentas/exportar_tabelas.py`](ferramentas/exportar_tabelas.py) só lê os arquivos SQL de migração daquele repositório. Ele gera [`tabelas-rtc.json`](src/auditor_ibs_cbs/dados/tabelas-rtc.json) e [`ncm.json`](src/auditor_ibs_cbs/dados/ncm.json), com a versão da base e o commit de origem.

Toda semana, o workflow [`atualizar-tabelas`](.github/workflows/atualizar-tabelas.yml) refaz a extração e abre um pull request quando a Receita publica uma base nova.

Para o cálculo completo (base de cálculo, alíquotas por município, geração do grupo do XML), use a própria calculadora oficial. Este projeto é um **complemento** a ela: confere documentos já emitidos, em lote, e explica o problema.

## O que ainda não é coberto

Veja o [ROADMAP](ROADMAP.md). Em resumo:
- Imposto Seletivo (começa em 2027);
- NFCom, NFAg, NFGas e outros documentos sem esquema na calculadora oficial;
- recálculo da devolução de tributos (sem fórmula publicada);
- validação XSD do NF3-e (o pacote oficial não traz o elemento raiz).

## Avisos

- **Projeto independente e não oficial.** Não tem relação com a Receita Federal, o Serpro ou as SEFAZ.
- O resultado ajuda a encontrar problemas, mas **não substitui a validação da SEFAZ nem a orientação do seu contador**. As regras mudam com novas versões da NT 2025.002; confira sempre a versão vigente.
- Os XMLs da pasta `exemplos/` são **fictícios** (empresas, CNPJ, produtos e valores inventados) e trazem só os campos que o auditor lê.

## Contribuir

Achou um falso alarme, um caso que não é conferido ou uma explicação confusa? [Abra uma issue](https://github.com/gavicoding/auditor-ibs-cbs/issues/new/choose). Pull requests são bem-vindos; veja o [guia de contribuição](CONTRIBUTING.md). **Nunca anexe XMLs reais**: eles têm dados de clientes. Monte um exemplo fictício com [`ferramentas/gerar_exemplos.py`](ferramentas/gerar_exemplos.py).

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest                                    # versão Python
node --test tests/web/paridade.test.mjs   # mesma bateria na versão web
python ferramentas/fuzz_paridade.py /tmp/fuzz 2000 && node tests/web/fuzz.mjs /tmp/fuzz   # Python x web em documentos aleatórios
```

A versão web ([`docs/auditor.js`](docs/auditor.js)) e a versão Python ([`src/auditor_ibs_cbs/`](src/auditor_ibs_cbs/)) seguem as mesmas regras. As duas são conferidas pelo mesmo gabarito ([`tests/esperado.json`](tests/esperado.json)) e, a cada mudança, por milhares de documentos aleatórios: os resultados têm de ser idênticos.

## Licença

[MIT](LICENSE). As tabelas e esquemas derivados da calculadora da Receita Federal seguem a licença MIT original; veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

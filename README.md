**🇧🇷 Português** | [🇺🇸 English](README.en.md)

# Auditor IBS/CBS: confira suas notas fiscais para a reforma tributária

[![CI](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml/badge.svg)](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml)
[![Usar no navegador](https://img.shields.io/badge/usar%20no%20navegador-gr%C3%A1tis-1a7f5a)](https://gavicoding.github.io/auditor-ibs-cbs/)
![NT](https://img.shields.io/badge/NT%202025.002--RTC-v1.53-0969da)
![Python](https://img.shields.io/badge/python-3.10%20a%203.13-blue)
![Dependências](https://img.shields.io/badge/depend%C3%AAncias-0-brightgreen)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

Desde 2026 os documentos fiscais precisam trazer o **grupo do IBS e da CBS**, com o **CST** e o **cClassTrib** certos. Errar o par de códigos, aplicar a redução da cesta básica num produto que não está na lista da lei, somar os totais com um centavo de diferença ou mandar valores que não batem faz a nota ser rejeitada pela SEFAZ ou ficar errada perante o fisco.

O **Auditor IBS/CBS** lê os XMLs, um ou milhares de uma vez, e diz **o que está errado, em qual item, como corrigir e qual rejeição da SEFAZ isso causa**, citando a regra e a página da nota técnica oficial.

👉 **[Usar agora no navegador](https://gavicoding.github.io/auditor-ibs-cbs/)**: arraste os XMLs ou um .zip. **Nada sai do seu computador.**

**Documentos:** NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e e NFS-e nacional.
**Base normativa:** NT 2025.002-RTC v1.53 (out/2026) e tabelas oficiais da calculadora da Receita Federal (base V0073).

---

## O que você ganha

- **Saber a rejeição antes de enviar:** cada achado de NF-e/NFC-e traz o código (ex.: `Rejeição 1085`), a regra (`W47-10`), a página da NT e se a regra **já vale em produção** ou ainda é "implementação futura" (aí ela aparece como aviso antecipado).
- **Pegar o erro mais caro:** produto usando um cClassTrib com redução (cesta básica, saúde, insumos agropecuários...) sem estar na lista da lei, com as exceções oficiais, a citação do anexo da LC 214/2025 e a sugestão dos códigos que o produto pode usar.
- **Explicação que dá para entender:** motivo e correção em português simples.
- **Resumo do lote** (problemas mais comuns, por cClassTrib, por NCM, por emitente; base, IBS e CBS por cClassTrib) e planilhas para o contador.
- **"Qual código meu produto pode usar?":** consulte o NCM e veja os cClassTrib com benefício que aceitam o produto.
- **Sempre em dia:** tabelas atualizadas todo dia e vigias que avisam quando sai norma nova (veja abaixo).
- **Privacidade:** nada é enviado para servidor nenhum; o relatório não inclui dados do destinatário.

---

## Formas de usar (escolha a sua)

| Forma | Para quem | Como |
| :--- | :--- | :--- |
| **Página web** | Contador, analista fiscal, qualquer pessoa | [gavicoding.github.io/auditor-ibs-cbs](https://gavicoding.github.io/auditor-ibs-cbs/) |
| **Programa para Windows (.exe)** | Quem não quer instalar nada | baixe `auditor-ibs-cbs.exe` na [página de versões](https://github.com/gavicoding/auditor-ibs-cbs/releases) |
| **Linha de comando e biblioteca Python** | Devs, automações, CI | `pip install git+https://github.com/gavicoding/auditor-ibs-cbs.git` |
| **API local (HTTP) e Docker** | Qualquer linguagem: Delphi, C#, Java, PHP, Node | `auditor-ibs-cbs servir` ou `docker run -p 127.0.0.1:8080:8080 ...` |
| **Pacote JavaScript** | ERPs web, Node e TypeScript | `npm install github:gavicoding/auditor-ibs-cbs` |
| **Pacote SQL** | Dentro do banco do ERP: SQL Server, PostgreSQL, MySQL, SQLite | scripts em [`sql/`](sql/) |
| **GitHub Action** | Testar o emissor a cada mudança | `uses: gavicoding/auditor-ibs-cbs@v1` |

Todas as formas usam as mesmas tabelas e as mesmas regras. As versões Python e JavaScript são comparadas em milhares de documentos aleatórios a cada mudança, e o pacote SQL roda num PostgreSQL 16, MySQL 8 e SQL Server 2022 de verdade no CI, com resultado conferido contra o Python.

### Linha de comando

```bash
auditor-ibs-cbs auditar notas/                       # pasta, subpastas e .zip
auditor-ibs-cbs auditar notas/ -f html -o relatorio.html
auditor-ibs-cbs auditar notas/ -f csv -o problemas.csv
auditor-ibs-cbs auditar notas/ -f resumo-csv -o valores-por-cclasstrib.csv
auditor-ibs-cbs auditar notas/ --falhar-em erro      # código de saída 1 se houver erro (CI)
auditor-ibs-cbs consultar 200003                     # cClassTrib: o que é e para quais NCMs vale
auditor-ibs-cbs consultar 10063021                   # NCM: quais cClassTrib com benefício aceitam
auditor-ibs-cbs atualizar                            # baixa as tabelas mais novas, sem reinstalar
auditor-ibs-cbs servir --porta 8080                  # API local
```

Exemplo de saída:

```text
[ERRO] NF-e 1007 série 1  chave 35261111222333000181550010000010071000010077
  - ERRO    AIC-041  Total de base de cálculo diferente da soma dos itens
      O total informa R$ 210,00, mas a soma dos itens dá R$ 200,00. A NT exige igualdade exata, sem tolerância de centavo.
      Como corrigir: Some os valores já arredondados de cada item; não recalcule o total sobre a base inteira.
      Rejeição 1076 · regra W35-10 · NT 2025.002-RTC v1.53, p. 71 · já em produção
```

### API local

```bash
curl -X POST --data-binary @nota.xml http://127.0.0.1:8080/auditar     # um XML ou um .zip
curl http://127.0.0.1:8080/consultar/10063021
```

Escuta só na própria máquina por padrão; os XMLs ficam só na memória do processo.

### Pacote SQL

```sql
-- 1) rode sql/<seu banco>/01_tabelas.sql e 02_auditoria.sql
-- 2) carregue os itens das suas notas:
INSERT INTO ibscbs_auditoria_item (chave, item, modelo, data_emissao, cst, cclasstrib, ncm)
VALUES ('3526...', '1', 55, '2026-11-20', '200', '200003', '48201000');
-- 3) veja os problemas:
SELECT * FROM ibscbs_auditoria_resultado ORDER BY chave, item, codigo;
```

Confere CST e cClassTrib (existência, vigência, par e documento) e NCM × cClassTrib com as exceções, com os mesmos códigos do auditor.

### GitHub Action

```yaml
- uses: gavicoding/auditor-ibs-cbs@v1
  with:
    caminho: testes/notas-geradas/
    falhar-em: erro
```

---

## O que é conferido

Para NF-e e NFC-e, a coluna **Rejeição** mostra o código da SEFAZ segundo a NT 2025.002-RTC v1.53.

| Código | O que significa | Rejeição |
| :--- | :--- | :--- |
| `AIC-010` | Item sem o grupo IBS/CBS (regime normal; exceções de devolução, complementar e combustíveis) | 1115 *(futura em produção)* |
| `AIC-011` a `AIC-016` | CST e cClassTrib: existência, vigência, par e permissão no tipo de documento | 1020, 1023, 1024, 1025 |
| `AIC-017` a `AIC-019` | NCM obrigatório, NCM fora da lista do cClassTrib (com exceções oficiais) e NCM inexistente | sem rejeição própria* |
| `AIC-024` / `AIC-025` | NFS-e: NBS obrigatório ou fora da lista do cClassTrib | |
| `AIC-020` / `AIC-021` | Grupos exigidos ou vedados pelo CST (gIBSCBS, monofásico, transferência, ZFM, ajuste) | 1021, 1022, 1116, 1131, 1132, 1135, 1151, 1170 |
| `AIC-022` / `AIC-027` | Grupo de redução vedado pelo CST, ou ausente quando o CST exige ou há compra governamental | 1007, 1028, 1032, 1033, 1074, 1079 |
| `AIC-023` | Percentual de redução diferente do oficial do cClassTrib | 1034, 1046, 1063 |
| `AIC-026` | Diferimento vedado ou exigido pelo CST | 1029, 1030, 1044, 1061, 1083, 1090 |
| `AIC-028` | Devolução de tributo (grupos vedados, percentual ausente, valor que não confere) | 1111, 1112, 1187, 1188, 1189 |
| `AIC-029` | Base de cálculo diferente da composição da NT (produto, frete, seguro... menos ICMS, PIS, COFINS...) | 1104 *(futura: aviso antecipado)* |
| `AIC-030` / `AIC-034` | Valor do tributo ≠ base × alíquota − diferido − devolvido; valor diferido que não confere | 1031, 1041, 1045, 1052, 1062, 1069 |
| `AIC-031` | vIBS ≠ vIBSUF + vIBSMun (menos crédito presumido, quando aplicável) | 1150 |
| `AIC-032` | Alíquota diferente da fixada em lei para o ano (2026: CBS 0,9%, IBS UF 0,1%, IBS Mun 0%) | 1026, 1036, 1037 |
| `AIC-033` | Alíquota efetiva ≠ alíquota × (1 − redução) × (1 − redutor de compra governamental), 4 casas | 1035, 1047, 1064 |
| `AIC-035` / `AIC-036` / `AIC-037` | Crédito presumido, compra governamental (grupos e soma) e tributação regular | 1040, 1051, 1068, 1141, 1142, 1144 |
| `AIC-040` / `AIC-041` / `AIC-042` | Totais ausentes, indevidos ou diferentes da soma dos itens (**sem tolerância**) | 1076 a 1093, 1118 a 1123, 1176, 1177 |
| `AIC-044` / `AIC-045` | Limites da NFC-e (compra governamental, crédito presumido) e crédito presumido da ZFM | 1006, 1049, 1138, 1158, 1159 |
| `AIC-046` | cClassTrib incompatível com a nota de débito ou de crédito | 1200, 1201, 1202 |
| `AIC-047` / `AIC-048` | Estorno de crédito e transferência de crédito | 1129, 1133, 1172, 1173 |
| `AIC-050` / `AIC-051` / `AIC-052` | Formato e campos obrigatórios do leiaute; com `--xsd`, validação contra o esquema | |
| `AIC-001` a `AIC-004` | Arquivo ilegível ou recusado por segurança, modelo não suportado, sem data, anterior à reforma | |

\* NCM × cClassTrib segue a mesma lógica da calculadora oficial da Receita (prefixo e exceções vigentes).

**Tolerâncias, como na NT:** valores do item aceitam R$ 0,01; soma da compra governamental, R$ 0,04; totais, **nenhuma**. Para CT-e, BP-e, NF3-e e NFS-e (que têm notas técnicas próprias) as mesmas conferências de tabela e cálculo são aplicadas, sem citar código de rejeição.

---

## Sempre atualizado

| Vigia | Frequência | O que faz |
| :--- | :--- | :--- |
| [`atualizar-tabelas`](.github/workflows/atualizar-tabelas.yml) | diário | Refaz a extração das tabelas a partir da calculadora oficial e abre um PR, com os testes rodados, quando os **dados** mudam |
| [`vigias`](.github/workflows/vigias.yml): publicações | diário | Lê o Portal da NF-e e abre uma issue para cada publicação nova sobre a reforma (NT, informe técnico, tabela) |
| [`vigias`](.github/workflows/vigias.yml): calculadora | diário | Abre uma issue quando os esquemas XSD da calculadora oficial mudam |

Tabelas mudam sozinhas (com PR e testes). **Regras fiscais novas nunca entram sozinhas:** elas pedem leitura da norma e revisão, e a issue já traz a lista do que fazer. Quem usa a linha de comando pode rodar `auditor-ibs-cbs atualizar` para receber as tabelas novas sem reinstalar; a página web e a API usam sempre a versão publicada.

---

## De onde vêm os dados

- **Tabelas** (CST, cClassTrib, documentos, NCM/NBS aplicáveis com exceções, anexos da LC 214/2025, reduções, alíquotas de referência, tabela NCM) e **esquemas XSD**: repositório público da [Calculadora de Tributos da Receita Federal](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular) (licença MIT), extraídos por [`ferramentas/exportar_tabelas.py`](ferramentas/exportar_tabelas.py).
- **Regras de validação e códigos de rejeição:** Nota Técnica 2025.002-RTC v1.53, publicada no Portal Nacional da NF-e; catálogo em [`src/auditor_ibs_cbs/nt.py`](src/auditor_ibs_cbs/nt.py), com regra e página de cada código.

Para o cálculo completo, use a calculadora oficial. Este projeto é um **complemento**: confere documentos já emitidos, em lote, e explica o problema.

## O que ainda não é coberto

Veja o [ROADMAP](ROADMAP.md): Imposto Seletivo (2027), recálculo do monofásico no leiaute novo da v1.53 (depende das tabelas de combustíveis), indicadores que a base oficial ainda não publica (tributação regular por cClassTrib, tabela de crédito presumido), NTs complementares (2026.005 Simples Nacional, 2026.006, 2026.008), NFCom e outros documentos.

## Avisos

- **Projeto independente e não oficial.** Não tem relação com a Receita Federal, o Serpro ou as SEFAZ.
- O resultado ajuda a encontrar problemas, mas **não substitui a validação da SEFAZ nem a orientação do seu contador**.
- Os XMLs de `exemplos/` são **fictícios** e trazem só os campos que o auditor lê.

## Contribuir

[Abra uma issue](https://github.com/gavicoding/auditor-ibs-cbs/issues/new/choose) para falso alarme, caso não coberto ou explicação confusa. **Nunca anexe XMLs reais.** Veja o [guia de contribuição](CONTRIBUTING.md).

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest                                    # Python, SQL (SQLite), API e atualização
node --test tests/web/paridade.test.mjs   # versão web
python ferramentas/fuzz_paridade.py /tmp/fuzz 3000 && node tests/web/fuzz.mjs /tmp/fuzz
python ferramentas/gerar_sql.py --exemplos
```

## Licença

[MIT](LICENSE). Tabelas e esquemas derivados da calculadora da Receita Federal seguem a licença MIT original; veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

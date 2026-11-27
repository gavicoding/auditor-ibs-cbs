# Mudanças

## Não publicado

- **Monofásico (AIC-038):** confere quantidade × alíquota ad rem nos grupos gMonoPadrao, gMonoReten e gMonoRet, o valor diferido (gMonoDif) e o total do item (vTotIBSMonoItem, vTotCBSMonoItem). Antes, só a presença do grupo e os totais da nota eram conferidos.
- **Exemplo 26 corrigido:** o XML "monofásico correto" tinha 100 litros × R$ 1,00 = R$ 90,00 de IBS e passava sem aviso. Novo exemplo 51 com o valor errado.
- **Atualização das tabelas:** o pull request diário agora traz o resumo do que entrou, saiu ou mudou (CST, cClassTrib, alíquotas de referência, NCM), registra a versão da base neste arquivo, regera o pacote SQL (sem isso o CI do próprio PR falhava) e dispara o CI no ramo do PR.

## 1.0.0

Primeira versão pública.

- **Regras da NT 2025.002-RTC v1.53:** cada achado de NF-e/NFC-e traz o código de rejeição, a regra, a página da NT e se a regra já vale em produção. Regras marcadas como "implementação futura" aparecem como aviso antecipado.
- **Documentos:** NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e e NFS-e nacional (DPS ou autorizada).
- **Conferências:**
  - CST e cClassTrib, inclusive o vínculo com o tipo de documento;
  - NCM e NBS aplicáveis, com as exceções oficiais e a citação do anexo da LC 214/2025;
  - grupos exigidos e vedados;
  - redução, diferimento, devolução, alíquotas de 2026, alíquota efetiva e valores;
  - crédito presumido, compra governamental e tributação regular;
  - notas de débito e de crédito, estorno e transferência de crédito;
  - composição da base (aviso antecipado);
  - totais sem tolerância;
  - formato e campos obrigatórios do leiaute, e XSD opcional.
- **Resumo do lote**, planilhas CSV e relatório HTML.
- **Consulta por CST, cClassTrib e NCM.**
- **Formas de uso:** página web, linha de comando e biblioteca Python, API HTTP local e Docker, pacote JavaScript, pacote SQL (SQL Server, PostgreSQL, MySQL e SQLite), programa para Windows e GitHub Action.
- **Atualização:** tabelas atualizadas todo dia a partir da calculadora oficial (base V0073, 09/11/2026); comando `atualizar`; vigias diários de publicações no Portal da NF-e e de mudanças nos esquemas da calculadora.

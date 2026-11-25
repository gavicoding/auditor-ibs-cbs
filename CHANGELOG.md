# Mudanças

## 1.0.0

Primeira versão pública.

- Documentos: NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e e NFS-e nacional (DPS ou autorizada).
- Regras `AIC-001` a `AIC-052`: códigos CST e cClassTrib (existência, vigência, par, documento), NCM e NBS aplicáveis com exceções oficiais, NCM inexistente, grupos exigidos pelo CST, formato e campos obrigatórios do leiaute, redução, alíquota efetiva, diferimento, crédito presumido, compra governamental, tributação regular, monofásico e totais.
- Resumo do lote (problemas, cClassTrib, NCM, emitente e valores por cClassTrib) e planilhas CSV.
- Consulta por CST, cClassTrib e NCM.
- Validação opcional contra o XSD oficial (`--xsd`).
- Versão web que roda no navegador, idêntica à versão Python (mesmo gabarito e teste com documentos aleatórios).
- Tabelas extraídas do repositório público da calculadora da Receita Federal (base V0073, 09/11/2026), com atualização semanal automática.

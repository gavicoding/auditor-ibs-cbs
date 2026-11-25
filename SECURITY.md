# Segurança

Se encontrar uma falha de segurança (por exemplo, um XML que faça o leitor travar, consumir memória sem limite ou executar algo), **não abra uma issue pública**. Use o [relato privado de vulnerabilidade do GitHub](https://github.com/gavicoding/auditor-ibs-cbs/security/advisories/new).

Proteções que já existem:

- XML com `DOCTYPE`/`ENTITY` é recusado (evita XXE e "billion laughs");
- limite de 20 MB por XML e de 200 mil arquivos por .zip; nada é extraído para o disco;
- a página web não envia dados para nenhum servidor e usa uma Content-Security-Policy restritiva;
- o CSV exportado neutraliza fórmulas (proteção contra CSV injection).

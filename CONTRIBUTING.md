# Como contribuir

Obrigado por querer ajudar! Este projeto existe para a comunidade: contadores, analistas fiscais e quem desenvolve ERPs e emissores.

## Antes de tudo: nunca envie dados reais

**Não anexe XMLs reais em issues ou pull requests.** Eles têm CNPJ, CPF, endereço e valores de clientes. Para mostrar um problema:

1. copie só o trecho do item com o grupo `IBSCBS` e troque os valores, ou
2. monte uma nota fictícia com [`ferramentas/gerar_exemplos.py`](ferramentas/gerar_exemplos.py).

## Tipos de contribuição

- **Falso alarme ou problema que não foi pego:** abra uma issue com o trecho fictício, o resultado que saiu e o que você esperava, citando a regra (NT 2025.002, informe técnico ou tabela) quando souber.
- **Explicação confusa:** sugira um texto melhor. Mensagem clara vale tanto quanto código.
- **Regra nova:** abra uma issue antes, com a referência normativa. Toda regra precisa existir nas duas versões (Python e web).

## Regras do código

- A regra entra em `src/auditor_ibs_cbs/regras.py` **e** em `docs/auditor.js`, com o mesmo código `AIC-0xx`, gravidade e texto.
- Inclua um XML fictício em `exemplos/` (gerado por `ferramentas/gerar_exemplos.py`) e regere o gabarito com `python ferramentas/gerar_esperado.py`, revisando o diff.
- Rode antes de abrir o PR:

```bash
ruff check . && ruff format --check .
pytest
node --test tests/web/paridade.test.mjs
python ferramentas/fuzz_paridade.py /tmp/fuzz 2000 && node tests/web/fuzz.mjs /tmp/fuzz
python ferramentas/sincronizar_web.py   # se mexeu nas tabelas ou nos exemplos
```

- As tabelas (`tabelas-rtc.json`) **não** são editadas à mão: elas vêm do repositório da Receita pelo `ferramentas/exportar_tabelas.py`.
- Sem dependências novas no pacote Python nem na página web.

## Conduta

Seja respeitoso e objetivo. Dúvidas tributárias de casos específicos devem ir para o seu contador; aqui discutimos o comportamento da ferramenta.

// A versão web precisa dar exatamente o mesmo resultado da versão Python (tests/esperado.json).
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { arredondar, auditar, criarTabelas, dec, lerNota, lerZip, XMLInvalido } from "../../docs/auditor.js";

const raiz = fileURLToPath(new URL("../../", import.meta.url));
const esperado = JSON.parse(readFileSync(raiz + "tests/esperado.json", "utf8"));
const tabelas = criarTabelas(JSON.parse(readFileSync(raiz + "docs/tabelas-rtc.json", "utf8")));
const chave = (x) => [x[0], x[1], x[2] ?? ""].join("|");
const ordenar = (lista) => [...lista].sort((a, b) => (chave(a) < chave(b) ? -1 : chave(a) > chave(b) ? 1 : 0));

for (const [nome, esp] of Object.entries(esperado)) {
  test(`exemplo ${nome}`, () => {
    const xml = readFileSync(raiz + "exemplos/" + nome, "utf8");
    if (esp.ilegivel) {
      assert.throws(() => lerNota(xml, nome), XMLInvalido);
      return;
    }
    const r = auditar(lerNota(xml, nome), tabelas);
    assert.deepEqual(ordenar(r.achados.map((a) => [a.codigo, a.gravidade, a.item])), ordenar(esp.achados));
  });
}

test("todos os exemplos estão no gabarito", () => {
  const xmls = readdirSync(raiz + "exemplos").filter((n) => n.endsWith(".xml"));
  assert.deepEqual(xmls.sort(), Object.keys(esperado).sort());
});

test("arredondamento bancário igual ao Python", () => {
  for (const [v, e] of [["0.125", "0.12"], ["0.135", "0.14"], ["1.005", "1.00"], ["2.675", "2.68"], ["10", "10.00"]]) {
    assert.equal(arredondar(dec(v)), dec(e));
  }
});

test("zip de exemplo é lido no navegador/Node", async () => {
  const bytes = new Uint8Array(readFileSync(raiz + "exemplos/lote-exemplo.zip"));
  const itens = await lerZip(bytes, "lote-exemplo.zip");
  assert.equal(itens.length, 3);
  assert.ok(itens.every(([o, c]) => o.includes("!lote/") && typeof c === "string"));
});

test("tabelas da página iguais às do pacote Python", () => {
  const web = readFileSync(raiz + "docs/tabelas-rtc.json", "utf8");
  const py = readFileSync(raiz + "src/auditor_ibs_cbs/dados/tabelas-rtc.json", "utf8");
  assert.equal(web, py);
});

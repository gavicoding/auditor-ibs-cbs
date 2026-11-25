// Compara a versão web com o gabarito gerado pela versão Python em ferramentas/fuzz_paridade.py.
import { readFileSync } from "node:fs";
import { auditar, criarTabelas, lerNota } from "../../docs/auditor.js";

const pasta = process.argv[2];
const raiz = new URL("../../", import.meta.url);
const tabelas = criarTabelas(
  JSON.parse(readFileSync(new URL("docs/tabelas-rtc.json", raiz), "utf8")),
  JSON.parse(readFileSync(new URL("docs/ncm.json", raiz), "utf8")).ncm,
);
const gabarito = JSON.parse(readFileSync(`${pasta}/gabarito.json`, "utf8"));
const chave = (x) => [x[0], x[1], x[2] ?? ""].join("|");
let falhas = 0;
for (const [nome, esperado] of Object.entries(gabarito)) {
  const r = auditar(lerNota(readFileSync(`${pasta}/${nome}`, "utf8"), nome), tabelas);
  const obtido = r.achados.map((a) => [a.codigo, a.gravidade, a.item]).map(chave).sort();
  const esp = esperado.map(chave).sort();
  if (JSON.stringify(obtido) !== JSON.stringify(esp)) {
    falhas++;
    if (falhas <= 5) console.error(nome, "\n  python:", esp, "\n  web:   ", obtido);
  }
}
const total = Object.keys(gabarito).length;
const achados = Object.values(gabarito).reduce((n, a) => n + a.length, 0);
console.log(`${total - falhas}/${total} notas iguais (${achados} achados comparados)`);
process.exit(falhas ? 1 : 0);

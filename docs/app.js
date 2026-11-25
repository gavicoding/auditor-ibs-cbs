// Interface da página. Todo texto vindo dos XMLs entra no DOM por textContent (nunca innerHTML).
import { auditarTexto, criarTabelas, lerZip, situacao, TAMANHO_MAXIMO } from "./auditor.js";

const EXEMPLOS = [
  "01-correta.xml", "02-sem-grupo-regime-normal.xml", "03-sem-grupo-simples-nacional.xml",
  "04-cclasstrib-de-outro-cst.xml", "05-cclasstrib-inexistente.xml", "06-cclasstrib-nao-permitido-nfce.xml",
  "07-valores-errados.xml", "08-reducao-diferente-da-oficial.xml", "09-grupo-gibscbs-ausente.xml",
  "10-reducao-correta-cesta-basica.xml", "12-cclasstrib-encerrado.xml",
];
const ROTULO = { erro: "ERRO", atencao: "ATENÇÃO", info: "INFO", ok: "OK" };
const $ = (s) => document.querySelector(s);
const el = (tag, props = {}, ...filhos) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const f of filhos) if (f) e.append(f);
  return e;
};

let tabelas = null;
let resultados = [];
let filtro = "problemas";

async function iniciar() {
  const resp = await fetch("tabelas-rtc.json");
  tabelas = criarTabelas(await resp.json());
  const f = tabelas.fonte;
  $("#fonte").textContent = `Tabelas oficiais: base ${f.versao_base} de ${f.data_base.split("-").reverse().join("/")} (${Object.keys(tabelas.dados.cst).length} CST e ${Object.keys(tabelas.dados.cclasstrib).length} cClassTrib de IBS/CBS). ${f.descricao_base}`;
}

async function processar(arquivos) {
  if (!tabelas) await iniciar();
  const barra = $("#progresso");
  barra.classList.remove("hidden");
  const entradas = [];
  for (const arq of arquivos) {
    if (arq.name.toLowerCase().endsWith(".zip")) {
      try {
        entradas.push(...(await lerZip(new Uint8Array(await arq.arrayBuffer()), arq.name)));
      } catch (e) {
        entradas.push([arq.name, e]);
      }
    } else if (arq.size > TAMANHO_MAXIMO) {
      entradas.push([arq.name, new Error("arquivo maior que 20 MB")]);
    } else {
      entradas.push([arq.name, await arq.text()]);
    }
  }
  for (let i = 0; i < entradas.length; i++) {
    const [origem, conteudo] = entradas[i];
    if (conteudo instanceof Error) {
      resultados.push({ origem, achados: [{ codigo: "AIC-001", gravidade: "erro", titulo: "Arquivo não pôde ser lido", explicacao: conteudo.message, como_corrigir: "Confira se é o XML da NF-e/NFC-e, completo e sem alterações." }] });
    } else {
      resultados.push(auditarTexto(conteudo, origem, tabelas));
    }
    if (i % 50 === 0) {
      barra.firstElementChild.style.width = `${Math.round(((i + 1) / entradas.length) * 100)}%`;
      await new Promise((r) => setTimeout(r, 0));
    }
  }
  barra.classList.add("hidden");
  desenhar();
}

function desenhar() {
  const sit = resultados.map((r) => situacao(r.achados));
  $("#s-notas").textContent = resultados.length;
  $("#s-ok").textContent = sit.filter((s) => s === "ok").length;
  $("#s-atencao").textContent = sit.filter((s) => s === "atencao").length;
  $("#s-erro").textContent = sit.filter((s) => s === "erro").length;
  $("#resultado").classList.toggle("hidden", resultados.length === 0);
  const lista = $("#lista");
  lista.replaceChildren();
  let mostradas = 0;
  resultados.forEach((r, i) => {
    const s = sit[i];
    if (filtro === "problemas" && s === "ok") return;
    if ((filtro === "erro" || filtro === "atencao") && s !== filtro) return;
    if (mostradas++ > 2000) return;
    const visiveis = r.achados.filter((a) => a.gravidade !== "info" || filtro === "todas");
    const nota = el("details", { class: "nota" });
    if (s !== "ok" && mostradas <= 20) nota.open = true;
    const ident = r.numero ? `NF ${r.numero} · série ${r.serie ?? "?"}` : "Arquivo";
    nota.append(
      el("summary", {},
        el("span", { class: `pill ${s}`, text: ROTULO[s] }),
        el("span", { class: "ident", text: ident }),
        el("span", { class: "orig", text: r.chave ? `chave ${r.chave}` : r.origem }),
      ),
    );
    if (!visiveis.length) nota.append(el("div", { class: "empty", text: "Nenhum problema encontrado nesta nota." }));
    for (const a of visiveis) {
      nota.append(
        el("div", { class: "achado" },
          el("span", { class: `pill ${a.gravidade}`, text: ROTULO[a.gravidade] }),
          el("div", {},
            el("h3", { text: (a.item ? `Item ${a.item}: ` : "") + a.titulo }),
            el("p", { text: a.explicacao }),
            el("p", { class: "fix", text: `Como corrigir: ${a.como_corrigir}` }),
            el("code", { text: a.codigo + (a.campo ? ` · ${a.campo}` : "") + ` · ${r.origem}` }),
          ),
        ),
      );
    }
    lista.append(nota);
  });
  if (!mostradas) lista.append(el("p", { class: "empty", text: "Nenhuma nota neste filtro." }));
}

function csv() {
  const linhas = [["arquivo", "chave", "numero", "serie", "emissao", "item", "gravidade", "codigo", "problema", "explicacao", "como_corrigir", "campo"]];
  for (const r of resultados) {
    for (const a of r.achados) {
      linhas.push([r.origem, r.chave, r.numero, r.serie, r.emissao, a.item, a.gravidade, a.codigo, a.titulo, a.explicacao, a.como_corrigir, a.campo]);
    }
  }
  // Protege contra fórmulas ao abrir no Excel (CSV injection)
  const celula = (v) => {
    let s = v == null ? "" : String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return `"${s.replace(/"/g, '""')}"`;
  };
  const texto = "﻿" + linhas.map((l) => l.map(celula).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob([texto], { type: "text/csv;charset=utf-8" }));
  const a = el("a", { href: url, download: "auditoria-ibs-cbs.csv" });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function consultar(codigo) {
  const saida = $("#consulta-saida");
  saida.replaceChildren();
  codigo = codigo.trim();
  if (!tabelas || !/^\d{3}(\d{3})?$/.test(codigo)) {
    saida.append(el("p", { class: "empty", text: "Digite 3 dígitos (CST) ou 6 dígitos (cClassTrib)." }));
    return;
  }
  const dl = el("dl");
  const par = (t, d) => dl.append(el("dt", { text: t }), el("dd", { text: d }));
  if (codigo.length === 3 && tabelas.cst(codigo)) {
    const c = tabelas.cst(codigo);
    par(`CST ${codigo}`, c.descricao);
    par("Grupos exigidos", Object.entries(c.grupos).filter(([, v]) => v).map(([k]) => k).join(", ") || "nenhum");
    const ul = el("ul");
    for (const [cod, reg] of Object.entries(tabelas.dados.cclasstrib)) if (reg.cst === codigo) ul.append(el("li", { text: `${cod}  ${reg.descricao}` }));
    dl.append(el("dt", { text: "cClassTrib deste CST" }), el("dd", {}, ul));
  } else if (tabelas.cclasstrib(codigo)) {
    const r = tabelas.cclasstrib(codigo);
    const nomes = { 55: "NF-e", 65: "NFC-e", 57: "CT-e", 67: "CT-e OS", 63: "BP-e", 66: "NF3-e", 91: "NFS-e", 62: "NFCom", 96: "Duimp" };
    par(`cClassTrib ${codigo}`, r.descricao);
    par("CST", `${r.cst} (${tabelas.cst(r.cst).descricao})`);
    par("Tipo de alíquota", r.tipo_aliquota);
    par("Vigência", `${r.inicio} a ${r.fim || "atual"}`);
    par("Pode ser usado em", [...new Set(r.documentos.map((d) => nomes[d.modelo] || `modelo ${d.modelo}`))].join(", "));
    const red = r.reducao.filter((x) => x.percentual);
    if (red.length) par("Redução", red.map((x) => `${x.tributo} ${String(x.percentual).replace(".", ",")}%`).join(", "));
  } else {
    saida.append(el("p", { class: "empty", text: `Código ${codigo} não encontrado na tabela ${tabelas.versao}.` }));
    return;
  }
  saida.append(dl);
}

// ---------------------------------------------------------------- eventos
const entrada = $("#arquivos");
const drop = $("#drop");
$("#escolher").addEventListener("click", () => entrada.click());
drop.addEventListener("click", () => entrada.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); entrada.click(); } });
entrada.addEventListener("change", () => { processar([...entrada.files]); entrada.value = ""; });
for (const ev of ["dragenter", "dragover"]) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); });
for (const ev of ["dragleave", "drop"]) drop.addEventListener(ev, () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); processar([...e.dataTransfer.files]); });
$("#exemplos").addEventListener("click", async () => {
  const arquivos = await Promise.all(EXEMPLOS.map(async (n) => new File([await (await fetch(`exemplos/${n}`)).text()], n)));
  processar(arquivos);
});
document.querySelectorAll("[data-filtro]").forEach((b) =>
  b.addEventListener("click", () => {
    filtro = b.dataset.filtro;
    document.querySelectorAll("[data-filtro]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    desenhar();
  }),
);
$("#baixar-csv").addEventListener("click", csv);
$("#limpar").addEventListener("click", () => { resultados = []; desenhar(); });
$("#consulta").addEventListener("submit", (e) => { e.preventDefault(); consultar($("#codigo").value); });
iniciar().catch(() => { $("#fonte").textContent = "Não foi possível carregar as tabelas."; });

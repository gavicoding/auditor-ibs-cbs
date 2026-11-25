// Interface da página. Todo texto vindo dos XMLs entra no DOM por textContent (nunca innerHTML).
import { auditarTexto, criarTabelas, lerZip, resumo, situacao, TAMANHO_MAXIMO } from "./auditor.js";

const ROTULO = { erro: "ERRO", atencao: "ATENÇÃO", info: "INFO", ok: "OK" };
const NOMES_DOC = { 55: "NF-e", 65: "NFC-e", 57: "CT-e", 67: "CT-e OS", 63: "BP-e", 66: "NF3-e", 91: "NFS-e", 62: "NFCom", 96: "Duimp" };
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
const semTags = (s) => String(s).replace(/<[^>]*>/g, "");
const hoje = () => new Date().toISOString().slice(0, 10);

let tabelas = null;
let resultados = [];
let filtro = "problemas";
let carregando = null;

function iniciar() {
  carregando ||= (async () => {
    const [dados, ncm] = await Promise.all([
      fetch("tabelas-rtc.json").then((r) => r.json()),
      fetch("ncm.json").then((r) => r.json()),
    ]);
    tabelas = criarTabelas(dados, ncm.ncm);
    const f = tabelas.fonte;
    $("#fonte").textContent =
      `Tabelas oficiais: base ${f.versao_base} de ${f.data_base.split("-").reverse().join("/")} ` +
      `(${Object.keys(dados.cst).length} CST, ${Object.keys(dados.cclasstrib).length} cClassTrib, ` +
      `${Object.keys(ncm.ncm).length.toLocaleString("pt-BR")} NCM). ${f.descricao_base}`;
  })();
  return carregando;
}

async function processar(arquivos) {
  await iniciar();
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
      resultados.push({ origem, linhas: [], achados: [{ codigo: "AIC-001", gravidade: "erro", titulo: "Arquivo não pôde ser lido", explicacao: conteudo.message, como_corrigir: "Confira se é o XML do documento fiscal, completo e sem alterações." }] });
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

function tabelaResumo(titulo, cabecalho, linhas) {
  if (!linhas.length) return null;
  const tabela = el("table", { class: "mini" });
  tabela.append(el("thead", {}, el("tr", {}, ...cabecalho.map((c) => el("th", { text: c })))));
  const corpo = el("tbody");
  for (const linha of linhas) corpo.append(el("tr", {}, ...linha.map((c) => el("td", { text: String(c) }))));
  tabela.append(corpo);
  return el("div", { class: "card mini-card" }, el("h3", { text: titulo }), el("div", { class: "rolagem" }, tabela));
}

function desenharResumo() {
  const s = resumo(resultados);
  const caixa = $("#resumo");
  caixa.replaceChildren();
  const blocos = [
    tabelaResumo("Problemas mais comuns", ["Código", "Problema", "Qtde"], s.problemasMaisComuns.map(([c, n, t]) => [c, t, n])),
    tabelaResumo("Itens com problema por cClassTrib", ["cClassTrib", "Itens"], s.porCclasstrib),
    tabelaResumo("Itens com problema por NCM", ["NCM", "Itens"], s.porNcm),
    tabelaResumo("Documentos com problema por emitente", ["CNPJ do emitente", "Docs"], s.porEmitente),
    tabelaResumo("Valores por cClassTrib (todas as notas)", ["cClassTrib", "Itens", "Base (R$)", "IBS (R$)", "CBS (R$)"], s.valores),
    tabelaResumo("Documentos por tipo", ["Tipo", "Qtde"], s.porTipo),
  ].filter(Boolean);
  caixa.append(...blocos);
  $("#resumo-titulo").classList.toggle("hidden", !blocos.length);
}

function desenhar() {
  const sit = resultados.map((r) => situacao(r.achados));
  $("#s-notas").textContent = resultados.length;
  $("#s-ok").textContent = sit.filter((s) => s === "ok").length;
  $("#s-atencao").textContent = sit.filter((s) => s === "atencao").length;
  $("#s-erro").textContent = sit.filter((s) => s === "erro").length;
  $("#resultado").classList.toggle("hidden", resultados.length === 0);
  desenharResumo();
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
    const ident = r.numero ? `${r.tipo || "Documento"} ${r.numero} · série ${r.serie ?? "?"}` : "Arquivo";
    nota.append(el("summary", {}, el("span", { class: `pill ${s}`, text: ROTULO[s] }), el("span", { class: "ident", text: ident }), el("span", { class: "orig", text: r.chave ? `chave ${r.chave}` : r.origem })));
    if (!visiveis.length) nota.append(el("div", { class: "empty", text: "Nenhum problema encontrado neste documento." }));
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
  if (!mostradas) lista.append(el("p", { class: "empty", text: "Nenhum documento neste filtro." }));
}

function baixar(nome, linhas) {
  // Protege contra fórmulas ao abrir no Excel (CSV injection)
  const celula = (v) => {
    let s = v == null ? "" : String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return `"${s.replace(/"/g, '""')}"`;
  };
  const texto = "﻿" + linhas.map((l) => l.map(celula).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob([texto], { type: "text/csv;charset=utf-8" }));
  const a = el("a", { href: url, download: nome });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function csvProblemas() {
  const linhas = [["arquivo", "documento", "chave", "numero", "serie", "emissao", "emitente", "item", "gravidade", "codigo", "problema", "explicacao", "como_corrigir", "campo"]];
  for (const r of resultados) for (const a of r.achados) linhas.push([r.origem, r.tipo, r.chave, r.numero, r.serie, r.emissao, r.emitente, a.item, a.gravidade, a.codigo, a.titulo, a.explicacao, a.como_corrigir, a.campo]);
  baixar("auditoria-ibs-cbs.csv", linhas);
}

function csvValores() {
  const s = resumo(resultados);
  const problemas = Object.fromEntries(s.porCclasstrib);
  baixar("valores-por-cclasstrib.csv", [["cclasstrib", "itens", "base_calculo", "ibs", "cbs", "itens_com_problema"], ...s.valores.map(([c, n, b, i, cb]) => [c, n, b, i, cb, problemas[c] || 0])]);
}

function consultar(codigo) {
  const saida = $("#consulta-saida");
  saida.replaceChildren();
  codigo = codigo.trim().replace(/\D/g, "");
  if (!tabelas || !/^(\d{3}|\d{6}|\d{8})$/.test(codigo)) {
    saida.append(el("p", { class: "empty", text: "Digite 3 dígitos (CST), 6 dígitos (cClassTrib) ou 8 dígitos (NCM)." }));
    return;
  }
  const dl = el("dl");
  const par = (t, d) => dl.append(el("dt", { text: t }), typeof d === "string" ? el("dd", { text: d }) : el("dd", {}, d));
  const dia = hoje();
  if (codigo.length === 3 && tabelas.cst(codigo)) {
    const c = tabelas.cst(codigo);
    par(`CST ${codigo}`, c.descricao);
    par("Grupos exigidos", Object.entries(c.grupos).filter(([, v]) => v).map(([k]) => k).join(", ") || "nenhum");
    const ul = el("ul");
    for (const [cod, reg] of Object.entries(tabelas.dados.cclasstrib)) if (reg.cst === codigo) ul.append(el("li", { text: `${cod}  ${reg.descricao}` }));
    par("cClassTrib deste CST", ul);
  } else if (codigo.length === 6 && tabelas.cclasstrib(codigo)) {
    const r = tabelas.cclasstrib(codigo);
    par(`cClassTrib ${codigo}`, r.descricao);
    par("CST", `${r.cst} (${tabelas.cst(r.cst).descricao})`);
    par("Tipo de alíquota", r.tipo_aliquota);
    par("Vigência", `${r.inicio} a ${r.fim || "atual"}`);
    par("Pode ser usado em", [...new Set(r.documentos.map((d) => NOMES_DOC[d.modelo] || `modelo ${d.modelo}`))].join(", "));
    const red = r.reducao.filter((x) => x.percentual);
    if (red.length) par("Redução", red.map((x) => `${x.tributo} ${String(x.percentual).replace(".", ",")}%`).join(", "));
    for (const tipo of ["ncm", "nbs"]) {
      const lista = [...new Set((r[tipo] || []).filter((n) => !n.fim).map((n) => n.codigo))];
      if (lista.length) {
        par(`Só vale para estes ${tipo.toUpperCase()} (${lista.length})`, lista.slice(0, 40).join(", ") + (lista.length > 40 ? " …" : ""));
        const anexos = tabelas.anexos(codigo, tipo, dia);
        if (anexos.length) par("Base legal (LC 214/2025)", anexos.slice(0, 8).join("; ") + (anexos.length > 8 ? " …" : ""));
      }
    }
  } else if (codigo.length === 8) {
    const reg = tabelas.ncm(codigo);
    par(`NCM ${codigo}`, reg ? semTags(reg[0]) : "não encontrado na tabela NCM");
    const aceitam = Object.keys(tabelas.dados.cclasstrib).filter((c) => tabelas.temLista(c, "ncm", dia) && tabelas.aplicavel(c, "ncm", codigo, dia));
    if (aceitam.length) {
      const ul = el("ul");
      for (const c of aceitam) {
        const r = tabelas.cclasstrib(c);
        const red = r.reducao.filter((x) => x.percentual).map((x) => x.percentual);
        ul.append(el("li", { text: `${c} (CST ${r.cst}) ${r.descricao}${red.length ? ` · redução ${Math.max(...red)}%` : ""}` }));
      }
      par("cClassTrib com lista de produtos que aceitam este NCM", ul);
    } else {
      par("cClassTrib com lista", "Nenhum cClassTrib com lista específica aceita este NCM; ele segue os códigos sem lista (ex.: 000001).");
    }
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
  const nomes = await (await fetch("exemplos/lista.json")).json();
  const arquivos = await Promise.all(nomes.map(async (n) => new File([await (await fetch(`exemplos/${n}`)).text()], n)));
  processar(arquivos);
});
document.querySelectorAll("[data-filtro]").forEach((b) =>
  b.addEventListener("click", () => {
    filtro = b.dataset.filtro;
    document.querySelectorAll("[data-filtro]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    desenhar();
  }),
);
$("#baixar-csv").addEventListener("click", csvProblemas);
$("#baixar-valores").addEventListener("click", csvValores);
$("#limpar").addEventListener("click", () => { resultados = []; desenhar(); });
$("#consulta").addEventListener("submit", async (e) => { e.preventDefault(); await iniciar(); consultar($("#codigo").value); });
iniciar().catch(() => { $("#fonte").textContent = "Não foi possível carregar as tabelas."; });

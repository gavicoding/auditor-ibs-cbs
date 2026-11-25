// auditor-ibs-cbs (versão web). Mesmas regras da versão Python (src/auditor_ibs_cbs/), conferidas
// pelo mesmo gabarito (tests/esperado.json) e por um teste com documentos aleatórios a cada mudança.
// Roda no navegador e no Node, sem dependências. Nenhum dado sai da máquina de quem usa.

export const TAMANHO_MAXIMO = 20 * 1024 * 1024;
const MODELOS_SUPORTADOS = new Set([55, 65, 57, 67, 63, 66, 91]);
const SIGLAS = { 55: "NF-e", 65: "NFC-e", 57: "CT-e", 67: "CT-e OS", 63: "BP-e", 66: "NF3-e", 91: "NFS-e" };
const RAIZES = {
  infNFe: ["NF-e", 55, "ide/nNF"],
  infCte: ["CT-e", 57, "ide/nCT"],
  infBPe: ["BP-e", 63, "ide/nBP"],
  infNF3e: ["NF3-e", 66, "ide/nNF"],
  infNFSe: ["NFS-e", 91, "nNFSe"],
  infDPS: ["NFS-e", 91, "nDPS"],
};
const GRUPOS_POR_INDICADOR = ["gIBSCBS", "gIBSCBSMono", "gTransfCred", "gCredPresIBSZFM", "gAjusteCompet"];
const EXIGEM_NCM_SEMPRE = new Set(["200038", "515001"]);
const NCM_ZERO = new Set(["00", "00000000"]);
const NUMERICOS = ["v", "p", "q", "adRem"];
const OBRIGATORIOS_GIBSCBS = ["vBC", "gIBSUF/pIBSUF", "gIBSUF/vIBSUF", "gIBSMun/pIBSMun", "gIBSMun/vIBSMun", "vIBS", "gCBS/pCBS", "gCBS/vCBS"];
const OBRIGATORIOS_SUB = { gRed: ["pRedAliq", "pAliqEfet"], gDif: ["pDif", "vDif"], gDevTrib: ["vDevTrib"] };
const FORMATOS_DFE = [
  [["CST", "CSTReg"], /^\d{3}$/, "3 dígitos", true],
  [["cClassTrib", "cClassTribReg"], /^\d{6}$/, "6 dígitos", true],
  [["cCredPres"], /^\d{2}$/, "2 dígitos", true],
  [["q"], /^(0|0\.[0-9]{4}|[1-9][0-9]{0,10}(\.[0-9]{4})?)$/, "número com 4 casas decimais", false],
  [["p", "adRem"], /^(0|0\.[0-9]{2,4}|[1-9][0-9]{0,2}(\.[0-9]{2,4})?)$/, "percentual com 2 a 4 casas decimais (ex.: 0.90)", false],
  [["v"], /^(0|0\.[0-9]{2}|[1-9][0-9]{0,12}(\.[0-9]{2})?)$/, "valor com 2 casas decimais (ex.: 10.50)", false],
];
const FORMATOS_NFSE = [
  [["CST", "CSTReg"], /^\d{3}$/, "3 dígitos", true],
  [["cClassTrib", "cClassTribReg"], /^\d{6}$/, "6 dígitos", true],
  [["v"], /^(0|0\.[0-9]{2}|[1-9][0-9]{0,14}(\.[0-9]{2})?)$/, "valor com 2 casas decimais (ex.: 10.50)", false],
];

export class XMLInvalido extends Error {}

// ---------------------------------------------------------------- leitor de XML mínimo e seguro
function decodificar(texto) {
  return texto.replace(/&(#x[0-9a-fA-F]+|#\d+|amp|lt|gt|quot|apos);/g, (_, e) => {
    if (e[0] === "#") return String.fromCodePoint(e[1] === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" }[e];
  });
}

export function parseXML(texto) {
  if (/<!DOCTYPE/i.test(texto.slice(0, 4096)) || /<!ENTITY/i.test(texto)) {
    throw new XMLInvalido("XML com DOCTYPE/ENTITY foi recusado por segurança");
  }
  const raiz = { tag: "#doc", attrs: {}, filhos: [], texto: "" };
  const pilha = [raiz];
  const re = /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[([\s\S]*?)\]\]>|<\/([^\s>]+)\s*>|<([^\s/>!?]+)((?:\s+[^\s=>/]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>|([^<]+)/g;
  let m;
  let pos = 0;
  while ((m = re.exec(texto)) !== null) {
    if (m.index !== pos) throw new XMLInvalido("XML mal formado");
    pos = re.lastIndex;
    const atual = pilha[pilha.length - 1];
    if (m[1] !== undefined) atual.texto += m[1];
    else if (m[2] !== undefined) {
      const nome = m[2].split(":").pop();
      if (pilha.length < 2 || atual.tag !== nome) throw new XMLInvalido("XML mal formado (tag fechada fora de ordem)");
      pilha.pop();
    } else if (m[3] !== undefined) {
      const attrs = {};
      for (const a of m[4].matchAll(/([^\s=]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) {
        attrs[a[1].split(":").pop()] = decodificar(a[2] ?? a[3]);
      }
      const no = { tag: m[3].split(":").pop(), attrs, filhos: [], texto: "" };
      atual.filhos.push(no);
      if (!m[5]) pilha.push(no);
    } else if (m[6] !== undefined) {
      if (pilha.length === 1) {
        if (m[6].trim()) throw new XMLInvalido("XML mal formado");
      } else atual.texto += decodificar(m[6]);
    }
  }
  if (pos !== texto.length || pilha.length !== 1) throw new XMLInvalido("XML mal formado (incompleto)");
  if (raiz.filhos.length !== 1) throw new XMLInvalido("XML mal formado");
  return raiz.filhos[0];
}

function filho(no, caminho) {
  let atual = no;
  for (const parte of caminho.split("/")) {
    if (!atual) return null;
    atual = atual.filhos.find((f) => f.tag === parte) || null;
  }
  return atual;
}
function todos(no, caminho) {
  const partes = caminho.split("/");
  let atuais = [no];
  for (const parte of partes) atuais = atuais.flatMap((a) => a.filhos.filter((f) => f.tag === parte));
  return atuais;
}
function texto(no, caminho) {
  const n = no ? filho(no, caminho) : null;
  return n ? n.texto.trim() : null;
}
function busca(no, tag) {
  if (no.tag === tag) return no;
  for (const f of no.filhos) {
    const r = busca(f, tag);
    if (r) return r;
  }
  return null;
}

// ---------------------------------------------------------------- números decimais exatos
// Valores em BigInt na escala de 16 casas: as contas do leiaute (2 e 4 casas, percentuais
// multiplicados entre si) ficam exatas, sem ponto flutuante.
const ESCALA = 16;
const UM = 10n ** BigInt(ESCALA);
const CEM = 100n * UM;
export function dec(t) {
  if (t === null || t === undefined || t === "") return null;
  const s = String(t).trim();
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
  const neg = s.startsWith("-");
  const [int, fra = ""] = s.replace("-", "").split(".");
  const fr = (fra + "0".repeat(ESCALA)).slice(0, ESCALA);
  const v = BigInt(int) * UM + BigInt(fr);
  return neg ? -v : v;
}
const mul = (a, b) => (a * b) / UM;
const div100 = (a) => a / 100n;
const abs = (a) => (a < 0n ? -a : a);
export function arredondar(v, casas = 2) {
  const passo = 10n ** BigInt(ESCALA - casas);
  const neg = v < 0n;
  const a = neg ? -v : v;
  let q = a / passo;
  const r = a % passo;
  const meio = passo / 2n;
  if (r > meio || (r === meio && q % 2n === 1n)) q += 1n;
  const res = q * passo;
  return neg ? -res : res;
}
const TOLERANCIA = dec("0.01");
const DEZ_MILESIMO = dec("0.0001");
function partes(v, casas) {
  const neg = v < 0n;
  const a = neg ? -v : v;
  const int = a / UM;
  const fra = (a % UM).toString().padStart(ESCALA, "0");
  return { neg, int, fra: casas === undefined ? fra.replace(/0+$/, "") : fra.slice(0, casas) };
}
function brl(v) {
  if (v === null || v === undefined) return "?";
  const { neg, int, fra } = partes(arredondar(v), 2);
  return (neg ? "-" : "") + int.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + fra;
}
function pct(v) {
  if (v === null || v === undefined) return "?";
  const { neg, int, fra } = partes(v);
  return (neg ? "-" : "") + int.toString() + (fra ? "," + fra : "") + "%";
}
function numeroTexto(v) {
  const { neg, int, fra } = partes(v);
  return (neg ? "-" : "") + int.toString() + (fra ? "." + fra : "");
}
const decNum = (n) => (n === null || n === undefined ? null : dec(String(n)));
const soma = (vs) => vs.reduce((a, b) => a + (b ?? 0n), 0n);

// ---------------------------------------------------------------- leitura dos documentos
function campos(el, prefixo) {
  const out = [];
  const visitar = (no) => {
    for (const f of no.filhos) {
      if (f.filhos.length) visitar(f);
      else out.push({ caminho: prefixo, nome: f.tag, valor: f.texto.trim() });
    }
  };
  visitar(el);
  return out;
}

function valores(el) {
  const out = {};
  if (!el) return out;
  const visitar = (no, prefixo) => {
    for (const f of no.filhos) {
      const caminho = prefixo + f.tag;
      if (f.filhos.length) visitar(f, caminho + "/");
      else out[caminho] = NUMERICOS.some((p) => f.tag.startsWith(p)) ? dec(f.texto.trim()) : f.texto.trim();
    }
  };
  visitar(el, "");
  return out;
}

function tributo(g, prefixo, item, nomeGrupo) {
  if (!g) return null;
  const red = filho(g, "gRed");
  const dif = filho(g, "gDif");
  const dev = filho(g, "gDevTrib");
  for (const [sub, el] of [["gRed", red], ["gDif", dif], ["gDevTrib", dev]]) {
    if (el) for (const o of OBRIGATORIOS_SUB[sub]) if (!filho(el, o)) item.faltando.push(`${nomeGrupo}/${sub}/${o}`);
  }
  return {
    aliquota: dec(texto(g, `p${prefixo}`)),
    valor: dec(texto(g, `v${prefixo}`)),
    reducao: red ? dec(texto(red, "pRedAliq")) : null,
    aliquotaEfetiva: red ? dec(texto(red, "pAliqEfet")) : null,
    temDiferimento: !!dif,
    pDif: dif ? dec(texto(dif, "pDif")) : null,
    vDif: dif ? dec(texto(dif, "vDif")) : null,
    temDevolucao: !!dev,
    vDev: dev ? dec(texto(dev, "vDevTrib")) : null,
    pDev: dev ? dec(texto(dev, "pDevTrib")) : null,
    temAlczfm: !!filho(g, "gALCZFMCBS"),
  };
}

function somaTags(el, tag) {
  if (!el) return null;
  const vals = [];
  const visitar = (no) => {
    for (const f of no.filhos) {
      if (f.tag === tag) {
        const v = dec(f.texto.trim());
        if (v !== null) vals.push(v);
      }
      visitar(f);
    }
  };
  visitar(el);
  return vals.length ? vals.reduce((a, b) => a + b, 0n) : null;
}

function composicao(det) {
  // Valores do item usados na fórmula da base do IBS/CBS (NT 2025.002, regra UB16-10).
  const prod = filho(det, "prod");
  const imposto = filho(det, "imposto");
  if (!prod || dec(texto(prod, "vProd")) === null) return null;
  const z = (v) => v ?? 0n;
  const c = {};
  for (const nome of ["vProd", "vFrete", "vSeg", "vOutro", "vDesc"]) c[nome] = z(dec(texto(prod, nome)));
  c.vII = z(dec(texto(imposto, "II/vII")));
  c.vIS = z(dec(texto(imposto, "IS/vIS")));
  c.vISSQN = z(dec(texto(imposto, "ISSQN/vISSQN")));
  const icms = imposto ? filho(imposto, "ICMS") : null;
  c.vICMS = z(somaTags(icms, "vICMS"));
  c.vFCP = z(somaTags(icms, "vFCP"));
  c.vICMSMono = z(somaTags(icms, "vICMSMono"));
  c.vICMSUFDest = z(dec(texto(imposto, "ICMSUFDest/vICMSUFDest")));
  c.vFCPUFDest = z(dec(texto(imposto, "ICMSUFDest/vFCPUFDest")));
  c.vPIS = z(somaTags(imposto ? filho(imposto, "PIS") : null, "vPIS"));
  c.vCOFINS = z(somaTags(imposto ? filho(imposto, "COFINS") : null, "vCOFINS"));
  if (imposto && filho(imposto, "PISST") && texto(imposto, "PISST/indSomaPISST") !== "1") c.vPIS += z(dec(texto(imposto, "PISST/vPIS")));
  if (imposto && filho(imposto, "COFINSST") && texto(imposto, "COFINSST/indSomaCOFINSST") !== "1") c.vCOFINS += z(dec(texto(imposto, "COFINSST/vCOFINS")));
  return c;
}

function novoItem(numero, descricao, temGrupo, extra = {}) {
  return { numero, descricao, temGrupo, ncm: null, nbs: null, cst: null, cclasstrib: null, grupos: new Set(), base: null, ibsUF: null, ibsMun: null, cbs: null, valorIBS: null, especiais: {}, faltando: [], campos: [], cprodAnp: null, composicao: null, ...extra };
}

function grupoDfe(grupo, numero, descricao, ncm) {
  if (!grupo) return novoItem(numero, descricao, false, { ncm });
  const item = novoItem(numero, descricao, true, {
    ncm,
    cst: texto(grupo, "CST"),
    cclasstrib: texto(grupo, "cClassTrib"),
    grupos: new Set(grupo.filhos.map((f) => f.tag).filter((t) => t.startsWith("g"))),
    campos: campos(grupo, "IBSCBS"),
  });
  const g = filho(grupo, "gIBSCBS");
  if (g) {
    for (const o of OBRIGATORIOS_GIBSCBS) if (!filho(g, o)) item.faltando.push(`gIBSCBS/${o}`);
    item.base = dec(texto(g, "vBC"));
    item.ibsUF = tributo(filho(g, "gIBSUF"), "IBSUF", item, "gIBSUF");
    item.ibsMun = tributo(filho(g, "gIBSMun"), "IBSMun", item, "gIBSMun");
    item.cbs = tributo(filho(g, "gCBS"), "CBS", item, "gCBS");
    item.valorIBS = dec(texto(g, "vIBS"));
    for (const nome of ["gTribRegular", "gTribCompraGov"]) if (filho(g, nome)) item.especiais[nome] = valores(filho(g, nome));
  }
  for (const nome of ["gIBSCBSMono", "gTransfCred", "gAjusteCompet", "gEstornoCred", "gCredPresOper", "gCredPresIBSZFM"]) {
    if (filho(grupo, nome)) item.especiais[nome] = valores(filho(grupo, nome));
  }
  return item;
}

function totais(tot) {
  return tot ? { presente: true, valores: valores(tot), campos: campos(tot, "IBSCBSTot") } : { presente: false, valores: {}, campos: [] };
}

const data = (t) => (t && /^\d{4}-\d{2}-\d{2}/.test(t) ? t.slice(0, 10) : null);

function lerNfse(raiz, origem) {
  const infNfse = raiz.tag === "infNFSe" ? raiz : busca(raiz, "infNFSe");
  const infDps = raiz.tag === "infDPS" ? raiz : busca(raiz, "infDPS");
  if (!infDps) throw new XMLInvalido("NFS-e sem o DPS (infDPS), onde ficam o CST e o cClassTrib");
  const trib = filho(infDps, "IBSCBS/valores/trib/gIBSCBS");
  const descricao = (texto(infDps, "serv/cServ/xDescServ") || "").slice(0, 120);
  const item = novoItem("1", descricao, !!trib, { nbs: texto(infDps, "serv/cServ/cNBS") });
  if (trib) {
    item.cst = texto(trib, "CST");
    item.cclasstrib = texto(trib, "cClassTrib");
    item.grupos = new Set(trib.filhos.map((f) => f.tag).filter((t) => t.startsWith("g")));
    item.campos = campos(trib, "IBSCBS/valores/trib/gIBSCBS");
    if (filho(trib, "gTribRegular")) item.especiais.gTribRegular = valores(filho(trib, "gTribRegular"));
  }
  const dif = trib ? filho(trib, "gDif") : null;
  const calc = infNfse ? filho(infNfse, "IBSCBS") : null;
  let redutor = null;
  if (calc) {
    const v = filho(calc, "valores");
    const tot = filho(calc, "totCIBS");
    redutor = dec(texto(calc, "pRedutor"));
    item.base = dec(texto(v, "vBC"));
    const tribNfse = (sigla, grupo, totValor, totDif, pDif) => {
      const g = v ? filho(v, grupo) : null;
      const suf = sigla === "CBS" ? "CBS" : sigla.slice(3);
      return {
        aliquota: dec(texto(g, `p${sigla}`)),
        valor: dec(texto(tot, totValor)),
        reducao: dec(texto(g, `pRedAliq${suf}`)),
        aliquotaEfetiva: dec(texto(g, `pAliqEfet${suf}`)),
        temDiferimento: !!dif,
        pDif: dif ? dec(texto(dif, pDif)) : null,
        vDif: dec(texto(tot, totDif)),
        temDevolucao: false,
        vDev: null,
        pDev: null,
        temAlczfm: false,
      };
    };
    item.ibsUF = tribNfse("IBSUF", "uf", "gIBS/gIBSUFTot/vIBSUF", "gIBS/gIBSUFTot/vDifUF", "pDifUF");
    item.ibsMun = tribNfse("IBSMun", "mun", "gIBS/gIBSMunTot/vIBSMun", "gIBS/gIBSMunTot/vDifMun", "pDifMun");
    item.cbs = tribNfse("CBS", "fed", "gCBS/vCBS", "gCBS/vDifCBS", "pDifCBS");
    item.valorIBS = dec(texto(tot, "gIBS/vIBSTot"));
    item.grupos.add("gIBSCBS");
    item.campos.push(...campos(calc, "infNFSe/IBSCBS"));
  }
  return {
    origem,
    chave: infNfse ? (infNfse.attrs.Id || "").replace(/^NFS/, "") || null : null,
    modelo: 91,
    tipo: "NFS-e",
    numero: texto(infNfse, "nNFSe") || texto(infDps, "nDPS"),
    serie: texto(infDps, "serie"),
    emissao: data(texto(infDps, "dhEmi")),
    crt: null,
    cnpjEmitente: texto(infDps, "prest/CNPJ"),
    itens: [item],
    totais: totais(null),
    redutorCompraGov: redutor,
    porItem: false,
    finNFe: null,
    tpNFDebito: null,
    tpNFCredito: null,
    temCompraGov: false,
  };
}

export function lerNota(conteudo, origem) {
  if (conteudo.length > TAMANHO_MAXIMO) throw new XMLInvalido("arquivo maior que 20 MB");
  const raiz = parseXML(conteudo);
  let inf = null;
  for (const tag of Object.keys(RAIZES)) {
    inf = raiz.tag === tag ? raiz : busca(raiz, tag);
    if (inf) break;
  }
  if (!inf) throw new XMLInvalido("não é um documento fiscal suportado (NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e ou NFS-e)");
  if (inf.tag === "infNFSe" || inf.tag === "infDPS") return lerNfse(raiz, origem);
  const [sigla, modeloPadrao, caminhoNumero] = RAIZES[inf.tag];
  const ide = filho(inf, "ide");
  const mod = texto(ide, "mod");
  const modelo = mod && /^\d+$/.test(mod) ? Number(mod) : modeloPadrao;
  let chave = (inf.attrs.Id || "").slice(-44) || null;
  if (!chave) {
    for (const tag of ["chNFe", "chCTe", "chBPe", "chNF3e"]) {
      const p = busca(raiz, tag);
      if (p && p.texto.trim()) { chave = p.texto.trim(); break; }
    }
  }
  let itens = [];
  let tot = totais(null);
  let porItem = true;
  if (inf.tag === "infNFe") {
    itens = inf.filhos.filter((f) => f.tag === "det").map((det) => {
      const item = grupoDfe(filho(det, "imposto/IBSCBS"), det.attrs.nItem || "?", texto(det, "prod/xProd") || "", texto(det, "prod/NCM"));
      item.cprodAnp = texto(det, "prod/comb/cProdANP");
      item.composicao = composicao(det);
      return item;
    });
    tot = totais(filho(inf, "total/IBSCBSTot"));
  } else if (inf.tag === "infNF3e") {
    for (const det of todos(inf, "NFdet/det")) {
      for (const di of det.filhos.filter((f) => f.tag === "detItem")) {
        itens.push(grupoDfe(filho(di, "imposto/IBSCBS"), det.attrs.nItem || di.attrs.nItem || "?", texto(di, "prod/xProd") || "", null));
      }
    }
    tot = totais(filho(inf, "total/IBSCBSTot"));
  } else {
    itens = [grupoDfe(filho(inf, "imp/IBSCBS"), "1", "", null)];
    porItem = false;
  }
  return {
    origem,
    chave,
    modelo,
    tipo: SIGLAS[modelo] || sigla,
    numero: texto(inf, caminhoNumero),
    serie: texto(ide, "serie"),
    emissao: data(texto(ide, "dhEmi") || texto(ide, "dEmi")),
    crt: texto(inf, "emit/CRT"),
    cnpjEmitente: texto(inf, "emit/CNPJ"),
    itens,
    totais: tot,
    redutorCompraGov: dec(texto(ide, "gCompraGov/pRedutor")),
    porItem,
    finNFe: texto(ide, "finNFe"),
    tpNFDebito: texto(ide, "tpNFDebito"),
    tpNFCredito: texto(ide, "tpNFCredito"),
    temCompraGov: !!(ide && filho(ide, "gCompraGov")),
  };
}

// ---------------------------------------------------------------- tabelas
const vigente = (inicio, fim, dia) => !((inicio && dia < inicio) || (fim && dia > fim));
export function criarTabelas(dados, ncm = null, ntCatalogo = null) {
  const f = dados.fonte;
  const t = {
    dados,
    nt: ntCatalogo,
    ncmTabela: ncm,
    fonte: f,
    versao: `${f.versao_base} (${f.data_base})`,
    cst: (c) => dados.cst[c] || null,
    cclasstrib: (c) => dados.cclasstrib[c] || null,
    vigente: (reg, dia) => vigente(reg.inicio, reg.fim, dia),
    nomeDocumento: (m) => (dados.tipos_documento || {})[String(m)] || `modelo ${m}`,
    permitidoNoModelo(c, modelo, dia) {
      const reg = dados.cclasstrib[c];
      return !!reg && reg.documentos.some((d) => d.modelo === modelo && vigente(d.inicio, d.fim, dia));
    },
    reducao(c, tributo, dia) {
      const reg = dados.cclasstrib[c];
      if (!reg) return null;
      const r = reg.reducao.find((x) => x.tributo === tributo && vigente(x.inicio, x.fim, dia));
      return r ? r.percentual : null;
    },
    aliquotaReferencia(tributo, dia) {
      const a = dados.aliquota_referencia.find((x) => x.tributo === tributo && vigente(x.inicio, x.fim, dia));
      return a ? a.percentual : null;
    },
    temLista(c, tipo, dia) {
      const reg = dados.cclasstrib[c];
      return !!reg && (reg[tipo] || []).some((n) => vigente(n.inicio, n.fim, dia));
    },
    aplicavel(c, tipo, valor, dia) {
      const reg = dados.cclasstrib[c];
      if (!reg) return false;
      const casam = (reg[tipo] || []).filter((n) => valor.startsWith(n.codigo) && vigente(n.inicio, n.fim, dia));
      if (!casam.length) return false;
      const temExcecao = casam.some((n) => (n.excecoes || []).some((e) => valor.startsWith(e.codigo) && vigente(e.inicio, e.fim, dia)));
      if (!temExcecao) return true;
      return casam.some((n) => !(n.excecoes || []).length || n.excecoes.some((e) => !vigente(e.inicio, e.fim, dia)));
    },
    anexos(c, tipo, dia) {
      const reg = dados.cclasstrib[c] || {};
      const vistos = [];
      for (const n of reg[tipo] || []) {
        const a = (dados.anexos || {})[String(n.anexo)];
        if (a && vigente(n.inicio, n.fim, dia)) {
          const rotulo = `Anexo ${a.anexo}, item ${a.item}`;
          if (!vistos.includes(rotulo)) vistos.push(rotulo);
        }
      }
      return vistos;
    },
    ncm: (codigo) => (t.ncmTabela ? t.ncmTabela[codigo] || null : undefined),
  };
  return t;
}

// ---------------------------------------------------------------- regras
// Para NF-e e NFC-e, cada achado ligado a uma regra da NT 2025.002-RTC traz o código de rejeição, a regra, a
// página e se a regra já vale em produção (catálogo em nt.json, gerado de src/auditor_ibs_cbs/nt.py).
const TOLERANCIA_COMPRA_GOV = dec("0.04");
const ZERO = 0n;
const TRIBUTOS = [["IBSUF", "IBS estadual"], ["IBSMun", "IBS municipal"], ["CBS", "CBS"]];
const GRUPOS_NFE = { gIBSCBS: ["1022", "1021"], gIBSCBSMono: ["1116", "1151"], gTransfCred: ["1132", "1131"], gCredPresIBSZFM: ["1135", null], gAjusteCompet: ["1170", null] };
const dataBR = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
function resumir(texto, limite = 80) {
  // Descrição de NCM legível: sem tags, sem os traços de hierarquia e cortada em palavra inteira.
  texto = texto.replace(/<[^>]*>/g, "").replace(/^[-\s]+/, "").trim();
  if (texto.length <= limite) return texto;
  const corte = texto.slice(0, limite);
  return corte.slice(0, corte.lastIndexOf(" ")).replace(/[,;:]+$/, "") + "…";
}

function coletor(nota, t) {
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  const lista = [];
  return {
    lista,
    ntTotais: t.nt ? t.nt.totais : null,
    add(codigo, gravidade, titulo, explicacao, comoCorrigir, item = null, campo = null, cstat = null) {
      const a = { codigo, gravidade, titulo, explicacao, como_corrigir: comoCorrigir, item, campo };
      const ref = cstat && nfe && t.nt ? t.nt.regras[cstat] : null;
      if (ref) {
        a.rejeicao = cstat;
        a.regra_nt = ref[0];
        a.pagina_nt = ref[1];
        a.em_producao = ref[2];
        if (!a.em_producao && a.gravidade === "erro") a.gravidade = "atencao";
      }
      lista.push(a);
    },
  };
}

export function situacao(achados) {
  const g = new Set(achados.map((a) => a.gravidade));
  return g.has("erro") ? "erro" : g.has("atencao") ? "atencao" : "ok";
}

export function auditar(nota, t) {
  const r = { origem: nota.origem, chave: nota.chave, modelo: nota.modelo, tipo: nota.tipo, numero: nota.numero, serie: nota.serie, emissao: nota.emissao, emitente: nota.cnpjEmitente, itens: nota.itens.length, achados: [], linhas: [] };
  const c = coletor(nota, t);
  if (!MODELOS_SUPORTADOS.has(nota.modelo)) {
    c.add("AIC-002", "info", "Documento fora do escopo", `O modelo ${nota.modelo} não é um documento suportado; o arquivo não foi auditado.`, "Nada a fazer.");
  } else if (!nota.emissao) {
    c.add("AIC-003", "erro", "Data de emissão ausente", "Sem a data de emissão (dhEmi) não dá para saber quais tabelas valiam no dia.", "Confira se o arquivo é o XML completo do documento.", null, "dhEmi");
  } else if (nota.emissao < "2026-01-01") {
    c.add("AIC-004", "info", "Documento anterior à reforma", "O documento foi emitido antes de 01/01/2026, quando o grupo IBS/CBS ainda não existia.", "Nada a fazer.");
  } else {
    if (nota.modelo === 65 && nota.temCompraGov) {
      c.add("AIC-044", "erro", "NFC-e com compra governamental", "A NFC-e não pode ter o grupo de compras governamentais (gCompraGov).", "Use NF-e (modelo 55) para compras governamentais.", null, "ide/gCompraGov", "1006");
    }
    for (const item of nota.itens) {
      auditarItem(item, nota, t, c);
      r.linhas.push({ item: item.numero, cst: item.cst, cclasstrib: item.cclasstrib, ncm: item.ncm, nbs: item.nbs, base: item.base, ibs: item.valorIBS, cbs: item.cbs ? item.cbs.valor : null });
    }
    if (nota.porItem) auditarTotais(nota, c);
  }
  r.achados = c.lista;
  return r;
}

function auditarItem(item, nota, t, c) {
  const dia = nota.emissao;
  const n = nota.porItem ? item.numero : null;
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  const nfse = nota.modelo === 91;
  if (!item.temGrupo) {
    const onde = nota.porItem ? "O item não tem" : "O documento não tem";
    let excecao = null;
    if (nfe && ["2", "4"].includes(nota.finNFe)) excecao = "Notas de devolução ou complementares que referenciam notas anteriores a 2027 são exceção a essa regra.";
    else if (nfe && item.cprodAnp) excecao = "Combustíveis da tabela de tributação monofásica são exceção a essa regra; confira se o produto está nela.";
    if (excecao) {
      c.add("AIC-010", "info", "Grupo IBS/CBS não informado", `${onde} o grupo IBSCBS. ${excecao}`, "Nada a fazer, se o caso se encaixa na exceção.", n, "IBSCBS");
    } else if (nota.crt === "3") {
      c.add("AIC-010", nfe ? "erro" : "atencao", "Grupo IBS/CBS não informado", `${onde} o grupo IBSCBS. Emitentes do regime normal (CRT 3) devem informar IBS e CBS.`, "Configure no sistema emissor o CST e o cClassTrib para gerar o grupo IBSCBS.", n, "IBSCBS", "1115");
    } else {
      const regime = ["1", "2", "4"].includes(nota.crt) ? "Para o Simples Nacional e o MEI (CRT 1, 2 ou 4)" : "Para este emitente";
      c.add("AIC-010", "info", "Grupo IBS/CBS não informado", `${onde} o grupo IBSCBS. ${regime}, a obrigatoriedade segue um cronograma próprio da NT 2025.002.`, "Confira na versão vigente da nota técnica a partir de quando o seu regime precisa informar.", n, "IBSCBS");
    }
    if (nfe && item.ncm) conferirNcmExiste(item, t, dia, n, c);
    return;
  }
  conferirFormatos(item.campos, nfse, n, c);
  for (const campo of item.faltando) {
    c.add("AIC-051", "erro", "Campo obrigatório ausente", `O campo ${campo} é obrigatório no grupo IBS/CBS e não foi informado.`, "Gere o grupo completo; o leiaute da NT 2025.002 lista os campos obrigatórios.", n, campo);
  }
  const cst = t.cst(item.cst || "");
  conferirCodigos(item.cst, item.cclasstrib, nota, t, n, "", c);
  const cl = t.cclasstrib(item.cclasstrib || "");
  if (nfe) {
    conferirNcm(item, cl, t, dia, n, c);
    conferirDebitoCredito(item, nota, t, n, c);
  }
  if (nfse && cl) conferirNbs(item, t, dia, c);
  if (cst && !nfse) {
    const grupos = nfe ? GRUPOS_NFE : { gIBSCBS: [null, null] };
    for (const [grupo, [codAusente, codIndevido]] of Object.entries(grupos)) {
      const exigido = !!cst.grupos[grupo];
      const presente = item.grupos.has(grupo);
      if (exigido && !presente && !(grupo === "gIBSCBS" && nota.tpNFDebito === "07")) {
        c.add("AIC-020", "erro", `Grupo ${grupo} ausente`, `O CST ${item.cst} (${cst.descricao}) exige o grupo ${grupo}, que não foi informado.`, `Gere o grupo ${grupo} ou confira se o CST está certo.`, n, `IBSCBS/${grupo}`, codAusente);
      } else if (presente && !exigido) {
        c.add("AIC-021", nfe && codIndevido ? "erro" : "atencao", `Grupo ${grupo} informado indevidamente`, `O grupo ${grupo} foi informado, mas o CST ${item.cst} (${cst.descricao}) não o permite.`, "Confira se o CST está certo para esta operação.", n, `IBSCBS/${grupo}`, codIndevido);
      }
    }
  }
  if (nfe && cl) conferirEstorno(item, cl, nota, n, c);
  if (item.grupos.has("gIBSCBS")) auditarValores(item, nota, t, cst, n, c);
  auditarEspeciais(item, nota, t, n, c);
}

function conferirFormatos(lista, nfse, n, c) {
  let total = 0;
  for (const campo of lista) {
    for (const [prefixos, regex, descricao, exato] of nfse ? FORMATOS_NFSE : FORMATOS_DFE) {
      const casa = exato ? prefixos.includes(campo.nome) : prefixos.some((p) => campo.nome.startsWith(p));
      if (!casa) continue;
      if (!regex.test(campo.valor)) {
        c.add("AIC-050", "erro", `Formato inválido em ${campo.nome}`, `O campo ${campo.nome} tem o valor '${campo.valor.slice(0, 30)}', mas o leiaute exige ${descricao}.`, "Corrija a formatação no sistema emissor (ponto como separador decimal, sem separador de milhar).", n, `${campo.caminho}/${campo.nome}`);
        total++;
      }
      break;
    }
    if (total >= 5) break;
  }
}

function conferirCodigos(cstCod, clCod, nota, t, n, sufixo, c) {
  const dia = nota.emissao;
  const doc = t.nomeDocumento(nota.modelo);
  const reg = !!sufixo;
  const rotulo = reg ? " da tributação regular" : "";
  const cst = t.cst(cstCod || "");
  if (!cst) {
    c.add("AIC-011", "erro", `CST${rotulo} inexistente`, `O CST '${cstCod}' não existe na tabela oficial (${t.versao}).`, "Use um dos CSTs da tabela oficial; o comando 'consultar' lista os códigos.", n, `CST${sufixo}`, reg ? "1066" : "1020");
  } else if (!t.vigente(cst, dia)) {
    c.add("AIC-012", "erro", `CST${rotulo} fora da vigência`, `O CST ${cstCod} não valia em ${dataBR(dia)} (vigência ${cst.inicio} a ${cst.fim || "atual"}).`, "Use um CST vigente na data de emissão.", n, `CST${sufixo}`);
  }
  const cl = t.cclasstrib(clCod || "");
  if (!cl) {
    c.add("AIC-013", "erro", `cClassTrib${rotulo} inexistente`, `O código de classificação tributária '${clCod}' não existe na tabela oficial (${t.versao}).`, "Corrija o cClassTrib; use 'consultar' para ver os códigos de cada CST.", n, `cClassTrib${sufixo}`, reg ? "1067" : "1023");
    return;
  }
  if (!t.vigente(cl, dia)) {
    c.add("AIC-014", "erro", `cClassTrib${rotulo} fora da vigência`, `O cClassTrib ${clCod} não valia em ${dataBR(dia)} (vigência ${cl.inicio} a ${cl.fim || "atual"}).`, "Troque pelo código que substituiu este na tabela vigente.", n, `cClassTrib${sufixo}`);
  }
  if (cstCod && cl.cst !== cstCod) {
    c.add("AIC-015", reg ? "atencao" : "erro", `cClassTrib${rotulo} não pertence ao CST`, `O cClassTrib ${clCod} (${cl.descricao}) é do CST ${cl.cst}, mas foi informado o CST ${cstCod}.`, `Use o CST ${cl.cst} ou escolha um cClassTrib do CST ${cstCod}.`, n, `CST${sufixo}`, reg ? null : "1024");
  }
  if (!reg && !t.permitidoNoModelo(clCod, nota.modelo, dia)) {
    c.add("AIC-016", "erro", `cClassTrib não permitido em ${doc}`, `Pela tabela oficial, o cClassTrib ${clCod} (${cl.descricao}) não pode ser usado em ${doc} na data de emissão.`, `Escolha um cClassTrib previsto para ${doc}.`, n, "cClassTrib", "1025");
  }
}

function conferirDebitoCredito(item, nota, t, n, c) {
  if (nota.modelo !== 55 || !item.cclasstrib || !t.nt) return;
  const cod = item.cclasstrib;
  const deb = nota.tpNFDebito;
  const cred = nota.tpNFCredito;
  const tabela = t.nt.cclass_debito_credito[cod];
  if (tabela) {
    const [aceitaDeb, aceitaCred] = tabela;
    if (!((deb && aceitaDeb.includes(deb)) || (cred && aceitaCred.includes(cred)))) {
      const exige = [...aceitaDeb.map((d) => `nota de débito tipo ${d}`), ...aceitaCred.map((x) => `nota de crédito tipo ${x}`)].join(" ou ");
      c.add("AIC-046", "erro", "cClassTrib incompatível com o tipo da nota", `O cClassTrib ${cod} só pode ser usado em ${exige}.`, "Confira a finalidade da nota e o tipo de nota de débito ou crédito.", n, "ide/tpNFDebito", "1202");
    }
  }
  const exDeb = deb ? t.nt.debito_exige[deb] : undefined;
  if (exDeb && cod !== exDeb) {
    c.add("AIC-046", "erro", "cClassTrib incompatível com a nota de débito", `Na nota de débito tipo ${deb}, os itens devem usar o cClassTrib ${exDeb}, mas este usa ${cod}.`, "Ajuste o cClassTrib ou o tipo da nota de débito.", n, "IBSCBS/cClassTrib", "1200");
  }
  const exCred = cred ? t.nt.credito_exige[cred] : undefined;
  if (exCred && cod !== exCred) {
    c.add("AIC-046", "erro", "cClassTrib incompatível com a nota de crédito", `Na nota de crédito tipo ${cred}, os itens devem usar o cClassTrib ${exCred}, mas este usa ${cod}.`, "Ajuste o cClassTrib ou o tipo da nota de crédito.", n, "IBSCBS/cClassTrib", "1201");
  }
}

function conferirEstorno(item, cl, nota, n, c) {
  const exige = !!(cl.indicadores && cl.indicadores.gEstornoCred) || nota.tpNFDebito === "07";
  const presente = item.grupos.has("gEstornoCred");
  if (presente && !exige) {
    c.add("AIC-047", "erro", "Grupo de estorno de crédito informado indevidamente", `O cClassTrib ${item.cclasstrib} não permite o grupo gEstornoCred.`, "Retire o grupo gEstornoCred ou confira o cClassTrib.", n, "IBSCBS/gEstornoCred", "1172");
  } else if (exige && !presente) {
    c.add("AIC-047", "erro", "Grupo de estorno de crédito não informado", `O cClassTrib ${item.cclasstrib} (ou a nota de débito por perda em estoque) exige o grupo gEstornoCred.`, "Gere o grupo gEstornoCred com os valores estornados.", n, "IBSCBS/gEstornoCred", "1173");
  }
}

function conferirNcmExiste(item, t, dia, n, c) {
  const ncm = item.ncm || "";
  if (ncm.length !== 8 || NCM_ZERO.has(ncm)) return;
  const reg = t.ncm(ncm);
  if (reg === undefined) return; // tabela NCM ainda não carregada
  if (reg === null || !(reg[1] <= dia && dia <= reg[2])) {
    const motivo = reg === null ? "não existe na tabela NCM" : `não estava vigente em ${dataBR(dia)}`;
    c.add("AIC-019", "atencao", "NCM inexistente ou fora da vigência", `O NCM ${ncm} ${motivo}.`, "Confira a classificação fiscal do produto na tabela NCM vigente.", n, "prod/NCM");
  }
}

function conferirNcm(item, cl, t, dia, n, c) {
  conferirNcmExiste(item, t, dia, n, c);
  if (!cl) return;
  const codigo = item.cclasstrib;
  const temLista = t.temLista(codigo, "ncm", dia);
  if (!temLista && !EXIGEM_NCM_SEMPRE.has(codigo)) return;
  const ncm = item.ncm || "";
  const anexos = t.anexos(codigo, "ncm", dia);
  const onde = anexos.length ? ` (${anexos.slice(0, 3).join(", ")}${anexos.length > 3 ? "…" : ""} da LC 214/2025)` : "";
  if (ncm.length !== 8 || NCM_ZERO.has(ncm)) {
    c.add("AIC-017", "erro", "NCM obrigatório para este cClassTrib", `O cClassTrib ${codigo} (${cl.descricao}) exige o NCM completo de 8 dígitos do produto, mas o item informa '${ncm || "nada"}'.`, "Informe o NCM correto do produto no cadastro.", n, "prod/NCM");
  } else if (temLista && !t.aplicavel(codigo, "ncm", ncm, dia)) {
    const desc = t.ncm(ncm);
    const produto = desc ? ` (${resumir(desc[0])})` : "";
    const possiveis = Object.keys(t.dados.cclasstrib).filter((x) => x !== codigo && t.temLista(x, "ncm", dia) && t.aplicavel(x, "ncm", ncm, dia));
    const dica = possiveis.length ? ` Para este NCM, os cClassTrib com lista que se aplicam são: ${possiveis.slice(0, 5).join(", ")}.` : " Nenhum cClassTrib com lista se aplica a este NCM; use o da tributação comum (ex.: 000001).";
    c.add("AIC-018", "erro", "NCM não pode usar este cClassTrib", `O cClassTrib ${codigo} (${cl.descricao}) só vale para os produtos listados na lei${onde}. O NCM ${ncm}${produto} não está nessa lista, então o tratamento (como a redução) não se aplica.`, "Confira o NCM e o cClassTrib do produto." + dica, n, "IBSCBS/cClassTrib");
  }
}

function conferirNbs(item, t, dia, c) {
  const codigo = item.cclasstrib;
  if (!t.temLista(codigo, "nbs", dia)) return;
  const cl = t.cclasstrib(codigo);
  const nbs = item.nbs || "";
  if (nbs.length !== 9) {
    c.add("AIC-024", "erro", "NBS obrigatório para este cClassTrib", `O cClassTrib ${codigo} (${cl.descricao}) exige o código NBS completo (9 dígitos) do serviço, mas a NFS-e informa '${nbs || "nada"}'.`, "Informe o NBS do serviço (cServ/cNBS).", null, "serv/cServ/cNBS");
  } else if (!t.aplicavel(codigo, "nbs", nbs, dia)) {
    c.add("AIC-025", "erro", "NBS não pode usar este cClassTrib", `O cClassTrib ${codigo} (${cl.descricao}) só vale para os serviços listados na lei. O NBS ${nbs} não está nessa lista.`, "Confira o NBS e o cClassTrib do serviço.", null, "IBSCBS/cClassTrib");
  }
}

const porTributo = (t, chave, sigla) => (t.nt ? t.nt.por_tributo[chave][sigla] : null);

function auditarValores(item, nota, t, cst, n, c) {
  const dia = nota.emissao;
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  const nfse = nota.modelo === 91;
  const preveReducao = !!(cst && cst.grupos.gRed);
  const preveDif = !!(cst && cst.grupos.gDif);
  const blocos = [["IBSUF", "IBS estadual", item.ibsUF], ["IBSMun", "IBS municipal", item.ibsMun], ["CBS", "CBS", item.cbs]];
  for (const [sigla, nome, tr] of blocos) {
    if (!tr) continue;
    if (cst && !nfse) {
      if (tr.temDiferimento && !preveDif) {
        c.add("AIC-026", "erro", `Diferimento não permitido (${nome})`, `Foi informado diferimento (gDif) no ${nome}, mas o CST ${item.cst} (${cst.descricao}) não permite.`, "Retire o gDif ou use um CST com diferimento (ex.: 510, 515).", n, `g${sigla}/gDif`, porTributo(t, "dif_indevido", sigla));
      } else if (preveDif && !tr.temDiferimento) {
        c.add("AIC-026", "erro", `Diferimento não informado (${nome})`, `O CST ${item.cst} (${cst.descricao}) exige o grupo de diferimento (gDif) no ${nome}.`, "Gere o grupo gDif com o percentual diferido ou confira o CST.", n, `g${sigla}/gDif`, porTributo(t, "dif_ausente", sigla));
      }
    }
    if (nfe && tr.temDevolucao) {
      if (sigla === "IBSUF") {
        c.add("AIC-028", "erro", "Devolução do IBS estadual informada indevidamente", "O grupo gDevTrib não pode ser informado no IBS estadual.", "Retire o grupo gDevTrib do IBS estadual.", n, "gIBSUF/gDevTrib", "1111");
      } else if (sigla === "IBSMun") {
        c.add("AIC-028", "erro", "Devolução do IBS municipal informada indevidamente", "O grupo gDevTrib não pode ser informado no IBS municipal.", "Retire o grupo gDevTrib do IBS municipal.", n, "gIBSMun/gDevTrib", "1112");
      } else if (nota.modelo === 65) {
        c.add("AIC-028", "erro", "Devolução da CBS informada indevidamente", "A NFC-e não pode ter o grupo de devolução da CBS (gDevTrib).", "Retire o grupo gDevTrib da CBS.", n, "gCBS/gDevTrib", "1187");
      } else if (tr.pDev === null) {
        c.add("AIC-028", "erro", "Percentual de devolução da CBS não informado", "O grupo de devolução da CBS exige o percentual devolvido (pDevTrib).", "Informe o pDevTrib.", n, "gCBS/gDevTrib/pDevTrib", "1188");
      } else {
        const aliq = tr.aliquotaEfetiva !== null ? tr.aliquotaEfetiva : tr.aliquota;
        if (item.base !== null && aliq !== null && tr.vDev !== null) {
          const esperado = div100(mul(div100(mul(item.base, aliq)), tr.pDev));
          if (abs(esperado - tr.vDev) > TOLERANCIA) {
            c.add("AIC-028", "erro", "Valor da CBS devolvida não confere", `Base R$ ${brl(item.base)} x ${pct(aliq)} x ${pct(tr.pDev)} devolvido = R$ ${brl(arredondar(esperado))}, mas foi informado R$ ${brl(tr.vDev)}.`, "O valor devolvido é base x alíquota x percentual devolvido.", n, "gCBS/gDevTrib/vDevTrib", "1189");
          }
        }
      }
    }
    const temRed = tr.reducao !== null || tr.aliquotaEfetiva !== null;
    if (cst && !nfse) {
      const excecaoGov = nota.temCompraGov && (tr.reducao ?? ZERO) === ZERO;
      if (temRed && !preveReducao && !excecaoGov && (nfe || (tr.reducao ?? ZERO) !== ZERO)) {
        c.add("AIC-022", nfe ? "erro" : "atencao", `Redução de alíquota não permitida (${nome})`, `Foi informada redução (gRed) no ${nome}, mas o CST ${item.cst} não permite redução.`, "Retire o gRed ou use um CST com redução (ex.: 200). Em compra governamental, o gRed vai com pRedAliq igual a zero.", n, `g${sigla}/gRed`, porTributo(t, "red_indevido", sigla));
      }
      if (nfe && !temRed && (preveReducao || nota.temCompraGov)) {
        const motivo = preveReducao ? "o CST exige redução" : "a nota é de compra governamental";
        c.add("AIC-027", "erro", `Grupo de redução não informado (${nome})`, `O grupo gRed do ${nome} é obrigatório porque ${motivo}.`, "Gere o grupo gRed com o percentual de redução e a alíquota efetiva.", n, `g${sigla}/gRed`, porTributo(t, "red_ausente", sigla));
      }
    }
    const oficial = item.cclasstrib ? decNum(t.reducao(item.cclasstrib, sigla, dia)) : null;
    if (tr.reducao !== null && oficial !== null && preveReducao && oficial !== tr.reducao) {
      c.add("AIC-023", nfe ? "erro" : "atencao", `Percentual de redução diferente do oficial (${nome})`, `Foi informada redução de ${pct(tr.reducao)}, mas a tabela oficial do cClassTrib ${item.cclasstrib} prevê ${pct(oficial)}.`, "Use o percentual de redução oficial do cClassTrib.", n, `g${sigla}/gRed/pRedAliq`, porTributo(t, "p_red", sigla));
    } else if (nfe && tr.reducao !== null && !preveReducao && nota.temCompraGov && tr.reducao !== ZERO) {
      c.add("AIC-023", "erro", `Percentual de redução não permitido (${nome})`, `O CST ${item.cst} não permite redução; em compra governamental o pRedAliq deve ser zero, mas foi informado ${pct(tr.reducao)}.`, "Informe pRedAliq igual a zero.", n, `g${sigla}/gRed/pRedAliq`, porTributo(t, "p_red", sigla));
    }
    conferirAliquotaEfetiva(tr, sigla, nome, nota, t, n, c);
    conferirValor(item, tr, sigla, nome, nota, t, n, c);
  }
  if (item.valorIBS !== null && item.ibsUF && item.ibsMun && item.ibsUF.valor !== null && item.ibsMun.valor !== null) {
    const s = item.ibsUF.valor + item.ibsMun.valor;
    const cred = (item.especiais.gCredPresOper || {})["gIBSCredPres/vCredPres"] ?? null;
    const aceitos = [s, ...(cred !== null ? [s - cred] : [])];
    if (aceitos.every((v) => abs(v - item.valorIBS) > TOLERANCIA)) {
      c.add("AIC-031", "erro", "IBS total diferente da soma", `O IBS total é R$ ${brl(item.valorIBS)}, mas IBS estadual + municipal dá R$ ${brl(s)}.`, "O vIBS deve ser vIBSUF + vIBSMun (menos o crédito presumido, quando o código manda deduzir).", n, "vIBS", "1150");
    }
  }
  conferirAliquotas(item, nota, t, n, c);
  if (nfe && item.composicao && item.base !== null) conferirBase(item, n, c);
}

function conferirAliquotas(item, nota, t, n, c) {
  const dia = nota.emissao;
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  const blocos = [["CBS", "CBS", item.cbs], ["IBSUF", "IBS estadual", item.ibsUF], ["IBSMun", "IBS municipal", item.ibsMun]];
  if (nfe) {
    const lei = (t.nt && t.nt.aliquotas_lei[dia.slice(0, 4)]) || {};
    const regular = "gTribRegular" in item.especiais;
    for (const [sigla, nome, tr] of blocos) {
      if (!tr || tr.aliquota === null || !(sigla in lei)) continue;
      if (nota.finNFe === "4" || ["03", "04", "06"].includes(nota.tpNFCredito)) continue;
      if (sigla === "CBS" && tr.temAlczfm) continue;
      const esperado = regular ? ZERO : dec(lei[sigla]);
      if (tr.aliquota !== esperado) {
        const motivo = regular ? "com tributação regular informada, ela deve ser zero" : `a lei fixa ${pct(esperado)} para ${dia.slice(0, 4)}`;
        c.add("AIC-032", "erro", `Alíquota do ${nome} inválida`, `Foi informada alíquota de ${pct(tr.aliquota)}, mas ${motivo}.`, "Corrija a alíquota no sistema emissor (as reduções vão no grupo gRed, não na alíquota).", n, `p${sigla}`, porTributo(t, "aliquota", sigla));
      }
    }
    return;
  }
  const cl = t.cclasstrib(item.cclasstrib || "");
  for (const [sigla, nome, tr] of blocos) {
    if (!tr || tr.aliquota === null || tr.reducao !== null || nota.redutorCompraGov !== null) continue;
    const ref = decNum(t.aliquotaReferencia(sigla, dia));
    if (ref !== null && cl && cl.tipo_aliquota === "Padrão" && tr.aliquota !== ref) {
      c.add("AIC-032", "info", `Alíquota diferente da referência (${nome})`, `A alíquota informada é ${pct(tr.aliquota)}; a de referência para ${dia.slice(0, 4)} é ${pct(ref)}.`, "Se não houver motivo específico (regime, benefício), confira a alíquota configurada.", n, `p${sigla}`);
    }
  }
}

function conferirBase(item, n, c) {
  const v = item.composicao;
  const s = v.vProd + v.vFrete + v.vSeg + v.vOutro + v.vII + v.vIS - (v.vDesc + v.vPIS + v.vCOFINS + v.vICMS + v.vICMSUFDest + v.vFCP + v.vFCPUFDest + v.vICMSMono + v.vISSQN);
  if (abs(s - item.base) > TOLERANCIA) {
    c.add("AIC-029", "erro", "Base de cálculo diferente da composição prevista",
      `A base do IBS/CBS é R$ ${brl(item.base)}, mas a composição da NT (produto + frete + seguro + outras + II + IS - desconto - PIS - COFINS - ICMS - FCP - ICMS monofásico - ISSQN) dá R$ ${brl(s)}. A SEFAZ ainda não rejeita por isso, mas a regra já está publicada.`,
      "Confira se o sistema monta a base como a NT descreve; vale corrigir antes de a regra entrar em produção.", n, "gIBSCBS/vBC", "1104");
  }
}

function aliquotaPublicada(tr, nota) {
  if (tr.aliquotaEfetiva !== null) return tr.aliquotaEfetiva;
  if (nota.redutorCompraGov !== null) return null;
  return tr.aliquota;
}

function conferirAliquotaEfetiva(tr, sigla, nome, nota, t, n, c) {
  if (tr.aliquota === null || tr.aliquotaEfetiva === null) return;
  const reducao = tr.reducao ?? ZERO;
  const redutor = nota.redutorCompraGov ?? ZERO;
  const exata = mul(mul(tr.aliquota, UM - div100(reducao)), UM - div100(redutor));
  const nfse = nota.modelo === 91;
  const esperada = arredondar(exata, nfse ? 2 : 4);
  const tolerancia = nfse ? TOLERANCIA : ZERO;
  if (abs(esperada - tr.aliquotaEfetiva) > tolerancia) {
    c.add("AIC-033", nota.modelo === 55 || nota.modelo === 65 ? "erro" : "atencao", `Alíquota efetiva não confere (${nome})`,
      `Com alíquota ${pct(tr.aliquota)}, redução ${pct(reducao)}` + (redutor ? ` e redutor de compra governamental ${pct(redutor)}` : "") + `, a alíquota efetiva seria ${pct(esperada)}, mas foi informada ${pct(tr.aliquotaEfetiva)}.`,
      "A alíquota efetiva é alíquota x (1 - redução) x (1 - redutor), com 4 casas decimais.", n, `pAliqEfet (${sigla})`, porTributo(t, "aliq_efet", sigla));
  }
}

function conferirValor(item, tr, sigla, nome, nota, t, n, c) {
  if (item.base === null || tr.valor === null) return;
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  if (tr.temDevolucao && !nfe) return;
  const aliquota = aliquotaPublicada(tr, nota);
  if (aliquota === null) return;
  const bruto = div100(mul(item.base, aliquota));
  if (tr.temDiferimento) {
    if (tr.pDif === null) return;
    const vDif = div100(mul(bruto, tr.pDif));
    if (tr.vDif !== null && abs(vDif - tr.vDif) > TOLERANCIA) {
      c.add("AIC-034", nfe ? "erro" : "atencao", `Valor diferido do ${nome} não confere`, `Base R$ ${brl(item.base)} x ${pct(aliquota)} x ${pct(tr.pDif)} diferido = R$ ${brl(arredondar(vDif))}, mas foi informado R$ ${brl(tr.vDif)}.`, "O valor diferido é base x alíquota x percentual de diferimento.", n, `vDif (${sigla})`, porTributo(t, "v_dif", sigla));
    }
  }
  const deducoes = (tr.temDiferimento ? tr.vDif ?? ZERO : ZERO) + (tr.temDevolucao ? tr.vDev ?? ZERO : ZERO);
  const devido = bruto - deducoes;
  if (abs(devido - tr.valor) > TOLERANCIA) {
    let conta = `Base R$ ${brl(item.base)} x ${pct(aliquota)} = R$ ${brl(arredondar(bruto))}`;
    if (deducoes) conta += `, menos diferido/devolvido (R$ ${brl(deducoes)}), dá R$ ${brl(arredondar(devido))}`;
    c.add("AIC-030", nfe ? "erro" : "atencao", `Valor do ${nome} não bate com base x alíquota`, `${conta}, mas foi informado R$ ${brl(tr.valor)}.`, "Confira a base de cálculo e a alíquota; a calculadora oficial da Receita ajuda a conferir.", n, `v${sigla}`, porTributo(t, "valor", sigla));
  }
}

const diferenca = (esperado, informado, tolerancia = TOLERANCIA) => informado !== null && informado !== undefined && abs(esperado - informado) > tolerancia;

function auditarEspeciais(item, nota, t, n, c) {
  const esp = item.especiais;
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  const cred = esp.gCredPresOper;
  if (cred) {
    if (nota.modelo === 65) c.add("AIC-045", "erro", "Crédito presumido não permitido na NFC-e", "A NFC-e não pode ter o grupo de crédito presumido da operação (gCredPresOper).", "Retire o grupo gCredPresOper.", n, "IBSCBS/gCredPresOper", "1049");
    const base = cred.vBCCredPres ?? null;
    for (const [g, nome] of [["gIBSCredPres", "IBS"], ["gCBSCredPres", "CBS"]]) {
      const p = cred[`${g}/pCredPres`] ?? null;
      const v = cred[`${g}/vCredPres`] !== undefined ? cred[`${g}/vCredPres`] : cred[`${g}/vCredPresCondSus`] ?? null;
      if (base !== null && p !== null && v !== null && diferenca(div100(mul(base, p)), v)) {
        c.add("AIC-035", "atencao", `Crédito presumido de ${nome} não confere`, `Base R$ ${brl(base)} x ${pct(p)} = R$ ${brl(arredondar(div100(mul(base, p))))}, mas foi informado R$ ${brl(v)}.`, "O crédito presumido é a base do crédito x o percentual.", n, `gCredPresOper/${g}`);
      }
    }
  }
  if (item.grupos.has("gCredPresIBSZFM") && nota.modelo === 65) {
    c.add("AIC-045", "erro", "Crédito presumido da ZFM não permitido na NFC-e", "A NFC-e não pode ter o grupo gCredPresIBSZFM.", "Retire o grupo gCredPresIBSZFM.", n, "IBSCBS/gCredPresIBSZFM", "1138");
  }
  if (nota.modelo === 55) {
    if (item.grupos.has("gCredPresIBSZFM") && nota.tpNFCredito !== "02") {
      c.add("AIC-045", "erro", "Crédito presumido da ZFM fora da nota de crédito tipo 02", "O grupo gCredPresIBSZFM só cabe na nota de crédito tipo 02 (apropriação de crédito presumido de IBS na ZFM).", "Confira o tipo da nota de crédito.", n, "IBSCBS/gCredPresIBSZFM", "1158");
    } else if (!item.grupos.has("gCredPresIBSZFM") && nota.tpNFCredito === "02" && item.temGrupo) {
      c.add("AIC-045", "erro", "Nota de crédito tipo 02 sem crédito presumido da ZFM", "A nota de crédito tipo 02 exige o grupo gCredPresIBSZFM.", "Gere o grupo gCredPresIBSZFM.", n, "IBSCBS/gCredPresIBSZFM", "1159");
    }
  }
  const transf = esp.gTransfCred;
  if (transf !== undefined && nota.modelo === 55) {
    if (nota.finNFe !== "6") c.add("AIC-048", "erro", "Transferência de crédito fora da nota de débito", "O grupo gTransfCred só pode ser usado em nota de débito (finNFe = 6).", "Confira a finalidade da nota.", n, "ide/finNFe", "1133");
    if ((transf.vIBS ?? ZERO) <= ZERO && (transf.vCBS ?? ZERO) <= ZERO) c.add("AIC-048", "erro", "Transferência de crédito sem valor", "Na transferência de crédito, o valor do IBS ou da CBS deve ser maior que zero.", "Informe os valores transferidos.", n, "gTransfCred", "1129");
  }
  const gov = esp.gTribCompraGov;
  if (nota.modelo === 55) {
    if (nota.temCompraGov && !gov && item.grupos.has("gIBSCBS")) {
      c.add("AIC-036", "erro", "Composição da compra governamental não informada", "A nota é de compra governamental, mas o item não tem o grupo gTribCompraGov.", "Gere o grupo gTribCompraGov com as alíquotas e valores sem o redutor.", n, "gIBSCBS/gTribCompraGov", "1141");
    } else if (gov && !nota.temCompraGov) {
      c.add("AIC-036", "erro", "Composição da compra governamental informada indevidamente", "O item tem o grupo gTribCompraGov, mas a nota não é de compra governamental (sem gCompraGov).", "Retire o grupo gTribCompraGov ou informe o gCompraGov.", n, "gIBSCBS/gTribCompraGov", "1144");
    }
  }
  if (gov && item.base !== null) {
    const tribGov = soma(TRIBUTOS.map(([s]) => gov[`vTrib${s}`] ?? null));
    const tribItem = soma([item.ibsUF, item.ibsMun, item.cbs].map((x) => (x ? x.valor : null)));
    if (nfe && abs(tribGov - tribItem) > TOLERANCIA_COMPRA_GOV) {
      c.add("AIC-036", "erro", "Soma da compra governamental divergente", `A soma de vTribIBSUF + vTribIBSMun + vTribCBS (R$ ${brl(tribGov)}) difere de vIBSUF + vIBSMun + vCBS (R$ ${brl(tribItem)}) em mais de R$ 0,04.`, "Os valores do gTribCompraGov devem somar o mesmo que os tributos do item.", n, "gTribCompraGov", "1142");
    }
    for (const [s, nome] of TRIBUTOS) {
      const p = gov[`pAliq${s}`] ?? null;
      const v = gov[`vTrib${s}`] ?? null;
      if (p !== null && v !== null && diferenca(div100(mul(item.base, p)), v)) {
        c.add("AIC-036", "atencao", `Tributo da compra governamental não confere (${nome})`, `Base R$ ${brl(item.base)} x ${pct(p)} = R$ ${brl(arredondar(div100(mul(item.base, p))))}, mas foi informado R$ ${brl(v)}.`, "Confira a alíquota da compra governamental.", n, `gTribCompraGov/vTrib${s}`);
      }
    }
  }
  const reg = esp.gTribRegular;
  if (reg) {
    conferirCodigos(reg.CSTReg ?? null, reg.cClassTribReg ?? null, nota, t, n, "Reg", c);
    if (item.base !== null) {
      for (const [s, nome] of TRIBUTOS) {
        const p = reg[`pAliqEfetReg${s}`] ?? null;
        const v = reg[`vTribReg${s}`] ?? null;
        if (p !== null && v !== null && diferenca(div100(mul(item.base, p)), v)) {
          c.add("AIC-037", nfe ? "erro" : "atencao", `Tributação regular não confere (${nome})`, `Base R$ ${brl(item.base)} x ${pct(p)} = R$ ${brl(arredondar(div100(mul(item.base, p))))}, mas foi informado R$ ${brl(v)}.`, "Confira a alíquota efetiva da tributação regular.", n, `gTribRegular/vTribReg${s}`, porTributo(t, "trib_regular", s));
        }
      }
    }
  }
}

function auditarTotais(nota, c) {
  const nfe = nota.modelo === 55 || nota.modelo === 65;
  const itens = nota.itens.filter((i) => i.temGrupo);
  const tot = nota.totais;
  if (!itens.length) {
    if (nfe && tot.presente) c.add("AIC-042", "erro", "Totais de IBS/CBS informados indevidamente", "O documento tem o grupo IBSCBSTot, mas nenhum item tem IBS/CBS.", "Retire o grupo IBSCBSTot ou gere o IBS/CBS dos itens.", null, "total/IBSCBSTot", "1118");
    return;
  }
  if (!tot.presente) {
    if (nfe || itens.some((i) => ["gIBSCBS", "gIBSCBSMono", "gEstornoCred"].some((g) => i.grupos.has(g)))) {
      c.add("AIC-040", "erro", "Totais de IBS/CBS ausentes", "Há itens com IBS/CBS, mas o documento não tem o grupo de totais IBSCBSTot.", "Gere o grupo IBSCBSTot com a soma dos itens.", null, "total/IBSCBSTot", "1119");
    }
    return;
  }
  const esp = (i, grupo, chave) => (i.especiais[grupo] || {})[chave] ?? null;
  const contas = [
    ["vBCIBSCBS", "base de cálculo", (i) => i.base],
    ["gIBS/gIBSUF/vIBSUF", "IBS estadual", (i) => (i.ibsUF ? i.ibsUF.valor : null)],
    ["gIBS/gIBSUF/vDif", "IBS estadual diferido", (i) => (i.ibsUF ? i.ibsUF.vDif : null)],
    ["gIBS/gIBSUF/vDevTrib", "IBS estadual devolvido", (i) => (i.ibsUF ? i.ibsUF.vDev : null)],
    ["gIBS/gIBSMun/vIBSMun", "IBS municipal", (i) => (i.ibsMun ? i.ibsMun.valor : null)],
    ["gIBS/gIBSMun/vDif", "IBS municipal diferido", (i) => (i.ibsMun ? i.ibsMun.vDif : null)],
    ["gIBS/gIBSMun/vDevTrib", "IBS municipal devolvido", (i) => (i.ibsMun ? i.ibsMun.vDev : null)],
    ["gIBS/vIBS", "IBS", (i) => i.valorIBS],
    ["gIBS/vCredPres", "crédito presumido de IBS", (i) => esp(i, "gCredPresOper", "gIBSCredPres/vCredPres")],
    ["gIBS/vCredPresCondSus", "crédito presumido de IBS em condição suspensiva", (i) => esp(i, "gCredPresOper", "gIBSCredPres/vCredPresCondSus")],
    ["gCBS/vCBS", "CBS", (i) => (i.cbs ? i.cbs.valor : null)],
    ["gCBS/vDif", "CBS diferida", (i) => (i.cbs ? i.cbs.vDif : null)],
    ["gCBS/vDevTrib", "CBS devolvida", (i) => (i.cbs ? i.cbs.vDev : null)],
    ["gCBS/vCredPres", "crédito presumido de CBS", (i) => esp(i, "gCredPresOper", "gCBSCredPres/vCredPres")],
    ["gCBS/vCredPresCondSus", "crédito presumido de CBS em condição suspensiva", (i) => esp(i, "gCredPresOper", "gCBSCredPres/vCredPresCondSus")],
    ["gMono/vIBSMono", "IBS monofásico", (i) => esp(i, "gIBSCBSMono", "gMonoPadrao/vIBSMono")],
    ["gMono/vCBSMono", "CBS monofásica", (i) => esp(i, "gIBSCBSMono", "gMonoPadrao/vCBSMono")],
    ["gMono/vIBSMonoReten", "IBS monofásico retido", (i) => esp(i, "gIBSCBSMono", "gMonoReten/vIBSMonoReten")],
    ["gMono/vCBSMonoReten", "CBS monofásica retida", (i) => esp(i, "gIBSCBSMono", "gMonoReten/vCBSMonoReten")],
    ["gMono/vIBSMonoRet", "IBS monofásico cobrado antes", (i) => esp(i, "gIBSCBSMono", "gMonoRet/vIBSMonoRet")],
    ["gMono/vCBSMonoRet", "CBS monofásica cobrada antes", (i) => esp(i, "gIBSCBSMono", "gMonoRet/vCBSMonoRet")],
    ["gEstornoCred/vIBSEstCred", "estorno de crédito de IBS", (i) => esp(i, "gEstornoCred", "vIBSEstCred")],
    ["gEstornoCred/vCBSEstCred", "estorno de crédito de CBS", (i) => esp(i, "gEstornoCred", "vCBSEstCred")],
  ];
  conferirFormatos(tot.campos, false, null, c);
  const tolerancia = nfe ? ZERO : TOLERANCIA;
  for (const [caminho, nome, valor] of contas) {
    const informado = tot.valores[caminho] ?? null;
    if (informado === null) continue;
    const calculado = soma(itens.map(valor));
    if (abs(informado - calculado) > tolerancia) {
      c.add("AIC-041", "erro", `Total de ${nome} diferente da soma dos itens`, `O total informa R$ ${brl(informado)}, mas a soma dos itens dá R$ ${brl(calculado)}` + (nfe ? ". A NT exige igualdade exata, sem tolerância de centavo." : "."), "Some os valores já arredondados de cada item; não recalcule o total sobre a base inteira.", null, `IBSCBSTot/${caminho}`, nfe && c.ntTotais ? c.ntTotais[caminho] ?? null : null);
    }
  }
}

// ---------------------------------------------------------------- resumo consolidado do lote
export function resumo(resultados) {
  const sit = resultados.map((r) => situacao(r.achados));
  const conta = (arr) => Object.entries(arr.reduce((m, k) => ((m[k] = (m[k] || 0) + 1), m), {})).sort((a, b) => b[1] - a[1]);
  const problemas = resultados.flatMap((r) => r.achados.filter((a) => a.gravidade !== "info").map((a) => [r, a]));
  const titulos = Object.fromEntries(problemas.map(([, a]) => [a.codigo, a.titulo]));
  const chaves = new Set(problemas.filter(([, a]) => a.item).map(([r, a]) => `${resultados.indexOf(r)}|${a.item}`));
  const porCclass = [];
  const porNcm = [];
  const valores = {};
  resultados.forEach((r, i) => {
    for (const l of r.linhas || []) {
      if (chaves.has(`${i}|${l.item}`)) {
        porCclass.push(l.cclasstrib || "(sem)");
        if (l.ncm) porNcm.push(l.ncm);
      }
      if (!l.cclasstrib) continue;
      const v = (valores[l.cclasstrib] ||= { itens: 0, base: 0n, ibs: 0n, cbs: 0n });
      v.itens += 1;
      for (const k of ["base", "ibs", "cbs"]) if (l[k] !== null && l[k] !== undefined) v[k] += l[k];
    }
  });
  return {
    notas: resultados.length,
    ok: sit.filter((s) => s === "ok").length,
    comAtencao: sit.filter((s) => s === "atencao").length,
    comErro: sit.filter((s) => s === "erro").length,
    porTipo: conta(resultados.map((r) => r.tipo || "?")),
    problemasMaisComuns: conta(problemas.map(([, a]) => a.codigo)).slice(0, 15).map(([c, n]) => [c, n, titulos[c]]),
    porCclasstrib: conta(porCclass).slice(0, 15),
    porNcm: conta(porNcm).slice(0, 15),
    porEmitente: conta(resultados.filter((_, i) => sit[i] !== "ok").map((r) => r.emitente || "?")).slice(0, 15),
    valores: Object.entries(valores).sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([c, v]) => [c, v.itens, brl(v.base), brl(v.ibs), brl(v.cbs)]),
  };
}

// ---------------------------------------------------------------- .zip no navegador (sem bibliotecas)
export async function lerZip(bytes, nomeZip, limite = 200000) {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let fim = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { fim = i; break; }
  }
  if (fim < 0) throw new XMLInvalido("zip inválido");
  const total = dv.getUint16(fim + 10, true);
  if (total > limite) throw new XMLInvalido(`zip com mais de ${limite} arquivos`);
  let p = dv.getUint32(fim + 16, true);
  const saida = [];
  const dec8 = new TextDecoder();
  for (let k = 0; k < total; k++) {
    if (dv.getUint32(p, true) !== 0x02014b50) throw new XMLInvalido("zip inválido");
    const metodo = dv.getUint16(p + 10, true);
    const comp = dv.getUint32(p + 20, true);
    const tam = dv.getUint32(p + 24, true);
    const nLen = dv.getUint16(p + 28, true);
    const xLen = dv.getUint16(p + 30, true);
    const cLen = dv.getUint16(p + 32, true);
    const local = dv.getUint32(p + 42, true);
    const nome = dec8.decode(bytes.subarray(p + 46, p + 46 + nLen));
    p += 46 + nLen + xLen + cLen;
    if (nome.endsWith("/") || !nome.toLowerCase().endsWith(".xml")) continue;
    const origem = `${nomeZip}!${nome}`;
    if (tam > TAMANHO_MAXIMO) { saida.push([origem, new XMLInvalido("arquivo maior que 20 MB")]); continue; }
    const ini = local + 30 + dv.getUint16(local + 26, true) + dv.getUint16(local + 28, true);
    const dados = bytes.subarray(ini, ini + comp);
    try {
      let bruto;
      if (metodo === 0) bruto = dados;
      else if (metodo === 8) bruto = new Uint8Array(await new Response(new Blob([dados]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).arrayBuffer());
      else throw new XMLInvalido("compressão de zip não suportada");
      if (bruto.length > TAMANHO_MAXIMO) throw new XMLInvalido("arquivo maior que 20 MB");
      saida.push([origem, new TextDecoder("utf-8").decode(bruto)]);
    } catch (e) {
      saida.push([origem, e instanceof XMLInvalido ? e : new XMLInvalido("não foi possível descompactar")]);
    }
  }
  return saida;
}

export function auditarTexto(conteudo, origem, t) {
  try {
    return auditar(lerNota(conteudo, origem), t);
  } catch (e) {
    const r = { origem, chave: null, modelo: null, tipo: null, numero: null, serie: null, emissao: null, emitente: null, itens: 0, achados: [], linhas: [] };
    r.achados.push({ codigo: "AIC-001", gravidade: "erro", titulo: "Arquivo não pôde ser lido", explicacao: e instanceof XMLInvalido ? e.message : "erro ao ler o arquivo", como_corrigir: "Confira se é o XML do documento fiscal, completo e sem alterações.", item: null, campo: null });
    return r;
  }
}

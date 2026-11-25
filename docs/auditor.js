// auditor-ibs-cbs (versão web). Mesmas regras da versão Python (src/auditor_ibs_cbs/regras.py),
// conferidas pelo mesmo gabarito (tests/esperado.json). Roda no navegador e no Node, sem dependências.
// Nenhum dado sai da máquina de quem usa.

export const TAMANHO_MAXIMO = 20 * 1024 * 1024;
const MODELOS = { 55: "NF-e", 65: "NFC-e" };
const GRUPOS_POR_INDICADOR = ["gIBSCBS", "gIBSCBSMono", "gTransfCred", "gCredPresIBSZFM", "gAjusteCompet"];

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
  const elementos = raiz.filhos;
  if (elementos.length !== 1) throw new XMLInvalido("XML mal formado");
  return elementos[0];
}

function filho(no, caminho) {
  let atual = no;
  for (const parte of caminho.split("/")) {
    if (!atual) return null;
    atual = atual.filhos.find((f) => f.tag === parte) || null;
  }
  return atual;
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
// Representamos valores como BigInt em décimos-milionésimos (escala 8), sem ponto flutuante.
const ESCALA = 8;
const UM = 10n ** BigInt(ESCALA);
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
const CENTAVO = 10n ** BigInt(ESCALA - 2);
export function arredondar(v) {
  // duas casas, arredondamento bancário (HALF_EVEN), como a calculadora oficial
  const neg = v < 0n;
  const a = neg ? -v : v;
  let q = a / CENTAVO;
  const r = a % CENTAVO;
  const meio = CENTAVO / 2n;
  if (r > meio || (r === meio && q % 2n === 1n)) q += 1n;
  const res = q * CENTAVO;
  return neg ? -res : res;
}
const mul = (a, b) => (a * b) / UM; // valores e alíquotas têm no máximo 4 casas: produto exato na escala 8
const abs = (a) => (a < 0n ? -a : a);
const TOLERANCIA = dec("0.01");
function fmt(v, casas) {
  const neg = v < 0n;
  const a = neg ? -v : v;
  const int = a / UM;
  let fra = (a % UM).toString().padStart(ESCALA, "0");
  return { neg, int, fra: casas === undefined ? fra.replace(/0+$/, "") : fra.slice(0, casas) };
}
function brl(v) {
  if (v === null) return "?";
  const { neg, int, fra } = fmt(v, 2);
  return (neg ? "-" : "") + int.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + fra;
}
function pct(v) {
  if (v === null) return "?";
  const { neg, int, fra } = fmt(v);
  return (neg ? "-" : "") + int.toString() + (fra ? "," + fra : "") + "%";
}
const decNum = (n) => (n === null || n === undefined ? null : dec(String(n)));

// ---------------------------------------------------------------- leitura da nota
function tributo(g, prefixo) {
  if (!g) return null;
  const red = filho(g, "gRed");
  return {
    aliquota: dec(texto(g, `p${prefixo}`)),
    valor: dec(texto(g, `v${prefixo}`)),
    reducao: red ? dec(texto(red, "pRedAliq")) : null,
    aliquotaEfetiva: red ? dec(texto(red, "pAliqEfet")) : null,
    temDiferimento: !!filho(g, "gDif"),
    temDevolucao: !!filho(g, "gDevTrib"),
  };
}

export function lerNota(conteudo, origem) {
  if (conteudo.length > TAMANHO_MAXIMO) throw new XMLInvalido("arquivo maior que 20 MB");
  const raiz = parseXML(conteudo);
  const inf = raiz.tag === "infNFe" ? raiz : busca(raiz, "infNFe");
  if (!inf) throw new XMLInvalido("não é um XML de NF-e/NFC-e (infNFe não encontrado)");
  const ide = filho(inf, "ide");
  const mod = texto(ide, "mod");
  const id = (inf.attrs.Id || "").replace(/^NFe/, "");
  const prot = busca(raiz, "chNFe");
  const emissaoTxt = texto(ide, "dhEmi") || texto(ide, "dEmi");
  const tot = filho(inf, "total/IBSCBSTot");
  const itens = inf.filhos
    .filter((f) => f.tag === "det")
    .map((det) => {
      const numero = det.attrs.nItem || "?";
      const grupo = filho(det, "imposto/IBSCBS");
      if (!grupo) return { numero, temGrupo: false, grupos: new Set() };
      const g = filho(grupo, "gIBSCBS");
      return {
        numero,
        temGrupo: true,
        cst: texto(grupo, "CST"),
        cclasstrib: texto(grupo, "cClassTrib"),
        grupos: new Set(grupo.filhos.map((f) => f.tag).filter((t) => t.startsWith("g"))),
        base: g ? dec(texto(g, "vBC")) : null,
        ibsUF: g ? tributo(filho(g, "gIBSUF"), "IBSUF") : null,
        ibsMun: g ? tributo(filho(g, "gIBSMun"), "IBSMun") : null,
        cbs: g ? tributo(filho(g, "gCBS"), "CBS") : null,
        valorIBS: g ? dec(texto(g, "vIBS")) : null,
      };
    });
  return {
    origem,
    chave: id || (prot ? prot.texto.trim() : null) || null,
    modelo: mod && /^\d+$/.test(mod) ? Number(mod) : null,
    numero: texto(ide, "nNF"),
    serie: texto(ide, "serie"),
    emissao: emissaoTxt && /^\d{4}-\d{2}-\d{2}/.test(emissaoTxt) ? emissaoTxt.slice(0, 10) : null,
    crt: texto(inf, "emit/CRT"),
    itens,
    totais: tot
      ? {
          presente: true,
          base: dec(texto(tot, "vBCIBSCBS")),
          ibsUF: dec(texto(tot, "gIBS/gIBSUF/vIBSUF")),
          ibsMun: dec(texto(tot, "gIBS/gIBSMun/vIBSMun")),
          ibs: dec(texto(tot, "gIBS/vIBS")),
          cbs: dec(texto(tot, "gCBS/vCBS")),
        }
      : { presente: false },
  };
}

// ---------------------------------------------------------------- tabelas
const vigente = (inicio, fim, dia) => !((inicio && dia < inicio) || (fim && dia > fim));
export function criarTabelas(dados) {
  const f = dados.fonte;
  return {
    dados,
    fonte: f,
    versao: `${f.versao_base} (${f.data_base})`,
    cst: (c) => dados.cst[c] || null,
    cclasstrib: (c) => dados.cclasstrib[c] || null,
    vigente: (reg, dia) => vigente(reg.inicio, reg.fim, dia),
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
  };
}

// ---------------------------------------------------------------- regras
const achado = (codigo, gravidade, titulo, explicacao, comoCorrigir, item = null, campo = null) => ({
  codigo,
  gravidade,
  titulo,
  explicacao,
  como_corrigir: comoCorrigir,
  item,
  campo,
});
const dataBR = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

export function situacao(achados) {
  const g = new Set(achados.map((a) => a.gravidade));
  return g.has("erro") ? "erro" : g.has("atencao") ? "atencao" : "ok";
}

export function auditar(nota, t) {
  const r = {
    origem: nota.origem,
    chave: nota.chave,
    modelo: nota.modelo,
    numero: nota.numero,
    serie: nota.serie,
    emissao: nota.emissao,
    itens: nota.itens.length,
    achados: [],
  };
  if (!(nota.modelo in MODELOS)) {
    r.achados.push(achado("AIC-002", "info", "Documento fora do escopo", `O modelo ${nota.modelo} não é NF-e (55) nem NFC-e (65); o arquivo não foi auditado.`, "Nada a fazer."));
    return r;
  }
  if (!nota.emissao) {
    r.achados.push(achado("AIC-003", "erro", "Data de emissão ausente", "Sem a data de emissão (dhEmi) não dá para saber quais tabelas valiam no dia.", "Confira se o arquivo é o XML completo da nota.", null, "ide/dhEmi"));
    return r;
  }
  if (nota.emissao < "2026-01-01") {
    r.achados.push(achado("AIC-004", "info", "Nota anterior à reforma", "A nota foi emitida antes de 01/01/2026, quando o grupo IBS/CBS ainda não existia.", "Nada a fazer."));
    return r;
  }
  for (const item of nota.itens) r.achados.push(...auditarItem(item, nota, t));
  r.achados.push(...auditarTotais(nota));
  return r;
}

function auditarItem(item, nota, t) {
  const out = [];
  const dia = nota.emissao;
  const n = item.numero;
  const modelo = MODELOS[nota.modelo];
  if (!item.temGrupo) {
    if (nota.crt === "3") {
      out.push(achado("AIC-010", "erro", "Grupo IBS/CBS não informado",
        "O item não tem o grupo IBSCBS. Pela NT 2025.002, emitentes do regime normal (CRT 3) devem informar IBS e CBS em todos os itens. A rejeição automática (1115) segue o cronograma da versão vigente da nota técnica.",
        "Configure no sistema emissor o CST e o cClassTrib do produto para gerar o grupo IBSCBS.", n, "det/imposto/IBSCBS"));
    } else {
      out.push(achado("AIC-010", "info", "Grupo IBS/CBS não informado",
        "O item não tem o grupo IBSCBS. Para o Simples Nacional e o MEI (CRT 1, 2 ou 4) a obrigatoriedade segue um cronograma próprio da NT 2025.002.",
        "Confira na versão vigente da nota técnica a partir de quando o seu regime precisa informar.", n, "det/imposto/IBSCBS"));
    }
    return out;
  }
  const cst = t.cst(item.cst || "");
  if (!cst) {
    out.push(achado("AIC-011", "erro", "CST do IBS/CBS inexistente", `O CST '${item.cst}' não existe na tabela oficial (${t.versao}).`, "Use um dos CSTs da tabela oficial; o comando 'consultar' lista os códigos.", n, "IBSCBS/CST"));
  } else if (!t.vigente(cst, dia)) {
    out.push(achado("AIC-012", "erro", "CST fora da vigência", `O CST ${item.cst} não valia em ${dataBR(dia)} (vigência ${cst.inicio} a ${cst.fim || "atual"}).`, "Use um CST vigente na data de emissão.", n, "IBSCBS/CST"));
  }
  const cl = t.cclasstrib(item.cclasstrib || "");
  if (!cl) {
    out.push(achado("AIC-013", "erro", "cClassTrib inexistente", `O código de classificação tributária '${item.cclasstrib}' não existe na tabela oficial (${t.versao}).`, "Corrija o cClassTrib do produto; use 'consultar' para ver os códigos de cada CST.", n, "IBSCBS/cClassTrib"));
  } else {
    if (!t.vigente(cl, dia)) {
      out.push(achado("AIC-014", "erro", "cClassTrib fora da vigência", `O cClassTrib ${item.cclasstrib} não valia em ${dataBR(dia)} (vigência ${cl.inicio} a ${cl.fim || "atual"}).`, "Troque pelo código que substituiu este na tabela vigente.", n, "IBSCBS/cClassTrib"));
    }
    if (item.cst && cl.cst !== item.cst) {
      out.push(achado("AIC-015", "erro", "cClassTrib não pertence ao CST", `O cClassTrib ${item.cclasstrib} (${cl.descricao}) é do CST ${cl.cst}, mas o item informa CST ${item.cst}.`, `Use o CST ${cl.cst} ou escolha um cClassTrib do CST ${item.cst}.`, n, "IBSCBS/CST"));
    }
    if (!t.permitidoNoModelo(item.cclasstrib, nota.modelo, dia)) {
      out.push(achado("AIC-016", "erro", `cClassTrib não permitido em ${modelo}`, `Pela tabela oficial, o cClassTrib ${item.cclasstrib} (${cl.descricao}) não pode ser usado em ${modelo} na data de emissão.`, `Escolha um cClassTrib previsto para ${modelo}.`, n, "IBSCBS/cClassTrib"));
    }
  }
  if (cst) {
    for (const grupo of GRUPOS_POR_INDICADOR) {
      const exigido = !!cst.grupos[grupo];
      const presente = item.grupos.has(grupo);
      if (exigido && !presente) {
        out.push(achado("AIC-020", "erro", `Grupo ${grupo} ausente`, `O CST ${item.cst} (${cst.descricao}) exige o grupo ${grupo}, que não está no item.`, `Gere o grupo ${grupo} ou confira se o CST está certo.`, n, `IBSCBS/${grupo}`));
      } else if (presente && !exigido) {
        out.push(achado("AIC-021", "atencao", `Grupo ${grupo} inesperado`, `O item traz o grupo ${grupo}, que o CST ${item.cst} (${cst.descricao}) não prevê.`, "Confira se o CST está certo para esta operação.", n, `IBSCBS/${grupo}`));
      }
    }
  }
  if (item.grupos.has("gIBSCBS")) out.push(...auditarValores(item, nota, t, cst));
  return out;
}

function auditarValores(item, nota, t, cst) {
  const out = [];
  const n = item.numero;
  const dia = nota.emissao;
  const preveReducao = !!(cst && cst.grupos.gRed);
  const blocos = [["IBSUF", "IBS estadual", item.ibsUF], ["IBSMun", "IBS municipal", item.ibsMun], ["CBS", "CBS", item.cbs]];
  for (const [sigla, nome, trib] of blocos) {
    if (!trib) continue;
    const temRed = trib.reducao !== null || trib.aliquotaEfetiva !== null;
    if (cst && temRed && !preveReducao) {
      out.push(achado("AIC-022", "atencao", `Redução de alíquota inesperada (${nome})`, `O item informa redução (gRed) no ${nome}, mas o CST ${item.cst} não prevê redução.`, "Confira o CST: operações com redução usam CSTs como 200 ou 515.", n, `g${sigla}/gRed`));
    }
    const oficial = item.cclasstrib ? decNum(t.reducao(item.cclasstrib, sigla, dia)) : null;
    if (trib.reducao !== null && oficial !== null && oficial !== trib.reducao) {
      out.push(achado("AIC-023", "atencao", `Percentual de redução diferente do oficial (${nome})`, `O item informa redução de ${pct(trib.reducao)}, mas a tabela oficial do cClassTrib ${item.cclasstrib} prevê ${pct(oficial)}.`, "Confira o cClassTrib e o percentual de redução configurados para o produto.", n, `g${sigla}/gRed/pRedAliq`));
    }
    out.push(...conferirValor(item, trib, sigla, nome));
  }
  if (item.valorIBS !== null && item.ibsUF && item.ibsMun && item.ibsUF.valor !== null && item.ibsMun.valor !== null) {
    const soma = item.ibsUF.valor + item.ibsMun.valor;
    if (abs(soma - item.valorIBS) > TOLERANCIA) {
      out.push(achado("AIC-031", "erro", "IBS total diferente da soma", `vIBS é R$ ${brl(item.valorIBS)}, mas IBS estadual + municipal dá R$ ${brl(soma)}.`, "O vIBS do item deve ser a soma de vIBSUF e vIBSMun.", n, "gIBSCBS/vIBS"));
    }
  }
  const refs = [["CBS", "CBS", item.cbs], ["IBSUF", "IBS estadual", item.ibsUF], ["IBSMun", "IBS municipal", item.ibsMun]];
  for (const [sigla, nome, trib] of refs) {
    if (!trib || trib.aliquota === null || trib.reducao !== null) continue;
    const ref = decNum(t.aliquotaReferencia(sigla, dia));
    const cl = t.cclasstrib(item.cclasstrib || "");
    if (ref !== null && cl && cl.tipo_aliquota === "Padrão" && trib.aliquota !== ref) {
      out.push(achado("AIC-032", "info", `Alíquota diferente da referência (${nome})`, `A alíquota informada é ${pct(trib.aliquota)}; a de referência para ${dia.slice(0, 4)} é ${pct(ref)}.`, "Se não houver motivo específico (regime, benefício), confira a alíquota configurada.", n, `g${sigla}/p${sigla}`));
    }
  }
  return out;
}

function conferirValor(item, trib, sigla, nome) {
  if (item.base === null || trib.valor === null || trib.aliquota === null) return [];
  if (trib.temDiferimento || trib.temDevolucao) return [];
  const aliquota = trib.aliquotaEfetiva !== null ? trib.aliquotaEfetiva : trib.aliquota;
  const esperado = arredondar(mul(item.base, aliquota) / 100n);
  if (abs(esperado - trib.valor) > TOLERANCIA) {
    return [achado("AIC-030", "atencao", `Valor do ${nome} não bate com base x alíquota`, `Base R$ ${brl(item.base)} x ${pct(aliquota)} = R$ ${brl(esperado)}, mas o item informa R$ ${brl(trib.valor)}.`, "Confira a base de cálculo e a alíquota; a calculadora oficial da Receita ajuda a conferir.", item.numero, `g${sigla}/v${sigla}`)];
  }
  return [];
}

function auditarTotais(nota) {
  const itens = nota.itens.filter((i) => i.grupos.has("gIBSCBS"));
  if (!itens.length) return [];
  const tot = nota.totais;
  if (!tot.presente) {
    return [achado("AIC-040", "erro", "Totais de IBS/CBS ausentes", "Há itens com IBS/CBS, mas a nota não tem o grupo total/IBSCBSTot.", "Gere o grupo IBSCBSTot com a soma dos itens.", null, "total/IBSCBSTot")];
  }
  const soma = (vs) => {
    const v = vs.filter((x) => x !== null && x !== undefined);
    return v.length ? v.reduce((a, b) => a + b, 0n) : null;
  };
  const contas = [
    ["vBCIBSCBS", "base de cálculo", tot.base, soma(itens.map((i) => i.base))],
    ["gIBSUF/vIBSUF", "IBS estadual", tot.ibsUF, soma(itens.map((i) => i.ibsUF && i.ibsUF.valor))],
    ["gIBSMun/vIBSMun", "IBS municipal", tot.ibsMun, soma(itens.map((i) => i.ibsMun && i.ibsMun.valor))],
    ["gIBS/vIBS", "IBS", tot.ibs, soma(itens.map((i) => i.valorIBS))],
    ["gCBS/vCBS", "CBS", tot.cbs, soma(itens.map((i) => i.cbs && i.cbs.valor))],
  ];
  const out = [];
  for (const [campo, nome, informado, calculado] of contas) {
    if (informado === null || informado === undefined || calculado === null) continue;
    if (abs(informado - calculado) > TOLERANCIA) {
      out.push(achado("AIC-041", "erro", `Total de ${nome} diferente da soma dos itens`, `O total informa R$ ${brl(informado)}, mas a soma dos itens dá R$ ${brl(calculado)}.`, "O total da nota deve ser a soma dos valores dos itens.", null, `IBSCBSTot/${campo}`));
    }
  }
  return out;
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
    const r = { origem, chave: null, modelo: null, numero: null, serie: null, emissao: null, itens: 0, achados: [] };
    r.achados.push(achado("AIC-001", "erro", "Arquivo não pôde ser lido", e instanceof XMLInvalido ? e.message : "erro ao ler o arquivo", "Confira se é o XML da NF-e/NFC-e, completo e sem alterações."));
    return r;
  }
}

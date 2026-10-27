// Felles kode for «Mine begreper» og «Meld inn begrep».
// Ingen avhengigheter: validering, YAML og GitHub-lenker er skrevet her.

export const $ = (s, rot = document) => rot.querySelector(s);
export const $$ = (s, rot = document) => [...rot.querySelectorAll(s)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const idag = () => new Date().toISOString().slice(0, 10);
export const kopi = (o) => JSON.parse(JSON.stringify(o ?? null));

// --- Data -------------------------------------------------------------------

export async function lastData() {
  const hent = (f) => fetch(f).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [fv, avh, samsvar, skjemaBegrep, skjemaForslag, config] = await Promise.all([
    hent("data/forvaltning.json"), hent("data/avhengigheter.json"), hent("data/samsvar.json"),
    hent("data/skjema-begrep.json"), hent("data/skjema-forslag.json"), hent("data/config.json"),
  ]);
  return { fv, avh, samsvar, skjemaBegrep, skjemaForslag, config: config ?? {} };
}

export function slug(tekst) {
  return String(tekst).toLowerCase().trim()
    .replace(/æ/g, "ae").replace(/ø/g, "o").replace(/å/g, "a")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export const term = (b) => b?.anbefalt_term?.nb ?? b?.id ?? "";
export const filnavnFor = (b) => `begreper/${b.id.replace(/^.*\//, "")}.yaml`;

// --- Status og visning -------------------------------------------------------

export const begrepsstatus = {
  DRAFT: ["Utkast", "neutral"], CANDIDATE: ["Kandidat", "info"], CURRENT: ["Gjeldende", "success"],
  DEPRECATED: ["Foreldet", "warning"], RETIRED: ["Trukket tilbake", "neutral"],
};
export const forslagsstatus = {
  innmeldt: ["Innmeldt", "info"], under_avklaring: ["Under avklaring", "warning"],
  avvist: ["Avvist", "neutral"], duplikat: ["Duplikat", "neutral"], opprettet: ["Opprettet som begrep", "success"],
};
export const tag = (tekst, farge) => `<span class="ds-tag" data-color="${esc(farge)}">${esc(tekst)}</span>`;

// --- Validering mot JSON Schema generert fra LinkML ----------------------------
// Dekker det gen-json-schema lager for disse modellene: type, required,
// properties, additionalProperties, enum, const, pattern, items, $ref,
// anyOf/oneOf og allOf med if/then (LinkML-regler).

function slaOpp(skjema, rot) {
  while (skjema && skjema.$ref) skjema = rot.$defs[skjema.$ref.replace("#/$defs/", "")];
  return skjema ?? {};
}
function typeAv(v) {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v;
}
function passer(v, skjema, rot) { return valider(v, skjema, rot).length === 0; }

export function valider(v, skjema, rot = skjema, sti = "") {
  skjema = slaOpp(skjema, rot);
  const feil = [];
  const f = (melding) => feil.push({ sti: sti || "/", melding });
  if (skjema.type) {
    const typer = [].concat(skjema.type);
    const t = typeAv(v);
    if (!typer.includes(t) && !(t === "integer" && typer.includes("number"))) {
      f(`må være ${typer.filter((x) => x !== "null").join(" eller ")}`);
      return feil;
    }
  }
  if (skjema.const !== undefined && v !== skjema.const) f(`må være «${skjema.const}»`);
  if (skjema.enum && !skjema.enum.includes(v)) f(`«${v}» er ikke en gyldig verdi`);
  if (typeof v === "string" && skjema.pattern && !new RegExp(skjema.pattern, "u").test(v)) f(`har feil format`);
  if (Array.isArray(v)) {
    if (skjema.minItems && v.length < skjema.minItems) f(`må ha minst ${skjema.minItems}`);
    if (skjema.items) v.forEach((x, i) => feil.push(...valider(x, skjema.items, rot, `${sti}/${i}`)));
  }
  if (typeAv(v) === "object") {
    for (const k of skjema.required ?? []) if (v[k] === undefined || v[k] === null || v[k] === "") feil.push({ sti: `${sti}/${k}`, melding: "må fylles ut" });
    for (const [k, x] of Object.entries(v)) {
      if (skjema.properties?.[k]) feil.push(...valider(x, skjema.properties[k], rot, `${sti}/${k}`));
      else if (skjema.additionalProperties === false) feil.push({ sti: `${sti}/${k}`, melding: "er ikke et felt i modellen" });
    }
  }
  if (skjema.anyOf && !skjema.anyOf.some((s) => passer(v, s, rot))) {
    // Vis feilene fra alternativet som er nærmest å passe
    const beste = skjema.anyOf.map((s) => valider(v, s, rot, sti)).sort((a, b) => a.length - b.length)[0];
    feil.push(...beste);
  }
  if (skjema.oneOf && skjema.oneOf.filter((s) => passer(v, s, rot)).length !== 1) f("må passe nøyaktig ett av alternativene");
  for (const del of skjema.allOf ?? []) {
    if (del.if) { if (passer(v, del.if, rot) && del.then) feil.push(...valider(v, del.then, rot, sti)); }
    else feil.push(...valider(v, del, rot, sti));
  }
  return feil;
}

// --- YAML -------------------------------------------------------------------
// Strenger skrives med doble anførselstegn (gyldig YAML, og ingen overraskelser
// med datoer, tall, «no» eller kolon). Tomme verdier utelates.

const tom = (v) => v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0) ||
  (typeof v === "object" && !Array.isArray(v) && Object.values(v).every(tom));
const nokkel = (k) => (/^[A-Za-z_][A-Za-z0-9_]*$/.test(k) ? k : JSON.stringify(k));
// Samme stil som PyYAML, slik at en endring bare gir diff på linjene som faktisk endres.
// Strenger står uten anførselstegn når det er trygt, ellers med doble.
function trengerFnutter(s) {
  return s === "" || /^[\s\-?:,\[\]{}#&*!|>'"%@`]/.test(s) || /:\s|\s#|:$|\s$|[\n\t]/.test(s) ||
    /^(true|false|yes|no|on|off|null|y|n|~)$/i.test(s) || /^[-+]?(\.\d+|\d[\d_]*(\.\d*)?)([eE][-+]?\d+)?$/.test(s) ||
    /^\d{4}-\d{2}-\d{2}/.test(s) || /^0x[0-9a-f]+$/i.test(s);
}
const skalar = (v) => (typeof v === "string" ? (trengerFnutter(v) ? JSON.stringify(v) : v) : String(v));

export function tilYaml(v, innrykk = 0) {
  const pad = " ".repeat(innrykk);
  if (Array.isArray(v)) {
    return v.filter((x) => !tom(x)).map((x) => {
      if (typeof x === "object" && x !== null) {
        const indre = tilYaml(x, innrykk + 2).replace(/^\s+/, "");
        return `${pad}- ${indre}`;
      }
      return `${pad}- ${skalar(x)}`;
    }).join("\n");
  }
  if (typeof v === "object" && v !== null) {
    return Object.entries(v).filter(([k, x]) => !k.startsWith("_") && !tom(x)).map(([k, x]) => {
      if (Array.isArray(x)) return `${pad}${nokkel(k)}:\n${tilYaml(x, innrykk)}`;
      if (typeof x === "object") return `${pad}${nokkel(k)}:\n${tilYaml(x, innrykk + 2)}`;
      return `${pad}${nokkel(k)}: ${skalar(x)}`;
    }).join("\n");
  }
  return pad + skalar(v);
}

// Finner delskjemaet for en sti som «definisjon[0].tekst.nb», for å vite om
// målet er en liste eller en enkeltverdi.
export function skjemaFor(skjema, sti, rot = skjema) {
  let s = slaOpp(skjema, rot);
  for (const del of sti.replace(/\[(\d+)\]/g, ".$1").split(".").filter(Boolean)) {
    if (/^\d+$/.test(del)) { s = slaOpp(s.items ?? {}, rot); continue; }
    const kand = [s, ...(s.anyOf ?? [])].map((x) => slaOpp(x, rot)).find((x) => x.properties?.[del]);
    if (!kand) return {};
    s = slaOpp(kand.properties[del], rot);
  }
  return s;
}
export const erListe = (s) => [].concat(s.type ?? []).includes("array");

export function settSti(obj, sti, verdi) {
  const deler = sti.replace(/\[(\d+)\]/g, ".$1").split(".").filter(Boolean);
  let o = obj;
  deler.forEach((d, i) => {
    const sist = i === deler.length - 1;
    const nesteErTall = /^\d+$/.test(deler[i + 1] ?? "");
    if (sist) o[d] = verdi;
    else { o[d] ??= nesteErTall ? [] : {}; o = o[d]; }
  });
  return obj;
}
export function rens(v) {
  // Fjerner tomme verdier og interne felt (som _fil), slik YAML-en gjør
  if (Array.isArray(v)) return v.map(rens).filter((x) => !tom(x));
  if (typeof v === "object" && v !== null) {
    const ut = {};
    for (const [k, x] of Object.entries(v)) if (!k.startsWith("_") && !tom(x)) ut[k] = rens(x);
    return ut;
  }
  return v;
}

// Enkel linje-diff (LCS), godt nok for én YAML-fil
export function diff(a, b) {
  const A = a.split("\n"), B = b.split("\n");
  const m = A.length, n = B.length, L = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const ut = []; let i = 0, j = 0;
  while (i < m && j < n) {
    if (A[i] === B[j]) { ut.push([" ", A[i]]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) ut.push(["-", A[i++]]);
    else ut.push(["+", B[j++]]);
  }
  while (i < m) ut.push(["-", A[i++]]);
  while (j < n) ut.push(["+", B[j++]]);
  return ut;
}
export function diffHtml(a, b) {
  const linjer = diff(a, b);
  if (!linjer.some(([t]) => t !== " ")) return `<p class="ds-paragraph" data-size="sm">Ingen endringer.</p>`;
  return `<pre class="diff">${linjer.map(([t, l]) => `<span class="d${t === "+" ? "p" : t === "-" ? "m" : "s"}">${esc(t)} ${esc(l)}</span>`).join("\n")}</pre>`;
}

// --- Innsending ---------------------------------------------------------------
// Siden kan ikke skrive til repoet selv. Den lager et GitHub-issue med YAML-en.
// En GitHub Action leser issuet, validerer filene og lager en pull request.

export const MARKOR = "<!-- begrepsforvaltning -->";

export function issueTekst({ type, oppsummering, filer }) {
  const blokker = filer.map((f) => `**Fil:** \`${f.fil}\`\n\n\`\`\`yaml fil=${f.fil}\n${f.yaml}\n\`\`\``).join("\n\n");
  return `${MARKOR}\n**Type:** ${type}\n\n${oppsummering}\n\n${blokker}\n\n---\n_Laget av begrepsforvaltningssidene. Filene valideres mot modellen og blir en pull request automatisk._`;
}

export function issueLenke(config, tittel, tekst) {
  if (!config.repo) return null;
  const u = new URL(`${config.server || "https://github.com"}/${config.repo}/issues/new`);
  u.searchParams.set("title", tittel);
  u.searchParams.set("body", tekst);
  const s = u.toString();
  return s.length < 8000 ? s : null; // GitHub avviser for lange adresser
}

// Viser valideringsfeil som Smudis ErrorSummary med lenker til feltene
export function feiloppsummering(feil, feltFor) {
  if (!feil.length) return "";
  return `<div class="ds-error-summary" tabindex="-1" role="alert">
    <h2 class="ds-heading" data-size="xs">Rett opp før du sender inn</h2>
    <ul class="ds-list">${feil.map((x) => {
      const felt = feltFor(x.sti);
      return `<li>${felt ? `<a class="ds-link" href="#${esc(felt.id)}">${esc(felt.navn)} ${esc(x.melding)}</a>` : `${esc(x.sti)} ${esc(x.melding)}`}</li>`;
    }).join("")}</ul></div>`;
}

export function kopierKnapp(tekst, etikett = "Kopier YAML") {
  const knapp = document.createElement("button");
  knapp.type = "button";
  knapp.className = "ds-button";
  knapp.dataset.variant = "tertiary";
  knapp.textContent = etikett;
  knapp.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(tekst); knapp.textContent = "Kopiert"; } catch { knapp.textContent = "Kunne ikke kopiere"; }
    setTimeout(() => (knapp.textContent = etikett), 2000);
  });
  return knapp;
}

// Husker hvem som er valgt (bare i denne nettleseren)
export const husk = {
  hent: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  sett: (k, v) => { try { localStorage.setItem(k, v); } catch { /* privat modus */ } },
};

"""Leser alle LinkML-modellene i en mappe og skriver avhengighetene til én JSON-fil.

Bruk:
    python scripts/analyser.py modeller begreper ut/avhengigheter.json

Filen beskriver tre nivåer:
  1. modell → modell     (imports)
  2. element → modell    (hvem som bruker hvilke slots, klasser og enums)
  3. element → begrep    (exact_mappings, close_mappings, slot_uri eller meaning
                          som peker inn i begrepskatalogen)
"""

import json
import sys
from pathlib import Path

import yaml
from linkml_runtime.utils.schemaview import SchemaView

MODELLMAPPE, BEGREPSFIL, UTFIL = (Path(a) for a in sys.argv[1:4])
BEGREP_NS = "https://example.org/begrep/"
LAG_REKKEFOLGE = {"kjerne": 1, "tverrgaende": 2, "fag": 3}


def tekst(v):
    """Gjør en verdi om til ren tekst (LinkML gir ofte egne objekttyper)."""
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return str(getattr(v, "value", v))


def egne(sv, elementer):
    """Bare elementene som er definert i dette skjemaet, ikke i importerte."""
    sid = sv.schema.id
    return {k: v for k, v in elementer.items() if (v.from_schema or sid) == sid}


def annotasjon(element, navn):
    ann = getattr(element, "annotations", None) or {}
    a = ann.get(navn)
    return tekst(a.value) if a is not None else None


# --- 1. Les alle skjemaene -------------------------------------------------

filer = sorted(MODELLMAPPE.rglob("*.yaml"))
lokal = {}      # skjemanavn -> SchemaView uten importer
fil_til_navn = {}
for f in filer:
    sv = SchemaView(str(f))
    lokal[sv.schema.name] = sv
    fil_til_navn[f.resolve().with_suffix("")] = sv.schema.name

modeller = {}
for navn, sv in lokal.items():
    s = sv.schema
    fil = next(f for f in filer if fil_til_navn[f.resolve().with_suffix("")] == navn)
    imports = []
    for imp in s.imports or []:
        if str(imp).startswith("linkml:"):
            continue
        mal = (fil.parent / str(imp)).resolve()
        imports.append(fil_til_navn.get(mal, str(imp)))
    modeller[navn] = {
        "navn": navn,
        "tittel": s.title or navn,
        "beskrivelse": s.description or "",
        "fil": str(fil.relative_to(MODELLMAPPE.parent)),
        "versjon": s.version or "",
        "status": tekst(s.status) or "",
        "lag": annotasjon(s, "lag"),
        "eier": annotasjon(s, "eier"),
        "imports": imports,
        "importert_av": [],
    }
for navn, m in modeller.items():
    for i in m["imports"]:
        if i in modeller:
            modeller[i]["importert_av"].append(navn)

# --- 2. Registrer alle elementene og hvor de er definert --------------------

elementer = {}   # elementnavn -> beskrivelse
definert_i = {}  # elementnavn -> [skjemaer]  (mer enn ett betyr navnekollisjon)


def registrer(navn, type_, skjema, obj, ekstra):
    definert_i.setdefault(navn, []).append(skjema)
    elementer[navn] = {
        "navn": navn,
        "type": type_,
        "modell": skjema,
        "beskrivelse": obj.description or "",
        "foreldet": tekst(getattr(obj, "deprecated", None)),
        "erstattes_av": tekst(getattr(obj, "deprecated_element_has_exact_replacement", None)),
        "uri": None,
        "begreper": [],
        **ekstra,
    }


for skjema, sv in lokal.items():
    for c in egne(sv, sv.all_classes(imports=False)).values():
        registrer(c.name, "klasse", skjema, c, {
            "abstrakt": bool(c.abstract), "mixin": bool(c.mixin),
            "arver_fra": c.is_a, "mixins": list(c.mixins or []),
            "slots": list(sv.class_slots(c.name)),
        })
        elementer[c.name]["uri"] = sv.get_uri(c, expand=True)
    for s in egne(sv, sv.all_slots(imports=False)).values():
        if s.name in elementer and elementer[s.name]["modell"] == skjema:
            continue  # attributter kan dukke opp flere ganger
        registrer(s.name, "slot", skjema, s, {
            "range": s.range, "paakrevd": bool(s.required), "flere": bool(s.multivalued),
            "pattern": s.pattern,
        })
        elementer[s.name]["uri"] = sv.get_uri(s, expand=True)
    for e in egne(sv, sv.all_enums(imports=False)).values():
        registrer(e.name, "enum", skjema, e, {
            "verdier": {
                k: {"meaning": sv.expand_curie(v.meaning) if v.meaning else None,
                    "foreldet": tekst(v.deprecated)}
                for k, v in (e.permissible_values or {}).items()
            },
        })

# --- 3. Bruk på tvers av modeller ------------------------------------------

bruk = []


def legg_til(element, brukt_av, klasse, hvordan, detaljer=None):
    if element not in elementer:
        return
    if elementer[element]["modell"] == brukt_av:
        return  # bruk innenfor egen modell er ikke en avhengighet
    bruk.append({
        "element": element, "fra": elementer[element]["modell"],
        "brukt_av": brukt_av, "klasse": klasse, "hvordan": hvordan,
        "detaljer": detaljer or {},
    })


for skjema, sv_lokal in lokal.items():
    sv = SchemaView(sv_lokal.schema.source_file)  # med importer
    for cnavn, c in sv.all_classes(imports=False).items():
        if c.is_a:
            legg_til(c.is_a, skjema, cnavn, "arver fra")
        for m in c.mixins or []:
            legg_til(m, skjema, cnavn, "mixin")
        for snavn in c.slots or []:
            legg_til(snavn, skjema, cnavn, "bruker")
        for snavn, su in (c.slot_usage or {}).items():
            endret = {k: tekst(v) if not isinstance(v, list) else [tekst(x) for x in v]
                      for k, v in su._as_dict.items()
                      if v not in (None, [], {}, False) and k not in ("name", "annotations")}
            if endret:
                legg_til(snavn, skjema, cnavn, "strammer inn", endret)
        for snavn in sv.class_slots(cnavn):
            r = sv.induced_slot(snavn, cnavn).range
            if r and r in elementer and elementer[r]["type"] in ("enum", "klasse"):
                legg_til(r, skjema, cnavn, "verdiområde", {"via": snavn})
    for snavn, s in egne(sv, sv.all_slots(imports=False)).items():
        if s.range in elementer and elementer[s.range]["type"] in ("enum", "klasse"):
            legg_til(s.range, skjema, None, "verdiområde", {"via": snavn})

# fjern duplikater
sett = set()
unik = []
for b in bruk:
    nokkel = (b["element"], b["brukt_av"], b["klasse"], b["hvordan"], json.dumps(b["detaljer"], sort_keys=True))
    if nokkel not in sett:
        sett.add(nokkel)
        unik.append(b)
bruk = unik

# --- 4. Koblinger til begreper ---------------------------------------------

begreper = {}
# BEGREPSFIL kan være én fil med en «begreper»-liste, eller en mappe med ett begrep per fil.
if BEGREPSFIL.is_dir():
    alle_begreper = [yaml.safe_load(f.read_text(encoding="utf-8")) for f in sorted(BEGREPSFIL.glob("*.yaml"))]
else:
    alle_begreper = (yaml.safe_load(BEGREPSFIL.read_text(encoding="utf-8")) or {}).get("begreper", [])
for b in alle_begreper:
    defs = b.get("definisjon") or []
    begreper[b["id"]] = {
        "id": b["id"],
        "term": (b.get("anbefalt_term") or {}).get("nb") or b["id"],
        "definisjon": next((d["tekst"].get("nb") for d in defs if d.get("tekst", {}).get("nb")), ""),
        "status": b.get("status"),
        "fagansvarlig": b.get("fagansvarlig"),
        "relatert": b.get("er_relatert_til") or [],
        "overordnet": [o for r in b.get("har_generisk_begrepsrelasjon") or [] for o in r.get("overbegrep") or []],
        "elementer": [],
    }

begrepslenker = []
for skjema, sv_lokal in lokal.items():
    sv = SchemaView(sv_lokal.schema.source_file)
    alle = list(egne(sv, sv.all_classes(imports=False)).values()) + list(egne(sv, sv.all_slots(imports=False)).values())
    for el in alle:
        kandidater = [("exact", m) for m in el.exact_mappings or []] + \
                     [("close", m) for m in el.close_mappings or []] + \
                     [("slot_uri", getattr(el, "slot_uri", None) or getattr(el, "class_uri", None))]
        for type_, curie in kandidater:
            if not curie:
                continue
            uri = sv.expand_curie(str(curie))
            if uri.startswith(BEGREP_NS):
                begrepslenker.append({"begrep": uri, "element": el.name, "modell": skjema, "type": type_})
    for enavn, e in egne(sv, sv.all_enums(imports=False)).items():
        for vnavn, v in (e.permissible_values or {}).items():
            if v.meaning and sv.expand_curie(v.meaning).startswith(BEGREP_NS):
                begrepslenker.append({"begrep": sv.expand_curie(v.meaning), "element": f"{enavn}.{vnavn}",
                                      "modell": skjema, "type": "meaning"})

for l in begrepslenker:
    if l["element"] in elementer:
        elementer[l["element"]]["begreper"].append(l["begrep"])
    if l["begrep"] in begreper:
        begreper[l["begrep"]]["elementer"].append({"element": l["element"], "modell": l["modell"], "type": l["type"]})
    else:
        begreper.setdefault(l["begrep"], {"id": l["begrep"], "term": None, "definisjon": "", "ukjent": True,
                                          "elementer": [], "relatert": [], "overordnet": []})
        begreper[l["begrep"]]["elementer"].append({"element": l["element"], "modell": l["modell"], "type": l["type"]})

# --- 5. Skriv ut ---------------------------------------------------------------

ut = {
    "lag": LAG_REKKEFOLGE,
    "modeller": modeller,
    "elementer": elementer,
    "definert_i": {k: v for k, v in definert_i.items()},
    "bruk": bruk,
    "begreper": begreper,
}
UTFIL.parent.mkdir(parents=True, exist_ok=True)
UTFIL.write_text(json.dumps(ut, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{len(modeller)} modeller, {len(elementer)} elementer, {len(bruk)} avhengigheter, "
      f"{len(begrepslenker)} begrepskoblinger → {UTFIL}")

"""Sjekker avhengighetene mot forvaltningsreglene.

Bruk:
    python scripts/sjekk.py _site/data/avhengigheter.json _site/data/sjekk.json

Nivåer:
  feil      – stopper bygget
  advarsel  – bør rettes, men stopper ikke
  merknad   – til informasjon
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

inn, ut = Path(sys.argv[1]), Path(sys.argv[2])
d = json.loads(inn.read_text(encoding="utf-8"))
modeller, elementer, bruk, begreper = d["modeller"], d["elementer"], d["bruk"], d["begreper"]
LAG = d["lag"]
funn = []


def meld(niva, regel, melding, modell=None, element=None):
    funn.append({"niva": niva, "regel": regel, "melding": melding, "modell": modell, "element": element})


# 1. Metadata: alle modeller skal ha lag, eier og versjon
for m in modeller.values():
    for felt in ("lag", "eier", "versjon"):
        if not m.get(felt):
            meld("feil", "metadata", f"{m['navn']} mangler «{felt}».", m["navn"])
    if m.get("lag") and m["lag"] not in LAG:
        meld("feil", "metadata", f"{m['navn']} har ukjent lag «{m['lag']}». Gyldige: {', '.join(LAG)}.", m["navn"])

# 2. Importer som ikke finnes
for m in modeller.values():
    for i in m["imports"]:
        if i not in modeller:
            meld("feil", "import", f"{m['navn']} importerer «{i}», som ikke finnes i modellmappen.", m["navn"])

# 3. Lagdeling: avhengigheter skal gå nedover. Fagmodeller skal ikke importere hverandre.
for m in modeller.values():
    for i in m["imports"]:
        if i not in modeller or not m.get("lag") or not modeller[i].get("lag"):
            continue
        fra, til = LAG.get(m["lag"], 0), LAG.get(modeller[i]["lag"], 0)
        if til > fra:
            meld("feil", "lagdeling",
                 f"{m['navn']} ({m['lag']}) importerer {i} ({modeller[i]['lag']}). "
                 "Avhengigheter skal bare gå til samme eller lavere lag.", m["navn"])
        elif til == fra and m["lag"] == "fag":
            meld("feil", "lagdeling",
                 f"Fagmodellen {m['navn']} importerer fagmodellen {i}. "
                 "Flytt det som deles ned i et tverrgående lag eller kjernen.", m["navn"])

# 4. Sykliske importer
graf = {n: [i for i in m["imports"] if i in modeller] for n, m in modeller.items()}
sett_sykler = set()


def dfs(node, sti):
    for nab in graf[node]:
        if nab in sti:
            syk = sti[sti.index(nab):] + [nab]
            nokkel = frozenset(syk)
            if nokkel not in sett_sykler:
                sett_sykler.add(nokkel)
                meld("feil", "sykel", "Syklisk import: " + " → ".join(syk), nab)
        else:
            dfs(nab, sti + [nab])


for n in graf:
    dfs(n, [n])

# 5. Navnekollisjoner: samme navn definert i flere modeller
for navn, skjemaer in d["definert_i"].items():
    if len(set(skjemaer)) > 1:
        meld("feil", "navnekollisjon",
             f"«{navn}» er definert i {', '.join(sorted(set(skjemaer)))}. "
             "Navn må være unike når modellene importeres sammen.", element=navn)

# 6. Bruk av foreldede elementer og kodeverdier
for b in bruk:
    e = elementer[b["element"]]
    if e.get("foreldet"):
        erstatt = f" Bruk «{e['erstattes_av']}» i stedet." if e.get("erstattes_av") else ""
        meld("advarsel", "foreldet",
             f"{b['brukt_av']} ({b['klasse'] or 'slot'}) bruker «{b['element']}», som er foreldet: {e['foreldet']}{erstatt}",
             b["brukt_av"], b["element"])
    for verdi in b["detaljer"].get("equals_string_in") or []:
        r = e.get("range")
        enum = elementer.get(r) if r else None
        if enum and enum["type"] == "enum" and verdi not in enum["verdier"]:
            meld("feil", "kodeverdi",
                 f"{b['brukt_av']} begrenser «{b['element']}» til «{verdi}», som ikke finnes i {r}.",
                 b["brukt_av"], b["element"])

# 7. Samme URI definert i flere modeller (mulig manglende gjenbruk)
per_uri = defaultdict(set)
for e in elementer.values():
    if e["type"] == "slot" and e.get("uri") and not e["uri"].startswith("https://example.org/modeller/"):
        per_uri[e["uri"]].add((e["modell"], e["navn"]))
for uri, forekomster in per_uri.items():
    if len({m for m, _ in forekomster}) > 1:
        liste = ", ".join(f"{n} ({m})" for m, n in sorted(forekomster))
        meld("merknad", "gjenbruk",
             f"<{uri}> brukes av flere slots i ulike modeller: {liste}. Vurder om én av dem kan gjenbrukes.")

# 8. Begreper
for b in begreper.values():
    if b.get("ukjent"):
        for el in b["elementer"]:
            meld("advarsel", "begrep",
                 f"«{el['element']}» i {el['modell']} peker til {b['id']}, som ikke finnes i begrepskatalogen.",
                 el["modell"], el["element"])
    elif not b["elementer"]:
        meld("merknad", "begrep", f"Begrepet «{b['term']}» brukes ikke i noen modell.")

for e in elementer.values():
    m = modeller[e["modell"]]
    if m.get("lag") == "fag" and e["type"] == "klasse" and not e["begreper"]:
        meld("merknad", "begrep", f"Klassen «{e['navn']}» i {e['modell']} peker ikke til noe begrep.",
             e["modell"], e["navn"])

# 9. Begrepsforvaltning: fagansvarlige og forslag (hvis forvaltning.json er gitt)
if len(sys.argv) > 3:
    import datetime
    fv = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    personer = {p["id"]: p for p in fv["fagansvarlige"]}
    begrep_ids = {b["id"] for b in fv["begreper"]}
    for b in fv["begreper"]:
        if b.get("fagansvarlig") not in personer:
            meld("feil", "forvaltning", f"{b['_fil']}: fagansvarlig «{b.get('fagansvarlig')}» finnes ikke i forvaltning/fagansvarlige.yaml.")
    idag = datetime.date.today()
    for f in fv["forslag"]:
        navn = f"{f['_fil']} («{f.get('foreslatt_term')}»)"
        if f.get("foreslatt_fagansvarlig") and f["foreslatt_fagansvarlig"] not in personer:
            meld("feil", "forvaltning", f"{navn}: foreslått fagansvarlig finnes ikke.")
        for felt in ("duplikat_av", "resultat_begrep"):
            if f.get(felt) and f[felt] not in begrep_ids:
                meld("feil", "forvaltning", f"{navn}: «{felt}» peker til et begrep som ikke finnes.")
        for r in f.get("ligner_pa") or []:
            if r not in begrep_ids:
                meld("advarsel", "forvaltning", f"{navn}: «ligner på» peker til {r}, som ikke finnes.")
        if f.get("forslagsstatus") == "innmeldt":
            dager = (idag - datetime.date.fromisoformat(str(f["opprettet"]))).days
            if dager > 14:
                meld("advarsel", "forvaltning", f"{navn} har ventet {dager} dager uten å bli tatt til avklaring.")
        if not f.get("foreslatt_fagansvarlig") and f.get("forslagsstatus") in ("innmeldt", "under_avklaring"):
            meld("merknad", "forvaltning", f"{navn} har ingen fagansvarlig. Begrepsforvaltningen må fordele det.")
    uten_github = [p["navn"] for p in fv["fagansvarlige"] if not p.get("github_bruker")]
    if uten_github:
        meld("merknad", "forvaltning", f"{len(uten_github)} fagansvarlige mangler GitHub-bruker og kan ikke bes om godkjenning automatisk: {', '.join(uten_github)}.")

# --- Resultat -----------------------------------------------------------------

rekkefolge = {"feil": 0, "advarsel": 1, "merknad": 2}
funn.sort(key=lambda f: (rekkefolge[f["niva"]], f["regel"], f["melding"]))
ut.parent.mkdir(parents=True, exist_ok=True)
ut.write_text(json.dumps(funn, ensure_ascii=False, indent=2), encoding="utf-8")

antall = {n: sum(f["niva"] == n for f in funn) for n in rekkefolge}
for f in funn:
    print(f"[{f['niva'].upper():8}] {f['regel']:14} {f['melding']}")
print(f"\n{antall['feil']} feil, {antall['advarsel']} advarsler, {antall['merknad']} merknader")
sys.exit(1 if antall["feil"] else 0)

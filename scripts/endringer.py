"""Sammenligner to versjoner av avhengigheter.json og finner endringer som kan
brekke andre modeller. Brukes i pull requests: «før» er main, «etter» er grenen.

Bruk:
    python scripts/endringer.py for.json etter.json [rapport.md]

Stopper med feil hvis en modell har en brytende endring uten at versjonen
er økt i første siffer (f.eks. 1.4.0 → 2.0.0).
"""

import json
import sys
from pathlib import Path

for_, etter = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:3])
rapportfil = Path(sys.argv[3]) if len(sys.argv) > 3 else None

E0, E1 = for_["elementer"], etter["elementer"]
M0, M1 = for_["modeller"], etter["modeller"]
brudd, andre = [], []


def berorte(element):
    """Modeller som bruker elementet, i både gammel og ny versjon."""
    return sorted({b["brukt_av"] for b in for_["bruk"] + etter["bruk"] if b["element"] == element})


def hovedversjon(v):
    try:
        return int(str(v).split(".")[0])
    except ValueError:
        return None


for navn, gammel in E0.items():
    ny = E1.get(navn)
    modell = gammel["modell"]
    if ny is None:
        brudd.append((modell, navn, f"{gammel['type']} «{navn}» er fjernet"))
        continue
    if ny["modell"] != modell:
        brudd.append((modell, navn, f"«{navn}» er flyttet fra {modell} til {ny['modell']}"))
    if gammel["type"] == "slot":
        if not gammel["paakrevd"] and ny["paakrevd"]:
            brudd.append((modell, navn, f"«{navn}» er blitt påkrevd"))
        if gammel["range"] != ny["range"]:
            brudd.append((modell, navn, f"verdiområdet til «{navn}» er endret fra {gammel['range']} til {ny['range']}"))
        if gammel["flere"] and not ny["flere"]:
            brudd.append((modell, navn, f"«{navn}» tillater ikke lenger flere verdier"))
        if gammel.get("pattern") != ny.get("pattern") and ny.get("pattern"):
            brudd.append((modell, navn, f"mønsteret for «{navn}» er endret"))
        if gammel.get("uri") != ny.get("uri"):
            brudd.append((modell, navn, f"URI for «{navn}» er endret fra {gammel['uri']} til {ny['uri']}"))
    if gammel["type"] == "enum":
        for v in gammel["verdier"]:
            if v not in ny["verdier"]:
                brudd.append((modell, navn, f"verdien «{v}» er fjernet fra {navn}"))
        for v in ny["verdier"]:
            if v not in gammel["verdier"]:
                andre.append((modell, navn, f"ny verdi «{v}» i {navn}"))
    if not gammel.get("foreldet") and ny.get("foreldet"):
        andre.append((modell, navn, f"«{navn}» er merket som foreldet"))

for navn, ny in E1.items():
    if navn not in E0:
        andre.append((ny["modell"], navn, f"nytt {ny['type']} «{navn}»"))

# Versjonssjekk
versjonsfeil = []
for modell in sorted({m for m, _, _ in brudd}):
    v0 = M0.get(modell, {}).get("versjon")
    v1 = M1.get(modell, {}).get("versjon")
    h0, h1 = hovedversjon(v0), hovedversjon(v1)
    if h0 is not None and (h1 is None or h1 <= h0):
        versjonsfeil.append(f"{modell} har brytende endringer, men versjonen er {v0} → {v1}. "
                            f"Øk til {h0 + 1}.0.0.")

# Rapport
L = ["## Endringer i modellene", ""]
if not brudd and not andre:
    L.append("Ingen endringer i modellelementene.")
if brudd:
    L += ["### ⚠️ Brytende endringer", "", "| Modell | Endring | Berørte modeller |", "|---|---|---|"]
    for modell, navn, tekst in brudd:
        b = berorte(navn)
        L.append(f"| {modell} | {tekst} | {', '.join(b) if b else '–'} |")
    L.append("")
if versjonsfeil:
    L += ["### ❌ Versjonen må økes", ""] + [f"- {v}" for v in versjonsfeil] + [""]
if andre:
    L += ["### Andre endringer", ""] + [f"- **{m}**: {t}" for m, _, t in andre] + [""]
rapport = "\n".join(L)
print(rapport)
if rapportfil:
    rapportfil.write_text(rapport, encoding="utf-8")
sys.exit(1 if versjonsfeil else 0)

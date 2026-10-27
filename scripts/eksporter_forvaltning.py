"""Samler begreper, forslag, fagansvarlige og mappingen fra modellen i én JSON-fil
som sidene «Mine begreper» og «Meld inn begrep» bruker.

Bruk:
    python scripts/eksporter_forvaltning.py ut/forvaltning.json

Mappingen fra skjemafelt til begrepsmodellen leses fra annotasjonene
«skjemafelt» og «overfores_til» på slotsene til Begrepsforslag. Endrer man
mappingen i modellen, endrer sidene seg ved neste bygg.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import yaml
from linkml_runtime.utils.schemaview import SchemaView

UT = Path(sys.argv[1])
MODELL = "modeller/tverrgaende/begrepsforvaltning.yaml"
sv = SchemaView(MODELL)


def les_mappe(mappe):
    ut = []
    for f in sorted(Path(mappe).glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        data["_fil"] = str(f)
        ut.append(data)
    return ut


def ann(element, navn):
    alle = element.annotations
    if not alle:
        return None
    # Annotasjoner er en dict, men en JsonObj når de kommer fra slot_usage
    a = alle.get(navn) if hasattr(alle, "get") else getattr(alle, navn, None)
    if a is None:
        return None
    v = getattr(a, "value", a)
    return str(v) if not isinstance(v, dict) else str(v.get("value"))


begreper = les_mappe("begreper")
forslag = les_mappe("forslag")
fagansvarlige = yaml.safe_load(Path("forvaltning/fagansvarlige.yaml").read_text(encoding="utf-8"))["fagansvarlige"]

# Mapping fra innmeldingsskjemaet til begrepsmodellen
mapping = []
for snavn in sv.class_slots("Begrepsforslag"):
    s = sv.induced_slot(snavn, "Begrepsforslag")
    felt = ann(s, "skjemafelt")
    if felt is None:
        continue
    mapping.append({
        "slot": snavn,
        "skjemafelt": felt,
        "overfores_til": ann(s, "overfores_til") or "",
        "paakrevd": bool(s.required),
        "beskrivelse": s.description or "",
        "range": s.range,
        "flere": bool(s.multivalued),
    })


def kodeliste(navn):
    e = sv.get_enum(navn)
    return [{"verdi": k, "beskrivelse": v.description or "", "meaning": sv.expand_curie(v.meaning) if v.meaning else None}
            for k, v in e.permissible_values.items()]


# Påkrevde felt i et begrep, slik at «opprett begrep» kan vise hva som mangler
paakrevd_begrep = [s for s in sv.class_slots("ForvaltetBegrep") if sv.induced_slot(s, "ForvaltetBegrep").required]

# Standardverdier for felt som er like for alle begreper hos oss
def vanligst(nokkel):
    verdier = [json.dumps(b.get(nokkel), sort_keys=True) for b in begreper if b.get(nokkel)]
    return json.loads(Counter(verdier).most_common(1)[0][0]) if verdier else None


ut = {
    "modell": {"navn": sv.schema.name, "versjon": sv.schema.version},
    "fagansvarlige": fagansvarlige,
    "begreper": begreper,
    "forslag": forslag,
    "mapping": mapping,
    "paakrevd_begrep": paakrevd_begrep,
    "kodelister": {n: kodeliste(n) for n in ["Begrepsstatus", "ForholdTilKilde", "Malgruppe", "Forslagsstatus"]},
    "standard": {"kontaktpunkt": vanligst("kontaktpunkt"), "utgiver": vanligst("utgiver")},
    "begrep_ns": "https://example.org/begrep/",
}
UT.parent.mkdir(parents=True, exist_ok=True)
UT.write_text(json.dumps(ut, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"{len(begreper)} begreper, {len(forslag)} forslag, {len(fagansvarlige)} fagansvarlige → {UT}")

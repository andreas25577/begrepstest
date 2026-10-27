"""Validerer begreper, forslag og fagansvarlige mot forvaltningsprofilen.

Bruk:
    python scripts/valider_data.py                 # alt
    python scripts/valider_data.py begreper/soknad.yaml forslag/x.yaml

Hvilken klasse en fil valideres mot, avgjøres av mappen den ligger i.
Skjemaet lastes én gang, så dette går mye raskere enn linkml-validate per fil.
Avslutter med kode 1 hvis noe er ugyldig.
"""

import sys
from pathlib import Path

import yaml
from linkml.validator import Validator
from linkml.validator.plugins import JsonschemaValidationPlugin

MODELL = "modeller/tverrgaende/begrepsforvaltning.yaml"
KLASSE_FOR_MAPPE = {
    "begreper": "ForvaltetBegrep",
    "forslag": "Begrepsforslag",
    "forvaltning": "Fagansvarligregister",
}


def klasse_for(fil: Path):
    return KLASSE_FOR_MAPPE.get(fil.parent.name)


def valider(filer):
    validator = Validator(MODELL, validation_plugins=[JsonschemaValidationPlugin(closed=True)])
    feil = 0
    for fil in filer:
        klasse = klasse_for(fil)
        if klasse is None:
            print(f"✗ {fil}: ligger ikke i begreper/, forslag/ eller forvaltning/")
            feil += 1
            continue
        try:
            data = yaml.safe_load(fil.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            print(f"✗ {fil}: ugyldig YAML: {e}")
            feil += 1
            continue
        if not isinstance(data, dict):
            print(f"✗ {fil}: filen må inneholde ett objekt")
            feil += 1
            continue
        resultater = list(validator.iter_results(data, klasse))
        if resultater:
            feil += 1
            print(f"✗ {fil} ({klasse})")
            for r in resultater:
                print(f"    {r.message}")
        else:
            print(f"✓ {fil}")
    return feil


if __name__ == "__main__":
    args = [Path(a) for a in sys.argv[1:]]
    if not args:
        args = sorted(Path("begreper").glob("*.yaml")) + sorted(Path("forslag").glob("*.yaml")) + [Path("forvaltning/fagansvarlige.yaml")]
    sys.exit(1 if valider(args) else 0)

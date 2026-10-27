#!/usr/bin/env bash
# Validerer, analyserer og sjekker alle modellene, og bygger sidene i _site/.
# Brukes både lokalt og av GitHub Actions.
set -euo pipefail

UT=_site
FORV=modeller/tverrgaende/begrepsforvaltning.yaml
rm -rf "$UT"
mkdir -p "$UT/data/diagram" "$UT/modeller"

echo "1/6 Validerer begreper, forslag og fagansvarlige mot modellen"
python scripts/valider_data.py

echo "2/6 Analyserer avhengigheter"
python scripts/analyser.py modeller begreper "$UT/data/avhengigheter.json"

echo "3/6 Samler data for begrepsforvaltningen"
python scripts/eksporter_forvaltning.py "$UT/data/forvaltning.json"
# JSON Schema fra LinkML, slik at skjemaene på sidene validerer etter samme regler
gen-json-schema --closed --top-class ForvaltetBegrep "$FORV" > "$UT/data/skjema-begrep.json" 2>/dev/null
gen-json-schema --closed --top-class Begrepsforslag "$FORV" > "$UT/data/skjema-forslag.json" 2>/dev/null

echo "4/6 Sjekker forvaltningsreglene"
# Feil her stopper bygget (exit 1), men resultatet skrives først.
python scripts/sjekk.py "$UT/data/avhengigheter.json" "$UT/data/sjekk.json" "$UT/data/forvaltning.json"

echo "5/6 Lager klassediagram for hver modell"
for f in modeller/*/*.yaml; do
  navn=$(basename "$f" .yaml)
  gen-erdiagram "$f" 2>/dev/null | sed '/^```/d' > "$UT/data/diagram/$navn.mmd"
  cp "$f" "$UT/modeller/$navn.yaml"
done

echo "6/6 Kopierer nettsidene"
cp -r site/* "$UT/"
# Samsvarsrapporten lages av en jobb innenfor eget nettverk. Her er den et eksempel.
if [ -f samsvar/samsvar.json ]; then cp samsvar/samsvar.json "$UT/data/"; fi
# Hvor innsendinger skal gå. På GitHub settes dette automatisk.
python - <<EOF > "$UT/data/config.json"
import json, os
print(json.dumps({
  "server": os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
  "repo": os.environ.get("GITHUB_REPOSITORY", ""),
  "gren": os.environ.get("GITHUB_REF_NAME", "main"),
}))
EOF

echo "Ferdig. Sidene ligger i $UT/"

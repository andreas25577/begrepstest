"""Gjør en innsending fra begrepssidene om til en pull request.

Kjøres av .github/workflows/innmelding.yml når et issue opprettes eller endres.
Issuet inneholder én eller flere YAML-blokker merket med filnavn:

    ```yaml fil=begreper/soknad.yaml
    ...
    ```

Skriptet
  1. henter blokkene og sjekker at de bare skriver til begreper/ eller forslag/,
  2. skriver filene og validerer dem mot modellen og forvaltningsreglene,
  3. lager eller oppdaterer en pull request, og ber fagansvarlig om godkjenning,
  4. kommenterer på issuet med resultatet.

Innholdet i issuet er ikke til å stole på. Det leses som data, kjøres aldri,
og sendes aldri via skallet.

Lokal prøvekjøring uten git og GitHub:
    python scripts/issue_til_pr.py --torrkjoring --tekst-fil issue.md --nummer 12 --tittel "..."
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

MARKOR = "<!-- begrepsforvaltning -->"
BLOKK = re.compile(r"```yaml fil=(\S+)\n(.*?)\n```", re.S)
LOVLIG_STI = re.compile(r"^(begreper|forslag)/[a-z0-9][a-z0-9-]{0,80}\.yaml$")
MAKS_FILER = 5
MAKS_STORRELSE = 50_000


class Avvist(Exception):
    pass


def hent_filer(tekst: str):
    if MARKOR not in tekst:
        return None
    filer = BLOKK.findall(tekst.replace("\r\n", "\n"))
    if not filer:
        raise Avvist("Fant ingen YAML-blokker i innsendingen.")
    if len(filer) > MAKS_FILER:
        raise Avvist(f"En innsending kan endre høyst {MAKS_FILER} filer.")
    ut = []
    for sti, innhold in filer:
        if not LOVLIG_STI.match(sti) or ".." in sti:
            raise Avvist(f"«{sti}» er ikke en lovlig fil. Bare begreper/<navn>.yaml og forslag/<navn>.yaml kan endres her.")
        if len(innhold.encode()) > MAKS_STORRELSE:
            raise Avvist(f"«{sti}» er for stor.")
        try:
            data = yaml.safe_load(innhold)
        except yaml.YAMLError as e:
            raise Avvist(f"«{sti}» er ikke gyldig YAML: {e}")
        if not isinstance(data, dict) or "id" not in data:
            raise Avvist(f"«{sti}» må inneholde ett objekt med en id.")
        navn = Path(sti).stem
        if sti.startswith("begreper/") and not str(data["id"]).endswith("/" + navn):
            raise Avvist(f"Filnavnet «{sti}» passer ikke med id-en {data['id']}.")
        if sti.startswith("forslag/") and str(data["id"]) != f"forslag:{navn}":
            raise Avvist(f"Filnavnet «{sti}» passer ikke med id-en {data['id']}.")
        ut.append((sti, innhold.rstrip("\n") + "\n", data))
    return ut


def kjor(*args, sjekk=True, **kw):
    return subprocess.run(list(args), check=sjekk, text=True, capture_output=True, **kw)


def fagansvarlige_for(filer):
    personer = {p["id"]: p for p in yaml.safe_load(Path("forvaltning/fagansvarlige.yaml").read_text(encoding="utf-8"))["fagansvarlige"]}
    ider = set()
    for sti, _, data in filer:
        ider.add(data.get("fagansvarlig") or data.get("foreslatt_fagansvarlig"))
        if Path(sti).exists():  # Ved overføring skal også den gamle eieren se endringen
            gammel = yaml.safe_load(Path(sti).read_text(encoding="utf-8")) or {}
            ider.add(gammel.get("fagansvarlig") or gammel.get("foreslatt_fagansvarlig"))
    return [personer[i] for i in ider if i in personer]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--torrkjoring", action="store_true", help="Ikke bruk git eller GitHub, bare valider og skriv ut")
    ap.add_argument("--tekst-fil")
    ap.add_argument("--nummer", type=int)
    ap.add_argument("--tittel", default="")
    a = ap.parse_args()

    if a.tekst_fil:
        tekst, nummer, tittel, bruker = Path(a.tekst_fil).read_text(encoding="utf-8"), a.nummer, a.tittel, "lokal"
    else:
        hendelse = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        issue = hendelse["issue"]
        tekst, nummer, tittel, bruker = issue.get("body") or "", issue["number"], issue["title"], issue["user"]["login"]

    def kommenter(melding):
        if a.torrkjoring:
            print("\n--- kommentar på issuet ---\n" + melding)
        else:
            kjor("gh", "issue", "comment", str(nummer), "--body", melding)

    try:
        filer = hent_filer(tekst)
    except Avvist as e:
        kommenter(f"❌ Innsendingen kunne ikke behandles.\n\n{e}")
        return 1
    if filer is None:
        print("Issuet kommer ikke fra begrepssidene. Hopper over.")
        return 0

    for sti, innhold, _ in filer:
        Path(sti).parent.mkdir(exist_ok=True)
        Path(sti).write_text(innhold, encoding="utf-8")

    # Samme validering og sjekker som bygget kjører
    validering = kjor(sys.executable, "scripts/valider_data.py", *[s for s, _, _ in filer], sjekk=False)
    ugyldig = validering.returncode != 0
    sjekker = ""
    if not ugyldig:
        bygg = kjor("bash", "scripts/bygg.sh", sjekk=False)
        funn = [l for l in bygg.stdout.splitlines() if l.startswith("[")]
        sjekker = "\n".join(funn)
        if bygg.returncode != 0:
            ugyldig = True
    if ugyldig:
        kommenter("❌ Innsendingen følger ikke modellen eller forvaltningsreglene, og er ikke sendt videre.\n\n"
                  f"```\n{validering.stdout.strip()}\n{sjekker}\n```\n\nRett opp og rediger issuet, så prøver vi igjen.")
        return 1

    eiere = fagansvarlige_for(filer)
    gren = f"begrep/issue-{nummer}"
    oppsummering = "\n".join(f"- `{s}`" for s, _, _ in filer)
    pr_tekst = (f"Fra #{nummer}, sendt inn av @{bruker}.\n\nCloses #{nummer}\n\n**Filer:**\n{oppsummering}\n\n"
                f"**Fagansvarlig:** {', '.join(p['navn'] for p in eiere) or 'ikke satt'}\n\n"
                f"✅ Validert mot modellen.\n\n<details><summary>Forvaltningssjekker</summary>\n\n```\n{sjekker}\n```\n</details>")
    if a.torrkjoring:
        print(f"Ville laget grenen {gren} og en pull request:\n\n{pr_tekst}")
        return 0

    kjor("git", "config", "user.name", "begrepsforvaltning[bot]")
    kjor("git", "config", "user.email", "begrepsforvaltning@users.noreply.github.com")
    kjor("git", "checkout", "-B", gren)
    kjor("git", "add", *[s for s, _, _ in filer])
    kjor("git", "commit", "-m", f"{tittel}\n\nFra #{nummer}.")
    kjor("git", "push", "--force", "origin", gren)
    finnes = json.loads(kjor("gh", "pr", "list", "--head", gren, "--json", "url").stdout or "[]")
    if finnes:
        url = finnes[0]["url"]
        kommenter(f"🔄 Pull requesten er oppdatert: {url}")
    else:
        args = ["gh", "pr", "create", "--head", gren, "--title", tittel, "--body", pr_tekst]
        for p in eiere:
            if p.get("github_bruker"):
                args += ["--reviewer", p["github_bruker"]]
        url = kjor(*args).stdout.strip()
        kommenter(f"✅ Innsendingen følger modellen og er sendt til godkjenning: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

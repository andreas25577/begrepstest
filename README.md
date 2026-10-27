# LinkML-modeller

En samling informasjonsmodeller i LinkML med automatisk oversikt over avhengighetene
mellom dem. Hver gang noe endres, blir modellene analysert og sjekket mot
forvaltningsreglene, og oversiktssiden publiseres på nytt på GitHub Pages.

## Mappene

| Mappe | Innhold |
| --- | --- |
| `modeller/kjerne/` | Felles byggesteiner: typer, flerspråklig tekst, kontaktpunkt, kodelister. |
| `modeller/tverrgaende/` | Standarder som brukes på tvers: SKOS-AP-NO-Begrep og en forenklet DCAT-AP-NO. |
| `modeller/fag/` | Fagmodeller, her `saksbehandling` og `statistikk`. |
| `begreper/` | Ett begrep per fil. Valideres mot `ForvaltetBegrep` (SKOS-AP-NO + fagansvarlig). |
| `forslag/` | Ett begrepsforslag per fil, meldt inn fra «Meld inn begrep». |
| `forvaltning/fagansvarlige.yaml` | Hvem som er fagansvarlig for begreper. |
| `scripts/valider_data.py` | Validerer begreper, forslag og fagansvarlige mot modellen. |
| `scripts/analyser.py` | Leser alle modellene og skriver avhengighetene til JSON. |
| `scripts/sjekk.py` | Sjekker forvaltningsreglene. |
| `scripts/endringer.py` | Finner brytende endringer i en pull request. |
| `scripts/eksporter_forvaltning.py` | Samler data og mapping for begrepssidene. |
| `scripts/issue_til_pr.py` | Gjør innsendinger fra begrepssidene om til pull requests. |
| `site/index.html` | Oversiktssiden. |
| `site/mine-begreper.html` | Siden for fagansvarlige. |
| `site/meld-inn.html` | Skjemaet for å melde inn nye begreper. |
| `site/vendor/smudi/` | Smudi sin CSS og font, hentet fra npm-pakken `@smudi/designsystem` (MIT). |

## Begrepsforvaltning

To sider for den daglige forvaltningen, laget med Smudi:

- **Mine begreper** (`mine-begreper.html`): En fagansvarlig ser begrepene sine, status,
  hvilke modeller som bruker dem og om databasene har avvik. Herfra kan begreper endres,
  og nye forslag kan tas til avklaring, opprettes som begrep, avvises eller markeres som duplikat.
- **Meld inn begrep** (`meld-inn.html`): Et enkelt skjema for alle. Det varsler hvis begrepet
  ser ut til å finnes allerede, og viser hvordan feltene lagres i modellen.

### Modellen

`modeller/tverrgaende/begrepsforvaltning.yaml` er en lokal profil oppå SKOS-AP-NO.
SKOS-AP-NO-modellen er uendret.

- `ForvaltetBegrep` er et SKOS-AP-NO-`Begrep` med en påkrevd `fagansvarlig`.
- `Begrepsforslag` er et innmeldt forslag med status: innmeldt → under avklaring →
  avvist / duplikat / opprettet. Regler i modellen krever `duplikat_av` og `resultat_begrep` der det trengs.
- Hvert felt i forslaget har annotasjonene `skjemafelt` (navnet i skjemaet) og
  `overfores_til` (hvor verdien havner i begrepet). Skjemaet og «opprett begrep»
  bygges fra disse annotasjonene, så det er modellen som bestemmer mappingen.

### Flyten

```
skjema på siden ──validerer mot JSON Schema fra LinkML
      │
      ▼
issue i GitHub med YAML-blokker
      │  .github/workflows/innmelding.yml
      ▼
scripts/issue_til_pr.py: sjekker filstier → validerer → bygger → lager pull request
      │  ber fagansvarlig om godkjenning (krever github_bruker i fagansvarlige.yaml)
      ▼
godkjent og flettet → sidene bygges på nytt
```

Skriptet godtar bare filer i `begreper/` og `forslag/`, sjekker at filnavn og id stemmer,
og leser issuet som data. Ingenting fra issuet sendes gjennom skallet.

**Innstillinger som må slås på i repoet:**
- Settings → Actions → General → Workflow permissions: «Read and write permissions» og
  «Allow GitHub Actions to create and approve pull requests».

**Kjent begrensning:** Pull requests som lages med Actions sitt eget token, starter ikke
andre workflows. Derfor validerer og bygger `issue_til_pr.py` selv før PR-en lages.
Vil dere at vanlige PR-sjekker også skal kjøre, bruk en GitHub App eller et eget token.

**«Vis som» er en prototype.** I en ekte løsning kommer brukeren fra innloggingen,
f.eks. ved at siden ligger bak Entra ID, og GitHub-brukeren kobles til `fagansvarlige.yaml`.

Prøv innsendingsskriptet lokalt uten GitHub:

```bash
python scripts/issue_til_pr.py --torrkjoring --tekst-fil innsending.md --nummer 1 --tittel "Test"
```

## Lagene

Modellene er delt i tre lag. Avhengigheter skal bare gå nedover.

```
fag           saksbehandling, statistikk       kan importere tverrgående og kjerne
tverrgående   skos_ap_no_begrep, dcat_ap_no_lett   kan importere hverandre og kjerne
kjerne        kjerne_typer, kjerne_kontakt, kjerne_kodelister   kan importere hverandre
```

Fagmodeller skal ikke importere hverandre. Hvis to fagmodeller trenger det samme, skal
det flyttes ned i et tverrgående lag eller i kjernen.

## Det hver modell må ha

Øverst i filen:

```yaml
version: 1.0.0
annotations:
  lag: fag                       # kjerne, tverrgaende eller fag
  eier: Seksjon for analyse
```

Hvis du vil koble en klasse eller slot til et begrep, legger du til `exact_mappings`
(eller `close_mappings`) med begrepets URI:

```yaml
classes:
  Vedtak:
    exact_mappings: [begrep:vedtak]
```

## Sjekkene

| Regel | Nivå | Hva den sjekker |
| --- | --- | --- |
| metadata | feil | Alle modeller har `lag`, `eier` og `version`. |
| import | feil | Alle importer peker til en modell som finnes. |
| lagdeling | feil | Ingen import oppover, og ingen import mellom fagmodeller. |
| sykel | feil | Ingen sykliske importer. |
| navnekollisjon | feil | Samme navn er ikke definert i to modeller. |
| kodeverdi | feil | `equals_string_in` bruker bare verdier som finnes i kodelisten. |
| foreldet | advarsel | Ingen bruker elementer merket `deprecated`. |
| begrep | advarsel/merknad | Begrepskoblinger peker til begreper som finnes. Klasser i fagmodeller har et begrep. |
| gjenbruk | merknad | Samme URI er ikke brukt av slots i ulike modeller (mulig manglende gjenbruk). |

**I pull requests** blir modellene i tillegg sammenlignet med `main`. En endring er
brytende hvis et element fjernes eller flyttes, en kodeverdi fjernes, en slot blir påkrevd,
eller verdiområde, mønster eller URI endres. Rapporten viser hvilke modeller som berøres.
Har en modell brytende endringer uten at første siffer i versjonen er økt, stopper sjekken.

Resultatene står under **Actions** i oppsummeringen for hver kjøring.

## Slik foreldes et element

Ikke slett det med en gang. Merk det først:

```yaml
endret_dato:
  deprecated: Erstattet av sist_endret i versjon 1.1.0. Fjernes i 2.0.0.
  deprecated_element_has_exact_replacement: sist_endret
```

Da får alle som bruker det en advarsel, og oversiktssiden viser hvem som må rydde.

## Oversiktssiden

- **Oversikt:** resultatet av sjekkene og en graf over importene, gruppert etter lag.
- **Modeller:** eier, versjon, hva hver modell bruker fra andre og hva andre bruker fra den, og klassediagram.
- **Matrise:** hvilke modeller som bruker hvilke delte elementer.
- **Brukes i:** søk etter et element og se konsekvensen av å endre det.
- **Begreper:** hvilke klasser og slots som representerer hvilke begreper.

- **Samsvar:** om databasene stemmer med modellene (se under).

Du kan lenke direkte til en modell, et element eller et system, f.eks. `…/#element=tilgangsniva` eller `…/#samsvar=SAKSDB`.

## Samsvar med databasene

`samsvar/samsvar.json` er et **eksempel** som viser hvordan en samsvarsrapport kan se ut.
Systemene og tallene er oppdiktet. I praksis lages filen av en planlagt jobb innenfor
eget nettverk, som kjører tre kontroller per system:

1. **Struktur:** Leser databasens metadata (`information_schema`) og sjekker tabeller,
   kolonner, typer, NOT NULL, fremmednøkler og kodelister mot modellen.
2. **Innhold:** Kjører spørringer generert fra reglene i modellen, som bare teller brudd.
3. **Mening:** Viser hvem som har bekreftet hver mapping og når. Er bekreftelsen eldre enn
   12 måneder, gir det en advarsel.

Jobben trenger bare en lesekonto til metadata og tellespørringer. Ingen verdier eller
rader forlater databasen. Rapporten inneholder likevel tabell- og kolonnenavn, så et
repo med ekte rapporter bør være internt.

Hvert system har en `fasit`:
- `database` (eksisterende system): Kolonner som mangler i modellen gir advarsel.
- `modell` (nytt system generert med `gen-sqlddl`): Kolonner som mangler i modellen gir feil.

Mappingene kan holdes i en egen fil i SSSOM-formatet og bygges om til rapporten av jobben.

Siden sammenligner også mappingene med modellene: Elementer i modellen som ingen mapping
peker til vises som «uten fysisk plassering», og mappinger til elementer som ikke finnes
markeres som feil.

## Legge det på GitHub

1. Lag et nytt repo og last opp innholdet i mappen. Sjekk at `.github`-mappen kom med.
2. Gå til **Settings → Pages** og velg **GitHub Actions** under **Source**.
3. Vent til jobben under **Actions** er grønn. Siden ligger på `https://BRUKERNAVN.github.io/REPONAVN/`.

For å se endringssjekken i bruk: Rediger en fil på github.com og velg
**Create a new branch and start a pull request** når du lagrer.

## Kjøre lokalt (valgfritt)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash scripts/bygg.sh
python -m http.server -d _site 8000
```

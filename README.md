# synthetic-doc-gen

Générateur de documents médicaux **entièrement fictifs** pour tester des chaînes de traitement
(OCR, extraction, anonymisation, GED…). Chaque page porte la mention
**DOCUMENT SYNTHÉTIQUE TEST** (en-tête, filigrane, pied de page) et les métadonnées PDF.

Aucune donnée réelle n'est utilisée : prénoms courants associés à des noms de famille composés de syllabes, téléphones dans les
plages réservées à la fiction (`01 99 00 xx xx`), codes postaux `99xxx` (inexistants),
identifiants préfixés `SYN-`, médicament « Placebomol ». Une homonymie fortuite avec une personne
réelle reste théoriquement possible. Les valeurs biologiques sont génériques et n'ont aucune
portée clinique.

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/), Python ≥ 3.11.

```bash
uv sync                      # crée .venv avec les dépendances (dont dev)
uv run synthetic-doc-gen list
```

## Utilisation

```bash
# 20 documents (alternance compte rendu / bilan biologique), graine de lot 42
uv run synthetic-doc-gen generate -o out -n 20 -s 42

# bilans biologiques seuls, profil dense
uv run synthetic-doc-gen generate -o out2 -n 5 -t bilan-biologique -p compact

# régénérer uniquement les documents 100 à 109 du même lot
uv run synthetic-doc-gen generate -o out3 -n 10 -s 42 --start-index 100
```

Options de `generate` : `-o/--out` (obligatoire), `-n/--count` (10), `-s/--seed` (0),
`-t/--types` (liste séparée par des virgules, défaut : tous), `-p/--profile` (`standard`),
`-m/--medium` (`pdf`), `--start-index`, `--force` (écraser). Sans `--force`, la commande refuse
d'écrire si un fichier cible ou le manifeste existe déjà. Chaque lot utilise son propre dossier :
`--start-index` ne reprend pas un manifeste existant. Avec `--force`, les fichiers cibles
peuvent être remplacés seulement en l'absence de manifeste ; pour préserver un lot existant,
choisir un autre dossier. Les autres fichiers ne sont pas supprimés. Une seule génération peut
utiliser le dossier à la fois. Le manifeste est complété ligne par ligne ; les documents déjà
inscrits restent disponibles en cas d'échec. Une interruption brutale entre la publication d'un
PDF et l'ajout de sa ligne peut laisser un PDF sans référence, ou une ligne partielle. Le lot
entier n'est pas une transaction ; inspecter le dossier avant de reprendre après une interruption.

Sortie :

```
out/
├── manifest.jsonl
└── pdf/
    ├── SYN-000000_compte-rendu.pdf
    ├── SYN-000001_bilan-biologique.pdf
    └── …
```

### Types de documents

| Type               | Contenu                                                              |
|--------------------|----------------------------------------------------------------------|
| `compte-rendu`     | Compte rendu de consultation (5 spécialités fictives, sections cliniques) |
| `bilan-biologique` | NFS, biochimie, inflammation ; valeurs de référence, indicateurs H/B |

Les types sont répartis en tournant selon l'index du document et l'ordre fourni à `--types` ;
modifier cet ordre change le type attribué à un index.

### Profils

| Profil         | Effet                                                       |
|----------------|-------------------------------------------------------------|
| `standard`     | A4, corps 10 pt, tableaux zébrés                            |
| `compact`      | A4 dense, corps 8,5 pt, marges réduites, documents plus longs |
| `large-print`  | A4, corps 13 pt, documents courts                           |
| `plain-letter` | US Letter, tableaux sans fond, accent noir                  |

Un profil (`profiles.py`) règle mise en page (format, corps, marges, style de tableau, couleur)
et longueur du contenu. Il fait partie des entrées du déterminisme.

## Déterminisme

La graine d'un document est `SHA-256("{graine_lot}:{index}:{type}")` tronquée à 64 bits : chaque
document a sa propre graine, indépendante du nombre de documents et des autres documents du lot.
Le contenu est donc une fonction pure de *(graine de lot, index, type, profil)* ; `--start-index`
permet de régénérer un sous-ensemble à l'identique. Le moteur PDF utilise `invariant=1` de
ReportLab (dates et identifiants internes figés).

**Garantie** : même entrées + même environnement (versions de Python et de ReportLab) ⇒ même
fichier, octet pour octet (vérifié par les tests). **Pas de promesse d'identité binaire
inter-plateformes ou inter-versions** : le contenu logique comme les octets peuvent changer selon les versions du logiciel ou de ses
dépendances, de Python ou la plateforme. Le manifeste enregistre les versions utilisées.

## Manifeste JSONL

Une ligne JSON (clés triées) par document :

```json
{"schema_version": 1, "doc_id": "SYN-000001", "index": 1, "doc_type": "bilan-biologique",
 "medium": "pdf", "profile": "standard", "profile_parameters": {"name": "standard", "…": "…"},
 "python_version": "3.11.0", "base_seed": 42, "seed": 123…,
 "path": "pdf/SYN-000001_bilan-biologique.pdf", "bytes": 4309, "sha256": "…", "pages": 1,
 "language": "fr", "synthetic": true, "marker": "DOCUMENT SYNTHÉTIQUE TEST",
 "generator": {"name": "synthetic-doc-gen", "version": "0.1.0"},
 "renderer": {"name": "reportlab", "version": "5.1.0"},
 "entities": {"patient_name": "…", "birth_date": "…", "patient_id": "SYN-PAT-…", "…": "…"}}
```

`entities` contient la vérité terrain fictive (nom, date de naissance, identifiants, date,
praticien, nombre de résultats anormaux…), utile pour évaluer une extraction ou une
anonymisation. Les `path` sont relatifs au dossier de sortie.

## Architecture

```
src/synthetic_doc_gen/
├── model.py        # Document = suite de blocs neutres (Heading, Paragraph, KeyValues, Table)
├── fictional.py    # personnes, praticiens, établissements fictifs
├── generators/     # un module par type de document : (rng, profil) -> Document
├── renderers/      # un moteur par média : Document -> octets (pdf.py = ReportLab)
├── profiles.py     # profils nommés
├── seeding.py      # graine par document
├── batch.py        # lot + manifeste
└── cli.py
```

Contenu (générateurs) et forme (moteurs de rendu) sont séparés :

- **Nouveau type** : ajouter `generators/mon_type.py` et l'inscrire dans `GENERATORS`.
- **Nouveau média** (image scannée, DOCX, HL7…) : écrire une classe `Renderer`
  (`name`, `extension`, `version()`, `render(document, profile, doc_id)`) et l'inscrire dans
  `RENDERERS` ; l'option `--medium` et le manifeste suivent sans autre changement.

## Développement

```bash
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format --check .   # format
```

Vérification visuelle : `pdftoppm -r 70 -png out/pdf/SYN-000000_compte-rendu.pdf page`.

## Limites connues (v0.1)

- Un seul moteur PDF (ReportLab), polices standard Helvetica non incorporées (jeu de caractères
  WinAnsi : pas de caractères hors latin-1/cp1252).
- Rendu « propre » : pas de bruit de scan, rotation, tampons ou signatures manuscrites.
- Français uniquement ; gabarits de texte simples (5 spécialités, 21 analytes).
- Les profils sont intégrés au code (pas de fichier de profil externe).
- La reproductibilité des octets dépend de l'environnement (voir Déterminisme).

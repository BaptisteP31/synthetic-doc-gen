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

# générer le premier préfixe atteignant au moins 10 Mo de PDF
uv run synthetic-doc-gen generate -o out-volume --total-size 10M --max-count 5000 -s 42

# bilans biologiques seuls, profil dense
uv run synthetic-doc-gen generate -o out2 -n 5 -t bilan-biologique -p compact

# régénérer uniquement les documents 100 à 109 du même lot
uv run synthetic-doc-gen generate -o out3 -n 10 -s 42 --start-index 100

# comptes rendus d'imagerie (~500 ko chacun, images synthétiques), taille moyenne visée 300 ko
uv run synthetic-doc-gen generate -o out5 -n 10 -t compte-rendu-imagerie --target-size 300k

# corpus mixte : 30 % de scans (images seules, 200 dpi, gris), 2 à 5 pages, logo et signature
# fictifs, taille moyenne visée 250 ko par fichier
uv run synthetic-doc-gen generate -o out4 -n 50 -s 42 --scan-ratio 30% --pages 2-5 \
    --scan-color gray --logo --signature --target-size 250k
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
├── report.json
└── pdf/
    ├── SYN-000000_compte-rendu.pdf
    ├── SYN-000001_bilan-biologique.pdf
    └── …
```

### Volume total

`--total-size` accepte les mêmes unités décimales que `--target-size` et exclut
`--count`. La génération s'arrête au premier document dont la somme des tailles PDF atteint
ou dépasse la cible : le dépassement peut atteindre la taille du dernier PDF. `report.json`
contient `total_target` (volume demandé et obtenu, nombre de documents, écart absolu et relatif,
indicateur `reached`) et `measured.scan_ratio` indique la proportion réelle de scans. La limite
`--max-count` vaut 10 000 par défaut ; si elle est atteinte avant la cible, le rapport est écrit,
un avertissement est affiché et la commande retourne le code 2.

Avec `--target-size`, les réglages sont calibrés une fois sur les premiers
`--calibration-count` documents (10 par défaut, maximum 100, limité par `--max-count`).
Si nécessaire, un premier scan ou PDF natif accessible dans la fenêtre est ajouté à
l'échantillon. La moyenne cible utilise la proportion de scans de toute la fenêtre
`[start-index, start-index + max-count)`, qui peut différer de celle du lot effectivement
produit. La proportion de PDF natifs à images est elle aussi calculée sur cette fenêtre :
dans un lot mixte, sa composition réelle peut différer et la moyenne finale manquer la cible,
même si la calibration estimait celle-ci atteignable. Si aucun scan n'est accessible,
un avertissement le signale. Le préflight parcourt cette fenêtre en temps proportionnel à
`--max-count` ; une limite très grande peut donc ralentir le démarrage, même si peu de
fichiers sont produits. Les options de pages, couleur, résolution et qualité s'appliquent
également aux documents de calibration. Rejouer avec la même graine, les mêmes
options, taille de calibration et environnement reproduit le lot ; les réglages retenus
figurent dans le rapport. Les vérifications de paramètres et de fichiers existants précèdent la
génération ; `--force` est interdit dans ce mode. Les pages demandées sont validées au fil de
l'eau, sauf pour l'échantillon de calibration : une erreur ou interruption peut laisser un lot
partiel avec son manifeste, sans rapport final. Aucun document déjà présent n'est modifié.

### PDF natifs, scans, pages, taille cible

Tout se règle à l'appel (options de `generate`, ou champs de `BatchConfig` en Python) ; sans
ces options, les fichiers sont identiques, octet pour octet, à ceux des versions précédentes.

| Option | Effet |
|--------|-------|
| `--scan-ratio R` | proportion de **scans** (`0.3` ou `30%`, défaut 0). Un scan est un PDF *image seule* : une image par page, aucun texte extractible, comme une numérisation non océrisée. Les autres sont des PDF **natifs** (texte sélectionnable). |
| `--pages N` ou `A-B` | nombre de pages **exact** par document (1-50) ; avec `A-B`, tirage par document, reproductible. Défaut : longueur du profil. |
| `--scan-dpi`, `--scan-color`, `--scan-quality` | résolution (72-600, défaut 150), `color`/`gray`/`bw` (défaut `color`), qualité JPEG 1-95 (défaut 75 ; sans effet en `bw`, compressé sans perte). |
| `--image-dpi`, `--image-quality`, `--image-format` | images synthétiques des types d'imagerie : résolution (72-600, défaut 200), qualité JPEG 1-95 (défaut 85), `jpeg` (défaut) ou `png` (sans perte, qualité sans effet). Sans effet sur les autres types. |
| `--logo`, `--signature` | logo d'établissement et signature manuscrite **fictifs**, dessinés en vectoriel (légendés « LOGO FICTIF » / « signature fictive »). Présents aussi dans les scans. |
| `--target-size T` | taille moyenne visée par fichier (`250k`, `1.5M` ; k = 1000 octets) : règle les scans et les images synthétiques, voir ci-dessous. `--target-tolerance` : écart toléré (défaut 10 %). |

**Répartition natifs / scans.** Déterministe : la décision ne dépend que de l'index, des types
et de la proportion, avec une répartition régulière dans chaque type (pas de corrélation avec la
rotation des types). Un sous-lot (`--start-index`) retrouve les mêmes choix ; le nombre de scans
a un écart strictement inférieur au nombre de types par rapport à `n × R` pour un préfixe
commençant à zéro, et inférieur à deux fois ce nombre pour un sous-lot quelconque.

**Nombre de pages.** Le contenu de base du document est inchangé ; on y ajoute du contenu réel
(notes de suivi datées pour un compte rendu, bilans antérieurs pour un bilan biologique,
cohérents avec l'âge et le sexe du patient) jusqu'à obtenir *exactement* le nombre de pages,
mesuré sur le rendu. Les `entities` du manifeste décrivent le document principal. Si le contenu
de base dépasse déjà la cible (ex. 1 page avec un profil très dense, un logo et une signature),
la génération échoue **avant écriture des documents et du manifeste**, avec l’identifiant du
document concerné. Une cible peut aussi être impossible si le contenu ajouté saute le nombre
de pages demandé, notamment avec une signature ; choisissez une autre cible ou un autre profil.

**Taille moyenne cible (au mieux, sans remplissage).** Aucun octet inutile n'est ajouté. Le
poids d'un PDF natif sans image vient de son contenu (≈ 3-5 ko par page) et ne se règle pas ;
celui des scans et celui des images synthétiques des PDF natifs d'imagerie se règlent, par la
résolution puis, en butée, la qualité JPEG, dans des plages réalistes (100-400 dpi,
qualité 40-95). Avec images et scans dans le même lot, les images sont réglées d'abord vers
la taille par fichier qui donnerait la moyenne cible (scans et natifs à images visent alors la
même taille) ; les scans absorbent ensuite l'écart qui reste, par exemple quand les images
sont en butée. Pour le PNG, seule la résolution agit. Le poids des images n'est jamais gonflé :
il vient de leur définition et de leur compression. Le réglage est calculé avant toute écriture, sur un échantillon de pages
réellement rendues et le nombre réel de pages de tous les scans, en déduisant la contribution
mesurée sur au plus huit natifs. L’estimation multiplie la taille moyenne des flux image
de dix pages au plus (réparties sur six scans au plus) par le nombre moyen réel de pages,
puis ajoute 2 000 octets de structure PDF par document. Cette approximation peut varier avec
le contenu et le nombre de pages ; le rapport donne la mesure effective. Les PDF utilisés pour
compter les pages sont libérés au fur et à mesure, sauf ceux de l’échantillon. Les réglages imposés
(`--scan-dpi`, `--scan-quality`, `--image-dpi`, `--image-quality`) ne sont jamais modifiés. La moyenne **réelle** est ensuite
mesurée sur les fichiers écrits (`report.json`, résumé en fin de commande) ; si elle s'écarte de
la cible au-delà de la tolérance, ou si la cible est hors de portée (aucun scan, réglages
imposés, limites réalistes), un **avertissement** est affiché sur stderr et consigné dans le
rapport (`warnings`), sans échec de la commande. Pour une cible plus haute, augmenter la
proportion de scans ou le nombre de pages.

La calibration dépend du lot entier : relancer `--target-size` sur un sous-lot peut choisir
d’autres réglages. Pour reproduire les octets d’un sous-lot, relevez `scan_settings` dans le
`report.json` du lot initial et relancez avec les mêmes options de contenu et de scan,
`--start-index`, `--scan-dpi`, `--scan-color` et `--scan-quality` correspondants, sans
`--target-size`. En mode `bw`, la qualité JPEG est sans effet. Les versions et la plateforme
doivent aussi être identiques.

`report.json` : paramètres demandés, mesures (total, moyenne, min/max, pages, ventilation
natifs/scans/documents à images, proportion effective), réglages de scan (`scan_settings`) et
d'image (`image_settings`, avec versions de Pillow, libjpeg et FreeType) retenus, bloc `target`
(écart, `reached`, réglages ajustés dont `image_dpi` / `image_jpeg_quality`) et avertissements.
`measured.with_images` compte les documents dont la source contient des images, scans compris ;
`measured.native_with_images` compte uniquement les PDF natifs avec images incorporées.
La cible n'est pas atteinte, avec avertissement, si l'écart mesuré dépasse la tolérance ou si les
plages réalistes ne suffisent pas (ex. 20 ko pour des comptes rendus d'imagerie : le minimum
est ≈ 70 ko à 100 dpi, qualité 40). En Python, `run_batch` est un générateur dont la valeur de
retour (`StopIteration.value`) est ce rapport.

### Types de documents

| Type               | Contenu                                                              |
|--------------------|----------------------------------------------------------------------|
| `compte-rendu`     | Compte rendu de consultation (5 spécialités fictives, sections cliniques) |
| `bilan-biologique` | NFS, biochimie, inflammation ; valeurs de référence, indicateurs H/B |
| `compte-rendu-imagerie` | Échographie abdominale, IRM cérébrale ou radiographie thoracique : texte sélectionnable et 4 à 6 images synthétiques, ≈ 500 ko par défaut |

Le compte rendu d'imagerie n'est pas dans les types par défaut (`--types` le demande) : sans
`--types`, les lots restent identiques à ceux des versions précédentes.

**Images synthétiques.** Fantômes procéduraux (secteur échographique, coupe axiale abstraite,
cliché thoracique abstrait) tirés d'une graine : aucune image réelle ni donnée de patient.
Chaque image porte dans ses pixels un bandeau « IMAGE SYNTHÉTIQUE - DOCUMENT SYNTHÉTIQUE TEST »
et une étiquette « … FICTIVE » ; le JPEG contient en plus un commentaire (segment COM) avec la
mention, la modalité et la graine. Les images sont en niveaux de gris et imprimées à taille
fixe (deux par ligne) : la résolution (`--image-dpi`) change leur poids, pas la mise en page,
donc ni le nombre de pages ni `--pages`. Le flux JPEG (ou Flate pour le PNG) est intégré tel
quel au PDF. Dans un scan, elles sont rastérisées avec la page ; le marquage reste visible.
Pour `--pages`, on ajoute des comptes rendus d'examens antérieurs (texte). Le contenu de base
tient en 2 pages ; `--pages 1` échoue donc avec l'identifiant du document concerné.

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
permet de régénérer un sous-ensemble à l'identique avec les mêmes réglages de rendu. Le moteur PDF utilise `invariant=1` de
ReportLab (dates et identifiants internes figés).

**Garantie** : même entrées + même environnement (versions de Python, ReportLab et, pour les
scans, pdfium et Pillow/libjpeg) ⇒ même fichier, octet pour octet (vérifié par les tests). La
proportion de scans et le nombre de pages tiré par document sont stables pour un sous-lot.
La calibration est déterministe pour un même lot, mais dépend de sa composition. **Pas de promesse d'identité binaire
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
 "render": {"kind": "native", "logo": false, "signature": false, "pages_requested": null,
            "scan": null, "images": null},
 "entities": {"patient_name": "…", "birth_date": "…", "patient_id": "SYN-PAT-…", "…": "…"}}
```

`render.kind` vaut `native` ou `scan` ; pour un scan, `render.scan` donne dpi, couleur, qualité
JPEG et version de pdfium ; pour un document à images, `render.images` donne nombre d'images,
dpi, format, qualité JPEG et versions de Pillow, libjpeg et FreeType. Pour un scan, ces paramètres
décrivent les images du PDF source avant rastérisation : le fichier final contient une image de
page par page, réglée par `render.scan`. Ces champs sont ajoutés sans changer
`schema_version`. `entities` contient la vérité terrain fictive (nom, date de naissance, identifiants, date,
praticien, nombre de résultats anormaux…), utile pour évaluer une extraction ou une
anonymisation. Les `path` sont relatifs au dossier de sortie.

## Architecture

```
src/synthetic_doc_gen/
├── model.py        # Document = suite de blocs neutres (Heading, Paragraph, KeyValues, Table)
├── fictional.py    # personnes, praticiens, établissements fictifs
├── generators/     # un module par type de document : (rng, profil) -> Document
├── renderers/      # un moteur par média : Document -> octets (pdf.py = ReportLab,
│                   #   scan.py = rastérisation pdfium -> PDF image seule, artwork.py = logo/signature,
│                   #   imaging.py = images synthétiques marquées)
├── options.py      # réglages de scan, logo, signature, bornes réalistes
├── pagination.py   # ajustement exact du nombre de pages par contenu réel
├── sizing.py       # réglage dpi/qualité des scans et des images pour la taille moyenne cible
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

## Données produites

Tous les documents sont fictifs et marqués sur chaque page (image comprise pour les scans) et
dans les métadonnées. Le générateur n'écrase ni ne supprime jamais de fichier existant (sauf
`--force`, jamais sur un manifeste existant), publie chaque fichier de façon atomique, verrouille
le dossier contre les générations simultanées et ne produit rien tant que les contrôles et le
réglage de la taille cible ne sont pas passés (le réglage se fait en mémoire). Le dossier de
sortie contient des données de test : le versionner ou le partager est une décision de
l'utilisateur ; `output/` est ignoré par git, et les permissions des fichiers suivent l'umask.

## Développement

```bash
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format --check .   # format
```

Vérification visuelle : `pdftoppm -r 70 -png out/pdf/SYN-000000_compte-rendu.pdf page`.
Vérifier qu'un scan n'a pas de texte : `pdftotext scan.pdf -` (vide) et `pdfimages -list scan.pdf`.

## Limites connues (v0.1)

- Un seul moteur PDF (ReportLab), polices standard Helvetica non incorporées (jeu de caractères
  WinAnsi : pas de caractères hors latin-1/cp1252).
- Scans « propres » : rastérisation fidèle du PDF natif, sans bruit, rotation, plis ni ombres
  (le noir et blanc est une simple binarisation). Pas de tampon ; logo et signature sont
  vectoriels et clairement fictifs.
- Taille cible best effort : estimée sur un échantillon, mesurée ensuite ; les PDF natifs sans
  image ne se règlent pas (≈ 3-5 ko/page, polices non incorporées) et un lot sans scan ni image
  ne peut pas approcher une cible élevée. Le nombre de pages d'un scan est celui de son équivalent natif.
- Pages : minimum selon profil et options (logo, signature) ; les pages ajoutées sont des notes
  ou historiques fictifs répétitifs dans leur forme, destinés aux tests de volumétrie.
- Les scans dépendent de pdfium (pypdfium2) : la rastérisation n'est pas garantie identique entre
  versions ; la rastérisation et l'ajustement de taille ralentissent la génération (≈ 0,1-0,5 s
  par page de scan).
- Images d'imagerie : trois modalités abstraites en niveaux de gris, volontairement peu
  réalistes ; pas de DICOM. Les octets des images dépendent de Pillow, libjpeg et FreeType
  (versions dans le manifeste). Mesure locale (cette machine) : 20 comptes rendus d'imagerie
  natifs en ≈ 1,7 s (≈ 0,5 Mo chacun), ≈ 5 s avec `--pages 4`, ≈ 3,4 s avec `--target-size` ;
  avec 50 % de scans et `--target-size`, ≈ 10 s (rastérisation pdfium).
- Français uniquement ; gabarits de texte simples (5 spécialités, 21 analytes).
- Les profils sont intégrés au code (pas de fichier de profil externe).
- La reproductibilité des octets dépend de l'environnement (voir Déterminisme).

### Parallélisme et grands lots

`--jobs N` utilise N processus de rendu (1 par défaut). Le manifeste et les fichiers
sont publiés dans l'ordre des indices, indépendamment de l'ordre de fin des rendus.
En mode `--total-size`, seul le premier préfixe atteignant la cible est publié ;
des rendus anticipés peuvent néanmoins être calculés puis abandonnés. Au plus N
rendus sont en attente ; davantage de processus augmente l'utilisation mémoire.
La calibration et les précontrôles de pagination restent séquentiels. Une erreur ou
une interruption laisse le préfixe déjà inscrit dans le manifeste, sans rapport final.

`--shard-size N` range les documents dans `pdf/000000/`, `pdf/000001/`, etc. :
le numéro est le quotient de l'indice absolu par N, y compris avec `--start-index`.
Les chemins du manifeste sont relatifs au dossier de sortie et incluent ce sous-dossier.
Les liens symboliques existants pour le dossier du support ou les sous-dossiers visés
sont refusés. Comme pour les sorties classiques, ces vérifications supposent que le
dossier de sortie n'est pas modifié simultanément par un autre programme ; le verrou
ne protège que les générations utilisant cet outil.

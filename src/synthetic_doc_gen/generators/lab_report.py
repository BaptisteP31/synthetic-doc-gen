"""Bilan biologique fictif : tableaux d'analyses avec valeurs de référence et indicateurs."""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

from synthetic_doc_gen.fictional import (
    ADULT_AGE,
    FACILITIES,
    Person,
    document_date,
    fmt_date,
    make_person,
    make_practitioner,
)
from synthetic_doc_gen.model import Document, Heading, KeyValues, Paragraph, Table
from synthetic_doc_gen.profiles import Profile

P_ABNORMAL = 0.25


@dataclass(frozen=True)
class Analyte:
    panel: str
    name: str
    unit: str
    low: float
    high: float
    decimals: int
    #: Bornes propres aux femmes quand elles diffèrent ; ``low``/``high`` valent alors pour
    #: les hommes.
    female: tuple[float, float] | None = None

    def bounds(self, sex: str) -> tuple[float, float]:
        if sex == "F" and self.female is not None:
            return self.female
        return self.low, self.high


# Valeurs de référence génériques, de démonstration uniquement.
CATALOG: tuple[Analyte, ...] = (
    Analyte("Hématologie (NFS)", "Hémoglobine", "g/dL", 13.0, 17.0, 1, (12.0, 16.0)),
    Analyte("Hématologie (NFS)", "Hématies", "T/L", 4.5, 5.8, 2, (4.0, 5.2)),
    Analyte("Hématologie (NFS)", "Hématocrite", "%", 40.0, 51.0, 1, (36.0, 47.0)),
    Analyte("Hématologie (NFS)", "VGM", "fL", 80.0, 100.0, 1),
    Analyte("Hématologie (NFS)", "Leucocytes", "G/L", 4.0, 10.0, 2),
    Analyte("Hématologie (NFS)", "Polynucléaires neutrophiles", "G/L", 1.8, 7.5, 2),
    Analyte("Hématologie (NFS)", "Lymphocytes", "G/L", 1.0, 4.0, 2),
    Analyte("Hématologie (NFS)", "Plaquettes", "G/L", 150.0, 400.0, 0),
    Analyte("Biochimie", "Glycémie à jeun", "g/L", 0.70, 1.10, 2),
    Analyte("Biochimie", "Créatinine", "µmol/L", 60.0, 105.0, 0, (45.0, 90.0)),
    Analyte("Biochimie", "Urée", "mmol/L", 2.5, 8.0, 1),
    Analyte("Biochimie", "Sodium", "mmol/L", 136.0, 145.0, 0),
    Analyte("Biochimie", "Potassium", "mmol/L", 3.5, 5.1, 1),
    Analyte("Biochimie", "Calcium", "mmol/L", 2.15, 2.55, 2),
    Analyte("Biochimie", "Cholestérol total", "g/L", 1.20, 2.00, 2),
    Analyte("Biochimie", "Triglycérides", "g/L", 0.40, 1.50, 2),
    Analyte("Biochimie", "ASAT", "UI/L", 10.0, 40.0, 0),
    Analyte("Biochimie", "ALAT", "UI/L", 7.0, 45.0, 0),
    Analyte("Inflammation", "CRP", "mg/L", 0.0, 5.0, 1),
    Analyte("Inflammation", "Ferritine", "µg/L", 30.0, 300.0, 0, (15.0, 200.0)),
    Analyte("Inflammation", "Vitesse de sédimentation (1 h)", "mm", 2.0, 20.0, 0),
)


def _fmt(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def draw_result(rng: random.Random, analyte: Analyte, sex: str) -> float:
    low, high = analyte.bounds(sex)
    span = high - low
    if rng.random() < P_ABNORMAL:
        excess = span * (0.05 + rng.random() * 0.45)
        value = high + excess if rng.random() < 0.5 else low - excess
    else:
        value = low + rng.random() * span
    return max(0.0, value)


def flag_for(analyte: Analyte, shown_value: float, sex: str) -> str:
    low, high = analyte.bounds(sex)
    if shown_value > high:
        return "H"
    if shown_value < low:
        return "B"
    return ""


def history_blocks(
    rng: random.Random, person: Person, biologist: str, day: dt.date, count: int
) -> list:
    """Bilans antérieurs fictifs (du plus récent au plus ancien), tirés à la suite.

    Le bilan ``i`` ne dépend pas de ``count``. Ils complètent le bilan principal : les
    entités du manifeste (nombre de résultats, anormaux...) ne portent que sur celui-ci.
    """
    out: list = []
    past = day
    for _ in range(count):
        past = max(past - dt.timedelta(days=rng.randint(30, 120)), person.birth_date)
        picked = sorted(rng.sample(range(len(CATALOG)), rng.randint(8, 12)))
        rows: list[tuple[str, ...]] = []
        emphasized: set[int] = set()
        for idx in picked:
            analyte = CATALOG[idx]
            shown = round(draw_result(rng, analyte, person.sex), analyte.decimals)
            flag = flag_for(analyte, shown, person.sex)
            if flag:
                emphasized.add(len(rows))
            low, high = analyte.bounds(person.sex)
            rows.append(
                (
                    analyte.name,
                    _fmt(shown, analyte.decimals),
                    analyte.unit,
                    f"{_fmt(low, analyte.decimals)} - {_fmt(high, analyte.decimals)}",
                    flag,
                )
            )
        out += [
            Heading(f"Historique - prélèvement du {fmt_date(past)}", level=2),
            Paragraph(
                f"N° d'échantillon SYN-ECH-{rng.randrange(10**8):08d}. Résultats antérieurs "
                f"fictifs, repris pour comparaison ({biologist}, biologiste fictif)."
            ),
            Table(
                ("Analyse", "Résultat", "Unité", "Valeurs de référence", "Ind."),
                tuple(rows),
                col_weights=(4.0, 1.5, 1.4, 2.4, 0.8),
                emphasized_rows=frozenset(emphasized),
            ),
        ]
    return out


def generate_lab_report(rng: random.Random, profile: Profile, filler_units: int = 0) -> Document:
    person = make_person(rng)
    prescriber = make_practitioner(rng)
    biologist = make_practitioner(rng)
    facility = rng.choice([f for f in FACILITIES if "Laboratoire" in f or "Centre" in f])
    day = document_date(rng)
    age = person.age_on(day)
    sample_id = f"SYN-ECH-{rng.randrange(10**8):08d}"

    n_rows = rng.randint(*profile.lab_rows)
    picked = sorted(rng.sample(range(len(CATALOG)), min(n_rows, len(CATALOG))))
    blocks: list = [
        KeyValues(
            (
                ("Patient", person.full_name),
                ("Date de naissance", f"{fmt_date(person.birth_date)} ({age} ans)"),
                ("Sexe", person.sex),
                ("Identifiant patient", person.patient_id),
                ("N° d'échantillon", sample_id),
                ("Date de prélèvement", fmt_date(day)),
                ("Prescripteur", prescriber),
            )
        )
    ]

    n_abnormal = 0
    current_panel = None
    rows: list[tuple[str, ...]] = []
    emphasized: set[int] = set()

    def flush() -> None:
        nonlocal rows, emphasized
        if rows:
            blocks.append(
                Table(
                    ("Analyse", "Résultat", "Unité", "Valeurs de référence", "Ind."),
                    tuple(rows),
                    col_weights=(4.0, 1.5, 1.4, 2.4, 0.8),
                    emphasized_rows=frozenset(emphasized),
                )
            )
        rows, emphasized = [], set()

    for idx in picked:
        analyte = CATALOG[idx]
        if analyte.panel != current_panel:
            flush()
            blocks.append(Heading(analyte.panel, level=2))
            current_panel = analyte.panel
        # Le drapeau est calculé sur la valeur arrondie, telle qu'affichée.
        shown = round(draw_result(rng, analyte, person.sex), analyte.decimals)
        flag = flag_for(analyte, shown, person.sex)
        if flag:
            n_abnormal += 1
            emphasized.add(len(rows))
        low, high = analyte.bounds(person.sex)
        rows.append(
            (
                analyte.name,
                _fmt(shown, analyte.decimals),
                analyte.unit,
                f"{_fmt(low, analyte.decimals)} - {_fmt(high, analyte.decimals)}",
                flag,
            )
        )
    flush()

    blocks.append(Paragraph("Ind. : H = supérieur à la valeur de référence, B = inférieur."))
    blocks.append(
        Paragraph(
            "Valeurs de référence génériques de démonstration. Ce bilan est entièrement fictif "
            "et ne doit servir à aucune interprétation clinique."
        )
    )
    if age < ADULT_AGE:
        minor_label = "Patiente mineure" if person.sex == "F" else "Patient mineur"
        blocks.append(
            Paragraph(
                f"{minor_label} : "
                "valeurs de référence adultes "
                "données à titre indicatif, "
                "à interpréter selon les normes pédiatriques."
            )
        )
    history_at = len(blocks)
    blocks.append(Paragraph(f"Validé par {biologist} (biologiste fictif)."))
    if filler_units:
        # Tirés en dernier : le bilan principal reste identique avec ou sans historique.
        history = history_blocks(
            random.Random(rng.getrandbits(64)), person, biologist, day, filler_units
        )
        blocks[history_at:history_at] = history

    return Document(
        doc_type="bilan-biologique",
        title="Compte rendu d'analyses biologiques",
        issuer=facility,
        blocks=tuple(blocks),
        entities={
            "patient_name": person.full_name,
            "birth_date": fmt_date(person.birth_date),
            "patient_id": person.patient_id,
            "sample_id": sample_id,
            "document_date": fmt_date(day),
            "prescriber": prescriber,
            "n_results": str(len(picked)),
            "n_abnormal": str(n_abnormal),
        },
        signer=biologist,
    )

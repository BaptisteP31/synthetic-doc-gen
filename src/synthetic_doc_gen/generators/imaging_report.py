"""Compte rendu d'imagerie fictif : texte structuré et images synthétiques marquées.

Les images sont des fantômes procéduraux (cf. :mod:`synthetic_doc_gen.renderers.imaging`),
jamais des clichés réels. Leurs pixels sont produits au rendu à partir de la graine portée par
chaque :class:`~synthetic_doc_gen.model.Figure`.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

from synthetic_doc_gen.fictional import (
    ADULT_AGE,
    FACILITIES,
    document_date,
    fmt_date,
    make_person,
    make_practitioner,
)
from synthetic_doc_gen.generators.clinical_report import Item, choose
from synthetic_doc_gen.model import Document, Figure, Heading, KeyValues, Paragraph
from synthetic_doc_gen.profiles import Profile


def _items(*entries: str | Item) -> tuple[Item, ...]:
    return tuple(Item(e) if isinstance(e, str) else e for e in entries)


@dataclass(frozen=True)
class Exam:
    name: str
    modality: str
    technique: str
    indications: tuple[Item, ...]
    #: Une ligne de constatations par organe ou structure : (libellé, variantes).
    findings: tuple[tuple[str, tuple[Item, ...]], ...]
    conclusions: tuple[Item, ...]
    captions: tuple[str, ...]
    #: Hauteur / largeur des images imprimées.
    aspect: float = 0.75


EXAMS: dict[str, Exam] = {
    "echographie": Exam(
        "Échographie abdominale",
        "echographie",
        "Sonde convexe 3,5 MHz, patient à jeun, coupes sous-costales et intercostales.",
        _items(
            "douleurs abdominales diffuses sans signe de gravité",
            "bilan de pesanteur de l'hypocondre droit",
            "contrôle d'une perturbation modérée du bilan hépatique",
        ),
        (
            (
                "Foie",
                _items(
                    "de taille normale, d'échostructure homogène",
                    "de contours réguliers, sans lésion focale décelable",
                    "discrètement hyperéchogène, sans lésion focale",
                ),
            ),
            (
                "Vésicule biliaire",
                _items(
                    "alithiasique, à paroi fine",
                    "normalement distendue, sans épaississement pariétal",
                ),
            ),
            (
                "Reins",
                _items(
                    "de taille normale, bien différenciés, sans dilatation des cavités",
                    "symétriques, sans lithiase ni dilatation pyélocalicielle",
                ),
            ),
            (
                "Rate et pancréas",
                _items(
                    "de morphologie normale dans les limites de l'exploration",
                    "sans anomalie visible, pancréas partiellement masqué par l'air digestif",
                ),
            ),
        ),
        _items(
            "échographie abdominale sans anomalie significative",
            "aspect hépatique discrètement hyperéchogène, corrélation clinique et biologique "
            "conseillée",
            "absence de lésion focale ou de dilatation des voies biliaires",
        ),
        (
            "Coupe sous-costale droite",
            "Coupe longitudinale du foie",
            "Vésicule biliaire",
            "Rein droit, coupe longitudinale",
            "Rein gauche, coupe longitudinale",
            "Coupe épigastrique",
        ),
    ),
    "irm": Exam(
        "IRM cérébrale",
        "irm",
        "Antenne tête 1,5 T, séquences T1, T2 et FLAIR axiales, sans injection.",
        _items(
            "céphalées persistantes sans signe neurologique focal",
            "bilan d'étourdissements récurrents",
            "contrôle d'une imagerie antérieure sans anomalie majeure",
        ),
        (
            (
                "Parenchyme cérébral",
                _items(
                    "de signal homogène, sans lésion focale",
                    "sans anomalie de signal significative sur les séquences réalisées",
                ),
            ),
            (
                "Système ventriculaire",
                _items(
                    "de taille normale et de position médiane",
                    "symétrique, sans signe d'hydrocéphalie",
                ),
            ),
            (
                "Structures de la ligne médiane",
                _items(
                    "en place, sans effet de masse",
                    "non déplacées, citernes de la base libres",
                ),
            ),
            (
                "Fosse postérieure",
                _items(
                    "sans anomalie morphologique ni de signal",
                    "de morphologie normale, cervelet et tronc cérébral respectés",
                ),
            ),
        ),
        _items(
            "IRM cérébrale sans anomalie décelable",
            "absence de lésion intracrânienne évolutive sur les séquences réalisées",
            "examen rassurant, sans argument pour une cause structurelle aux symptômes",
        ),
        (
            "Axial T1",
            "Axial T2",
            "Axial FLAIR",
            "Axial T2, niveau ventriculaire",
            "Axial T1, niveau de la fosse postérieure",
            "Axial FLAIR, niveau supérieur",
        ),
    ),
    "radiographie": Exam(
        "Radiographie thoracique",
        "radiographie",
        "Incidences de face debout en inspiration profonde et de profil gauche.",
        _items(
            "toux persistante sans fièvre",
            "bilan d'une gêne respiratoire d'effort",
            "contrôle thoracique avant reprise d'une activité physique",
        ),
        (
            (
                "Champs pulmonaires",
                _items(
                    "bien ventilés, sans foyer de condensation",
                    "d'aspect normal, sans opacité parenchymateuse",
                ),
            ),
            (
                "Médiastin",
                _items(
                    "de largeur normale, sans élargissement",
                    "de morphologie normale, trachée médiane",
                ),
            ),
            (
                "Silhouette cardiaque",
                _items(
                    "de taille normale, rapport cardio-thoracique inférieur à 0,5",
                    "de volume normal, contours nets",
                ),
            ),
            (
                "Cadre osseux et plèvre",
                _items(
                    "sans anomalie visible, culs-de-sac pleuraux libres",
                    "sans fracture décelable, absence d'épanchement pleural",
                ),
            ),
        ),
        _items(
            "radiographie thoracique normale",
            "absence d'anomalie pleuro-pulmonaire décelable",
            "pas d'argument radiologique pour une pathologie aiguë",
        ),
        (
            "Face, inspiration",
            "Profil gauche",
            "Face, centrage médiastinal",
            "Profil gauche, centrage rachidien",
        ),
        aspect=1.0,
    ),
}

DISCUSSION = (
    "Les images ont été relues en double lecture et les constatations ci-dessus sont "
    "concordantes. Les images illustrant ce compte rendu sont entièrement synthétiques.",
    "L'examen a été réalisé dans de bonnes conditions techniques et la qualité des images est "
    "jugée suffisante pour l'interprétation. Aucun incident n'est survenu.",
    "Ces constatations sont à confronter à la clinique. Aucun examen complémentaire n'est "
    "proposé à ce stade, et ce compte rendu est entièrement fictif.",
    "Le dossier d'imagerie a été transmis au médecin demandeur avec le présent compte rendu. "
    "Les consignes de suivi ont été remises au patient.",
)
PRIOR_FINDINGS = (
    "L'aspect est stable par rapport à l'examen précédent, sans élément nouveau.",
    "Aucune modification significative n'est notée entre les deux examens.",
    "Les constatations sont superposables à celles de l'examen de référence.",
)
PRIOR_CONTEXT = (
    "Examen de contrôle réalisé dans les mêmes conditions techniques que l'examen actuel.",
    "Examen de référence relu pour comparaison, images entièrement fictives.",
    "Comparaison faite avec les images archivées sur le poste de lecture fictif.",
)


def prior_exam_notes(
    rng: random.Random, exam: Exam, day: dt.date, radiologist: str, count: int
) -> list:
    """Comptes rendus d'examens antérieurs, du plus récent au plus ancien, tirés à la suite.

    L'élément ``i`` ne dépend pas de ``count`` : ajouter des examens n'altère pas les précédents.
    """
    notes: list = []
    prior_day = day
    for _ in range(count):
        prior_day -= dt.timedelta(days=rng.randint(30, 200))
        organ, variants = rng.choice(exam.findings)
        notes += [
            Heading(f"Examen antérieur du {fmt_date(prior_day)} - {exam.name}", level=2),
            Paragraph(f"{rng.choice(PRIOR_CONTEXT)} {organ} : {rng.choice(variants).text}."),
            Paragraph(f"{rng.choice(PRIOR_FINDINGS)} Relu par {radiologist} (praticien fictif)."),
        ]
    return notes


def generate_imaging_report(
    rng: random.Random, profile: Profile, filler_units: int = 0
) -> Document:
    person = make_person(rng)
    radiologist = make_practitioner(rng)
    requester = make_practitioner(rng)
    day = document_date(rng)
    age = person.age_on(day)
    exam = EXAMS[rng.choice(list(EXAMS))]
    facility = rng.choice([f for f in FACILITIES if "Laboratoire" not in f])
    exam_id = f"SYN-IMG-{rng.randrange(10**8):08d}"

    indication = choose(rng, exam.indications, person, age)
    findings = [(organ, choose(rng, variants, person, age)) for organ, variants in exam.findings]
    conclusion = choose(rng, exam.conclusions, person, age)
    figures = tuple(
        Figure(
            f"Fig. {n} - {caption} (image synthétique)",
            exam.modality,
            rng.getrandbits(48),
            exam.aspect,
        )
        for n, caption in enumerate(exam.captions, 1)
    )
    is_minor = age < ADULT_AGE
    subject = person.patient_ref(age, capitalize=True) if is_minor else person.civility
    n_extra = rng.randint(*profile.report_extra_paragraphs)
    extra = rng.sample(DISCUSSION, min(n_extra, len(DISCUSSION)))

    blocks: list = [
        KeyValues(
            (
                ("Patient", person.full_name),
                ("Date de naissance", f"{fmt_date(person.birth_date)} ({age} ans)"),
                ("Identifiant patient", person.patient_id),
                ("Adresse", person.address),
                ("Téléphone", person.phone),
                ("Examen", exam.name),
                ("Date de l'examen", fmt_date(day)),
                ("Médecin demandeur", requester),
                ("Radiologue", radiologist),
                ("N° d'examen", exam_id),
            )
        ),
        Heading("Indication"),
        Paragraph(
            f"{subject} {person.last_name.upper()}, {age} ans, {person.agree('adressé')} "
            f"par {requester} pour {indication}."
        ),
        Heading("Technique"),
        Paragraph(exam.technique),
        Heading("Images"),
        *figures,
        Heading("Résultats"),
        *(Paragraph(f"{organ} : {text}.") for organ, text in findings),
        Heading("Comparaison"),
        Paragraph("Aucun examen antérieur n'est disponible pour comparaison."),
    ]
    compare_at = len(blocks)
    blocks += [Heading("Conclusion"), Paragraph(f"{conclusion[0].upper()}{conclusion[1:]}.")]
    blocks += [Paragraph(text) for text in extra]
    blocks.append(Paragraph(f"Fait à titre de démonstration, {radiologist} (praticien fictif)."))

    if filler_units:
        # Tirés en dernier : le contenu de base reste identique avec ou sans examens antérieurs.
        notes = prior_exam_notes(
            random.Random(rng.getrandbits(64)), exam, day, radiologist, filler_units
        )
        blocks[compare_at:compare_at] = notes

    return Document(
        doc_type="compte-rendu-imagerie",
        title=f"Compte rendu d'imagerie - {exam.name}",
        issuer=facility,
        blocks=tuple(blocks),
        entities={
            "patient_name": person.full_name,
            "birth_date": fmt_date(person.birth_date),
            "patient_id": person.patient_id,
            "exam_id": exam_id,
            "document_date": fmt_date(day),
            "radiologist": radiologist,
            "requesting_physician": requester,
            "exam": exam.name,
            "modality": exam.modality,
            "n_images": str(len(figures)),
        },
        signer=radiologist,
    )

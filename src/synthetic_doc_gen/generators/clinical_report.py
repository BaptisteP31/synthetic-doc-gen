"""Compte rendu de consultation fictif, à partir de gabarits par spécialité."""

from __future__ import annotations

import random
from dataclasses import dataclass

from synthetic_doc_gen.fictional import (
    FACILITIES,
    SERVICES,
    document_date,
    fmt_date,
    make_person,
    make_practitioner,
)
from synthetic_doc_gen.model import Document, Heading, KeyValues, Paragraph
from synthetic_doc_gen.profiles import Profile


@dataclass(frozen=True)
class Specialty:
    service: str
    motifs: tuple[str, ...]
    antecedents: tuple[str, ...]
    exams: tuple[str, ...]
    conclusions: tuple[str, ...]


SPECIALTIES: dict[str, Specialty] = {
    "Médecine interne": Specialty(
        "Médecine interne",
        (
            "asthénie persistante depuis trois semaines",
            "douleurs articulaires diffuses",
            "fièvre résolutive sans cause retrouvée",
        ),
        ("hypertension artérielle équilibrée", "aucun antécédent notable", "diabète de type 2"),
        (
            "abdomen souple et indolore",
            "absence d'adénopathie palpable",
            "auscultation cardiaque sans souffle",
        ),
        (
            "tableau compatible avec un syndrome viral banal",
            "bilan initial rassurant",
            "absence de signe de gravité",
        ),
    ),
    "Cardiologie": Specialty(
        "Cardiologie",
        ("palpitations à l'effort", "dyspnée d'effort modérée", "contrôle de tension artérielle"),
        ("dyslipidémie traitée", "tabagisme sevré", "aucun antécédent cardiovasculaire"),
        (
            "rythme régulier, sans souffle",
            "pouls périphériques perçus",
            "absence d'œdème des membres inférieurs",
        ),
        (
            "palpitations probablement bénignes",
            "tension artérielle bien contrôlée",
            "surveillance tensionnelle ambulatoire proposée",
        ),
    ),
    "Pneumologie": Specialty(
        "Pneumologie",
        ("toux chronique", "dyspnée nocturne", "bilan d'une gêne respiratoire saisonnière"),
        (
            "asthme allergique de l'enfance",
            "exposition professionnelle aux poussières",
            "aucun antécédent respiratoire",
        ),
        (
            "murmure vésiculaire symétrique",
            "quelques sibilants expiratoires",
            "saturation en air ambiant normale",
        ),
        (
            "asthme probable à confirmer par explorations",
            "bronchite aiguë en voie de résolution",
            "examen pulmonaire normal",
        ),
    ),
    "Endocrinologie": Specialty(
        "Endocrinologie",
        ("suivi de diabète", "prise de poids progressive", "fatigue et frilosité"),
        ("diabète gestationnel ancien", "thyroïdite en antécédent familial", "obésité modérée"),
        (
            "thyroïde non palpable",
            "pas de lésion cutanée des pieds",
            "tour de taille mesuré et consigné",
        ),
        (
            "équilibre glycémique à améliorer",
            "bilan thyroïdien à compléter",
            "mesures hygiéno-diététiques renforcées",
        ),
    ),
    "Gériatrie": Specialty(
        "Gériatrie",
        (
            "chutes à répétition",
            "troubles de mémoire modérés",
            "évaluation gérontologique annuelle",
        ),
        ("arthrose du genou", "ostéoporose traitée", "polymédication surveillée"),
        (
            "marche prudente sans aide technique",
            "test de l'horloge discrètement perturbé",
            "pas d'hypotension orthostatique",
        ),
        (
            "autonomie conservée pour les actes essentiels",
            "adaptation du domicile conseillée",
            "réévaluation cognitive à six mois",
        ),
    ),
}

EXTRA = (
    "L'évolution est favorable depuis la dernière consultation, sans nouvel événement "
    "intercurrent. Le patient décrit une amélioration progressive de la gêne initiale.",
    "Les explications ont été données de manière claire et le patient a pu poser ses questions. "
    "Les consignes de surveillance ont été reprises oralement et remises par écrit.",
    "Les résultats des examens antérieurs, entièrement fictifs, ont été relus en consultation "
    "et ne modifient pas la stratégie de prise en charge retenue.",
    "Aucun effet indésirable n'est rapporté avec le traitement en cours. L'observance est jugée "
    "satisfaisante et la tolérance globale est bonne.",
    "Un point a été fait sur le mode de vie : activité physique régulière, alimentation "
    "équilibrée et limitation des facteurs de risque modifiables.",
    "La coordination avec le médecin traitant est assurée par l'envoi du présent compte rendu. "
    "Un courrier complémentaire sera adressé si les explorations prévues le justifient.",
)


def generate_clinical_report(rng: random.Random, profile: Profile) -> Document:
    person = make_person(rng)
    doctor = make_practitioner(rng)
    spec = SPECIALTIES[rng.choice(SERVICES)]
    facility = rng.choice([f for f in FACILITIES if "Laboratoire" not in f])
    day = document_date(rng)
    age = person.age_on(day)
    visit_id = f"SYN-CONS-{rng.randrange(10**8):08d}"

    motif = rng.choice(spec.motifs)
    antecedent = rng.choice(spec.antecedents)
    vitals = (
        f"Tension artérielle {rng.randrange(105, 160)}/{rng.randrange(60, 98)} mmHg, "
        f"fréquence cardiaque {rng.randrange(52, 105)}/min, "
        f"température {f'{rng.randrange(364, 378) / 10:.1f}'.replace('.', ',')} °C, "
        f"poids {rng.randrange(48, 105)} kg."
    )

    blocks: list = [
        KeyValues(
            (
                ("Patient", person.full_name),
                ("Date de naissance", f"{fmt_date(person.birth_date)} ({age} ans)"),
                ("Identifiant patient", person.patient_id),
                ("Adresse", person.address),
                ("Téléphone", person.phone),
                ("Service", spec.service),
                ("Date de consultation", fmt_date(day)),
                ("Praticien", doctor),
                ("N° de consultation", visit_id),
            )
        ),
        Heading("Motif de consultation"),
        Paragraph(
            f"{person.civility} {person.last_name.upper()}, {age} ans, est "
            f"reçu{'e' if person.sex == 'F' else ''} en consultation de "
            f"{spec.service.lower()} pour {motif}."
        ),
        Heading("Antécédents"),
        Paragraph(f"{antecedent.capitalize()}. Aucune allergie médicamenteuse connue."),
        Heading("Examen clinique"),
        Paragraph(f"{vitals} {rng.choice(spec.exams).capitalize()}."),
        Heading("Évolution et discussion"),
    ]
    n_extra = rng.randint(*profile.report_extra_paragraphs)
    extra = rng.sample(EXTRA, min(n_extra, len(EXTRA)))
    for text in extra:
        blocks.append(Paragraph(text))
    blocks += [
        Heading("Conclusion"),
        Paragraph(f"{rng.choice(spec.conclusions).capitalize()}."),
        Heading("Conduite à tenir"),
        Paragraph(
            f"Poursuite du traitement par Placebomol {rng.choice((250, 500, 1000))} mg "
            f"(médicament fictif). Contrôle clinique dans {rng.choice((1, 3, 6))} mois."
        ),
        Paragraph(f"Fait à titre de démonstration, {doctor} (praticien fictif)."),
    ]

    return Document(
        doc_type="compte-rendu",
        title=f"Compte rendu de consultation - {spec.service}",
        issuer=facility,
        blocks=tuple(blocks),
        entities={
            "patient_name": person.full_name,
            "birth_date": fmt_date(person.birth_date),
            "patient_id": person.patient_id,
            "visit_id": visit_id,
            "document_date": fmt_date(day),
            "practitioner": doctor,
            "service": spec.service,
        },
    )

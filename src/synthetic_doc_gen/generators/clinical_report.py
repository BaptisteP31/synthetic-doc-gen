"""Compte rendu de consultation fictif, à partir de gabarits par spécialité."""

from __future__ import annotations

import random
from dataclasses import dataclass

from synthetic_doc_gen.fictional import (
    ADULT_AGE,
    FACILITIES,
    GERIATRIC_AGE,
    SERVICES,
    Person,
    document_date,
    fmt_date,
    make_person,
    make_practitioner,
)
from synthetic_doc_gen.model import Document, Heading, KeyValues, Paragraph
from synthetic_doc_gen.profiles import Profile


@dataclass(frozen=True)
class Item:
    """Élément de gabarit, avec ses conditions d'applicabilité au patient."""

    text: str
    min_age: int = 0
    max_age: int = 150
    sex: str | None = None  # "F", "M" ou None (indifférent)

    def fits(self, person: Person, age: int) -> bool:
        return self.min_age <= age <= self.max_age and self.sex in (None, person.sex)


def _items(*entries: str | Item) -> tuple[Item, ...]:
    return tuple(Item(e) if isinstance(e, str) else e for e in entries)


@dataclass(frozen=True)
class Specialty:
    service: str
    motifs: tuple[Item, ...]
    antecedents: tuple[Item, ...]
    exams: tuple[Item, ...]
    conclusions: tuple[Item, ...]
    #: Âge minimal pour que la spécialité soit vraisemblable (ex. gériatrie : 65 ans).
    min_age: int = 0


SPECIALTIES: dict[str, Specialty] = {
    "Médecine interne": Specialty(
        "Médecine interne",
        _items(
            "asthénie persistante depuis trois semaines",
            "douleurs articulaires diffuses",
            "fièvre résolutive sans cause retrouvée",
        ),
        _items(
            Item("hypertension artérielle équilibrée", min_age=ADULT_AGE),
            "aucun antécédent notable",
            Item("diabète de type 2", min_age=ADULT_AGE),
        ),
        _items(
            "abdomen souple et indolore",
            "absence d'adénopathie palpable",
            "auscultation cardiaque sans souffle",
        ),
        _items(
            "tableau compatible avec un syndrome viral banal",
            "bilan initial rassurant",
            "absence de signe de gravité",
        ),
    ),
    "Cardiologie": Specialty(
        "Cardiologie",
        _items(
            "palpitations à l'effort",
            "dyspnée d'effort modérée",
            Item("contrôle de tension artérielle", min_age=ADULT_AGE),
        ),
        _items(
            Item("dyslipidémie traitée", min_age=ADULT_AGE),
            Item("tabagisme sevré", min_age=ADULT_AGE),
            "aucun antécédent cardiovasculaire",
        ),
        _items(
            "rythme régulier, sans souffle",
            "pouls périphériques perçus",
            "absence d'œdème des membres inférieurs",
        ),
        _items(
            "palpitations probablement bénignes",
            "tension artérielle bien contrôlée",
            "surveillance tensionnelle ambulatoire proposée",
        ),
    ),
    "Pneumologie": Specialty(
        "Pneumologie",
        _items("toux chronique", "dyspnée nocturne", "bilan d'une gêne respiratoire saisonnière"),
        _items(
            "asthme allergique de l'enfance",
            Item("exposition professionnelle aux poussières", min_age=ADULT_AGE),
            "aucun antécédent respiratoire",
        ),
        _items(
            "murmure vésiculaire symétrique",
            "quelques sibilants expiratoires",
            "saturation en air ambiant normale",
        ),
        _items(
            "asthme probable à confirmer par explorations",
            "bronchite aiguë en voie de résolution",
            "examen pulmonaire normal",
        ),
    ),
    "Endocrinologie": Specialty(
        "Endocrinologie",
        _items("suivi de diabète", "prise de poids progressive", "fatigue et frilosité"),
        _items(
            Item("diabète gestationnel ancien", min_age=ADULT_AGE, sex="F"),
            "thyroïdite en antécédent familial",
            "obésité modérée",
        ),
        _items(
            "thyroïde non palpable",
            "pas de lésion cutanée des pieds",
            "tour de taille mesuré et consigné",
        ),
        _items(
            "équilibre glycémique à améliorer",
            "bilan thyroïdien à compléter",
            "mesures hygiéno-diététiques renforcées",
        ),
    ),
    "Gériatrie": Specialty(
        "Gériatrie",
        _items(
            "chutes à répétition",
            "troubles de mémoire modérés",
            "évaluation gérontologique annuelle",
        ),
        _items("arthrose du genou", "ostéoporose traitée", "polymédication surveillée"),
        _items(
            "marche prudente sans aide technique",
            "test de l'horloge discrètement perturbé",
            "pas d'hypotension orthostatique",
        ),
        _items(
            "autonomie conservée pour les actes essentiels",
            "adaptation du domicile conseillée",
            "réévaluation cognitive à six mois",
        ),
        min_age=GERIATRIC_AGE,
    ),
}

# Gabarits de texte : {Patient} / {patient} s'accordent avec le sexe et l'âge (cf. Person).
EXTRA = (
    "L'évolution est favorable depuis la dernière consultation, sans nouvel événement "
    "intercurrent. {Patient} décrit une amélioration progressive de la gêne initiale.",
    "Les explications ont été données de manière claire et {patient} a pu poser ses "
    "questions. Les consignes de surveillance ont été reprises oralement et remises par écrit.",
    "Les résultats des examens antérieurs, entièrement fictifs, ont été relus en consultation "
    "et ne modifient pas la stratégie de prise en charge retenue.",
    "Aucun effet indésirable n'est rapporté avec le traitement en cours. L'observance est jugée "
    "satisfaisante et la tolérance globale est bonne.",
    "Un point a été fait sur le mode de vie : activité physique régulière, alimentation "
    "équilibrée et limitation des facteurs de risque modifiables.",
    "La coordination avec le médecin traitant est assurée par l'envoi du présent compte rendu. "
    "Un courrier complémentaire sera adressé si les explorations prévues le justifient.",
)


def eligible_services(age: int) -> list[str]:
    """Services dont l'âge minimal est compatible avec celui du patient."""
    return [s for s in SERVICES if SPECIALTIES[s].min_age <= age]


def choose(rng: random.Random, items: tuple[Item, ...], person: Person, age: int) -> str:
    """Tire un élément applicable au patient ; ``ValueError`` si aucun ne l'est."""
    fitting = [i for i in items if i.fits(person, age)]
    if not fitting:
        raise ValueError("aucun élément de gabarit applicable à ce patient")
    return rng.choice(fitting).text


def vitals_text(rng: random.Random, age: int) -> str:
    """Constantes vraisemblables pour l'âge (plages pédiatriques pour un mineur)."""
    if age < ADULT_AGE:
        systolic, diastolic = rng.randrange(95, 130), rng.randrange(55, 80)
        heart_rate, weight = rng.randrange(65, 105), rng.randrange(30, 75)
    else:
        systolic, diastolic = rng.randrange(105, 160), rng.randrange(60, 98)
        heart_rate, weight = rng.randrange(52, 105), rng.randrange(48, 105)
    temperature = f"{rng.randrange(364, 378) / 10:.1f}".replace(".", ",")
    return (
        f"Tension artérielle {systolic}/{diastolic} mmHg, fréquence cardiaque {heart_rate}/min, "
        f"température {temperature} °C, poids {weight} kg."
    )


def generate_clinical_report(rng: random.Random, profile: Profile) -> Document:
    person = make_person(rng)
    doctor = make_practitioner(rng)
    day = document_date(rng)
    age = person.age_on(day)
    spec = SPECIALTIES[rng.choice(eligible_services(age))]
    facility = rng.choice([f for f in FACILITIES if "Laboratoire" not in f])
    visit_id = f"SYN-CONS-{rng.randrange(10**8):08d}"

    motif = choose(rng, spec.motifs, person, age)
    antecedent = choose(rng, spec.antecedents, person, age)
    vitals = vitals_text(rng, age)
    exam = choose(rng, spec.exams, person, age)
    conclusion = "évaluation clinique à poursuivre selon le motif de consultation"
    is_minor = age < ADULT_AGE
    subject = person.patient_ref(age, capitalize=True) if is_minor else person.civility
    escort = " Un parent l'accompagne." if is_minor else ""

    service_prefix = "d'" if spec.service == "Endocrinologie" else "de "

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
            f"{subject} {person.last_name.upper()}, {age} ans, est "
            f"{person.agree('reçu')} en consultation {service_prefix}"
            f"{spec.service.lower()} pour {motif}.{escort}"
        ),
        Heading("Antécédents"),
        Paragraph(f"{antecedent.capitalize()}. Aucune allergie médicamenteuse connue."),
        Heading("Examen clinique"),
        Paragraph(f"{vitals} {exam.capitalize()}."),
        Heading("Évolution et discussion"),
    ]
    doses = (125, 250, 500) if is_minor else (250, 500, 1000)
    n_extra = rng.randint(*profile.report_extra_paragraphs)
    extra = rng.sample(EXTRA, min(n_extra, len(EXTRA)))
    fmt = {
        "Patient": person.patient_ref(age, capitalize=True),
        "patient": person.patient_ref(age),
    }
    for text in extra:
        blocks.append(Paragraph(text.format(**fmt)))
    blocks += [
        Heading("Conclusion"),
        Paragraph(f"{conclusion.capitalize()}."),
        Heading("Conduite à tenir"),
        Paragraph(
            f"Poursuite du traitement par Placebomol {rng.choice(doses)} mg "
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

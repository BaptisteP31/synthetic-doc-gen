"""Données entièrement fictives : personnes, praticiens, établissements.

Aucune donnée réelle n'est utilisée. Les téléphones sont dans les plages réservées à la
fiction (01 99 00 xx xx), les codes postaux en 99xxx (inexistants) et les identifiants
préfixés ``SYN-``. Une homonymie fortuite avec une personne réelle reste possible.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

FIRST_NAMES_F = (
    "Aurélie",
    "Camille",
    "Dorothée",
    "Élodie",
    "Fanny",
    "Gwenaëlle",
    "Hélène",
    "Inès",
    "Jeanne",
    "Louise",
    "Maëlle",
    "Noémie",
    "Océane",
    "Prune",
    "Solène",
)
FIRST_NAMES_M = (
    "Adrien",
    "Baptiste",
    "Cédric",
    "Damien",
    "Étienne",
    "Florian",
    "Gaspard",
    "Hugo",
    "Isidore",
    "Julien",
    "Lucien",
    "Mathis",
    "Nolan",
    "Octave",
    "Quentin",
)
SURNAME_PREFIXES = (
    "Val",
    "Mont",
    "Bel",
    "Cor",
    "Dur",
    "Fer",
    "Gal",
    "Lor",
    "Mar",
    "Ner",
    "Pel",
    "Rav",
    "Sar",
    "Tor",
    "Vil",
)
SURNAME_SUFFIXES = (
    "morin",
    "chard",
    "vier",
    "lenc",
    "bert",
    "tin",
    "ssier",
    "dal",
    "mont",
    "rieux",
    "gnac",
    "pan",
    "veau",
    "zet",
    "lard",
)
STREETS = (
    "rue des Tilleuls",
    "avenue du Test",
    "impasse des Fictifs",
    "place de l'Exemple",
    "chemin des Mirabelliers",
    "boulevard Imaginaire",
    "allée des Peupliers",
)
CITIES = (
    "Valmorin",
    "Saint-Exemple",
    "Bellefiction",
    "Montéchantillon",
    "Port-Synthèse",
    "Lorvaux-sur-Test",
)
FACILITIES = (
    "Centre Hospitalier Fictif de Valmorin",
    "Clinique Imaginaire des Tilleuls",
    "Laboratoire d'Analyses Fictif Bellefiction",
    "Institut Synthétique de Port-Synthèse",
    "Hôpital Exemple de Lorvaux",
)
SERVICES = ("Médecine interne", "Cardiologie", "Pneumologie", "Endocrinologie", "Gériatrie")


@dataclass(frozen=True)
class Person:
    first_name: str
    last_name: str
    sex: str  # "F" ou "M"
    birth_date: dt.date
    patient_id: str
    address: str
    phone: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name.upper()}"

    @property
    def civility(self) -> str:
        return "Madame" if self.sex == "F" else "Monsieur"

    def age_on(self, day: dt.date) -> int:
        years = day.year - self.birth_date.year
        if (day.month, day.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years


def random_date(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    return start + dt.timedelta(days=rng.randrange((end - start).days + 1))


def fmt_date(day: dt.date) -> str:
    return day.strftime("%d/%m/%Y")


def fictional_phone(rng: random.Random) -> str:
    return f"01 99 00 {rng.randrange(100):02d} {rng.randrange(100):02d}"


def make_person(rng: random.Random) -> Person:
    sex = rng.choice("FM")
    first = rng.choice(FIRST_NAMES_F if sex == "F" else FIRST_NAMES_M)
    last = rng.choice(SURNAME_PREFIXES) + rng.choice(SURNAME_SUFFIXES)
    return Person(
        first_name=first,
        last_name=last,
        sex=sex,
        birth_date=random_date(rng, dt.date(1938, 1, 1), dt.date(2012, 12, 31)),
        patient_id=f"SYN-PAT-{rng.randrange(10**7):07d}",
        address=f"{rng.randrange(1, 120)} {rng.choice(STREETS)}, 99{rng.randrange(1000):03d} "
        f"{rng.choice(CITIES)}",
        phone=fictional_phone(rng),
    )


def make_practitioner(rng: random.Random) -> str:
    first = rng.choice(FIRST_NAMES_F + FIRST_NAMES_M)
    last = rng.choice(SURNAME_PREFIXES) + rng.choice(SURNAME_SUFFIXES)
    return f"Dr {first} {last.upper()}"


def document_date(rng: random.Random) -> dt.date:
    """Date de document fictive, fixe (indépendante de la date du jour) pour le déterminisme."""
    return random_date(rng, dt.date(2024, 1, 1), dt.date(2026, 6, 30))

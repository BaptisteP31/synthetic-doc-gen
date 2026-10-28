"""Registre des types de documents. Ajouter un type = un module + une entrée ici."""

from __future__ import annotations

from collections.abc import Callable

from synthetic_doc_gen.generators.clinical_report import generate_clinical_report
from synthetic_doc_gen.generators.imaging_report import generate_imaging_report
from synthetic_doc_gen.generators.lab_report import generate_lab_report
from synthetic_doc_gen.model import Document

#: ``filler_units`` : unités de contenu complémentaires (notes, historique) pour allonger le
#: document sans modifier son contenu de base.
Generator = Callable[..., Document]

GENERATORS: dict[str, Generator] = {
    "compte-rendu": generate_clinical_report,
    "bilan-biologique": generate_lab_report,
    "compte-rendu-imagerie": generate_imaging_report,
}

#: Types utilisés sans ``--types`` : le compte rendu d'imagerie, plus lourd (images), se demande.
DEFAULT_DOC_TYPES: tuple[str, ...] = ("compte-rendu", "bilan-biologique")

#: Types dont le PDF natif contient des images : leur poids se règle par les images.
IMAGE_DOC_TYPES: frozenset[str] = frozenset({"compte-rendu-imagerie"})

DOC_TYPE_DESCRIPTIONS: dict[str, str] = {
    "compte-rendu": "Compte rendu de consultation médicale",
    "bilan-biologique": "Bilan biologique (NFS, biochimie, inflammation)",
    "compte-rendu-imagerie": "Compte rendu d'imagerie avec images synthétiques (~500 ko)",
}


def get_generator(doc_type: str) -> Generator:
    try:
        return GENERATORS[doc_type]
    except KeyError:
        raise ValueError(
            f"type de document inconnu : {doc_type!r} (disponibles : {', '.join(GENERATORS)})"
        ) from None

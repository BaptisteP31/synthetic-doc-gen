"""Registre des types de documents. Ajouter un type = un module + une entrée ici."""

from __future__ import annotations

from collections.abc import Callable

from synthetic_doc_gen.generators.clinical_report import generate_clinical_report
from synthetic_doc_gen.generators.lab_report import generate_lab_report
from synthetic_doc_gen.model import Document

#: ``filler_units`` : unités de contenu complémentaires (notes, historique) pour allonger le
#: document sans modifier son contenu de base.
Generator = Callable[..., Document]

GENERATORS: dict[str, Generator] = {
    "compte-rendu": generate_clinical_report,
    "bilan-biologique": generate_lab_report,
}

DOC_TYPE_DESCRIPTIONS: dict[str, str] = {
    "compte-rendu": "Compte rendu de consultation médicale",
    "bilan-biologique": "Bilan biologique (NFS, biochimie, inflammation)",
}


def get_generator(doc_type: str) -> Generator:
    try:
        return GENERATORS[doc_type]
    except KeyError:
        raise ValueError(
            f"type de document inconnu : {doc_type!r} (disponibles : {', '.join(GENERATORS)})"
        ) from None

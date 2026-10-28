"""Modèle de document neutre vis-à-vis du média (PDF aujourd'hui, autres plus tard).

Les générateurs produisent un :class:`Document` ; les moteurs de rendu
(:mod:`synthetic_doc_gen.renderers`) le transforment en fichier.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Heading:
    text: str
    level: int = 1


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class KeyValues:
    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    #: Largeurs relatives des colonnes (même longueur que ``header``), ou None.
    col_weights: tuple[float, ...] | None = None
    #: Indices des lignes à mettre en évidence (ex. résultats hors normes).
    emphasized_rows: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Figure:
    """Image synthétique légendée ; ses pixels se déduisent de ``modality`` et ``seed``."""

    caption: str
    #: Modalité simulée (« echographie », « irm », « radiographie »).
    modality: str
    seed: int
    #: Hauteur / largeur de l'image imprimée.
    aspect: float = 0.75


Block = Heading | Paragraph | KeyValues | Table | Figure


@dataclass(frozen=True)
class Document:
    doc_type: str
    title: str
    #: Établissement fictif affiché en en-tête.
    issuer: str
    blocks: tuple[Block, ...]
    #: Vérité terrain fictive (nom, identifiants...), reprise dans le manifeste.
    entities: dict[str, str] = field(default_factory=dict)
    #: Praticien fictif qui « signe » le document (signature optionnelle au rendu).
    signer: str = ""

    @property
    def figures(self) -> tuple[Figure, ...]:
        return tuple(block for block in self.blocks if isinstance(block, Figure))

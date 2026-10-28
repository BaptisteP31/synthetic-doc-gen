"""Registre des moteurs de rendu, un par média. Ajouter un média = un module + une entrée."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from synthetic_doc_gen.model import Document
from synthetic_doc_gen.profiles import Profile


@dataclass(frozen=True)
class Rendered:
    data: bytes
    #: Nombre de pages, si le média en a.
    pages: int | None = None


class Renderer(Protocol):
    name: str  # nom du moteur, ex. "reportlab"
    extension: str  # sans point, ex. "pdf"

    def version(self) -> str: ...

    def render(self, document: Document, profile: Profile, doc_id: str) -> Rendered: ...


def _registry() -> dict[str, Renderer]:
    from synthetic_doc_gen.renderers.pdf import ReportLabPdfRenderer

    return {"pdf": ReportLabPdfRenderer()}


RENDERERS: dict[str, Renderer] = _registry()


def get_renderer(medium: str) -> Renderer:
    try:
        return RENDERERS[medium]
    except KeyError:
        raise ValueError(
            f"média inconnu : {medium!r} (disponibles : {', '.join(RENDERERS)})"
        ) from None

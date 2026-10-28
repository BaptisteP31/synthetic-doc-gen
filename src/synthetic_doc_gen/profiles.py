"""Profils de rendu/contenu simples, sélectionnables par nom."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    page_size: str = "A4"  # "A4" ou "LETTER"
    font_size: float = 10.0
    margin_mm: float = 18.0
    table_style: str = "zebra"  # "zebra", "grid" ou "plain"
    accent_color: str = "#1f4e79"
    #: Nombre de lignes d'analyses d'un bilan biologique (min, max inclus).
    lab_rows: tuple[int, int] = (10, 16)
    #: Paragraphes d'évolution ajoutés à un compte rendu (min, max inclus).
    report_extra_paragraphs: tuple[int, int] = (1, 2)


PROFILES: dict[str, Profile] = {
    p.name: p
    for p in (
        Profile("standard", "A4, corps 10 pt, tableaux zébrés, longueur moyenne."),
        Profile(
            "compact",
            "A4 dense : corps 8,5 pt, marges réduites, documents plus longs.",
            font_size=8.5,
            margin_mm=12.0,
            table_style="grid",
            lab_rows=(16, 22),
            report_extra_paragraphs=(3, 5),
        ),
        Profile(
            "large-print",
            "A4 gros caractères : corps 13 pt, documents courts.",
            font_size=13.0,
            margin_mm=22.0,
            lab_rows=(6, 9),
            report_extra_paragraphs=(0, 1),
        ),
        Profile(
            "plain-letter",
            "US Letter, sobre : tableaux sans fond, accent noir.",
            page_size="LETTER",
            table_style="plain",
            accent_color="#222222",
        ),
    )
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(
            f"profil inconnu : {name!r} (disponibles : {', '.join(PROFILES)})"
        ) from None

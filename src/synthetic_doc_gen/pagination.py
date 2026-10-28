"""Ajustement du nombre de pages : ajoute du contenu complémentaire réel, jamais du remplissage."""

from __future__ import annotations

from collections.abc import Callable

from synthetic_doc_gen.model import Document

#: Plage de pages acceptée à l'appel (au-delà, le rendu de test devient peu réaliste).
MAX_PAGES = 50
#: Unités de contenu complémentaire autorisées par page demandée avant d'abandonner.
MAX_UNITS_PER_PAGE = 40


def fit_pages(
    build: Callable[[int], Document], count_pages: Callable[[Document], int], target: int
) -> tuple[Document, int]:
    """Plus petit nombre d'unités de contenu qui donne exactement ``target`` pages.

    ``build(k)`` rend le document avec ``k`` unités complémentaires (préfixe stable : les
    ``k`` premières unités ne changent pas quand ``k`` augmente) ; ``count_pages`` mesure le
    rendu réel. Retourne (document, k). ``ValueError`` si la cible est inatteignable.
    """
    cache: dict[int, tuple[Document, int]] = {}

    def measure(units: int) -> int:
        if units not in cache:
            document = build(units)
            cache[units] = (document, count_pages(document))
        return cache[units][1]

    if measure(0) > target:
        raise ValueError(
            f"le contenu de base compte déjà {measure(0)} pages, plus que les {target} demandées"
        )
    if measure(0) == target:
        return cache[0][0], 0
    limit = target * MAX_UNITS_PER_PAGE
    low, high = 0, 1
    while measure(high) < target:
        low, high = high, high * 2
        if high > limit:
            raise ValueError(f"impossible d'atteindre {target} pages")
    while high - low > 1:
        middle = (low + high) // 2
        if measure(middle) < target:
            low = middle
        else:
            high = middle
    if measure(high) != target:  # pas de plus d'une page par unité : ne devrait pas arriver
        raise ValueError(f"impossible d'obtenir exactement {target} pages")
    return cache[high][0], high

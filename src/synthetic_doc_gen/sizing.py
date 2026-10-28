"""Réglage des scans pour approcher une taille moyenne cible, sans remplissage artificiel.

Seules deux vraies causes de poids sont mobilisées : la résolution (dpi) et la qualité JPEG
des scans, dans des plages de numérisation courantes (``options.TUNING_*``). Les réglages
imposés à l'appel ne sont jamais modifiés. Les PDF natifs ne se règlent pas (leur poids vient
du contenu et du nombre de pages) : leur contribution est mesurée sur un échantillon et
déduite de la cible. L'ajustement s'appuie sur un échantillon de pages réellement rendues ;
la moyenne effective est mesurée ensuite sur le lot entier (rapport).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol, TypeVar

from synthetic_doc_gen.options import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_SCAN_DPI,
    TUNING_DPI,
    TUNING_QUALITY,
    ScanSettings,
)
from synthetic_doc_gen.renderers import Rendered, scan

SAMPLE_NATIVES = 8
SAMPLE_SCANS = 6
SAMPLE_PAGES = 10
#: Écart relatif toléré à l'estimation ; la recherche s'arrête dès qu'il est atteint.
SEARCH_TOLERANCE = 0.03
MAX_STEPS = 9

T = TypeVar("T")


class Planned(Protocol):
    scan: bool


@dataclass(frozen=True)
class Calibration:
    settings: ScanSettings
    #: Réglages ajustés automatiquement (``dpi``, ``jpeg_quality``).
    tuned: tuple[str, ...] = ()
    #: Taille moyenne estimée d'un document scanné après réglage, ou ``None``.
    estimated_scan_bytes: float | None = None
    #: Contribution moyenne estimée des PDF natifs, ou ``None``.
    estimated_native_bytes: float | None = None
    warnings: tuple[str, ...] = ()


def spread(items: Sequence[T], count: int) -> list[T]:
    """``count`` éléments régulièrement répartis (tous si moins nombreux)."""
    if len(items) <= count:
        return list(items)
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def _search(
    low: int, high: int, evaluate: Callable[[int], float], needed: float
) -> tuple[int, float, str]:
    """Valeur entière de ``[low, high]`` dont ``evaluate`` (croissante) approche ``needed``.

    Retourne (valeur, taille estimée, état) ; état : ``ok``, ``below`` (même ``high`` reste
    trop léger) ou ``above`` (même ``low`` reste trop lourd).
    """
    best: tuple[float, int, float] | None = None

    def probe(value: int) -> float:
        nonlocal best
        size = evaluate(value)
        error = abs(size - needed) / needed
        if best is None or error < best[0]:
            best = (error, value, size)
        return size

    if probe(high) < needed:
        status = "ok" if best and best[0] <= SEARCH_TOLERANCE else "below"
        return high, best[2] if best else 0.0, status
    if probe(low) > needed:
        status = "ok" if best and best[0] <= SEARCH_TOLERANCE else "above"
        return low, best[2] if best else 0.0, status
    steps = 0
    while high - low > 1 and steps < MAX_STEPS and best and best[0] > SEARCH_TOLERANCE:
        middle = (low + high) // 2
        if probe(middle) < needed:
            low = middle
        else:
            high = middle
        steps += 1
    assert best is not None
    return best[1], best[2], "ok"


def calibrate(
    plan: Sequence[Planned],
    *,
    target_mean_bytes: int,
    color: str,
    dpi: int | None,
    quality: int | None,
    render_native: Callable[[Planned], Rendered],
    population_counts: tuple[int, int] | None = None,
) -> Calibration:
    """Choisit dpi et qualité JPEG des scans pour approcher la moyenne cible du lot."""
    scans = [item for item in plan if item.scan]
    natives = [item for item in plan if not item.scan]
    base = ScanSettings(
        dpi=DEFAULT_SCAN_DPI if dpi is None else dpi,
        color=color,
        jpeg_quality=DEFAULT_JPEG_QUALITY if quality is None else quality,
    )
    if not scans:
        return Calibration(
            base,
            warnings=(
                "aucun scan dans le lot : la taille ne se règle ni par dpi ni par qualité ; "
                "elle dépend du contenu et du nombre de pages des PDF natifs",
            ),
        )

    native_mean = 0.0
    if natives:
        sizes = [len(render_native(item).data) for item in spread(natives, SAMPLE_NATIVES)]
        native_mean = sum(sizes) / len(sizes)
    scan_count, native_count = population_counts or (len(scans), len(natives))
    needed = (
        target_mean_bytes * (scan_count + native_count) - native_mean * native_count
    ) / scan_count
    warnings: list[str] = []
    if needed <= 0:
        warnings.append(
            "les PDF natifs dépassent à eux seuls la taille moyenne cible ; scans réglés au "
            "plus léger"
        )
        needed = 1.0

    sample_indices = set(spread(range(len(scans)), SAMPLE_SCANS))
    sample = []
    total_pages = 0
    for index, item in enumerate(scans):
        rendered = render_native(item)
        count = rendered.pages if rendered.pages is not None else scan.page_count(rendered.data)
        total_pages += count
        if index in sample_indices:
            sample.append((rendered, count))
    pool = [(doc, page) for doc, (_, count) in enumerate(sample) for page in range(count)]
    pool = spread(pool, SAMPLE_PAGES)
    pages_per_scan = total_pages / len(scans)

    def estimate(settings: ScanSettings) -> float:
        sizes: list[int] = []
        for doc in sorted({d for d, _ in pool}):
            pages = [p for d, p in pool if d == doc]
            for width, height, raster in scan.iter_rasters(
                sample[doc][0].data, settings.dpi, pages
            ):
                sizes.append(scan.encoded_size(scan.encode_page(width, height, raster, settings)))
        return sum(sizes) / len(sizes) * pages_per_scan + 2000

    free_dpi = dpi is None
    free_quality = quality is None and color != "bw"
    settings, size, status = base, None, "ok"
    tuned: list[str] = []
    if free_dpi:
        value, size, status = _search(
            TUNING_DPI[0],
            TUNING_DPI[1],
            lambda v: estimate(replace(base, dpi=v)),
            needed,
        )
        settings = replace(base, dpi=value)
        tuned.append("dpi")
    if free_quality and (not free_dpi or status != "ok"):
        # Qualité : seul levier, ou levier de secours une fois la résolution en butée.
        if not free_dpi or status == "below":
            low, high = (base.jpeg_quality if free_dpi else TUNING_QUALITY[0]), TUNING_QUALITY[1]
        else:
            low, high = TUNING_QUALITY[0], base.jpeg_quality
        value, size, status = _search(
            low, high, lambda v: estimate(replace(settings, jpeg_quality=v)), needed
        )
        settings = replace(settings, jpeg_quality=value)
        tuned.append("jpeg_quality")
    if not tuned:
        size = estimate(settings)
        warnings.append(
            "dpi imposé : la taille cible n'est pas ajustée (mesure seule)"
            if color == "bw"
            else "dpi et qualité JPEG imposés : la taille cible n'est pas ajustée (mesure seule)"
        )
    elif status != "ok":
        if color == "bw":
            warnings.append(
                f"taille cible hors de portée des réglages réalistes (dpi {TUNING_DPI[0]}-"
                f"{TUNING_DPI[1]}) : scans réglés à {settings.dpi} dpi"
            )
        else:
            warnings.append(
                f"taille cible hors de portée des réglages réalistes (dpi {TUNING_DPI[0]}-"
                f"{TUNING_DPI[1]}, qualité JPEG {TUNING_QUALITY[0]}-{TUNING_QUALITY[1]}) : scans "
                f"réglés à {settings.dpi} dpi, qualité {settings.jpeg_quality}"
            )
    return Calibration(
        settings,
        tuple(tuned),
        estimated_scan_bytes=size,
        estimated_native_bytes=native_mean if natives else None,
        warnings=tuple(warnings),
    )

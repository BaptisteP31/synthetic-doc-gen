"""Réglage des scans et des images pour approcher une taille moyenne cible, sans remplissage.

Seules deux vraies causes de poids sont mobilisées : la résolution (dpi) et la qualité JPEG,
dans des plages courantes (``options.TUNING_*``), pour les scans et pour les images
synthétiques des PDF natifs qui en contiennent. Les réglages imposés à l'appel ne sont jamais
modifiés. Les autres PDF natifs ne se règlent pas (leur poids vient du contenu et du nombre de
pages) : leur contribution est mesurée sur un échantillon et déduite de la cible. Les images
sont réglées d'abord, vers la taille par fichier qui donnerait la moyenne cible ; les scans
absorbent ensuite l'écart restant. L'ajustement s'appuie sur un échantillon réellement rendu ;
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
    ImageSettings,
    ScanSettings,
)
from synthetic_doc_gen.renderers import Rendered, scan

SAMPLE_NATIVES = 8
SAMPLE_IMAGE_DOCS = 4
SAMPLE_SCANS = 6
SAMPLE_PAGES = 10
#: Écart relatif toléré à l'estimation ; la recherche s'arrête dès qu'il est atteint.
SEARCH_TOLERANCE = 0.03
MAX_STEPS = 9

T = TypeVar("T")


class Planned(Protocol):
    scan: bool


@dataclass(frozen=True)
class ImageTuning:
    """Documents natifs à images : ce qu'il faut savoir d'eux pour régler leurs images."""

    #: Réglages imposés, ou de départ pour ceux qui ne le sont pas.
    base: ImageSettings
    free_dpi: bool
    free_quality: bool
    has_images: Callable[[Planned], bool]
    #: Octets des flux image d'un document à des réglages donnés.
    stream_bytes: Callable[[Planned, ImageSettings], int]
    #: Rendu natif d'un document à des réglages d'image donnés.
    render: Callable[[Planned, ImageSettings], Rendered]
    #: Nombre de natifs à images dans toute la population, si différent de l'échantillon.
    native_count: int | None = None


@dataclass(frozen=True)
class Calibration:
    settings: ScanSettings
    #: Réglages ajustés automatiquement (``dpi``, ``jpeg_quality``, et ``image_`` + nom).
    tuned: tuple[str, ...] = ()
    #: Taille moyenne estimée d'un document scanné après réglage, ou ``None``.
    estimated_scan_bytes: float | None = None
    #: Contribution moyenne estimée des PDF natifs sans image, ou ``None``.
    estimated_native_bytes: float | None = None
    #: Réglages retenus des images synthétiques, ou ``None`` sans natif à images.
    image_settings: ImageSettings | None = None
    #: Taille moyenne estimée d'un natif à images après réglage, ou ``None``.
    estimated_image_bytes: float | None = None
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


def _tune(
    base: T,
    free_dpi: bool,
    free_quality: bool,
    needed: float,
    estimate: Callable[[T], float],
) -> tuple[T, float | None, str, list[str]]:
    """Règle dpi puis, en butée, qualité JPEG de ``base`` ; retourne (réglages, taille, état, noms).

    La résolution est le premier levier ; la qualité sert seule, ou de secours une fois la
    résolution en butée. ``estimate`` croît avec les deux.
    """
    settings, size, status = base, None, "ok"
    tuned: list[str] = []
    if free_dpi:
        value, size, status = _search(
            TUNING_DPI[0], TUNING_DPI[1], lambda v: estimate(replace(base, dpi=v)), needed
        )
        settings = replace(base, dpi=value)
        tuned.append("dpi")
    if free_quality and (not free_dpi or status != "ok"):
        if not free_dpi or status == "below":
            low, high = (base.jpeg_quality if free_dpi else TUNING_QUALITY[0]), TUNING_QUALITY[1]
        else:
            low, high = TUNING_QUALITY[0], base.jpeg_quality
        value, size, status = _search(
            low, high, lambda v: estimate(replace(settings, jpeg_quality=v)), needed
        )
        settings = replace(settings, jpeg_quality=value)
        tuned.append("jpeg_quality")
    return settings, size, status, tuned


def _out_of_range(label: str, settings: ScanSettings | ImageSettings, lossless: bool) -> str:
    """Avertissement de cible hors de portée ; ``label`` : « scans réglés », « images réglées »."""
    if lossless:
        return (
            f"taille cible hors de portée des réglages réalistes (dpi {TUNING_DPI[0]}-"
            f"{TUNING_DPI[1]}) : {label} à {settings.dpi} dpi"
        )
    return (
        f"taille cible hors de portée des réglages réalistes (dpi {TUNING_DPI[0]}-"
        f"{TUNING_DPI[1]}, qualité JPEG {TUNING_QUALITY[0]}-{TUNING_QUALITY[1]}) : {label} "
        f"à {settings.dpi} dpi, qualité {settings.jpeg_quality}"
    )


def calibrate(
    plan: Sequence[Planned],
    *,
    target_mean_bytes: int,
    color: str,
    dpi: int | None,
    quality: int | None,
    render_native: Callable[[Planned], Rendered],
    population_counts: tuple[int, int] | None = None,
    images: ImageTuning | None = None,
) -> Calibration:
    """Choisit dpi et qualité JPEG des scans, et des images, pour approcher la moyenne cible."""
    scans = [item for item in plan if item.scan]
    natives = [item for item in plan if not item.scan]
    has_images = [images is not None and images.has_images(item) for item in natives]
    imaged = [item for item, flag in zip(natives, has_images, strict=True) if flag]
    plain = [item for item, flag in zip(natives, has_images, strict=True) if not flag]
    base = ScanSettings(
        dpi=DEFAULT_SCAN_DPI if dpi is None else dpi,
        color=color,
        jpeg_quality=DEFAULT_JPEG_QUALITY if quality is None else quality,
    )
    if not scans and not imaged:
        return Calibration(
            base,
            warnings=(
                "aucun scan dans le lot : la taille ne se règle ni par dpi ni par qualité ; "
                "elle dépend du contenu et du nombre de pages des PDF natifs",
            ),
        )

    plain_mean = 0.0
    if plain:
        sizes = [len(render_native(item).data) for item in spread(plain, SAMPLE_NATIVES)]
        plain_mean = sum(sizes) / len(sizes)
    scan_count, native_count = population_counts or (len(scans), len(natives))
    image_count = 0
    if imaged:
        image_count = images.native_count if images.native_count is not None else len(imaged)
    total = target_mean_bytes * (scan_count + native_count)
    fixed = plain_mean * (native_count - image_count)
    warnings: list[str] = []

    def positive(needed: float, message: str) -> float:
        if needed > 0:
            return needed
        warnings.append(message)
        return 1.0

    free_dpi = dpi is None
    free_quality = quality is None and color != "bw"
    scans_free = bool(scans) and (free_dpi or free_quality)

    def scan_estimator(render: Callable[[Planned], Rendered]) -> Callable[[ScanSettings], float]:
        sample_indices = set(spread(range(len(scans)), SAMPLE_SCANS))
        sample = []
        total_pages = 0
        for index, item in enumerate(scans):
            rendered = render(item)
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
                    sizes.append(
                        scan.encoded_size(scan.encode_page(width, height, raster, settings))
                    )
            return sum(sizes) / len(sizes) * pages_per_scan + 2000

        return estimate

    # Les scans non réglables sont mesurés d'abord : leur poids se déduit de la cible des images.
    estimate_scans: Callable[[ScanSettings], float] | None = None
    if scans and not scans_free:
        estimate_scans = scan_estimator(render_native)
    scans_fixed_total = (
        estimate_scans(base) * scan_count if estimate_scans is not None and imaged else 0.0
    )

    image_settings: ImageSettings | None = None
    image_size: float | None = None
    image_tuned: list[str] = []
    if imaged:
        image_settings = images.base
        sample_docs = spread(imaged, SAMPLE_IMAGE_DOCS)
        # Le poids hors images ne dépend pas de leurs réglages : une seule mesure par document.
        measured = [
            (len(render_native(item).data), images.stream_bytes(item, images.base))
            for item in sample_docs
        ]

        def estimate_images(settings: ImageSettings) -> float:
            sizes = [
                size - stream + images.stream_bytes(item, settings)
                for item, (size, stream) in zip(sample_docs, measured, strict=True)
            ]
            return sum(sizes) / len(sizes)

        if images.free_dpi or images.free_quality:
            shared = scan_count + image_count if scans_free else image_count
            needed = positive(
                (total - fixed - scans_fixed_total) / shared,
                "les autres PDF dépassent à eux seuls la taille moyenne cible ; images "
                "réglées au plus léger",
            )
            image_settings, image_size, status, names = _tune(
                images.base, images.free_dpi, images.free_quality, needed, estimate_images
            )
            image_tuned = [f"image_{name}" for name in names]
            if status != "ok":
                warnings.append(
                    _out_of_range("images réglées", image_settings, images.base.format == "png")
                )
        else:
            image_size = estimate_images(images.base)
            warnings.append(
                "dpi et qualité JPEG des images imposés : la taille cible n'est pas ajustée "
                "(mesure seule)"
                if images.base.format == "jpeg"
                else "dpi des images imposé : la taille cible n'est pas ajustée (mesure seule)"
            )

    settings, size, tuned = base, None, []
    if scans:
        if estimate_scans is None:
            render = render_native
            if image_settings is not None and image_settings != images.base:
                # Les scans reprennent les images telles qu'elles seront écrites.
                def render(item: Planned, final=image_settings) -> Rendered:
                    return images.render(item, final)

            estimate_scans = scan_estimator(render)
        needed = positive(
            (total - fixed - (image_size or 0.0) * image_count) / scan_count,
            "les PDF natifs dépassent à eux seuls la taille moyenne cible ; scans réglés au "
            "plus léger",
        )
        if scans_free:
            settings, size, status, tuned = _tune(
                base, free_dpi, free_quality, needed, estimate_scans
            )
            if status != "ok":
                warnings.append(_out_of_range("scans réglés", settings, color == "bw"))
        else:
            size = estimate_scans(settings)
            warnings.append(
                "dpi imposé : la taille cible n'est pas ajustée (mesure seule)"
                if color == "bw"
                else "dpi et qualité JPEG imposés : la taille cible n'est pas ajustée "
                "(mesure seule)"
            )
    return Calibration(
        settings,
        tuple(tuned) + tuple(image_tuned),
        estimated_scan_bytes=size,
        estimated_native_bytes=plain_mean if plain else None,
        image_settings=image_settings,
        estimated_image_bytes=image_size,
        warnings=tuple(warnings),
    )

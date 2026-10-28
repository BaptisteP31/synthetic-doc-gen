"""Génération par lots : fichiers + manifeste JSONL."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import platform
import secrets
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction
from importlib import metadata
from pathlib import Path

from synthetic_doc_gen import SYNTHETIC_MARKER, __version__
from synthetic_doc_gen.generators import get_generator
from synthetic_doc_gen.model import Document
from synthetic_doc_gen.options import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_SCAN_DPI,
    RenderOptions,
    ScanSettings,
)
from synthetic_doc_gen.pagination import MAX_PAGES, fit_pages
from synthetic_doc_gen.profiles import Profile
from synthetic_doc_gen.renderers import Rendered, get_renderer, scan
from synthetic_doc_gen.seeding import derive_seed, make_rng
from synthetic_doc_gen.sizing import Calibration, calibrate

MANIFEST_NAME = "manifest.jsonl"
REPORT_NAME = "report.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BatchConfig:
    out_dir: Path
    count: int
    base_seed: int
    doc_types: Sequence[str]
    profile: Profile
    medium: str = "pdf"
    start_index: int = 0
    overwrite: bool = False
    #: Proportion de PDF scannés (images seules) ; les autres sont des PDF natifs (texte).
    scan_ratio: float = 0.0
    #: Pages par document : (min, max) inclus, tirage par document ; ``None`` : longueur du profil.
    pages: tuple[int, int] | None = None
    #: Réglages de scan imposés ; ``None`` : valeur par défaut, ou ajustée si taille cible.
    scan_dpi: int | None = None
    scan_color: str = "color"
    scan_quality: int | None = None
    #: Logo et signature fictifs (vectoriels, déterministes).
    logo: bool = False
    signature: bool = False
    #: Taille moyenne cible des fichiers (octets), atteinte au mieux par réglage des scans.
    target_mean_bytes: int | None = None
    #: Écart relatif toléré entre moyenne mesurée et cible avant avertissement.
    target_tolerance: float = 0.10


@dataclass(frozen=True)
class PlannedDocument:
    index: int
    doc_type: str
    scan: bool
    #: Nombre de pages exact demandé, ou ``None``.
    pages: int | None
    #: Unités de contenu complémentaire nécessaires pour atteindre ``pages`` (0 sans cible).
    units: int = 0


@dataclass(frozen=True)
class BatchReport:
    """Mesures du lot écrit (``report.json``) ; ``warnings`` non vide : cible non atteinte."""

    data: dict = field(default_factory=dict)

    @property
    def warnings(self) -> list[str]:
        return self.data["warnings"]


def doc_id_for(index: int) -> str:
    return f"SYN-{index:06d}"


def doc_type_for(index: int, doc_types: Sequence[str]) -> str:
    """Répartition tournante : l'index seul détermine le type (stable si le lot change)."""
    return doc_types[index % len(doc_types)]


def build_document(
    index: int, base_seed: int, doc_type: str, profile: Profile, filler_units: int = 0
) -> tuple[Document, int]:
    """Contenu du document ``index`` : fonction pure de (graine de lot, index, type, profil).

    ``filler_units`` ajoute des unités de contenu complémentaires (pour atteindre un nombre
    de pages) sans modifier le contenu de base.
    """
    seed = derive_seed(base_seed, index, doc_type)
    generator = get_generator(doc_type)
    if filler_units:
        return generator(make_rng(seed), profile, filler_units=filler_units), seed
    return generator(make_rng(seed), profile), seed


def is_scan(index: int, doc_types: Sequence[str], ratio: float) -> bool:
    """Le document ``index`` est-il un scan ? Fonction de (index, types, proportion) seulement.

    Répartition régulière (Bresenham) *au sein de chaque type* : sans corrélation avec la
    rotation des types, et un sous-lot (``--start-index``) retrouve les mêmes choix. Chaque
    type reçoit ``floor(n * ratio + décalage)`` scans sur ses ``n`` premiers documents ; les
    décalages sont étagés entre types pour que le total reste à un scan près de ``n * ratio``.
    """
    share = Fraction(ratio).limit_denominator(10_000)
    rank, position = divmod(index, len(doc_types))
    offset = Fraction(position + 1, len(doc_types) + 1)
    return math.floor((rank + 1) * share + offset) > math.floor(rank * share + offset)


def pages_for(base_seed: int, index: int, doc_type: str, bounds: tuple[int, int]) -> int:
    """Nombre de pages du document, tiré dans ``bounds`` avec une graine indépendante."""
    return make_rng(derive_seed(base_seed, index, f"{doc_type}:pages")).randint(*bounds)


def plan_documents(config: BatchConfig) -> list[PlannedDocument]:
    return [
        PlannedDocument(
            index,
            doc_type,
            is_scan(index, config.doc_types, config.scan_ratio),
            pages_for(config.base_seed, index, doc_type, config.pages) if config.pages else None,
        )
        for index in range(config.start_index, config.start_index + config.count)
        for doc_type in (doc_type_for(index, config.doc_types),)
    ]


def _relative_path(medium: str, doc_id: str, doc_type: str, extension: str) -> Path:
    return Path(medium) / f"{doc_id}_{doc_type}.{extension}"


def _scan_description(settings: ScanSettings) -> dict:
    return {
        "dpi": settings.dpi,
        "color": settings.color,
        "jpeg_quality": None if settings.color == "bw" else settings.jpeg_quality,
        "rasterizer": {
            "name": "pdfium",
            "version": scan.pdfium_version(),
            "binding": f"pypdfium2 {metadata.version('pypdfium2')}",
        },
    }


def _manifest_record(
    *,
    index,
    base_seed,
    seed,
    document: Document,
    profile: Profile,
    medium: str,
    path: Path,
    rendered: Rendered,
    renderer,
    options: RenderOptions,
    pages_requested: int | None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "doc_id": doc_id_for(index),
        "index": index,
        "doc_type": document.doc_type,
        "medium": medium,
        "profile": profile.name,
        "profile_parameters": json.loads(json.dumps(asdict(profile))),
        "python_version": platform.python_version(),
        "base_seed": base_seed,
        "seed": seed,
        "path": path.as_posix(),
        "bytes": len(rendered.data),
        "sha256": hashlib.sha256(rendered.data).hexdigest(),
        "pages": rendered.pages,
        "language": "fr",
        "synthetic": True,
        "marker": SYNTHETIC_MARKER,
        "generator": {"name": "synthetic-doc-gen", "version": __version__},
        "renderer": {"name": renderer.name, "version": renderer.version()},
        "render": {
            "kind": "native" if options.scan is None else "scan",
            "logo": options.logo,
            "signature": options.signature,
            "pages_requested": pages_requested,
            "scan": None if options.scan is None else _scan_description(options.scan),
        },
        "entities": document.entities,
    }


def build_report(
    config: BatchConfig, records: Sequence[dict], calibration: Calibration | None
) -> BatchReport:
    """Mesures réelles du lot (taille des fichiers écrits) et avertissements éventuels."""

    def stats(rows: Sequence[dict]) -> dict:
        sizes = [r["bytes"] for r in rows]
        pages = [r["pages"] or 0 for r in rows]
        return {
            "documents": len(rows),
            "total_bytes": sum(sizes),
            "mean_bytes": round(sum(sizes) / len(sizes), 1) if sizes else None,
            "min_bytes": min(sizes, default=None),
            "max_bytes": max(sizes, default=None),
            "total_pages": sum(pages),
            "mean_pages": round(sum(pages) / len(pages), 2) if pages else None,
        }

    native = [r for r in records if r["render"]["kind"] == "native"]
    scanned = [r for r in records if r["render"]["kind"] == "scan"]
    warnings = list(calibration.warnings) if calibration else []
    measured = stats(records)
    target = None
    if config.target_mean_bytes is not None:
        mean = measured["mean_bytes"]
        deviation = (
            None if mean is None else (mean - config.target_mean_bytes) / (config.target_mean_bytes)
        )
        reached = deviation is not None and abs(deviation) <= config.target_tolerance
        target = {
            "mean_bytes": config.target_mean_bytes,
            "tolerance": config.target_tolerance,
            "deviation": None if deviation is None else round(deviation, 4),
            "reached": reached,
            "tuned": list(calibration.tuned) if calibration else [],
            "estimated_scan_bytes": calibration.estimated_scan_bytes if calibration else None,
        }
        if records and not reached:
            warnings.append(
                f"taille moyenne cible non atteinte : {mean:.0f} octets mesurés pour "
                f"{config.target_mean_bytes} visés ({deviation:+.1%}, tolérance "
                f"±{config.target_tolerance:.0%}) ; cible au mieux, sans remplissage artificiel"
            )
        elif not records:
            warnings.append("lot vide : taille moyenne cible non évaluable")
    return BatchReport(
        {
            "schema_version": SCHEMA_VERSION,
            "generator": {"name": "synthetic-doc-gen", "version": __version__},
            "base_seed": config.base_seed,
            "requested": {
                "count": config.count,
                "scan_ratio": config.scan_ratio,
                "pages": list(config.pages) if config.pages else None,
                "logo": config.logo,
                "signature": config.signature,
                "scan_dpi": config.scan_dpi,
                "scan_color": config.scan_color,
                "scan_quality": config.scan_quality,
            },
            "measured": {
                **measured,
                "native": stats(native),
                "scan": stats(scanned),
                "scan_ratio": round(len(scanned) / len(records), 4) if records else None,
            },
            "scan_settings": _scan_description(_final_settings(config, calibration))
            if scanned
            else None,
            "target": target,
            "warnings": warnings,
        }
    )


def _final_settings(config: BatchConfig, calibration: Calibration | None) -> ScanSettings:
    if calibration is not None:
        return calibration.settings
    return ScanSettings(
        dpi=DEFAULT_SCAN_DPI if config.scan_dpi is None else config.scan_dpi,
        color=config.scan_color,
        jpeg_quality=DEFAULT_JPEG_QUALITY if config.scan_quality is None else config.scan_quality,
    )


def run_batch(config: BatchConfig) -> Iterator[dict]:
    """Empêche deux générations simultanées dans un même dossier.

    Générateur : rend chaque enregistrement du manifeste ; sa valeur de retour
    (``StopIteration.value``) est le :class:`BatchReport` du lot.
    """
    config.out_dir.mkdir(parents=True, exist_ok=True)
    with (config.out_dir / ".synthetic-doc-gen.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FileExistsError("une génération est déjà en cours dans ce dossier") from None
        return (yield from _run_batch(config))


def _validate(config: BatchConfig) -> None:
    if config.count < 0 or config.start_index < 0:
        raise ValueError("count et start_index doivent être positifs ou nuls")
    if not config.doc_types:
        raise ValueError("au moins un type de document est requis")
    if not 0 <= config.scan_ratio <= 1:
        raise ValueError("la proportion de scans doit être comprise entre 0 et 1")
    if config.pages is not None:
        low, high = config.pages
        if not 1 <= low <= high <= MAX_PAGES:
            raise ValueError(f"pages : intervalle attendu dans 1-{MAX_PAGES}, reçu {config.pages}")
    if config.target_mean_bytes is not None and config.target_mean_bytes <= 0:
        raise ValueError("la taille moyenne cible doit être strictement positive")
    if not 0 < config.target_tolerance <= 1:
        raise ValueError("la tolérance de taille doit être dans ]0, 1]")
    # Valide aussi dpi / qualité / couleur demandés.
    ScanSettings(
        dpi=DEFAULT_SCAN_DPI if config.scan_dpi is None else config.scan_dpi,
        color=config.scan_color,
        jpeg_quality=DEFAULT_JPEG_QUALITY if config.scan_quality is None else config.scan_quality,
    )


def _run_batch(config: BatchConfig) -> Iterator[dict]:
    """Génère le lot et rend chaque enregistrement du manifeste au fur et à mesure.

    Refuse d'écraser des fichiers existants sauf ``overwrite``, avant toute écriture. L'ajustement
    de la taille cible se fait en mémoire, avant la première écriture.
    """
    _validate(config)
    for doc_type in config.doc_types:
        get_generator(doc_type)  # échoue tôt sur un type inconnu, quel que soit count
    renderer = get_renderer(config.medium)
    plan = plan_documents(config)

    manifest_path = config.out_dir / MANIFEST_NAME
    report_path = config.out_dir / REPORT_NAME
    targets = [
        config.out_dir
        / _relative_path(config.medium, doc_id_for(item.index), item.doc_type, renderer.extension)
        for item in plan
    ]

    def present(path: Path) -> bool:
        return os.path.lexists(path)

    if not config.overwrite:
        existing = [p for p in (manifest_path, report_path, *targets) if present(p)]
        if existing:
            raise FileExistsError(
                f"{len(existing)} fichier(s) existent déjà (ex. {existing[0]}) ; "
                "utiliser --force pour écraser"
            )
    elif present(manifest_path):
        raise ValueError("--force ne remplace pas un manifeste existant ; choisir un autre dossier")

    medium_dir = config.out_dir / config.medium
    if medium_dir.is_symlink():
        raise ValueError("le dossier du support ne doit pas être un lien symbolique")

    base_options = RenderOptions(logo=config.logo, signature=config.signature)

    def build(item: PlannedDocument) -> tuple[Document, int]:
        return build_document(
            item.index, config.base_seed, item.doc_type, config.profile, item.units
        )

    def fit(item: PlannedDocument) -> PlannedDocument:
        """Cherche le contenu qui donne exactement ``item.pages`` pages (rendu réel mesuré)."""
        doc_id = doc_id_for(item.index)

        def native_pages(document: Document) -> int:
            return renderer.render_native(document, config.profile, doc_id, base_options).pages

        _, units = fit_pages(
            lambda k: build_document(
                item.index, config.base_seed, item.doc_type, config.profile, k
            )[0],
            native_pages,
            item.pages,
        )
        return replace(item, units=units)

    def render_native(item: PlannedDocument) -> Rendered:
        document, _ = build(item)
        return renderer.render_native(
            document, config.profile, doc_id_for(item.index), base_options
        )

    # Avant toute écriture : une page cible inatteignable échoue sans rien laisser dans le dossier.
    plan = [fit(item) if item.pages is not None else item for item in plan]

    calibration: Calibration | None = None
    if config.target_mean_bytes is not None:
        calibration = calibrate(
            plan,
            target_mean_bytes=config.target_mean_bytes,
            color=config.scan_color,
            dpi=config.scan_dpi,
            quality=config.scan_quality,
            render_native=render_native,
        )
    scan_settings = _final_settings(config, calibration)
    scan_options = RenderOptions(config.logo, config.signature, scan_settings)

    medium_dir.mkdir(parents=True, exist_ok=True)

    def publish(path: Path, data: bytes, *, replace: bool) -> None:
        while True:
            temp = path.parent / f".synthetic-doc-gen-{secrets.token_hex(16)}"
            try:
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
                break
            except FileExistsError:
                continue
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            if replace:
                os.replace(temp, path)
            else:
                os.link(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    publish(manifest_path, b"", replace=False)
    manifest = manifest_path.open("r+b", buffering=0)
    records: list[dict] = []
    try:
        for item, target in zip(plan, targets, strict=True):
            document, seed = build(item)
            options = scan_options if item.scan else base_options
            rendered = renderer.render(document, config.profile, doc_id_for(item.index), options)
            record = _manifest_record(
                index=item.index,
                base_seed=config.base_seed,
                seed=seed,
                document=document,
                profile=config.profile,
                medium=config.medium,
                path=target.relative_to(config.out_dir),
                rendered=rendered,
                renderer=renderer,
                options=options,
                pages_requested=item.pages,
            )
            line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            publish(target, rendered.data, replace=config.overwrite)
            position = manifest.tell()
            try:
                written = manifest.write(line)
                if written != len(line):
                    raise OSError("écriture incomplète du manifeste")
            except BaseException:
                manifest.truncate(position)
                target.unlink(missing_ok=True)
                raise
            records.append(record)
            yield record
    finally:
        manifest.close()
    report = build_report(config, records, calibration)
    payload = json.dumps(report.data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    publish(report_path, payload.encode("utf-8"), replace=config.overwrite)
    return report

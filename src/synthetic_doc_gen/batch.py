"""Génération par lots : fichiers + manifeste JSONL."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import secrets
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from synthetic_doc_gen import SYNTHETIC_MARKER, __version__
from synthetic_doc_gen.generators import get_generator
from synthetic_doc_gen.model import Document
from synthetic_doc_gen.profiles import Profile
from synthetic_doc_gen.renderers import Rendered, get_renderer
from synthetic_doc_gen.seeding import derive_seed, make_rng

MANIFEST_NAME = "manifest.jsonl"
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


def doc_id_for(index: int) -> str:
    return f"SYN-{index:06d}"


def doc_type_for(index: int, doc_types: Sequence[str]) -> str:
    """Répartition tournante : l'index seul détermine le type (stable si le lot change)."""
    return doc_types[index % len(doc_types)]


def build_document(
    index: int, base_seed: int, doc_type: str, profile: Profile
) -> tuple[Document, int]:
    """Contenu du document ``index`` : fonction pure de (graine de lot, index, type, profil)."""
    seed = derive_seed(base_seed, index, doc_type)
    return get_generator(doc_type)(make_rng(seed), profile), seed


def _relative_path(medium: str, doc_id: str, doc_type: str, extension: str) -> Path:
    return Path(medium) / f"{doc_id}_{doc_type}.{extension}"


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
        "entities": document.entities,
    }


def run_batch(config: BatchConfig) -> Iterator[dict]:
    """Empêche deux générations simultanées dans un même dossier."""
    config.out_dir.mkdir(parents=True, exist_ok=True)
    with (config.out_dir / ".synthetic-doc-gen.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FileExistsError("une génération est déjà en cours dans ce dossier") from None
        yield from _run_batch(config)


def _run_batch(config: BatchConfig) -> Iterator[dict]:
    """Génère le lot et rend chaque enregistrement du manifeste au fur et à mesure.

    Refuse d'écraser des fichiers existants sauf ``overwrite``, avant toute écriture.
    """
    if config.count < 0 or config.start_index < 0:
        raise ValueError("count et start_index doivent être positifs ou nuls")
    if not config.doc_types:
        raise ValueError("au moins un type de document est requis")
    for doc_type in config.doc_types:
        get_generator(doc_type)  # échoue tôt sur un type inconnu, quel que soit count
    renderer = get_renderer(config.medium)
    indices = range(config.start_index, config.start_index + config.count)
    plan = [
        (
            i,
            doc_type_for(i, config.doc_types),
        )
        for i in indices
    ]

    manifest_path = config.out_dir / MANIFEST_NAME
    targets = [
        config.out_dir / _relative_path(config.medium, doc_id_for(i), t, renderer.extension)
        for i, t in plan
    ]

    def present(path: Path) -> bool:
        return os.path.lexists(path)

    if not config.overwrite:
        existing = [p for p in (manifest_path, *targets) if present(p)]
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
    try:
        for (index, doc_type), target in zip(plan, targets, strict=True):
            document, seed = build_document(index, config.base_seed, doc_type, config.profile)
            rendered = renderer.render(document, config.profile, doc_id_for(index))
            record = _manifest_record(
                index=index,
                base_seed=config.base_seed,
                seed=seed,
                document=document,
                profile=config.profile,
                medium=config.medium,
                path=target.relative_to(config.out_dir),
                rendered=rendered,
                renderer=renderer,
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
            yield record
    finally:
        manifest.close()

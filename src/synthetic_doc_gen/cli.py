"""Interface en ligne de commande : ``synthetic-doc-gen generate|list``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from synthetic_doc_gen import SYNTHETIC_MARKER, __version__
from synthetic_doc_gen.batch import MANIFEST_NAME, BatchConfig, run_batch
from synthetic_doc_gen.generators import DOC_TYPE_DESCRIPTIONS, GENERATORS
from synthetic_doc_gen.profiles import PROFILES, get_profile
from synthetic_doc_gen.renderers import RENDERERS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthetic-doc-gen",
        description=f"Génère des documents médicaux fictifs marqués {SYNTHETIC_MARKER}.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="générer un lot de documents et son manifeste")
    gen.add_argument("-o", "--out", type=Path, required=True, help="dossier de sortie")
    gen.add_argument("-n", "--count", type=int, default=10, help="nombre de documents (10)")
    gen.add_argument("-s", "--seed", type=int, default=0, help="graine du lot (0)")
    gen.add_argument(
        "-t",
        "--types",
        default=",".join(GENERATORS),
        help=f"types séparés par des virgules, parmi : {', '.join(GENERATORS)} (tous)",
    )
    gen.add_argument("-p", "--profile", default="standard", choices=list(PROFILES))
    gen.add_argument("-m", "--medium", default="pdf", choices=list(RENDERERS))
    gen.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="index du premier document (utiliser un dossier séparé pour chaque lot)",
    )
    gen.add_argument("--force", action="store_true", help="écraser les fichiers existants")

    sub.add_parser("list", help="lister types, profils et médias disponibles")
    return parser


def _cmd_list() -> int:
    print("Types de documents :")
    for name, desc in DOC_TYPE_DESCRIPTIONS.items():
        print(f"  {name:<18} {desc}")
    print("Profils :")
    for p in PROFILES.values():
        print(f"  {p.name:<18} {p.description}")
    print("Médias :")
    for name, renderer in RENDERERS.items():
        print(f"  {name:<18} {renderer.name} {renderer.version()}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    doc_types = [t.strip() for t in args.types.split(",") if t.strip()]
    config = BatchConfig(
        out_dir=args.out,
        count=args.count,
        base_seed=args.seed,
        doc_types=doc_types,
        profile=get_profile(args.profile),
        medium=args.medium,
        start_index=args.start_index,
        overwrite=args.force,
    )
    n = 0
    try:
        for record in run_batch(config):
            n += 1
            print(
                f"{record['doc_id']}  {record['doc_type']:<17} "
                f"{record['pages']} p.  {record['path']}"
            )
    except (OSError, ValueError):
        if n:
            print(f"échec partiel : {n} document(s) inscrit(s) au manifeste", file=sys.stderr)
        raise
    print(f"{n} document(s) dans {args.out} ; manifeste : {args.out / MANIFEST_NAME}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return _cmd_list()
        return _cmd_generate(args)
    except (ValueError, OSError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

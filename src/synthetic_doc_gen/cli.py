"""Interface en ligne de commande : ``synthetic-doc-gen generate|list``."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from synthetic_doc_gen import SYNTHETIC_MARKER, __version__
from synthetic_doc_gen.batch import MANIFEST_NAME, REPORT_NAME, BatchConfig, BatchReport, run_batch
from synthetic_doc_gen.generators import DOC_TYPE_DESCRIPTIONS, GENERATORS
from synthetic_doc_gen.options import SCAN_COLORS
from synthetic_doc_gen.pagination import MAX_PAGES
from synthetic_doc_gen.profiles import PROFILES, get_profile
from synthetic_doc_gen.renderers import RENDERERS

_SIZE_UNITS = {
    "": 1,
    "o": 1,
    "k": 1000,
    "ko": 1000,
    "m": 10**6,
    "mo": 10**6,
    "kb": 1000,
    "mb": 10**6,
}


def _size(text: str) -> int:
    """Taille en octets : ``200000``, ``150k``, ``1.5M`` (unités décimales : k = 1000 octets)."""
    digits = text.strip().lower()
    number = digits.rstrip("abkmo")
    unit = digits[len(number) :]
    try:
        value = float(number.replace(",", ".")) * _SIZE_UNITS[unit]
    except (ValueError, KeyError):
        raise argparse.ArgumentTypeError(f"taille invalide : {text!r} (ex. 150k, 1.5M)") from None
    if not math.isfinite(value) or value < 1 or value > sys.maxsize:
        raise argparse.ArgumentTypeError("la taille doit être strictement positive")
    return round(value)


def _ratio(text: str) -> float:
    """Proportion : ``0.3``, ``30%`` ou ``30%``."""
    try:
        value = float(text[:-1]) / 100 if text.endswith("%") else float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"proportion invalide : {text!r}") from None
    if not 0 <= value <= 1:
        raise argparse.ArgumentTypeError("la proportion doit être entre 0 et 1 (ou 0%-100%)")
    return value


def _pages(text: str) -> tuple[int, int]:
    """Pages par document : ``3`` ou ``2-5``."""
    try:
        low, _, high = text.partition("-")
        bounds = (int(low), int(high or low))
    except ValueError:
        raise argparse.ArgumentTypeError(f"pages invalides : {text!r} (ex. 3 ou 2-5)") from None
    if not 1 <= bounds[0] <= bounds[1] <= MAX_PAGES:
        raise argparse.ArgumentTypeError(f"pages : intervalle croissant dans 1-{MAX_PAGES}")
    return bounds


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
    gen.add_argument(
        "--force", action="store_true", help="écraser les fichiers cibles sans manifeste existant"
    )

    layout = gen.add_argument_group("PDF natifs et scans")
    layout.add_argument(
        "--scan-ratio",
        type=_ratio,
        default=0.0,
        help="proportion de scans (PDF image seule), ex. 0.3 ou 30%% ; le reste est natif (0)",
    )
    layout.add_argument(
        "--pages",
        type=_pages,
        help=f"pages par document, ex. 3 ou 2-5 (1-{MAX_PAGES}) ; défaut : longueur du profil",
    )
    layout.add_argument("--scan-dpi", type=int, help="résolution des scans (150)")
    layout.add_argument("--scan-color", choices=SCAN_COLORS, default="color", help="(color)")
    layout.add_argument("--scan-quality", type=int, help="qualité JPEG des scans, 1-95 (75)")
    layout.add_argument("--logo", action="store_true", help="logo fictif d'établissement")
    layout.add_argument("--signature", action="store_true", help="signature manuscrite fictive")
    layout.add_argument(
        "--target-size",
        type=_size,
        metavar="TAILLE",
        help="taille moyenne visée par fichier (ex. 150k, 1.5M) : règle dpi/qualité des scans "
        "non imposés, sans remplissage ; avertit si l'écart mesuré dépasse la tolérance",
    )
    layout.add_argument(
        "--target-tolerance",
        type=_ratio,
        default=0.10,
        metavar="RATIO",
        help="écart toléré à la taille visée, ex. 10%% (10%%)",
    )

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
        scan_ratio=args.scan_ratio,
        pages=args.pages,
        scan_dpi=args.scan_dpi,
        scan_color=args.scan_color,
        scan_quality=args.scan_quality,
        logo=args.logo,
        signature=args.signature,
        target_mean_bytes=args.target_size,
        target_tolerance=args.target_tolerance,
    )
    n = 0
    report: BatchReport | None = None
    batch = run_batch(config)
    try:
        while True:
            try:
                record = next(batch)
            except StopIteration as done:
                report = done.value
                break
            n += 1
            kind = "scan  " if record["render"]["kind"] == "scan" else "natif "
            print(
                f"{record['doc_id']}  {record['doc_type']:<17} {kind} "
                f"{record['pages']} p.  {record['bytes']:>8} o  {record['path']}"
            )
    except (OSError, ValueError):
        if n:
            print(f"échec partiel : {n} document(s) inscrit(s) au manifeste", file=sys.stderr)
        raise
    print(f"{n} document(s) dans {args.out} ; manifeste : {args.out / MANIFEST_NAME}")
    if report is not None:
        _print_report(report, args.out / REPORT_NAME)
    return 0


def _print_report(report: BatchReport, path: Path) -> None:
    measured = report.data["measured"]
    if measured["documents"]:
        print(
            f"mesuré : taille moyenne {measured['mean_bytes']:.0f} o "
            f"(min {measured['min_bytes']}, max {measured['max_bytes']}), "
            f"{measured['native']['documents']} natif(s), {measured['scan']['documents']} "
            f"scan(s), {measured['mean_pages']} page(s) en moyenne ; rapport : {path}"
        )
    target = report.data["target"]
    if target is not None and target["reached"]:
        print(f"taille cible atteinte ({target['deviation']:+.1%} de {target['mean_bytes']} o)")
    for warning in report.warnings:
        print(f"avertissement : {warning}", file=sys.stderr)


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

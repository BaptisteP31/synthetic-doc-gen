import hashlib
import json
from dataclasses import replace

import pytest
from pypdf import PdfReader

from synthetic_doc_gen import SYNTHETIC_MARKER
from synthetic_doc_gen.batch import (
    REPORT_NAME,
    BatchReport,
    build_document,
    is_scan,
    run_batch,
)
from synthetic_doc_gen.cli import main
from synthetic_doc_gen.options import RenderOptions, ScanSettings
from synthetic_doc_gen.pagination import fit_pages
from synthetic_doc_gen.profiles import PROFILES, get_profile
from synthetic_doc_gen.renderers import get_renderer

TYPES = ("compte-rendu", "bilan-biologique")


def _run(config):
    """Consomme le lot ; retourne (enregistrements, rapport)."""
    batch = run_batch(config)
    records = []
    while True:
        try:
            records.append(next(batch))
        except StopIteration as done:
            return records, done.value


def _images(path):
    reader = PdfReader(path)
    return [list(page.images) for page in reader.pages]


# --- proportion et déterminisme -------------------------------------------------------------


@pytest.mark.parametrize("ratio", [0, 0.1, 0.25, 1 / 3, 0.5, 0.8, 1])
@pytest.mark.parametrize("types", [TYPES[:1], TYPES, (*TYPES, "autre")])
def test_scan_ratio_is_regular_and_close_to_exact(ratio, types):
    count = 30 * len(types)
    flags = [is_scan(i, types, ratio) for i in range(count)]
    assert abs(sum(flags) - count * ratio) <= 1
    for t in range(len(types)):  # chaque type reçoit aussi sa part
        assert abs(sum(flags[t :: len(types)]) - 30 * ratio) <= 1
    if ratio in (0, 1):
        assert set(flags) == {bool(ratio)}


def test_scan_choice_is_independent_of_batch_window():
    full = [is_scan(i, TYPES, 0.3) for i in range(60)]
    assert [is_scan(i, TYPES, 0.3) for i in range(20, 40)] == full[20:40]


def test_scan_choice_is_not_locked_to_type_rotation():
    # Avec 2 types et 50 %, un découpage naïf (index pair/impair) ferait scanner un seul type.
    scanned = {TYPES[i % 2] for i in range(40) if is_scan(i, TYPES, 0.5)}
    assert scanned == set(TYPES)


# --- scans ----------------------------------------------------------------------------------


def test_scans_are_image_only_and_natives_have_text(make_config):
    config = make_config(count=4, scan_ratio=0.5, scan_dpi=100)
    records, _ = _run(config)
    kinds = {r["render"]["kind"] for r in records}
    assert kinds == {"native", "scan"}
    for r in records:
        reader = PdfReader(config.out_dir / r["path"])
        assert len(reader.pages) == r["pages"]
        assert SYNTHETIC_MARKER in (reader.metadata.title or "")
        for page in reader.pages:
            text = page.extract_text().strip()
            if r["render"]["kind"] == "scan":
                assert text == ""
                assert len(page.images) == 1
            else:
                assert SYNTHETIC_MARKER in text


def test_scan_keeps_page_geometry_and_content_of_native(make_config, tmp_path):
    native, _ = _run(make_config(count=2, out_dir=tmp_path / "n"))
    scanned, _ = _run(make_config(count=2, out_dir=tmp_path / "s", scan_ratio=1, scan_dpi=100))
    for a, b in zip(native, scanned, strict=True):
        assert (a["entities"], a["pages"]) == (b["entities"], b["pages"])
        page_a = PdfReader(tmp_path / "n" / a["path"]).pages[0]
        page_b = PdfReader(tmp_path / "s" / b["path"]).pages[0]
        assert [round(float(x)) for x in page_a.mediabox] == [
            round(float(x)) for x in page_b.mediabox
        ]


def test_scan_dpi_changes_image_resolution_and_size(make_config, tmp_path):
    sizes = {}
    for dpi in (100, 200):
        config = make_config(count=1, out_dir=tmp_path / str(dpi), scan_ratio=1, scan_dpi=dpi)
        (record,), _ = _run(config)
        (image,) = _images(config.out_dir / record["path"])[0]
        sizes[dpi] = (image.image.size, record["bytes"])
        assert record["render"]["scan"]["dpi"] == dpi
    assert sizes[200][0][0] == pytest.approx(2 * sizes[100][0][0], abs=2)
    assert sizes[200][1] > sizes[100][1]


def test_scan_color_modes(make_config, tmp_path):
    results = {}
    for color in ("color", "gray", "bw"):
        config = make_config(
            count=1, out_dir=tmp_path / color, scan_ratio=1, scan_dpi=100, scan_color=color
        )
        (record,), _ = _run(config)
        (image,) = _images(config.out_dir / record["path"])[0]
        results[color] = (image.image.mode, record["bytes"])
        assert record["render"]["scan"]["color"] == color
    assert results["color"][0] == "RGB"
    assert results["gray"][0] == "L"
    assert results["bw"][0] in {"L", "1"}
    assert results["bw"][1] < results["gray"][1] < results["color"][1]


def test_jpeg_quality_changes_size_not_geometry(make_config, tmp_path):
    sizes = []
    for quality in (30, 90):
        config = make_config(
            count=1, out_dir=tmp_path / str(quality), scan_ratio=1, scan_dpi=100,
            scan_quality=quality,
        )  # fmt: skip
        (record,), _ = _run(config)
        sizes.append(record["bytes"])
    assert sizes[0] < sizes[1]


def test_scans_are_reproducible_byte_for_byte(make_config, tmp_path):
    runs = [
        _run(make_config(count=3, out_dir=tmp_path / f"r{i}", scan_ratio=1, scan_dpi=100))[0]
        for i in range(2)
    ]
    assert [r["sha256"] for r in runs[0]] == [r["sha256"] for r in runs[1]]


def test_default_options_do_not_change_native_rendering(make_config):
    profile = get_profile("standard")
    document, _ = build_document(0, 7, "compte-rendu", profile)
    renderer = get_renderer("pdf")
    plain = renderer.render(document, profile, "SYN-000000")
    assert plain.data == renderer.render(document, profile, "SYN-000000", RenderOptions()).data
    assert plain.data == renderer.render_native(document, profile, "SYN-000000").data
    with_art = renderer.render(
        document, profile, "SYN-000000", RenderOptions(logo=True, signature=True)
    )
    assert with_art.data != plain.data


def test_invalid_scan_settings_rejected(make_config):
    for overrides in (
        {"scan_color": "sepia"},
        {"scan_dpi": 10},
        {"scan_quality": 0},
        {"scan_ratio": 1.5},
        {"target_mean_bytes": 0},
        {"target_tolerance": 0},
        {"pages": (0, 2)},
        {"pages": (3, 2)},
        {"pages": (1, 500)},
    ):
        with pytest.raises(ValueError):
            _run(make_config(count=1, **overrides))
    with pytest.raises(ValueError):
        ScanSettings(color="bw", dpi=5)


# --- pages ----------------------------------------------------------------------------------


@pytest.mark.parametrize("profile_name", list(PROFILES))
@pytest.mark.parametrize("target", [1, 3])
def test_exact_page_count_for_every_profile_and_type(make_config, profile_name, target):
    # Une page seule : sans logo ni signature, qui occupent de la place (voir le test suivant).
    config = make_config(
        count=4, profile=get_profile(profile_name), pages=(target, target),
        logo=target > 1, signature=target > 1,
    )  # fmt: skip
    records, _ = _run(config)
    for r in records:
        assert r["pages"] == target == r["render"]["pages_requested"]
        reader = PdfReader(config.out_dir / r["path"])
        assert len(reader.pages) == target
        for number, page in enumerate(reader.pages, start=1):
            assert f"Page {number} / {target}" in page.extract_text()


def test_unreachable_page_count_fails_before_any_write(make_config):
    profile = replace(get_profile("large-print"), font_size=22.0, lab_rows=(18, 20))
    config = make_config(count=3, profile=profile, pages=(1, 1), doc_types=TYPES[1:])
    with pytest.raises(ValueError, match="déjà"):
        _run(config)
    assert not (config.out_dir / "manifest.jsonl").exists()
    assert (
        not list((config.out_dir / "pdf").glob("*")) if (config.out_dir / "pdf").exists() else True
    )


def test_page_range_is_drawn_per_document_and_reproducible(make_config, tmp_path):
    first, _ = _run(make_config(count=12, out_dir=tmp_path / "a", pages=(2, 4)))
    second, _ = _run(make_config(count=12, out_dir=tmp_path / "b", pages=(2, 4)))
    assert [r["pages"] for r in first] == [r["pages"] for r in second]
    assert {r["pages"] for r in first} <= {2, 3, 4} and len({r["pages"] for r in first}) > 1


@pytest.mark.parametrize("doc_type", TYPES)
def test_extra_pages_extend_without_altering_base_content(doc_type):
    profile = get_profile("standard")
    base, _ = build_document(5, 11, doc_type, profile)
    longer, _ = build_document(5, 11, doc_type, profile, 4)
    shorter, _ = build_document(5, 11, doc_type, profile, 2)
    assert longer.entities == base.entities and longer.title == base.title
    assert len(longer.blocks) > len(shorter.blocks) > len(base.blocks)
    for smaller, larger in ((base, shorter), (shorter, longer)):
        remaining = iter(larger.blocks)  # sous-suite : même contenu, même ordre
        assert all(any(block == other for other in remaining) for block in smaller.blocks)


def test_followup_notes_are_dated_consistently_with_the_patient():
    import datetime as dt
    import random

    from synthetic_doc_gen.fictional import fmt_date, make_person
    from synthetic_doc_gen.generators.clinical_report import SPECIALTIES, followup_notes
    from synthetic_doc_gen.model import Heading

    rng = random.Random(4)
    for _ in range(60):
        person = make_person(rng)
        spec = SPECIALTIES["Gériatrie"] if rng.random() < 0.5 else SPECIALTIES["Pneumologie"]
        day = dt.date(2025, 3, 1)
        if person.age_on(day) < spec.min_age:
            continue
        notes = followup_notes(random.Random(rng.random()), person, spec, day, 25)
        dates = [
            dt.datetime.strptime(b.text.rsplit(" ", 1)[1], "%d/%m/%Y").date()
            for b in notes
            if isinstance(b, Heading)
        ]
        assert dates == sorted(dates, reverse=True) and dates[0] <= day
        assert all(person.age_on(d) >= spec.min_age and d >= person.birth_date for d in dates)
        assert fmt_date(dates[0]) in notes[0].text


def test_fit_pages_finds_exact_target_or_fails():
    class Fake:
        def __init__(self, units):
            self.units = units

    build, pages = Fake, lambda doc: 1 + doc.units // 3
    document, units = fit_pages(build, pages, 4)
    assert pages(document) == 4 and units == 9
    assert fit_pages(build, pages, 1)[1] == 0
    with pytest.raises(ValueError, match="impossible"):
        fit_pages(build, lambda doc: 1, 2)
    with pytest.raises(ValueError, match="déjà"):
        fit_pages(build, lambda doc: 5, 2)


# --- logo et signature ----------------------------------------------------------------------


def test_logo_and_signature_are_optional_and_labelled_fictional(make_config, tmp_path):
    texts = {}
    for name, kwargs in {
        "none": {},
        "logo": {"logo": True},
        "sig": {"signature": True},
    }.items():
        config = make_config(count=1, out_dir=tmp_path / name, **kwargs)
        (record,), _ = _run(config)
        texts[name] = PdfReader(config.out_dir / record["path"]).pages[-1].extract_text()
        assert record["render"]["logo"] is ("logo" in kwargs)
        assert record["render"]["signature"] is ("signature" in kwargs)
    assert "LOGO FICTIF" not in texts["none"] and "signature fictive" not in texts["none"]
    assert "LOGO FICTIF" in texts["logo"] and "signature fictive" not in texts["logo"]
    assert "signature fictive" in texts["sig"] and "LOGO FICTIF" not in texts["sig"]


def test_signature_names_the_document_signer(make_config):
    config = make_config(count=2, signature=True)
    for r in _run(config)[0]:
        text = PdfReader(config.out_dir / r["path"]).pages[-1].extract_text()
        signer = r["entities"].get("practitioner")
        if signer:
            assert signer in text


# --- taille cible et rapport ----------------------------------------------------------------


def test_report_matches_manifest(make_config):
    config = make_config(count=6, scan_ratio=0.5, scan_dpi=100, pages=(1, 2))
    records, report = _run(config)
    assert isinstance(report, BatchReport)
    on_disk = json.loads((config.out_dir / REPORT_NAME).read_text())
    assert on_disk == report.data
    measured = on_disk["measured"]
    assert measured["documents"] == 6
    assert measured["total_bytes"] == sum(r["bytes"] for r in records)
    assert measured["total_bytes"] == sum(
        (config.out_dir / r["path"]).stat().st_size for r in records
    )
    assert measured["scan"]["documents"] + measured["native"]["documents"] == 6
    assert measured["scan_ratio"] == 0.5
    assert measured["total_pages"] == sum(r["pages"] for r in records)
    assert on_disk["target"] is None and on_disk["warnings"] == []


def test_target_size_is_reached_by_tuning_scans(make_config):
    target = 90_000
    config = make_config(
        count=8, scan_ratio=0.5, scan_color="gray", target_mean_bytes=target,
        target_tolerance=0.10,
    )  # fmt: skip
    records, report = _run(config)
    mean = sum(r["bytes"] for r in records) / len(records)
    assert abs(mean - target) / target <= 0.10
    assert report.data["target"]["reached"] is True and report.warnings == []
    assert "dpi" in report.data["target"]["tuned"]
    scans = [r for r in records if r["render"]["kind"] == "scan"]
    assert len({r["render"]["scan"]["dpi"] for r in scans}) == 1  # un seul réglage pour le lot
    assert 100 <= scans[0]["render"]["scan"]["dpi"] <= 400
    # Pas de remplissage : les natifs gardent leur taille naturelle, de quelques ko.
    assert all(r["bytes"] < 30_000 for r in records if r["render"]["kind"] == "native")


def test_target_never_overrides_explicit_scan_settings(make_config):
    config = make_config(
        count=4, scan_ratio=1, scan_dpi=100, scan_quality=60, target_mean_bytes=5_000_000
    )
    records, report = _run(config)
    assert {r["render"]["scan"]["dpi"] for r in records} == {100}
    assert {r["render"]["scan"]["jpeg_quality"] for r in records} == {60}
    assert report.data["target"]["reached"] is False
    assert any("imposés" in w for w in report.warnings)
    assert any("non atteinte" in w for w in report.warnings)


def test_pinned_dpi_lets_quality_absorb_the_target(make_config):
    config = make_config(count=3, scan_ratio=1, scan_dpi=150, target_mean_bytes=120_000)
    records, report = _run(config)
    assert report.data["target"]["tuned"] == ["jpeg_quality"]
    assert {r["render"]["scan"]["dpi"] for r in records} == {150}


def test_unreachable_target_warns_without_padding(make_config):
    config = make_config(count=3, scan_ratio=0, target_mean_bytes=500_000)
    records, report = _run(config)
    assert all(r["bytes"] < 30_000 for r in records)
    assert report.data["target"]["reached"] is False
    assert any("aucun scan" in w for w in report.warnings)
    assert any("sans remplissage" in w for w in report.warnings)


def test_target_out_of_realistic_range_stays_inside_bounds(make_config):
    config = make_config(
        count=2, doc_types=TYPES[:1], scan_ratio=1, scan_color="gray",
        target_mean_bytes=30_000_000,
    )  # fmt: skip
    _, report = _run(config)
    settings = report.data["scan_settings"]
    assert settings["dpi"] == 400 and settings["jpeg_quality"] == 95
    assert report.data["target"]["reached"] is False
    assert any("hors de portée" in w for w in report.warnings)


def test_calibration_writes_nothing_outside_final_files(make_config):
    config = make_config(count=4, scan_ratio=0.5, scan_color="gray", target_mean_bytes=60_000)
    _run(config)
    names = {p.name for p in config.out_dir.iterdir()}
    assert names == {"manifest.jsonl", "report.json", "pdf", ".synthetic-doc-gen.lock"}
    assert len(list((config.out_dir / "pdf").iterdir())) == 4


def test_existing_report_blocks_a_new_run_without_force(make_config):
    config = make_config(count=1)
    _run(config)
    (config.out_dir / "manifest.jsonl").unlink()
    (config.out_dir / "pdf").joinpath(next((config.out_dir / "pdf").iterdir()).name).unlink()
    with pytest.raises(FileExistsError):
        _run(config)
    assert json.loads((config.out_dir / REPORT_NAME).read_text())["measured"]["documents"] == 1


def test_manifest_scan_record_is_complete(make_config):
    config = make_config(count=1, scan_ratio=1, scan_dpi=100, scan_color="gray")
    (record,), _ = _run(config)
    scan = record["render"]["scan"]
    assert scan["dpi"] == 100 and scan["color"] == "gray"
    assert scan["rasterizer"]["name"] == "pdfium" and scan["rasterizer"]["version"]
    assert (
        hashlib.sha256((config.out_dir / record["path"]).read_bytes()).hexdigest()
        == (record["sha256"])
    )
    assert replace(config).doc_types == config.doc_types


# --- CLI ------------------------------------------------------------------------------------


def test_cli_scan_pages_and_target(tmp_path, capsys):
    out = tmp_path / "out"
    code = main(
        [
            "generate", "-o", str(out), "-n", "4", "-s", "3", "--scan-ratio", "50%",
            "--pages", "2", "--scan-color", "gray", "--target-size", "70k", "--logo",
            "--signature",
        ]
    )  # fmt: skip
    captured = capsys.readouterr()
    assert code == 0
    assert "scan" in captured.out and "natif" in captured.out
    assert "taille cible atteinte" in captured.out
    records = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
    assert {r["pages"] for r in records} == {2}
    assert (out / "report.json").is_file()


def test_cli_warns_on_stderr_but_succeeds_when_target_missed(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["generate", "-o", str(out), "-n", "2", "--target-size", "1M"]) == 0
    captured = capsys.readouterr()
    assert "avertissement" in captured.err and "aucun scan" in captured.err
    assert "taille cible atteinte" not in captured.out


@pytest.mark.parametrize(
    "flags",
    [
        ["--scan-ratio", "1.5"],
        ["--pages", "0"],
        ["--pages", "4-2"],
        ["--pages", "abc"],
        ["--target-size", "beaucoup"],
        ["--scan-color", "sepia"],
    ],
)
def test_cli_rejects_invalid_values(tmp_path, flags):
    with pytest.raises(SystemExit):
        main(["generate", "-o", str(tmp_path / "o"), *flags])


def test_cli_size_units():
    from synthetic_doc_gen.cli import _size

    assert (_size("150k"), _size("1.5M"), _size("2048"), _size("2 Ko")) == (
        150_000, 1_500_000, 2048, 2000,
    )  # fmt: skip

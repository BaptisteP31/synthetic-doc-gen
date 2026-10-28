import io
import json

import pytest
from PIL import Image
from pypdf import PdfReader

from synthetic_doc_gen import SYNTHETIC_MARKER
from synthetic_doc_gen.batch import build_document, doc_id_for, run_batch
from synthetic_doc_gen.cli import main
from synthetic_doc_gen.generators import DEFAULT_DOC_TYPES, GENERATORS
from synthetic_doc_gen.options import ImageSettings, RenderOptions
from synthetic_doc_gen.profiles import PROFILES, get_profile
from synthetic_doc_gen.renderers import get_renderer, imaging

IMAGING = "compte-rendu-imagerie"


def _run(config):
    batch = run_batch(config)
    records = []
    try:
        while True:
            records.append(next(batch))
    except StopIteration as done:
        return records, done.value.data


def _render(index=0, profile="standard", **settings):
    profile = get_profile(profile)
    document, _ = build_document(index, 3, IMAGING, profile)
    options = RenderOptions(image=ImageSettings(**settings))
    return document, get_renderer("pdf").render_native(
        document, profile, doc_id_for(index), options
    )


def _images(pdf: bytes):
    reader = PdfReader(io.BytesIO(pdf))
    return [image for page in reader.pages for image in page.images]


def test_default_types_unchanged_and_imaging_is_opt_in():
    assert DEFAULT_DOC_TYPES == ("compte-rendu", "bilan-biologique")
    assert IMAGING in GENERATORS


@pytest.mark.parametrize("profile", PROFILES)
def test_native_imaging_report_has_selectable_text_and_marked_images(profile):
    document, rendered = _render(profile=profile)
    reader = PdfReader(io.BytesIO(rendered.data))
    assert len(reader.pages) == rendered.pages
    assert SYNTHETIC_MARKER in reader.pages[0].extract_text()
    assert document.entities["patient_name"] in reader.pages[0].extract_text()
    images = _images(rendered.data)
    assert len(images) == len(document.figures) >= 4
    # Chaque flux JPEG est celui produit à l'encodage : commentaire de mention inclus.
    for image in images:
        assert image.data.startswith(b"\xff\xd8")
        assert SYNTHETIC_MARKER.encode() in image.data[:200]


def test_default_size_is_about_half_a_megabyte():
    sizes = [len(_render(index)[1].data) for index in range(6)]
    assert all(400_000 <= size <= 650_000 for size in sizes), sizes


def test_images_are_deterministic_and_controllable():
    first = _render(dpi=150, jpeg_quality=70)[1].data
    assert first == _render(dpi=150, jpeg_quality=70)[1].data
    by_dpi = [len(_render(dpi=dpi)[1].data) for dpi in (100, 200, 300)]
    by_quality = [len(_render(jpeg_quality=q)[1].data) for q in (40, 85, 95)]
    assert by_dpi == sorted(by_dpi) and len(set(by_dpi)) == 3
    assert by_quality == sorted(by_quality) and len(set(by_quality)) == 3


def test_image_pixels_are_marked_and_seeded():
    image = imaging.synthesize("irm", 5, 400, 300)
    band = image.crop((0, 300 - 25, 400, 300))
    assert image.mode == "L" and image.size == (400, 300)
    low, high = band.getextrema()
    assert low < 60 and high > 200  # texte sombre sur bandeau clair
    assert image.tobytes() == imaging.synthesize.__wrapped__("irm", 5, 400, 300).tobytes()
    assert image.tobytes() != imaging.synthesize("irm", 6, 400, 300).tobytes()
    comment = Image.open(io.BytesIO(imaging.encode("irm", 5, 400, 300, "jpeg", 80).data))
    assert SYNTHETIC_MARKER in comment.info["comment"].decode()


def test_png_images_are_lossless_marked_and_quality_independent():
    low = _render(format="png", dpi=120, jpeg_quality=40)
    high = _render(format="png", dpi=120, jpeg_quality=95)
    assert low[1].data == high[1].data
    images = _images(low[1].data)
    assert len(images) == len(low[0].figures)
    width, height = images[0].image.size
    expected = {
        imaging.synthesize(figure.modality, figure.seed, width, height).tobytes()
        for figure in low[0].figures
    }
    # Sans perte : les pixels intégrés sont exactement ceux de l'image synthétique marquée.
    assert {image.image.convert("L").tobytes() for image in images} == expected


def test_unknown_modality_and_invalid_settings():
    with pytest.raises(ValueError, match="modalité"):
        imaging.synthesize("scanner", 1, 50, 50)
    for bad in ({"dpi": 10}, {"jpeg_quality": 99}, {"format": "gif"}):
        with pytest.raises(ValueError):
            ImageSettings(**bad)


def test_exact_pages_and_scan_of_imaging_report(make_config):
    config = make_config(
        count=2,
        doc_types=(IMAGING,),
        pages=(3, 3),
        scan_ratio=0.5,
        logo=True,
        signature=True,
        scan_dpi=100,
    )
    records, _ = _run(config)
    assert {r["render"]["kind"] for r in records} == {"native", "scan"}
    for record in records:
        path = config.out_dir / record["path"]
        reader = PdfReader(path)
        assert len(reader.pages) == record["pages"] == 3
        text = "".join(page.extract_text() for page in reader.pages)
        if record["render"]["kind"] == "scan":
            assert text.strip() == ""  # image seule : le marquage est dans les pixels
            assert record["render"]["images"]["count"] >= 4
        else:
            assert SYNTHETIC_MARKER in text
    with pytest.raises(ValueError, match="2 pages"):
        _run(make_config(count=1, doc_types=(IMAGING,), pages=(1, 1), out_dir=config.out_dir / "x"))


def test_manifest_and_report_record_image_parameters_and_versions(make_config):
    config = make_config(
        count=3, doc_types=("compte-rendu", IMAGING), image_dpi=120, image_quality=60
    )
    records, report = _run(config)
    plain, imaged = records[0], records[1]
    assert plain["render"]["images"] is None
    images = imaged["render"]["images"]
    assert images["dpi"] == 120 and images["jpeg_quality"] == 60 and images["format"] == "jpeg"
    assert images["encoder"]["name"] == "Pillow" and images["encoder"]["version"]
    assert images["count"] == len(build_document(1, 7, IMAGING, config.profile)[0].figures)
    assert report["image_settings"]["dpi"] == 120
    assert report["requested"]["image_dpi"] == 120
    assert report["measured"]["with_images"]["documents"] == 1
    assert plain["bytes"] < imaged["bytes"]


def test_plain_documents_have_no_image_block(make_config):
    config = make_config(count=4)
    records, report = _run(config)
    assert all(r["render"]["images"] is None for r in records)
    assert report["image_settings"] is None


def _calibrated(make_config, **overrides):
    return _run(make_config(**{"doc_types": (IMAGING,), "count": 4, **overrides}))


def test_target_size_tunes_native_images(make_config):
    records, report = _calibrated(make_config, target_mean_bytes=300_000)
    assert report["target"]["reached"] and not report["warnings"]
    assert report["target"]["tuned"] == ["image_dpi"]
    assert report["image_settings"]["dpi"] < 200
    mean = sum(r["bytes"] for r in records) / len(records)
    assert mean == pytest.approx(300_000, rel=0.05)


def test_target_size_png_tunes_only_resolution(make_config):
    _, report = _calibrated(make_config, target_mean_bytes=600_000, image_format="png", count=2)
    assert report["target"]["tuned"] == ["image_dpi"]
    assert report["image_settings"]["jpeg_quality"] is None
    assert report["target"]["reached"]


def test_target_size_unreachable_warns_with_realistic_limits(make_config, tmp_path):
    _, low = _calibrated(make_config, target_mean_bytes=20_000, count=2)
    assert not low["target"]["reached"]
    assert low["image_settings"]["dpi"] == 100 and low["image_settings"]["jpeg_quality"] == 40
    assert any("hors de portée" in w and "images" in w for w in low["warnings"])
    assert any("non atteinte" in w for w in low["warnings"])
    _, high = _calibrated(
        make_config, target_mean_bytes=9_000_000, count=2, out_dir=tmp_path / "high"
    )
    assert high["image_settings"]["dpi"] == 400 and high["image_settings"]["jpeg_quality"] == 95
    assert any("non atteinte" in w for w in high["warnings"])


def test_imposed_image_settings_are_never_tuned(make_config):
    records, report = _calibrated(
        make_config, target_mean_bytes=300_000, image_dpi=150, image_quality=70, count=2
    )
    assert report["image_settings"]["dpi"] == 150
    assert report["image_settings"]["jpeg_quality"] == 70
    assert report["target"]["tuned"] == []
    assert any("images imposés" in w for w in report["warnings"])
    assert not report["target"]["reached"] and records


def test_quality_is_tuned_when_only_dpi_is_imposed(make_config):
    _, report = _calibrated(make_config, target_mean_bytes=200_000, image_dpi=200, count=2)
    assert report["target"]["tuned"] == ["image_jpeg_quality"]
    assert report["image_settings"]["dpi"] == 200
    assert report["image_settings"]["jpeg_quality"] < 85


def test_target_size_mixes_images_scans_and_plain_documents(make_config):
    records, report = _run(
        make_config(
            doc_types=(IMAGING, "compte-rendu", "bilan-biologique"),
            count=9,
            scan_ratio=0.34,
            target_mean_bytes=250_000,
        )
    )
    assert set(report["target"]["tuned"]) == {"dpi", "image_dpi"}
    assert report["target"]["reached"], report["warnings"]
    kinds = {(r["doc_type"], r["render"]["kind"]) for r in records}
    assert (IMAGING, "native") in kinds and any(kind == "scan" for _, kind in kinds)


def test_cli_image_options_and_validation(tmp_path):
    out = tmp_path / "out"
    args = ["generate", "-o", str(out), "-n", "1", "-t", IMAGING, "--image-dpi", "120"]
    assert main([*args, "--image-quality", "60", "--image-format", "jpeg"]) == 0
    record = json.loads((out / "manifest.jsonl").read_text())
    assert record["render"]["images"]["dpi"] == 120
    assert main(["generate", "-o", str(tmp_path / "bad"), "-t", IMAGING, "--image-dpi", "5"]) == 2


def test_total_size_mode_counts_image_natives_in_calibration(tmp_path):
    out = tmp_path / "total"
    args = ["generate", "-o", str(out), "--total-size", "1M", "-t", IMAGING, "--max-count", "6"]
    assert main([*args, "--target-size", "300k", "--calibration-count", "2"]) == 0
    report = json.loads((out / "report.json").read_text())
    assert report["target"]["tuned"] == ["image_dpi"]
    assert report["total_target"]["reached"]

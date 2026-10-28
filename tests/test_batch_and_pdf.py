import hashlib
import json
from dataclasses import replace

import pytest
from pypdf import PdfReader

from synthetic_doc_gen import SYNTHETIC_MARKER
from synthetic_doc_gen.batch import MANIFEST_NAME, run_batch
from synthetic_doc_gen.profiles import PROFILES, get_profile


def _read_manifest(out_dir):
    lines = (out_dir / MANIFEST_NAME).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_batch_writes_pdfs_and_consistent_manifest(make_config):
    config = make_config(count=4)
    records = list(run_batch(config))
    manifest = _read_manifest(config.out_dir)
    assert manifest == records
    assert [r["index"] for r in manifest] == [0, 1, 2, 3]
    assert {r["doc_type"] for r in manifest} == {"compte-rendu", "bilan-biologique"}
    assert len({r["doc_id"] for r in manifest}) == 4
    for r in manifest:
        data = (config.out_dir / r["path"]).read_bytes()
        assert data.startswith(b"%PDF-")
        assert r["bytes"] == len(data)
        assert r["sha256"] == hashlib.sha256(data).hexdigest()
        assert r["synthetic"] is True
        assert r["marker"] == SYNTHETIC_MARKER
        assert r["base_seed"] == 7


@pytest.mark.parametrize("profile_name", list(PROFILES))
def test_every_page_is_openable_and_marked_synthetic(make_config, profile_name):
    config = make_config(count=4, profile=get_profile(profile_name))
    for r in run_batch(config):
        reader = PdfReader(config.out_dir / r["path"])
        assert len(reader.pages) == r["pages"] >= 1
        assert SYNTHETIC_MARKER in (reader.metadata.title or "")
        for page in reader.pages:
            assert SYNTHETIC_MARKER in page.extract_text()
        first_page = reader.pages[0].extract_text()
        assert r["entities"]["patient_name"] in first_page
        assert r["entities"]["patient_id"] in first_page


def test_multi_page_footer_numbering(make_config):
    # Un profil artificiellement très gros force plusieurs pages.
    profile = replace(get_profile("large-print"), font_size=22.0, lab_rows=(18, 20))
    config = make_config(count=1, doc_types=("bilan-biologique",), profile=profile)
    (record,) = run_batch(config)
    reader = PdfReader(config.out_dir / record["path"])
    assert record["pages"] > 1
    for number, page in enumerate(reader.pages, start=1):
        assert f"Page {number} / {record['pages']}" in page.extract_text()


def test_same_inputs_give_identical_files(make_config, tmp_path):
    a = list(run_batch(make_config(out_dir=tmp_path / "a")))
    b = list(run_batch(make_config(out_dir=tmp_path / "b")))
    assert [r["sha256"] for r in a] == [r["sha256"] for r in b]
    assert a == b


def test_document_is_independent_of_batch_size_and_start(make_config, tmp_path):
    full = list(run_batch(make_config(out_dir=tmp_path / "full", count=6)))
    part = list(run_batch(make_config(out_dir=tmp_path / "part", count=2, start_index=4)))
    assert [r["sha256"] for r in part] == [r["sha256"] for r in full[4:]]
    assert [r["seed"] for r in part] == [r["seed"] for r in full[4:]]


def test_different_batch_seed_changes_documents(make_config, tmp_path):
    a = list(run_batch(make_config(out_dir=tmp_path / "a", base_seed=1)))
    b = list(run_batch(make_config(out_dir=tmp_path / "b", base_seed=2)))
    assert [r["sha256"] for r in a] != [r["sha256"] for r in b]


def test_refuses_to_overwrite_unless_forced(make_config):
    config = make_config(count=2)
    list(run_batch(config))
    marker = config.out_dir / "pdf" / "unrelated.pdf"
    marker.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        list(run_batch(config))
    assert marker.read_bytes() == b"keep"
    forced = make_config(count=2, overwrite=True)
    with pytest.raises(ValueError, match="manifeste existant"):
        list(run_batch(forced))
    assert marker.read_bytes() == b"keep"


def test_overwrite_check_happens_before_any_write(make_config):
    config = make_config(count=3)
    list(run_batch(config))
    # Supprime uniquement le dernier fichier : le contrôle doit tout de même refuser.
    (config.out_dir / "pdf" / "SYN-000000_compte-rendu.pdf").unlink()
    before = (config.out_dir / MANIFEST_NAME).read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        list(run_batch(config))
    assert (config.out_dir / MANIFEST_NAME).read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "overrides",
    [{"doc_types": ("inconnu",)}, {"medium": "docx"}, {"count": -1}, {"doc_types": ()}],
)
def test_invalid_config_is_rejected(make_config, overrides):
    with pytest.raises(ValueError):
        list(run_batch(make_config(**overrides)))


@pytest.mark.parametrize("count", [0, 1])
def test_unknown_type_is_rejected_whatever_the_count(make_config, count):
    # Types non utilisés par le lot (count=0, ou au-delà du premier type) validés aussi.
    config = make_config(count=count, doc_types=("compte-rendu", "inconnu"))
    with pytest.raises(ValueError):
        list(run_batch(config))
    assert not (config.out_dir / MANIFEST_NAME).exists()


def test_force_refuses_to_orphan_previous_documents(make_config):
    config = make_config(count=2, doc_types=("bilan-biologique",))
    records = list(run_batch(config))
    before = (config.out_dir / MANIFEST_NAME).read_bytes()
    with pytest.raises(ValueError, match="manifeste existant"):
        list(run_batch(replace(config, count=1, overwrite=True)))
    assert (config.out_dir / MANIFEST_NAME).read_bytes() == before
    assert all((config.out_dir / r["path"]).exists() for r in records)


def test_broken_symlink_is_an_existing_target(make_config):
    config = make_config(count=1)
    target = config.out_dir / "pdf" / "SYN-000000_compte-rendu.pdf"
    target.parent.mkdir(parents=True)
    target.symlink_to("missing")
    with pytest.raises(FileExistsError):
        list(run_batch(config))
    assert target.is_symlink()


def test_manifest_records_full_profile_and_python(make_config):
    import platform

    profile = replace(get_profile("standard"), font_size=17)
    (record,) = run_batch(make_config(count=1, profile=profile, doc_types=("bilan-biologique",)))
    assert record["python_version"] == platform.python_version()
    assert record["profile_parameters"]["font_size"] == 17
    assert _read_manifest(make_config().out_dir)[0]["profile_parameters"]["lab_rows"] == list(
        profile.lab_rows
    )


def test_concurrent_batch_is_rejected(make_config):
    config = make_config(count=2, doc_types=("bilan-biologique",))
    first = run_batch(config)
    next(first)
    with pytest.raises(FileExistsError, match="en cours"):
        list(run_batch(make_config(count=1, overwrite=True)))
    first.close()


def test_permissions_follow_umask(make_config):
    import os

    previous = os.umask(0o027)
    try:
        config = make_config(count=1)
        (record,) = run_batch(config)
    finally:
        os.umask(previous)
    assert (config.out_dir / MANIFEST_NAME).stat().st_mode & 0o777 == 0o640
    assert (config.out_dir / record["path"]).stat().st_mode & 0o777 == 0o640


def test_medium_symlink_rejected(make_config, tmp_path):
    config = make_config(count=1, overwrite=True)
    config.out_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (config.out_dir / "pdf").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="lien symbolique"):
        list(run_batch(config))
    assert not list(external.iterdir())
    assert not (config.out_dir / MANIFEST_NAME).exists()


def test_render_failure_preserves_completed_records(make_config, monkeypatch):
    from synthetic_doc_gen import batch

    config = make_config(count=2)
    original = batch.build_document

    def fail_second(index, *args):
        if index == 1:
            raise OSError("panne")
        return original(index, *args)

    monkeypatch.setattr(batch, "build_document", fail_second)
    with pytest.raises(OSError, match="panne"):
        list(run_batch(config))
    (record,) = _read_manifest(config.out_dir)
    data = (config.out_dir / record["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == record["sha256"]


def test_partial_manifest_write_is_rolled_back(make_config, monkeypatch):
    from pathlib import Path

    original_open = Path.open

    class FailingStream:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, data):
            self.stream.write(data[:10])
            raise OSError("panne manifeste")

    def failing_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.name == MANIFEST_NAME and args and args[0] == "r+b":
            return FailingStream(stream)
        return stream

    monkeypatch.setattr(Path, "open", failing_open)
    config = make_config(count=1)
    with pytest.raises(OSError, match="panne manifeste"):
        list(run_batch(config))
    assert (config.out_dir / MANIFEST_NAME).read_bytes() == b""
    assert not list((config.out_dir / "pdf").glob("*.pdf"))

import json

import pytest

from synthetic_doc_gen.cli import main


def records(out):
    return [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]


def test_total_first_prefix_and_ratio(tmp_path):
    out = tmp_path / "out"
    assert (
        main(
            [
                "generate",
                "-o",
                str(out),
                "--total-size",
                "15k",
                "--scan-ratio",
                "50%",
                "--scan-dpi",
                "72",
            ]
        )
        == 0
    )
    rows = records(out)
    report = json.loads((out / "report.json").read_text())
    sizes = [r["bytes"] for r in rows]
    assert sum(sizes[:-1]) < 15000 <= sum(sizes)
    assert report["total_target"]["obtained_bytes"] == sum(sizes)
    assert report["measured"]["scan_ratio"] == round(
        sum(r["render"]["kind"] == "scan" for r in rows) / len(rows), 4
    )


def test_minimum_and_limit(tmp_path):
    out = tmp_path / "min"
    assert main(["generate", "-o", str(out), "--total-size", "1"]) == 0
    assert len(records(out)) == 1
    out = tmp_path / "limit"
    assert main(["generate", "-o", str(out), "--total-size", "1M", "--max-count", "1"]) == 2
    assert not json.loads((out / "report.json").read_text())["total_target"]["reached"]


def test_calibration_replay(tmp_path):
    outputs = [tmp_path / "a", tmp_path / "b"]
    for out in outputs:
        assert (
            main(
                [
                    "generate",
                    "-o",
                    str(out),
                    "--total-size",
                    "10k",
                    "--target-size",
                    "20k",
                    "--scan-ratio",
                    "100%",
                    "--calibration-count",
                    "2",
                    "--seed",
                    "42",
                ]
            )
            == 0
        )
    a, b = map(records, outputs)
    assert [r["sha256"] for r in a] == [r["sha256"] for r in b]
    assert (
        json.loads((outputs[0] / "report.json").read_text())["requested"]["calibration_count"] == 2
    )


def test_invalid_and_existing(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        main(["generate", "-o", str(out), "-n", "1", "--total-size", "1k"])
    assert main(["generate", "-o", str(out), "--total-size", "1k", "--max-count", "0"]) == 2
    assert not out.exists()
    path = out / "pdf" / "SYN-000000_compte-rendu.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing")
    assert main(["generate", "-o", str(out), "--total-size", "1k"]) == 2
    assert path.read_bytes() == b"existing"
    assert not (out / "manifest.jsonl").exists()


def test_interruption_preserves_manifest(tmp_path, monkeypatch):
    from synthetic_doc_gen import batch

    original = batch.build_document

    def interrupted(index, *args):
        if index == 1:
            raise KeyboardInterrupt
        return original(index, *args)

    monkeypatch.setattr(batch, "build_document", interrupted)
    out = tmp_path / "out"
    with pytest.raises(KeyboardInterrupt):
        main(["generate", "-o", str(out), "--total-size", "1M"])
    rows = records(out)
    assert len(rows) == 1 and (out / rows[0]["path"]).exists()
    assert not (out / "report.json").exists()

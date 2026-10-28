import json

import pytest

from synthetic_doc_gen.cli import main


def test_generate_via_cli(tmp_path, capsys):
    out = tmp_path / "out"
    code = main(
        [
            "generate",
            "-o",
            str(out),
            "-n",
            "3",
            "-s",
            "5",
            "-t",
            "bilan-biologique",
            "-p",
            "compact",
        ]
    )
    assert code == 0
    assert "3 document(s)" in capsys.readouterr().out
    records = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
    assert len(records) == 3
    assert {r["doc_type"] for r in records} == {"bilan-biologique"}
    assert {r["profile"] for r in records} == {"compact"}
    assert all((out / r["path"]).is_file() for r in records)


def test_cli_reports_existing_files_with_exit_code_2(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["generate", "-o", str(out), "-n", "1"]) == 0
    capsys.readouterr()
    assert main(["generate", "-o", str(out), "-n", "1"]) == 2
    assert "existent déjà" in capsys.readouterr().err
    assert main(["generate", "-o", str(out), "-n", "1", "--force"]) == 2


def test_cli_rejects_unknown_type(tmp_path, capsys):
    assert main(["generate", "-o", str(tmp_path / "o"), "-t", "radio"]) == 2
    assert "type de document inconnu" in capsys.readouterr().err


def test_cli_rejects_unknown_profile(tmp_path):
    with pytest.raises(SystemExit):
        main(["generate", "-o", str(tmp_path / "o"), "-p", "nope"])


def test_list_command(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "compte-rendu" in out and "bilan-biologique" in out and "standard" in out
    assert "pdf" in out


def test_cli_rejects_unknown_type_with_empty_batch(tmp_path, capsys):
    out = tmp_path / "o"
    assert main(["generate", "-o", str(out), "-n", "0", "-t", "inconnu"]) == 2
    assert "type de document inconnu" in capsys.readouterr().err
    assert not (out / "manifest.jsonl").exists()


def test_cli_reports_partial_failure_without_traceback(tmp_path, capsys, monkeypatch):
    from synthetic_doc_gen import batch

    original = batch.build_document

    def fail_second(index, *args):
        if index == 1:
            raise OSError("disque plein")
        return original(index, *args)

    monkeypatch.setattr(batch, "build_document", fail_second)
    out = tmp_path / "out"
    assert main(["generate", "-o", str(out), "-n", "2", "-t", "bilan-biologique"]) == 2
    error = capsys.readouterr().err
    assert "échec partiel" in error and "disque plein" in error
    assert "Traceback" not in error
    records = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
    assert len(records) == 1 and (out / records[0]["path"]).is_file()

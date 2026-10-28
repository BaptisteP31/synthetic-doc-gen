import json

import pytest

from synthetic_doc_gen.batch import run_batch


def test_parallel_reproducible_and_sharded(make_config, tmp_path):
    one = list(run_batch(make_config(out_dir=tmp_path / "one", count=5, shard_size=2)))
    many = list(run_batch(make_config(out_dir=tmp_path / "many", count=5, shard_size=2, jobs=2)))
    assert many == one
    assert [r["index"] for r in many] == list(range(5))
    for record in many:
        path = tmp_path / "many" / record["path"]
        assert path.is_file()
        assert path.parent.name == f"{record['index'] // 2:06d}"


def test_parallel_total_stops_at_same_prefix(make_config, tmp_path):
    args = {"total_size": 10000, "max_count": 8, "shard_size": 2}
    one = list(run_batch(make_config(out_dir=tmp_path / "one", **args)))
    many = list(run_batch(make_config(out_dir=tmp_path / "many", jobs=3, **args)))
    assert many == one
    assert sum(r["bytes"] for r in many[:-1]) < 10000 <= sum(r["bytes"] for r in many)
    assert len(list((tmp_path / "many" / "pdf").rglob("*.pdf"))) == len(many)


def test_parallel_close_keeps_published_prefix(make_config, tmp_path):
    out = tmp_path / "out"
    batch = run_batch(make_config(out_dir=out, count=5, jobs=2))
    first = next(batch)
    batch.close()
    assert [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()] == [
        first
    ]
    assert len(list((out / "pdf").glob("*.pdf"))) == 1
    assert not (out / "report.json").exists()


def test_shard_symlink_rejected_before_publication(make_config, tmp_path):
    out = tmp_path / "out"
    (out / "pdf").mkdir(parents=True)
    (out / "pdf" / "000001").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="lien symbolique"):
        list(run_batch(make_config(out_dir=out, count=3, shard_size=2, jobs=2)))
    assert not (out / "manifest.jsonl").exists()


@pytest.mark.parametrize("option", [{"jobs": 0}, {"shard_size": 0}])
def test_invalid_parallel_options(make_config, option):
    with pytest.raises(ValueError):
        list(run_batch(make_config(**option)))


def test_parallel_worker_error_preserves_prefix(make_config, tmp_path, monkeypatch):
    from concurrent.futures import Future

    from synthetic_doc_gen import batch as batch_module

    class Executor:
        def __init__(self, **kwargs):
            pass

        def submit(self, function, config, item, options):
            future = Future()
            if item.index == 1:
                future.set_exception(ValueError("échec du rendu"))
            else:
                future.set_result(function(config, item, options))
            return future

        def shutdown(self, **kwargs):
            pass

    monkeypatch.setattr(batch_module, "ProcessPoolExecutor", Executor)
    out = tmp_path / "error"
    with pytest.raises(ValueError, match="échec du rendu"):
        list(run_batch(make_config(out_dir=out, count=4, jobs=2)))
    rows = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
    assert [row["index"] for row in rows] == [0]
    assert len(list((out / "pdf").glob("*.pdf"))) == 1
    assert not (out / "report.json").exists()


def test_parallel_total_defers_fit_error_beyond_required_prefix(make_config, tmp_path):
    args = {
        "total_size": 1,
        "max_count": 2,
        "pages": (1, 1),
        "doc_types": ("compte-rendu", "compte-rendu-imagerie"),
    }
    one = list(run_batch(make_config(out_dir=tmp_path / "one", **args)))
    many = list(run_batch(make_config(out_dir=tmp_path / "many", jobs=2, **args)))
    assert many == one
    assert len(many) == 1
    assert json.loads((tmp_path / "many" / "report.json").read_text())["total_target"]["reached"]


@pytest.mark.parametrize("jobs", [1, 2])
def test_total_fit_error_preserves_published_prefix(make_config, tmp_path, jobs):
    out = tmp_path / str(jobs)
    config = make_config(
        out_dir=out,
        total_size=10**9,
        max_count=2,
        pages=(1, 1),
        doc_types=("compte-rendu", "compte-rendu-imagerie"),
        jobs=jobs,
    )
    with pytest.raises(ValueError):
        list(run_batch(config))
    rows = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
    assert [row["index"] for row in rows] == [0]
    assert len(list((out / "pdf").glob("*.pdf"))) == 1
    assert not (out / "report.json").exists()

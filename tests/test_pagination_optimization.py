from synthetic_doc_gen.batch import run_batch
from synthetic_doc_gen.pagination import fit_pages
from synthetic_doc_gen.renderers.pdf import ReportLabPdfRenderer


def test_search_preserves_first_exact_unit_for_varied_thresholds():
    for target in (2, 10, 20):
        for width in (1, 3, 7, 20):
            document, units = fit_pages(int, lambda k, w=width: 1 + k // w, target)
            assert document == units == (target - 1) * width


def test_native_output_reuses_winning_render(make_config, monkeypatch):
    calls = []
    original = ReportLabPdfRenderer.render_native

    def counted(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        calls.append(result.data)
        return result

    monkeypatch.setattr(ReportLabPdfRenderer, "render_native", counted)
    config = make_config(count=1, doc_types=("compte-rendu",), pages=(2, 2))
    (record,) = run_batch(config)
    data = (config.out_dir / record["path"]).read_bytes()
    assert data in calls
    assert calls.count(data) == 1

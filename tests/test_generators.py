import pytest

from synthetic_doc_gen.generators import GENERATORS
from synthetic_doc_gen.generators.lab_report import CATALOG
from synthetic_doc_gen.model import Table
from synthetic_doc_gen.profiles import PROFILES
from synthetic_doc_gen.seeding import make_rng


@pytest.mark.parametrize("profile", PROFILES.values(), ids=list(PROFILES))
@pytest.mark.parametrize("doc_type", GENERATORS)
def test_generators_produce_fictional_entities(doc_type, profile):
    for seed in range(20):
        doc = GENERATORS[doc_type](make_rng(seed), profile)
        assert doc.doc_type == doc_type
        assert doc.entities["patient_id"].startswith("SYN-PAT-")
        assert doc.entities["patient_name"]


def test_lab_flags_match_displayed_values():
    doc = GENERATORS["bilan-biologique"](make_rng(5), PROFILES["compact"])
    by_name = {a.name: a for a in CATALOG}
    checked = 0
    for block in doc.blocks:
        if not isinstance(block, Table):
            continue
        for i, (name, value, unit, _ref, flag) in enumerate(block.rows):
            analyte = by_name[name]
            shown = float(value.replace(",", "."))
            expected = "H" if shown > analyte.high else "B" if shown < analyte.low else ""
            assert flag == expected
            assert (i in block.emphasized_rows) == bool(flag)
            assert unit == analyte.unit
            checked += 1
    assert checked == int(doc.entities["n_results"])


def test_abnormal_count_in_entities_is_consistent():
    for seed in range(10):
        doc = GENERATORS["bilan-biologique"](make_rng(seed), PROFILES["standard"])
        flagged = sum(1 for b in doc.blocks if isinstance(b, Table) for r in b.rows if r[4])
        assert flagged == int(doc.entities["n_abnormal"])


def test_profile_controls_lab_length():
    short = GENERATORS["bilan-biologique"](make_rng(1), PROFILES["large-print"])
    long = GENERATORS["bilan-biologique"](make_rng(1), PROFILES["compact"])
    assert int(short.entities["n_results"]) <= 9
    assert int(long.entities["n_results"]) >= 16

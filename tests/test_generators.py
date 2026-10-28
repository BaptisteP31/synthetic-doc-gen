import re

import pytest

from synthetic_doc_gen.generators import GENERATORS
from synthetic_doc_gen.generators.lab_report import CATALOG
from synthetic_doc_gen.model import KeyValues, Paragraph, Table
from synthetic_doc_gen.profiles import PROFILES
from synthetic_doc_gen.seeding import make_rng


def _kv(doc) -> dict[str, str]:
    return dict(next(b for b in doc.blocks if isinstance(b, KeyValues)).items)


def _text(doc) -> str:
    return "\n".join(b.text for b in doc.blocks if isinstance(b, Paragraph))


def _reports(n: int = 400, doc_type: str = "compte-rendu"):
    for seed in range(n):
        doc = GENERATORS[doc_type](make_rng(seed), PROFILES["standard"])
        kv = _kv(doc)
        age = int(kv["Date de naissance"].split("(")[1].split()[0])
        yield doc, kv, age


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
    sex = _kv(doc)["Sexe"]
    for block in doc.blocks:
        if not isinstance(block, Table):
            continue
        for i, (name, value, unit, _ref, flag) in enumerate(block.rows):
            analyte = by_name[name]
            low, high = analyte.bounds(sex)
            shown = float(value.replace(",", "."))
            expected = "H" if shown > high else "B" if shown < low else ""
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


def test_geriatrics_only_for_seniors():
    services = set()
    for doc, _unused, age in _reports():
        services.add(doc.entities["service"])
        if doc.entities["service"] == "Gériatrie":
            assert age >= 65
    assert "Gériatrie" in services


def test_gestational_diabetes_only_for_adult_women():
    seen = 0
    for doc, _unused, age in _reports(800):
        if "gestationnel" in _text(doc):
            seen += 1
            assert age >= 18
            assert "Madame" in _text(doc)
    assert seen


def test_minors_get_age_appropriate_content():
    adult_only = (
        "tabagisme",
        "exposition professionnelle",
        "dyslipidémie",
        "hypertension",
        "diabète de type 2",
        "tension artérielle",
        "Madame",
        "Monsieur",
        "1000 mg",
    )
    minors = 0
    for doc, _unused, age in _reports(800):
        if age >= 18:
            continue
        minors += 1
        text = _text(doc)
        assert "jeune patient" in text and "accompagne" in text
        for term in adult_only:
            if term == "tension artérielle":
                continue  # constantes mesurées pour tous, pas un antécédent
            assert term not in text, (term, text)
    assert minors


def test_clinical_text_agrees_with_sex():
    seen = set()
    for doc, _unused, age in _reports(300):
        text = _text(doc)
        female = "Madame" in text if age >= 18 else "jeune patiente" in text
        seen.add(female)
        assert ("reçue en" in text) == female
        assert ("reçu en" in text) == (not female)
        masculine = re.search(r"\bpatient\b", text)
        assert not (female and masculine)
    assert seen == {True, False}


def test_lab_reference_ranges_follow_sex():
    by_name = {a.name: a for a in CATALOG}
    seen = set()
    for doc, kv, _age in _reports(60, "bilan-biologique"):
        seen.add(kv["Sexe"])
        for block in doc.blocks:
            if isinstance(block, Table):
                for name, _v, _u, ref, _f in block.rows:
                    low, high = by_name[name].bounds(kv["Sexe"])
                    assert ref.replace(",", ".").split(" - ") == [
                        f"{low:.{by_name[name].decimals}f}",
                        f"{high:.{by_name[name].decimals}f}",
                    ]
    assert seen == {"F", "M"}


def test_lab_report_flags_pediatric_reference_values():
    notes = {
        age < 18: "mineur" in _text(doc) for doc, _unused, age in _reports(200, "bilan-biologique")
    }
    assert notes == {True: True, False: False}


def test_clinical_service_wording_and_neutral_conclusion():
    endocrinology_seen = False
    for doc, _kv, _age in _reports(400):
        text = _text(doc)
        assert "Évaluation clinique à poursuivre selon le motif de consultation." in text
        if doc.entities["service"] == "Endocrinologie":
            endocrinology_seen = True
            assert "consultation d'endocrinologie" in text
    assert endocrinology_seen


def test_minor_lab_label_agrees_with_sex():
    seen = set()
    for doc, kv, age in _reports(400, "bilan-biologique"):
        if age < 18:
            seen.add(kv["Sexe"])
            assert ("Patiente mineure" if kv["Sexe"] == "F" else "Patient mineur") in _text(doc)
    assert seen == {"F", "M"}

from synthetic_doc_gen.batch import build_document, doc_type_for
from synthetic_doc_gen.profiles import get_profile
from synthetic_doc_gen.seeding import derive_seed


def test_derive_seed_is_stable_and_distinct():
    # Valeur figée : SHA-256 ne dépend ni de la plateforme ni du processus.
    assert derive_seed(42, 0, "compte-rendu") == 11056949009711432978
    seeds = {derive_seed(1, i, t) for i in range(50) for t in ("compte-rendu", "bilan-biologique")}
    assert len(seeds) == 100


def test_document_content_is_deterministic_and_seed_dependent():
    profile = get_profile("standard")
    a, _ = build_document(3, 1, "bilan-biologique", profile)
    b, _ = build_document(3, 1, "bilan-biologique", profile)
    c, _ = build_document(3, 2, "bilan-biologique", profile)
    assert a == b
    assert a != c


def test_type_assignment_depends_only_on_index():
    types = ("compte-rendu", "bilan-biologique")
    assert [doc_type_for(i, types) for i in range(4)] == [
        "compte-rendu",
        "bilan-biologique",
        "compte-rendu",
        "bilan-biologique",
    ]

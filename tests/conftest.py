from pathlib import Path

import pytest

from synthetic_doc_gen.batch import BatchConfig
from synthetic_doc_gen.profiles import get_profile


@pytest.fixture
def make_config(tmp_path: Path):
    def _make(**overrides) -> BatchConfig:
        params = {
            "out_dir": tmp_path / "out",
            "count": 4,
            "base_seed": 7,
            "doc_types": ("compte-rendu", "bilan-biologique"),
            "profile": get_profile("standard"),
        }
        params.update(overrides)
        return BatchConfig(**params)

    return _make

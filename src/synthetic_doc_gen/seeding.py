"""Dérivation déterministe des graines : une graine indépendante par document."""

from __future__ import annotations

import hashlib
import random


def derive_seed(base_seed: int, index: int, doc_type: str) -> int:
    """Graine 64 bits d'un document, fonction de (graine de lot, index, type).

    Basée sur SHA-256 (et non sur ``hash()``, randomisé par processus), elle ne dépend
    ni du nombre de documents du lot ni de la présence des autres documents : régénérer
    le document ``index`` seul redonne le même contenu.
    """
    digest = hashlib.sha256(f"{base_seed}:{index}:{doc_type}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def make_rng(seed: int) -> random.Random:
    return random.Random(seed)

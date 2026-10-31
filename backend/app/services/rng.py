"""Server-side card drawing (spec §8).

Uses `secrets.SystemRandom` — the backend is the only source of randomness.
MVP: all cards are drawn upright (reversed orientations are disabled until
reversal content is prepared — documented product decision).
"""
from __future__ import annotations

import secrets


def draw_cards(card_ids: list[int], count: int) -> list[tuple[int, str]]:
    """Draw `count` unique cards without replacement using a CSPRNG.

    Returns a list of (card_id, orientation) tuples; orientation is always
    "upright" in the MVP.
    """
    if count > len(card_ids):
        raise ValueError("spread requires more cards than deck size")
    picked = secrets.SystemRandom().sample(card_ids, count)
    return [(cid, "upright") for cid in picked]

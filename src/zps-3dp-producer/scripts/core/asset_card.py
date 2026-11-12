"""What the asset card changes in the pipeline of one asset: the `views` field (D35)."""
from __future__ import annotations

import re
from pathlib import Path

SIDE_IMAGE = re.compile(r"^final/(back|left|right|top)\.png$")
SIDE_TILE = re.compile(r"[/_](back|left|right|top)(?:_guide)?\.png$")


def views(st: dict) -> str:
    from check_card import card_views
    return card_views(st.get("concept_dir"))


def card(st: dict) -> dict:
    """The asset card as a map; {} for an asset made by `new` (no card) or a card that is not a map."""
    from check_card import CARD
    from check_profile import load_yaml
    f = Path(st["concept_dir"]) / CARD if st.get("concept_dir") else None
    c = load_yaml(f) if f and f.is_file() else None
    return c if isinstance(c, dict) else {}


def sides(st: dict) -> tuple[str, ...]:
    """The side views this asset's views step makes besides front."""
    from check_card import NO_CARD_VIEWS, VIEW_SETS
    return VIEW_SETS.get(views(st), VIEW_SETS[NO_CARD_VIEWS])


def skipped(step: dict, st: dict) -> bool:
    """A `views_set` step (pipeline.toml) does not run for a card with `views: none`."""
    return bool(step.get("views_set")) and views(st) == "none"


def keep_output(step: dict, st: dict, out: str) -> bool:
    """A `views_set` step needs only the side images of the card's views."""
    m = SIDE_IMAGE.match(out) if step.get("views_set") else None
    return not m or m[1] in sides(st)


def sheet(step: dict, st: dict) -> list[str]:
    """A `views_set` step shows on its review sheet only the sides of the card's views: the guides of all five exist."""
    return [g for g in step.get("sheet") or [] if not step.get("views_set") or not (m := SIDE_TILE.search(g))
            or m[1] in sides(st)]


def regions(step: dict, st: dict) -> list[str]:
    return [r for r in step["regions"] if r not in ("back", "left", "right", "top") or r in sides(st)] \
        if step.get("views_set") else step["regions"]


def steps(cfg: dict, st: dict) -> list[dict]:
    """The steps this asset runs, in pipeline order."""
    return [s for s in cfg["steps"] if not skipped(s, st)]

"""What the asset card changes in the pipeline of one asset: the `views` field (D35)."""
from __future__ import annotations

import re

SIDE_IMAGE = re.compile(r"^final/(back|left|right|top)\.png$")


def views(st: dict) -> str:
    from check_card import card_views
    return card_views(st.get("concept_dir"))


def sides(st: dict) -> tuple[str, ...]:
    """The side views this asset's views_rest makes."""
    from check_card import DEFAULT_VIEWS, VIEW_SETS
    return VIEW_SETS.get(views(st), VIEW_SETS[DEFAULT_VIEWS])


def skipped(step: dict, st: dict) -> bool:
    """A `views_set` step (pipeline.toml) does not run for a card with `views: none`."""
    return bool(step.get("views_set")) and views(st) == "none"


def keep_output(step: dict, st: dict, out: str) -> bool:
    """A `views_set` step needs only the side images of the card's views."""
    m = SIDE_IMAGE.match(out) if step.get("views_set") else None
    return not m or m[1] in sides(st)


def regions(step: dict, st: dict) -> list[str]:
    return [r for r in step["regions"] if r not in ("back", "left", "right", "top") or r in sides(st)] \
        if step.get("views_set") else step["regions"]


def steps(cfg: dict, st: dict) -> list[dict]:
    """The steps this asset runs, in pipeline order."""
    return [s for s in cfg["steps"] if not skipped(s, st)]

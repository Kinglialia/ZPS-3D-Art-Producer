#!/usr/bin/env python3
"""Kiểm thư mục `_approved/<id>/`: `check_card.py <dir> [--profile PROJECT-PROFILE.yaml]`.
Mỗi lỗi một dòng, thoát 1 nếu có lỗi. Không có --profile thì không biết has_map: bỏ qua size_m bắt buộc và layout.md."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_profile import is_num, is_pos_int, is_str, load_yaml

TYPES = ("building", "prop", "tree", "rock")
UNSUPPORTED = ("character", "creature")
TIERS = ("hero", "standard", "background")
REQUIRED = ("asset", "type", "tier", "symmetric", "hidden_sides", "real_texture_only_notes")
CARD = "asset-card.yaml"
SIDES = {"back", "left", "right", "top", "bottom", "front"}


def required_files(aid: str, has_map: bool | None) -> list[str]:
    return ["concept_albedo.png", "concept_shadow.png", CARD, f"{aid}.material.md"] + (
        [f"{aid}.layout.md"] if has_map else [])


def check(d: Path, has_map: bool | None) -> list[tuple[str, str]]:
    errs: list[tuple[str, str]] = []
    for name in required_files(d.name, has_map):
        f = d / name
        if not (f.is_file() and f.stat().st_size > 0):
            errs.append(("files", f"thiếu file {name}"))
    if any(m == f"thiếu file {CARD}" for _, m in errs):
        return errs
    try:
        c = load_yaml(d / CARD)
    except (ValueError, FileNotFoundError):
        return errs + [("card", "thẻ: YAML sai")]
    if not isinstance(c, dict):
        return errs + [("card", "thẻ sai: cần map")]

    def bad(key: str, need: str, group: str = "card"):
        errs.append((group, f"thẻ: {key} sai: {need}"))

    errs.extend(("card", f"thẻ: thiếu trường {k}") for k in REQUIRED if k not in c)
    if "asset" in c and c["asset"] != d.name:
        bad("asset", f"'{c['asset']}' khác tên thư mục '{d.name}'")
    if "type" in c:
        if c["type"] in UNSUPPORTED:
            errs.append(("type", f"thẻ: type '{c['type']}' v1 chưa hỗ trợ"))
        elif c["type"] not in TYPES:
            bad("type", f"'{c['type']}' ({' | '.join(TYPES)})")
    if "tier" in c and c["tier"] not in TIERS:
        bad("tier", f"'{c['tier']}' ({' | '.join(TIERS)})")
    for k in ("texture_res", "tris_max"):
        if c.get(k) is not None and not is_pos_int(c[k]):
            bad(k, "cần số nguyên > 0 hoặc null")
    if c.get("scale_overrides") is not None:
        so = c["scale_overrides"]
        if not (isinstance(so, list) and all(
                isinstance(o, dict) and is_str(o.get("name")) and is_num(o.get("height_m")) and o["height_m"] > 0
                for o in so)):
            bad("scale_overrides", "cần danh sách {name, height_m > 0}")
    if "symmetric" in c:
        s = c["symmetric"]
        if not (isinstance(s, dict) and set(s) == {"left_right", "front_back"} and all(isinstance(v, bool) for v in s.values())):
            bad("symmetric", "cần {left_right, front_back} là true | false")
    if "hidden_sides" in c:
        h = c["hidden_sides"]
        ok_list = isinstance(h, list) and h and all(is_str(x) for x in h)
        ok_map = isinstance(h, dict) and h and set(h) <= SIDES and all(is_str(x) for x in h.values())
        if not (ok_list or ok_map):
            bad("hidden_sides", "cần danh sách chuỗi, hoặc {back|left|right|top|bottom|front: chuỗi}, "
                "ít nhất một dòng (ghi 'chưa biết' nếu chưa rõ)")
    if "real_texture_only_notes" in c:
        n = c["real_texture_only_notes"]
        if not (isinstance(n, list) and all(is_str(x) for x in n)):
            bad("real_texture_only_notes", "cần danh sách chuỗi")
    sm = c.get("size_m")
    if sm is None:
        if has_map is False:
            errs.append(("card", "thẻ: size_m thiếu (bắt buộc khi has_map: false)"))
    elif not (isinstance(sm, dict) and set(sm) == {"w", "d", "h"} and all(is_num(v) and v > 0 for v in sm.values())):
        bad("size_m", "cần {w, d, h} là số mét > 0")
    return errs


def has_map_of(profile: Path) -> bool:
    p = load_yaml(profile)
    if not isinstance(p, dict) or not isinstance(p.get("has_map"), bool):
        raise ValueError("thiếu has_map")
    return p["has_map"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--profile", type=Path)
    a = ap.parse_args()
    has_map = None
    if a.profile:
        try:
            has_map = has_map_of(a.profile)
        except (ValueError, FileNotFoundError):
            print(f"profile: không đọc được {a.profile}")
            sys.exit(1)
    d = a.dir.resolve()
    errs = check(d, has_map)
    if errs:
        print("\n".join(m for _, m in errs))
        sys.exit(1)


if __name__ == "__main__":
    main()

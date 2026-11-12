#!/usr/bin/env python3
"""Kiểm thư mục `_approved/<id>/`: `check_card.py <dir> [--profile PROJECT-PROFILE.yaml]`.
Mỗi lỗi một dòng, thoát 1 nếu có lỗi. Không có --profile thì không biết has_map: bỏ qua size_m bắt buộc và layout.md;
cũng không biết `counts_keys` của dự án: không cảnh báo khóa `counts` (D34.3).
Cảnh báo in sau lỗi, mỗi dòng bắt đầu bằng "cảnh báo:", không đổi mã thoát."""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image

from check_profile import is_num, is_pos_int, is_str, load_yaml

TYPES = ("building", "prop", "tree", "rock")
UNSUPPORTED = ("character", "creature")
TIERS = ("hero", "standard", "background")
REQUIRED = ("asset", "type", "tier", "view", "views", "counts", "symmetric", "hidden_sides", "real_texture_only_notes")
CARD = "asset-card.yaml"
SIDES = ("back", "left", "right", "top")
VIEWS = ("front", "34", "game_camera")
VIEW_SIDES = ("left", "right")
LIGHT_FROM = ("left", "right", "front")
BEVELS = ("none", "toon")
# D35: `views` -> the side views views_rest makes; views_front always makes front unless `none`.
VIEW_SETS = {"none": (), "back": ("back",), "full": ("back", "left", "right"), "full_top": ("back", "left", "right", "top")}
NO_CARD_VIEWS = "full"
IMAGES = ("concept_albedo.png", "concept_shadow.png")
IMAGE_34 = "concept_34.png"
MIN_EDGE = 1024
BORDER_PX, BORDER_TOL, BORDER_OFF_MAX = 4, 12, 0.02


def required_files(aid: str, has_map: bool | None) -> list[str]:
    return ["concept_albedo.png", "concept_shadow.png", CARD, f"{aid}.material.md"] + (
        [f"{aid}.layout.md"] if has_map else [])


def views_of(card) -> str:
    """The card's `views` mode. check() refuses a card without it (D43.6); a card registered before that rule gets
    NO_CARD_VIEWS here instead of a crash. A wrong value is check()'s error, not this function's."""
    v = card.get("views") if isinstance(card, dict) else None
    return NO_CARD_VIEWS if v is None else str(v)


def card_views(concept_dir) -> str:
    """views_of() of `<concept_dir>/asset-card.yaml`; no dir or no card (an asset made by `new`) = full."""
    f = Path(concept_dir) / CARD if concept_dir else None
    return views_of(load_yaml(f)) if f and f.is_file() else NO_CARD_VIEWS


def present(f: Path) -> bool:
    return f.is_file() and f.stat().st_size > 0


def image_errors(d: Path) -> list[tuple[str, str]]:
    sizes = {}
    for name in IMAGES:
        if present(d / name):
            try:
                with Image.open(d / name) as im:
                    sizes[name] = im.size
            except OSError:
                return [("files", f"ảnh {name}: không đọc được")]
    if len(sizes) < 2:
        return []
    (a, sa), (b, sb) = sizes.items()
    if sa != sb:
        return [("files", f"ảnh concept: {a} {sa[0]}x{sa[1]} khác {b} {sb[0]}x{sb[1]}, cần trùng khung")]
    if max(sa) < MIN_EDGE:
        return [("files", f"ảnh concept: cạnh dài {max(sa)} px, cần ≥ {MIN_EDGE} px")]
    return []


def image_34_errors(d: Path) -> list[tuple[str, str]]:
    """concept_34.png is optional and shows another angle, so it need not share the frame of the other two."""
    if not (d / IMAGE_34).is_file():
        return []
    try:
        with Image.open(d / IMAGE_34) as im:
            edge = max(im.size)
    except OSError:
        return [("files", f"ảnh {IMAGE_34}: không đọc được")]
    return [("files", f"ảnh {IMAGE_34}: cạnh dài {edge} px, cần ≥ {MIN_EDGE} px")] if edge < MIN_EDGE else []


def check(d: Path, has_map: bool | None) -> list[tuple[str, str]]:
    errs: list[tuple[str, str]] = []
    for name in required_files(d.name, has_map):
        if not present(d / name):
            errs.append(("files", f"thiếu file {name}"))
    errs += image_errors(d)
    errs += image_34_errors(d)
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
    if "view" in c and not (isinstance(c["view"], (str, int)) and not isinstance(c["view"], bool)
                            and str(c["view"]) in VIEWS):
        bad("view", f"'{c['view']}' ({' | '.join(VIEWS)})")
    side = c.get("view_side")
    if side is None:
        if str(c.get("view")) == "34":
            errs.append(("card", "thẻ: view_side thiếu (bắt buộc khi view: '34')"))
    elif not (isinstance(side, str) and side in VIEW_SIDES):
        bad("view_side", f"'{side}' ({' | '.join(VIEW_SIDES)})")
    if "views" in c and not (isinstance(c["views"], str) and c["views"] in VIEW_SETS):
        bad("views", f"'{c['views']}' ({' | '.join(VIEW_SETS)})")
    if "counts" in c and not (isinstance(c["counts"], dict) and all(
            is_key(k) and isinstance(v, int) and not isinstance(v, bool) and v >= 0 for k, v in c["counts"].items())):
        bad("counts", "cần map {khóa: số nguyên ≥ 0}, khóa là tên param (chữ thường, số, _; bắt đầu bằng chữ)")
    if c.get("light") is not None:
        lt = c["light"]
        if not (isinstance(lt, dict) and set(lt) == {"from", "elevation_deg"} and isinstance(lt["from"], str)
                and lt["from"] in LIGHT_FROM and is_num(lt["elevation_deg"])):
            bad("light", f"cần {{from: {' | '.join(LIGHT_FROM)}, elevation_deg: số}}")
    if c.get("marks") is not None:
        mk = c["marks"]
        if not (isinstance(mk, list) and all(
                isinstance(m, dict) and set(m) == {"name", "z_m"} and is_str(m["name"]) and is_num(m["z_m"]) and m["z_m"] > 0
                for m in mk)):
            bad("marks", "cần danh sách {name, z_m > 0}")
    if c.get("bottom_visible") is not None and not isinstance(c["bottom_visible"], bool):
        bad("bottom_visible", "cần true | false")
    if c.get("text_codes") is not None and not (isinstance(c["text_codes"], list) and all(is_str(x) for x in c["text_codes"])):
        bad("text_codes", "cần danh sách mã vật liệu (chuỗi)")
    if c.get("bevel") is not None and c["bevel"] not in BEVELS:
        bad("bevel", f"'{c['bevel']}' (null | {' | '.join(BEVELS)})")
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
        if not (isinstance(h, dict) and set(h) == set(SIDES) and all(is_str(x) for x in h.values())):
            missing = [s for s in SIDES if s not in h] if isinstance(h, dict) else []
            bad("hidden_sides", "cần đủ 4 mặt {back, left, right, top}, mỗi mặt một chuỗi (chưa biết thì ghi "
                "'chưa biết')" + (f"; thiếu: {', '.join(missing)}" if missing else ""))
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


def flat_background(f: Path) -> bool:
    with Image.open(f) as im:
        a = np.asarray(im.convert("RGBA"), float)
    k = BORDER_PX
    ring = np.concatenate([a[:k].reshape(-1, 4), a[-k:].reshape(-1, 4), a[:, :k].reshape(-1, 4), a[:, -k:].reshape(-1, 4)])
    return (np.abs(ring - np.median(ring, 0)).max(1) > BORDER_TOL).mean() <= BORDER_OFF_MAX


def is_key(k) -> bool:
    """A `counts` key becomes a param name and a `tag` of the part graph (D30.6)."""
    return isinstance(k, str) and re.fullmatch(r"[a-z][a-z0-9_]*", k) is not None


def warnings(d: Path, counts_keys: dict | None = None) -> list[str]:
    """counts_keys: the profile's `counts_keys` ({} when the profile has none); None when no profile was given."""
    out = []
    for name in (*IMAGES, IMAGE_34):
        try:
            if present(d / name) and not flat_background(d / name):
                out.append(f"cảnh báo: ảnh {name}: nền viền ảnh không phẳng một màu")
        except OSError:
            pass
    try:
        c = load_yaml(d / CARD)
    except (ValueError, FileNotFoundError):
        return out
    notes = c.get("real_texture_only_notes") if isinstance(c, dict) else None
    if isinstance(notes, list) and c.get("bevel") is None and any(k in unicodedata.normalize("NFC", str(n)).lower() for n in notes for k in ("bo cạnh", "cạnh bo")):
        out.append("cảnh báo: thẻ: real_texture_only_notes có \"bo cạnh\" nhưng bevel trống; "
                   "ghi bevel: toon hoặc none (3D Artist chỉ đọc trường bevel)")
    counts = c.get("counts") if isinstance(c, dict) else None
    if counts_keys is not None and isinstance(counts, dict) and (extra := [k for k in counts if k not in counts_keys]):
        out.append(f"cảnh báo: thẻ: counts có khóa ngoài counts_keys của profile: {', '.join(map(str, extra))}")
    return out


def profile_of(profile: Path) -> tuple[bool, dict]:
    """has_map and counts_keys ({} when absent) of the profile."""
    p = load_yaml(profile)
    if not isinstance(p, dict) or not isinstance(p.get("has_map"), bool):
        raise ValueError("thiếu has_map")
    keys = p.get("counts_keys") or {}
    return p["has_map"], keys if isinstance(keys, dict) else {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--profile", type=Path)
    a = ap.parse_args()
    has_map, counts_keys = None, None
    if a.profile:
        try:
            has_map, counts_keys = profile_of(a.profile)
        except (ValueError, FileNotFoundError):
            print(f"profile: không đọc được {a.profile}")
            sys.exit(1)
    d = a.dir.resolve()
    errs = check(d, has_map)
    lines = [m for _, m in errs] + warnings(d, counts_keys)
    if lines:
        print("\n".join(lines))
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    main()

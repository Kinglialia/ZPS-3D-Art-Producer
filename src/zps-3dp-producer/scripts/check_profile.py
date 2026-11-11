#!/usr/bin/env python3
"""Kiểm PROJECT-PROFILE.yaml: `check_profile.py <file> [--presets DIR]`. Mỗi lỗi một dòng, thoát 1 nếu có lỗi."""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

PRESETS = Path(os.environ.get("PRODUCER_PRESETS") or Path(__file__).resolve().parent.parent / "presets")
FORBIDDEN = ("approvals", "review_board")
LIGHT = ("unlit_flat", "painted_top_light")
BEVELS = ("none", "toon")
REQUIRED = ("project", "preset", "paths", "has_map", "pilot_asset", "scale_refs", "hidden_side_rules", "style",
            "texture_simple")


def load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise ValueError("YAML sai")
    except OSError:
        raise FileNotFoundError(path)


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def is_pos_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def is_str(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def check(path: Path, presets: Path = PRESETS) -> list[str]:
    try:
        p = load_yaml(path)
    except FileNotFoundError:
        return [f"profile: không đọc được {path}"]
    except ValueError as ex:
        return [f"profile: {ex}"]
    if not isinstance(p, dict):
        return ["profile sai: cần map"]
    errs = [f"thiếu trường {k}" for k in REQUIRED if k not in p]

    def bad(key: str, need: str):
        errs.append(f"{key} sai: cần {need}")

    def sub(key: str, fields: tuple[str, ...]) -> dict | None:
        if key not in p:
            return None
        if not isinstance(p[key], dict):
            bad(key, "map")
            return None
        errs.extend(f"thiếu trường {key}.{f}" for f in fields if f not in p[key])
        return p[key]

    if "project" in p and not is_str(p["project"]):
        bad("project", "chuỗi")
    if "preset" in p:
        name = p["preset"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            errs.append("preset sai: tên không hợp lệ")
        elif not (presets / f"{name}.yaml").is_file():
            errs.append(f"preset sai: không có file presets/{name}.yaml")
    if "has_map" in p and not isinstance(p["has_map"], bool):
        bad("has_map", "true | false")
    if "pilot_asset" in p and p["pilot_asset"] is not None and not is_str(p["pilot_asset"]):
        bad("pilot_asset", "mã asset hoặc null")
    if (paths := sub("paths", ("approved", "production", "deliver"))) is not None:
        for f in ("approved", "production", "deliver", "env_file"):
            if f in paths and not is_str(paths[f]):
                bad(f"paths.{f}", "chuỗi")
    if "scale_refs" in p:
        refs = p["scale_refs"]
        if not (isinstance(refs, list) and refs and all(
                isinstance(r, dict) and is_str(r.get("name")) and is_num(r.get("height_m")) and r["height_m"] > 0
                for r in refs)):
            bad("scale_refs", "danh sách {name, height_m > 0}")
    if "hidden_side_rules" in p:
        rules = p["hidden_side_rules"]
        if not (isinstance(rules, list) and all(is_str(r) for r in rules)):
            bad("hidden_side_rules", "danh sách chuỗi")
    if (style := sub("style", ("light_convention", "top_vs_side_L"))) is not None:
        if "light_convention" in style and style["light_convention"] not in LIGHT:
            bad("style.light_convention", " | ".join(LIGHT))
        if "top_vs_side_L" in style and not is_num(style["top_vs_side_L"]):
            bad("style.top_vs_side_L", "số")
        if style.get("view_bg") is not None and not is_str(style["view_bg"]):
            bad("style.view_bg", "chuỗi hoặc null")
        if "bevel" in style and style["bevel"] not in BEVELS:
            bad("style.bevel", " | ".join(BEVELS))
    if (ts := sub("texture_simple", ("max_materials", "max_color_clusters"))) is not None:
        for f in ("max_materials", "max_color_clusters"):
            if f in ts and not is_pos_int(ts[f]):
                bad(f"texture_simple.{f}", "số nguyên > 0")
    if p.get("counts_keys") is not None:
        ck = p["counts_keys"]
        if not (isinstance(ck, dict) and all(isinstance(k, str) and re.fullmatch(r"[a-z][a-z0-9_]*", k) and is_str(v)
                                             for k, v in ck.items())):
            bad("counts_keys", "map {khóa: nghĩa}, khóa là tên param (chữ thường, số, _; bắt đầu bằng chữ), nghĩa là "
                "chuỗi")
    for k in ("detail_examples", "overrides"):
        if k in p and not isinstance(p[k], dict):
            bad(k, "map")
    errs.extend(f"{k}: không thuộc profile, đặt trong production/policy.yaml" for k in FORBIDDEN if k in p)
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path)
    ap.add_argument("--presets", type=Path, default=PRESETS)
    a = ap.parse_args()
    errs = check(a.file, a.presets)
    if errs:
        print("\n".join(errs))
        sys.exit(1)


if __name__ == "__main__":
    main()

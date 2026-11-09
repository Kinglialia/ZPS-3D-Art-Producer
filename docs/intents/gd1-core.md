# Intent: GĐ 1, Producer core and blockout

## Problem

The spec (`docs/`, D1–D26) is approved, but no code exists. The user asked: "bắt đầu code theo spec… code gọn, stable và chạy nhanh", and later "đảm bảo đúng yêu cầu, không bug, thời gian chạy nhanh và ít tốn token khi chạy skill".

## Outcome

GĐ 1 of `docs/producer.md` §18 works on a synthetic pilot asset:

- `producer.py` (the base `producer` skill, renamed `zps-3dp-producer`) runs the 6-step pipeline schema, with only `blockout` wired end to end.
- Findings per version, fix rounds by finding (`PRIOR`, `COMPARE`, `PICK`), early stop, best version, `need_evidence`, `policy.yaml`, `review_human`, decision dedupe, input hashes, stale labels, `[limits]`, `preflight`.
- Intake checks (`check_card.py`, `check_profile.py`, pilot-first rule).
- The `zps-3dp-step-blockout` and `zps-3dp-check-blockout` agents with their tools.
- A minimal local review board.
- One end-to-end test drives `P brief` → fake report → `P ingest` through fix rounds to blockout approval, and asserts literal values in `status.json`, `findings.json` and `ledger.md`.

Ticket graph: `docs/intents/gd1-core-tickets.md`.

## Surfaces

- The user (art producer): reviews by images on the local board, gives feedback in chat.
- The Producer skill in the main Claude Code session: runs `P` commands and reads only their short output.
- Sub-agents `zps-3dp-step-blockout`, `zps-3dp-check-blockout`: read briefs, write reports.
- Kit v0.10.4 tools (`upstream/zps-art-assets-kit-v0.10.4`, commit 905dc93): copied, never edited.

## Constraints

- Keep the mechanisms of the base `producer` skill (D14): state in files, script decides order, briefs by file, `KEY: value` contracts.
- Token cost at run time is a first-class constraint. Every `P` command prints the shortest output the Producer needs (one JSON line or a few short lines). Briefs hold paths, not pasted content. The reviewer message back to the Producer is only `VERDICT` and `COUNTS` (D22.6).
- Speed: `producer.py` starts fast (stdlib plus PyYAML, lazy imports). Pure checks on `part_graph.json` run without Blender. Only render and gate scripts open Blender.
- Python 3.11+. Dependencies install into a venv under `.deps/` (gitignored) by `setup_deps.sh`, the kit pattern.
- No edits to copied kit files. Record each copied file with sha256 in `SOURCE.md`.
- Tests assert literal expected values and encode why the rule matters.
- Git: land on local `main` by fast-forward only. Push `main` only when the user asks. Push no new branch (CLAUDE.md).

## Out of scope

Steps `views_front`, `views_rest`, `model`, `texture`, `assemble`; Meshy; Codex image generation; review board annotation, remote board, `P show --bundle`; Codex edition, `build.py`, A/B; Project Setup skill. `pipeline.toml` declares all 6 steps, but steps after `blockout` are not wired.

## Decisions

The user's:
- Delegate to sub-agents.
- Scope is GĐ 1 only.
- Test on a synthetic asset now. The real pilot comes later when the user sends a concept.
- "Còn lại em tự quyết định cách làm."

Mine:
- Split the base `producer.py` into a small `core/` package with pinned module names, so tickets do not write the same file. The mechanism stays the same.
- Layout follows the kit: `src/zps-3dp-producer/` holds `SKILL.md`, `scripts/`, `references/`, `templates/`, `agents/`.
- Core tickets T2 → T3 → T4 run in sequence because they all touch ingest.
- `pipeline.toml` declares all 6 steps; GĐ 1 wires only `blockout`.
- PyYAML in a venv, not a hand-written YAML parser.

## Open questions

- Reviewer writes all `PRIOR` lines (checklist 49): needs a real agent run on a real concept.
- Claude Code honours `model` per dispatch and resume by SendMessage (checklist 61, 73): needs a real run.

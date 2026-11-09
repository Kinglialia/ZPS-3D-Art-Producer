"""Time and cost estimates per modeling method, learned from the project's own records.

  python3 estimate.py show [--project <root>] [--json]
  python3 estimate.py log --project <root> --method self|meshy|tripo|zps3d --minutes N
                          [--credits N] [--tris N] [--complexity 0-1] [--asset NAME] [--note TEXT]

Defaults come from estimates.json next to the skill. Records go to <root>/.zps-art/estimates.jsonl:
the skills folder can be read-only (Codex), and learning stays project data. Standard library only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

DEFAULTS = Path(__file__).resolve().parents[1] / 'estimates.json'
MIN_RECORDS = 3  # fewer records than this are noise; keep the defaults


def records(project):
    path = Path(project) / '.zps-art' / 'estimates.jsonl'
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # one bad line must not hide every other record
    return out


def show(project):
    methods = json.loads(DEFAULTS.read_text())['methods']
    recs = records(project) if project else []
    result = {}
    for key, d in methods.items():
        mine = [r for r in recs if r.get('method') == key]
        row = {'label': d['label'], 'texture': d['texture'], 'minutes': d['minutes'], 'credits': d['credits'],
               'source': 'default', 'records': len(mine)}
        if len(mine) >= MIN_RECORDS:
            mins = [r['minutes'] for r in mine]
            row['minutes'] = [min(mins), statistics.median(mins), max(mins)]
            creds = [r['credits'] for r in mine if r.get('credits') is not None]
            if creds:
                row['credits'] = statistics.median(creds)
            row['source'] = 'project median'
        result[key] = row
    return result


def log(a):
    rec = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'method': a.method,
           'minutes': a.minutes, 'credits': a.credits, 'tris': a.tris, 'complexity': a.complexity,
           'asset': a.asset, 'note': a.note}
    path = Path(a.project) / '.zps-art' / 'estimates.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return {'logged': str(path), 'record': rec}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('show'); s.add_argument('--project'); s.add_argument('--json', action='store_true')
    g = sub.add_parser('log')
    g.add_argument('--project', required=True)
    g.add_argument('--method', required=True, choices=sorted(json.loads(DEFAULTS.read_text())['methods']))
    g.add_argument('--minutes', type=float, required=True)
    g.add_argument('--credits', type=float); g.add_argument('--tris', type=int)
    g.add_argument('--complexity', type=float); g.add_argument('--asset'); g.add_argument('--note')
    a = p.parse_args()
    if a.cmd == 'log':
        print(json.dumps(log(a), indent=2, ensure_ascii=False))
        return 0
    rows = show(a.project)
    if a.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for key, r in rows.items():
        m = r['minutes']
        span = f'{m[0]}-{m[-1]} min' + (f' (median {m[1]})' if len(m) == 3 else '')
        print(f"{r['label']:22} {span:28} credits {r['credits']:<6} texture: {r['texture']:18} [{r['source']}, {r['records']} records]")
    return 0


if __name__ == '__main__':
    sys.exit(main())

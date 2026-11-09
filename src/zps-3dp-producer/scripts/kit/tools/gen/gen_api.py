"""Meshy and Tripo client for the 3D Artist paths: generate a mesh, remesh (Meshy), texture a final
mesh, read the balance. Every live call except `keys` and `balance` costs credits.

  python3 gen_api.py keys
  python3 gen_api.py balance  --provider meshy|tripo
  python3 gen_api.py generate --provider meshy|tripo --view front=<png> [--view back=<png> ...]
                              --out <dir> --budget-file <json> [--dry-run]
  python3 gen_api.py remesh   --provider meshy (--task-id <id> | --model <glb>) --polycount N
                              [--topology triangle|quad] --out <dir> --budget-file <json> [--dry-run]
  python3 gen_api.py texture  --provider meshy|tripo --model <glb with UVs> --style-image <png>
                              [--prompt TEXT] --out <dir> --budget-file <json> [--dry-run]

Keys: MESHY_API_KEY / TRIPO_API_KEY from the environment, else from the key file
~/.config/zps-art-assets-kit/.env (ZPS_ART_ENV_FILE overrides the path). Keys are never printed.
Budget file: {"max_credits": N, "used_credits": 0}. The expected cost is counted before the call,
because a failed paid call can still spend. Results are downloaded at once (Meshy deletes them
after 3 days; Tripo's URL lifetime is not documented). Standard library only. Not yet tested
against the live services: check the first live result by hand."""
import argparse
import base64
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

ENV_FILE = Path(os.environ.get('ZPS_ART_ENV_FILE', '~/.config/zps-art-assets-kit/.env')).expanduser()
KEY_ENV = {'meshy': 'MESHY_API_KEY', 'tripo': 'TRIPO_API_KEY'}
MESHY = 'https://api.meshy.ai/openapi/v1'
TRIPO = 'https://openapi.tripo3d.ai/v3'
VIEWS = ('front', 'left', 'back', 'right')
# Settings chosen for a dense, untextured mesh that the kit reduces later (paths/meshy.md, paths/tripo.md).
MESHY_GEN = {'ai_model': 'meshy-7.1', 'model_type': 'standard', 'geometry_resolution': '2k',
             'should_texture': False, 'should_remesh': False, 'save_pre_remeshed_model': True,
             'target_formats': ['glb']}
TRIPO_GEN = {'model': 'v3.1-20260211', 'texture': False, 'pbr': False, 'geometry_quality': 'detailed'}
# Credits per call from the providers' price pages (2026-11-06). The record stores what the task reports.
COST = {('meshy', 'generate'): 25, ('meshy', 'remesh'): 5, ('meshy', 'texture'): 10,
        ('tripo', 'generate'): 40, ('tripo', 'texture'): 10}
POLL_S, TIMEOUT_S = 5, 1200


class BudgetError(Exception):
    pass


def read_env_file(path=ENV_FILE):
    out = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def key_for(provider):
    return os.environ.get(KEY_ENV[provider]) or read_env_file().get(KEY_ENV[provider]) or None


def data_uri(path, mime=None):
    mime = mime or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()


def parse_views(items):
    views = {}
    for item in items or []:
        name, _, p = item.partition('=')
        if name not in VIEWS or not p:
            raise ValueError(f'--view must be <{"|".join(VIEWS)}>=<image>, got {item!r}')
        views[name] = Path(p)
    if 'front' not in views:
        raise ValueError('a front view is required')
    for p in views.values():
        if not p.is_file():
            raise ValueError(f'missing image {p}')
    return views


def plan(a):
    """Describe every HTTP step of the job. Pure: no network, no key. Files appear as
    {"upload": path} (Tripo) or {"data_uri": path} (Meshy) and are read only at send time."""
    pv, op = a.provider, a.op
    if pv == 'meshy':
        if op == 'generate':
            views = parse_views(a.view)
            if len(views) == 1:
                body = dict(MESHY_GEN, image_url={'data_uri': str(views['front'])})
                return [('POST', f'{MESHY}/image-to-3d', body)], 'image-to-3d'
            order = ['front'] + [v for v in VIEWS if v in views and v != 'front']  # first image = front
            body = dict(MESHY_GEN, image_urls=[{'data_uri': str(views[v])} for v in order])
            return [('POST', f'{MESHY}/multi-image-to-3d', body)], 'multi-image-to-3d'
        if op == 'remesh':
            body = {'topology': a.topology, 'target_polycount': a.polycount, 'target_formats': ['glb']}
            if a.task_id:
                body['input_task_id'] = a.task_id
            else:
                body['model_url'] = {'data_uri': a.model, 'mime': 'application/octet-stream'}
            return [('POST', f'{MESHY}/remesh', body)], 'remesh'
        if op == 'texture':
            body = {'model_url': {'data_uri': a.model, 'mime': 'application/octet-stream'},
                    'image_style_url': {'data_uri': a.style_image}, 'enable_original_uv': True,
                    'enable_pbr': False, 'target_formats': ['glb']}
            if a.prompt:
                body['text_style_prompt'] = a.prompt
            return [('POST', f'{MESHY}/retexture', body)], 'retexture'
    if pv == 'tripo':
        if op == 'generate':
            views = parse_views(a.view)
            steps = [('UPLOAD', f'{TRIPO}/files', {'upload': str(p), 'as': v}) for v, p in views.items()]
            if len(views) == 1:
                body = dict(TRIPO_GEN, input={'token_of': 'front'})
                steps.append(('POST', f'{TRIPO}/generation/image-to-model', body))
            else:
                body = dict(TRIPO_GEN, inputs=[{v: {'token_of': v}} for v in VIEWS if v in views])
                steps.append(('POST', f'{TRIPO}/generation/multiview-to-model', body))
            return steps, 'tripo'
        if op == 'texture':
            steps = [('UPLOAD', f'{TRIPO}/files', {'upload': a.model, 'as': 'model'}),
                     ('UPLOAD', f'{TRIPO}/files', {'upload': a.style_image, 'as': 'style'})]
            body = {'input': {'token_of': 'model'}, 'texture_prompt': {'image': {'token_of': 'style'}},
                    'pbr': False, 'texture_alignment': 'geometry', 'bake': True}
            if a.prompt:
                body['texture_prompt']['text'] = a.prompt
            steps.append(('POST', f'{TRIPO}/models/texture', body))
            return steps, 'tripo'
    raise ValueError(f'{pv} has no {op!r} operation (remesh is Meshy only; reduce Tripo meshes with the kit sweep)')


def http(method, url, key, body=None, ctype='application/json'):
    headers = {'Authorization': f'Bearer {key}'}
    if body is not None:
        headers['Content-Type'] = ctype
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raise ValueError(f'HTTP {e.code} from {url}: {e.read()[:400].decode(errors="replace")}') from None


def tripo_data(resp):
    if resp.get('code') != 0:
        raise ValueError(f'Tripo error {resp.get("code")}: {resp.get("message") or resp}')
    return resp['data']


def upload(url, key, path):
    boundary = uuid.uuid4().hex
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{p.name}"\r\n'
            f'Content-Type: {mime}\r\n\r\n').encode() + p.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    return tripo_data(http('POST', url, key, body, f'multipart/form-data; boundary={boundary}'))['file_token']


def resolve(obj, tokens):
    if isinstance(obj, dict):
        if 'data_uri' in obj:
            return data_uri(Path(obj['data_uri']), obj.get('mime'))
        if 'token_of' in obj:
            return tokens[obj['token_of']]
        return {k: resolve(v, tokens) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve(v, tokens) for v in obj]
    return obj


def wait(provider, kind, task_id, key):
    url = f'{MESHY}/{kind}/{task_id}' if provider == 'meshy' else f'{TRIPO}/tasks/{task_id}'
    end = time.time() + TIMEOUT_S
    while time.time() < end:
        t = http('GET', url, key)
        t = tripo_data(t) if provider == 'tripo' else t
        status = str(t.get('status', '')).upper()
        if status in ('SUCCEEDED', 'SUCCESS'):
            return t
        if status in ('FAILED', 'CANCELED', 'CANCELLED', 'BANNED', 'EXPIRED'):
            err = t.get('task_error') or {'message': t.get('error_message'), 'code': t.get('error_code')}
            raise ValueError(f'task {task_id} {status}: {err}')
        time.sleep(POLL_S)
    raise ValueError(f'task {task_id} still running after {TIMEOUT_S} s; read its state before any retry')


def download(url, dest):
    with urllib.request.urlopen(url, timeout=300) as r, dest.open('xb') as f:
        f.write(r.read())
    return str(dest)


def charge(budget_file, cost):
    b = json.loads(budget_file.read_text())
    if not isinstance(b.get('max_credits'), (int, float)) or not isinstance(b.get('used_credits'), (int, float)):
        raise ValueError('budget file must contain numbers "max_credits" and "used_credits"')
    if b['used_credits'] + cost > b['max_credits']:
        raise BudgetError(f'budget would be exceeded ({b["used_credits"]}+{cost} > {b["max_credits"]}); '
                          'ask the user before you raise it')
    b['used_credits'] += cost
    budget_file.write_text(json.dumps(b, indent=2) + '\n')
    return b


def run(a):
    steps, kind = plan(a)
    cost = COST[(a.provider, a.op)]
    record = {'tool': 'zps_gen_api', 'provider': a.provider, 'op': a.op, 'expected_credits': cost,
              'steps': [{'method': m, 'url': u, 'body': b} for m, u, b in steps]}
    if a.dry_run:
        record.update(dry_run=True, note='no request sent, no key read, no credit spent')
        return record
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'{out} is not empty; use a new versioned folder')
    key = key_for(a.provider)
    if not key:
        raise ValueError(f'{KEY_ENV[a.provider]} is not set; ask the user to paste it into {ENV_FILE}')
    budget = charge(Path(a.budget_file), cost)
    out.mkdir(parents=True, exist_ok=True)
    tokens, task_id = {}, None
    for method, url, body in steps:
        if method == 'UPLOAD':
            tokens[body['as']] = upload(url, key, body['upload'])
            continue
        resp = http('POST', url, key, json.dumps(resolve(body, tokens)).encode())
        task_id = resp['result'] if a.provider == 'meshy' else tripo_data(resp)['task_id']
    record['task_id'] = task_id
    (out / 'task.json').write_text(json.dumps(record, indent=2) + '\n')  # keep the id even if the wait fails
    task = wait(a.provider, kind, task_id, key)
    files = {}
    if a.provider == 'meshy':
        for name, url in (task.get('model_urls') or {}).items():
            if name in ('glb', 'pre_remeshed_glb') and url:
                files[name] = download(url, out / f'{name}.glb')
        record['consumed_credits'] = task.get('consumed_credits')
    else:
        url = (task.get('output') or {}).get('model_url')
        if url:
            files['glb'] = download(url, out / 'model.glb')
        record['consumed_credits'] = task.get('credits_consumed')
    if not files:
        raise ValueError(f'task {task_id} succeeded but returned no GLB: {list(task)}')
    record.update(files=files, budget=budget, finished_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  next='Open the GLB renders and run the kit checks before any further paid call.')
    (out / 'task.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def keys():
    present = read_env_file()
    return {'key_file': str(ENV_FILE), 'key_file_exists': ENV_FILE.is_file(),
            'keys': {pv: ('environment' if os.environ.get(env) else 'key file' if present.get(env) else 'missing')
                     for pv, env in KEY_ENV.items()}}


def balance(provider):
    key = key_for(provider)
    if not key:
        raise ValueError(f'{KEY_ENV[provider]} is not set; ask the user to paste it into {ENV_FILE}')
    if provider == 'meshy':
        return http('GET', f'{MESHY}/balance', key)
    return tripo_data(http('GET', f'{TRIPO}/account/balance', key))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='op', required=True)
    sub.add_parser('keys')
    b = sub.add_parser('balance'); b.add_argument('--provider', choices=sorted(KEY_ENV), required=True)
    for name in ('generate', 'remesh', 'texture'):
        s = sub.add_parser(name)
        s.add_argument('--provider', choices=sorted(KEY_ENV), required=True)
        s.add_argument('--out'); s.add_argument('--budget-file')
        s.add_argument('--dry-run', action='store_true', help='describe the requests; send nothing')
        if name == 'generate':
            s.add_argument('--view', action='append', help='front=<image>; also left, back, right')
        if name == 'remesh':
            s.add_argument('--task-id'); s.add_argument('--model')
            s.add_argument('--polycount', type=int, required=True)
            s.add_argument('--topology', choices=['triangle', 'quad'], default='triangle')
        if name == 'texture':
            s.add_argument('--model', required=True); s.add_argument('--style-image', required=True)
            s.add_argument('--prompt')
    a = p.parse_args()
    try:
        if a.op == 'keys':
            result = keys()
        elif a.op == 'balance':
            result = balance(a.provider)
        else:
            if a.op == 'remesh' and not (a.task_id or a.model):
                p.error('remesh needs --task-id or --model')
            for f in [getattr(a, 'model', None), getattr(a, 'style_image', None)]:
                if f and not Path(f).is_file():
                    raise ValueError(f'missing file {f}')
            if not a.dry_run and (not a.out or not a.budget_file):
                p.error('--out and --budget-file are required unless --dry-run')
            result = run(a)
        print(json.dumps(result, indent=2))
        return 0
    except BudgetError as e:
        print(json.dumps({'error': str(e)}))
        return 3
    except (OSError, ValueError, KeyError, urllib.error.URLError) as e:
        print(json.dumps({'error': str(e)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())

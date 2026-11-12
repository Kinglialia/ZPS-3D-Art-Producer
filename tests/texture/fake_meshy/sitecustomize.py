"""Stand-in for the Meshy HTTP API, loaded by every Python child that has this folder on PYTHONPATH: tests never reach
api.meshy.ai. It replaces urllib.request.urlopen. FAKE_MESHY_MODE is a comma list of <fault>:<n> (the first n requests
of that kind fail): post_fail (connection refused: the POST never left), post_lost (the server creates the task, the
response is lost as a connection reset), poll_fail (HTTP 503 on the task GET), task_failed (the
task ends FAILED), download_fail
(network error on the GLB URL), truncated (GLB cut off), base_fail (network error on the base_color URL), echo_key
(HTTP 401 whose body repeats the Authorization header), running (the task GET says IN_PROGRESS: a slow task),
failed_after_running (the first n task GETs say IN_PROGRESS, every later one says FAILED). The returned GLB is the uploaded model, as Meshy returns the mesh
with original UVs, or the file FAKE_MESHY_GLB (a real Meshy GLB, normalized). A succeeded task also has
texture_urls[0].base_color: a PNG of FAKE_MESHY_BASE_PX (default 2048) square, one colour, or
one-pixel black and white columns when FAKE_MESHY_BASE_STRIPES is set.
Each request is logged to FAKE_MESHY_LOG (method, url, authorization, the texture_resolution of a POST, the wait limit
TIMEOUT_S the kit has in that process, and the pid files in FAKE_MESHY_PIDS)."""
import base64
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

LOG = os.environ.get("FAKE_MESHY_LOG")
ASSET = "https://assets.meshy.fake/task-{n}.glb"
BASE = "https://assets.meshy.fake/task-{n}/base_color.png?Signature=fake-signed"


def faults():
    out = {}
    for item in filter(None, os.environ.get("FAKE_MESHY_MODE", "").split(",")):
        k, _, n = item.partition(":")
        out[k] = int(n or 1)
    return out


def calls():
    p = Path(LOG)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def log(entry):
    pids = os.environ.get("FAKE_MESHY_PIDS")
    if pids:
        entry["pids"] = sorted(x.name for x in Path(pids).glob("*.pid"))
    entry["kit_wait_s"] = getattr(sys.modules.get("gen_api"), "TIMEOUT_S", None)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def fail_now(kind, past):
    return sum(c.get("kind") == kind for c in past) < faults().get(kind, 0)


def urlopen(req, timeout=None):
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    method = req.get_method() if isinstance(req, urllib.request.Request) else "GET"
    auth = req.get_header("Authorization") if isinstance(req, urllib.request.Request) else None
    past = calls()
    store = Path(LOG).with_suffix(".model.glb")
    if method == "POST" and url.endswith("/retexture"):
        kind = next((k for k in ("echo_key", "post_fail", "post_lost") if fail_now(k, past)), "post")
        log({"method": method, "url": url, "auth": auth, "kind": kind,
             "texture_resolution": json.loads(req.data).get("texture_resolution")})
        if kind == "echo_key":
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(f"bad token {auth}".encode()))
        if kind == "post_fail":
            raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        body = json.loads(req.data)
        store.write_bytes(base64.b64decode(body["model_url"].split(",", 1)[1]))
        n = sum(c["kind"] in ("post", "post_lost") for c in past) + 1
        if kind == "post_lost":
            raise urllib.error.URLError(ConnectionResetError(54, "Connection reset by peer"))
        return Resp(json.dumps({"result": f"task-{n}"}).encode())
    if method == "GET" and (m := re.search(r"/retexture/(task-\d+)$", url)):
        late_fail = faults().get("failed_after_running")
        kind = ("poll_fail" if fail_now("poll_fail", past) else "task_failed" if fail_now("task_failed", past)
                else "running" if fail_now("running", past) else "poll")
        if late_fail and kind == "poll":
            kind = "running" if sum(c.get("kind") == "running" for c in past) < late_fail else "task_failed"
        log({"method": method, "url": url, "auth": auth, "kind": kind})
        if kind == "poll_fail":
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, io.BytesIO(b"busy"))
        if kind == "running":
            return Resp(json.dumps({"id": m.group(1), "status": "IN_PROGRESS", "progress": 40}).encode())
        if kind == "task_failed":
            return Resp(json.dumps({"id": m.group(1), "status": "FAILED", "consumed_credits": 0,
                                    "task_error": {"message": "mesh không hợp lệ"}}).encode())
        n = m.group(1).split("-")[1]
        return Resp(json.dumps({"id": m.group(1), "status": "SUCCEEDED", "consumed_credits": 10,
                                "model_urls": {"glb": ASSET.format(n=n)},
                                "texture_urls": [{"base_color": BASE.format(n=n)}]}).encode())
    if url.startswith("https://assets.meshy.fake/") and "/base_color.png" in url:
        kind = "base_fail" if fail_now("base_fail", past) else "base_color"
        log({"method": method, "url": url.split("?")[0], "auth": auth, "kind": kind})
        if kind == "base_fail":
            raise urllib.error.URLError("download reset")
        from PIL import Image
        px = int(os.environ.get("FAKE_MESHY_BASE_PX") or 2048)
        buf = io.BytesIO()
        im = Image.new("RGB", (px, px), (160, 110, 60))
        if os.environ.get("FAKE_MESHY_BASE_STRIPES"):
            im.paste((0, 0, 0), (0, 0, px, px))
            for x in range(0, px, 2):
                im.paste((255, 255, 255), (x, 0, x + 1, px))
        im.save(buf, "PNG")
        return Resp(buf.getvalue())
    if url.startswith("https://assets.meshy.fake/"):
        kind = ("download_fail" if fail_now("download_fail", past) else
                "truncated" if fail_now("truncated", past) else "download")
        log({"method": method, "url": url, "auth": auth, "kind": kind})
        if kind == "download_fail":
            raise urllib.error.URLError("download reset")
        data = Path(os.environ.get("FAKE_MESHY_GLB") or store).read_bytes()
        return Resp(data[:len(data) // 2] if kind == "truncated" else data)
    raise urllib.error.URLError(f"fake meshy: no route for {method} {url}")


if LOG:
    urllib.request.urlopen = urlopen

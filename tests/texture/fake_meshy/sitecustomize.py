"""Stand-in for the Meshy HTTP API, loaded by every Python child that has this folder on PYTHONPATH: tests never reach
api.meshy.ai. It replaces urllib.request.urlopen. FAKE_MESHY_MODE is a comma list of <fault>:<n> (the first n requests
of that kind fail): post_fail (connection refused: the POST never left), post_lost (the server creates the task, the
response is lost as a connection reset), poll_fail (HTTP 503 on the task GET), task_failed (the
task ends FAILED), download_fail
(network error on the GLB URL), truncated (GLB cut off), echo_key (HTTP 401 whose body repeats the Authorization
header). The returned GLB is the uploaded model, as Meshy returns the mesh with original UVs.
Each request is logged to FAKE_MESHY_LOG (method, url, authorization, and the pid files in FAKE_MESHY_PIDS)."""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

LOG = os.environ.get("FAKE_MESHY_LOG")
ASSET = "https://assets.meshy.fake/task-{n}.glb"


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
        log({"method": method, "url": url, "auth": auth, "kind": kind})
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
        kind = ("poll_fail" if fail_now("poll_fail", past) else "task_failed" if fail_now("task_failed", past)
                else "poll")
        log({"method": method, "url": url, "auth": auth, "kind": kind})
        if kind == "poll_fail":
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, io.BytesIO(b"busy"))
        if kind == "task_failed":
            return Resp(json.dumps({"id": m.group(1), "status": "FAILED", "consumed_credits": 0,
                                    "task_error": {"message": "mesh không hợp lệ"}}).encode())
        n = m.group(1).split("-")[1]
        return Resp(json.dumps({"id": m.group(1), "status": "SUCCEEDED", "consumed_credits": 10,
                                "model_urls": {"glb": ASSET.format(n=n)}}).encode())
    if url.startswith("https://assets.meshy.fake/"):
        kind = ("download_fail" if fail_now("download_fail", past) else
                "truncated" if fail_now("truncated", past) else "download")
        log({"method": method, "url": url, "auth": auth, "kind": kind})
        if kind == "download_fail":
            raise urllib.error.URLError("download reset")
        data = store.read_bytes()
        return Resp(data[:len(data) // 2] if kind == "truncated" else data)
    raise urllib.error.URLError(f"fake meshy: no route for {method} {url}")


if LOG:
    urllib.request.urlopen = urlopen

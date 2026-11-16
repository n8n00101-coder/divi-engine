"""gpupool adapters — one class per compute provider, one contract.

Every adapter exposes:
    name                      short id ("kaggle", "modal", ...)
    weight                    scheduler split weight (relative)
    max_lines                 hard cap per job (None = uncapped)
    health()                  -> (ok: bool, reason: str); cheap, local
                                 checks only (credentials/SDK present)
    run_batch(items, lang, timeout_s=..., poll_s=..., sleep=..., now=...)
                              -> ({global_idx: mp3_bytes}, qc_dict)
                                 or raises ProviderError

Credentials come from the environment / the provider's own config
file and are NEVER logged: error strings are built from fixed text +
HTTP status codes only, never from response bodies that could echo
a key.
"""

import json
import os
import re
import subprocess
import sys
import time

from .common import ProviderError, extract_batch_zip, is_limit_text

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_REPO_URL = "https://github.com/n8n00101-coder/julie-ai-voice-engine.git"
ENGINE_REPO = "n8n00101-coder/julie-ai-voice-engine"
KAGGLE_API = "https://www.kaggle.com/api/v1"
GH_API = "https://api.github.com"


def _default_http():
    import httpx
    return httpx.Client(follow_redirects=True, timeout=120)


# ------------------------------------------------------------------ Kaggle

_KERNEL_TEMPLATE = '''# Julie voice batch on Kaggle — pushed by gpupool via the Kaggle API.
# Same contract as gpu-pack/gpu_batch.py: lines in, out.zip with
# <nnn>.mp3 + batch.qc.json out. Lines + first index ride inside.
import json, os, subprocess, sys

LINES = json.loads({lines_json!r})
LANG = {lang!r}
FIRST_INDEX = {first_index}
WORK = "/kaggle/working"
REPO_DIR = os.path.join(WORK, "julie-ai-voice-engine")
REPO_URL = {repo_url!r}


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def flip(path, old, new):
    src = open(path).read()
    if src.count(old) >= 1:
        open(path, "w").write(src.replace(old, new, 1))
        print("flipped to GPU:", path)
    else:
        print("WARN: device line not found in", path, "- running as-is")


def main():
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("No GPU visible on this kernel session.")
    print("GPU:", torch.cuda.get_device_name(0))
    with open(os.path.join(WORK, "lines.txt"), "w") as fh:
        fh.write("\\n".join(LINES) + "\\n")
    if not os.path.isdir(REPO_DIR):
        run(["git", "clone", "--depth", "1", REPO_URL, REPO_DIR])
    run([sys.executable, "-m", "pip", "install", "-q",
         "torch==2.6.0", "torchaudio==2.6.0",
         "--index-url", "https://download.pytorch.org/whl/cu124"])
    reqs = [os.path.join(REPO_DIR, "requirements.txt")]
    if LANG in ("te", "hi"):
        reqs.append(os.path.join(REPO_DIR, "requirements-indicf5.txt"))
    for req in reqs:
        run([sys.executable, "-m", "pip", "install", "-q", "httpx",
             "-r", req])
    flip(os.path.join(REPO_DIR, "engine.py"),
         'ChatterboxTTS.from_pretrained(device="cpu")',
         'ChatterboxTTS.from_pretrained(device="cuda")')
    flip(os.path.join(REPO_DIR, "gates.py"),
         'WhisperModel(_model_path(), device="cpu", compute_type="int8")',
         'WhisperModel(_model_path(), device="cuda", compute_type="float16")')
    outdir = os.path.join(WORK, "out")
    # NOT check=True: the engine exits 2 when some lines fail the gates
    # after re-rolls — those lines are named in batch.qc.json and the
    # passing lines must still ship. No qc at all = caller-side failure.
    r = subprocess.run([sys.executable, "engine.py", "--batch",
                        os.path.join(WORK, "lines.txt"), "--lang", LANG,
                        "--outdir", outdir, "--jobs", "1", "--rerolls", "2",
                        "--first-index", str(FIRST_INDEX)],
                       cwd=REPO_DIR)
    print("engine exit", r.returncode)
    run(["bash", "-c", "cd " + outdir + " && zip -r " +
         os.path.join(WORK, "out.zip") + " ."])
    print("Done.")


main()
'''


def build_kernel_script(lines, lang, first_index):
    return _KERNEL_TEMPLATE.format(
        lines_json=json.dumps(list(lines), ensure_ascii=False),
        lang=lang, first_index=int(first_index), repo_url=ENGINE_REPO_URL)


def _kaggle_creds():
    user = os.environ.get("KAGGLE_USERNAME", "").strip()
    key = os.environ.get("KAGGLE_KEY", "").strip()
    if user and key:
        return user, key
    path = os.path.expanduser("~/.kaggle/kaggle.json")
    if os.path.exists(path):
        try:
            j = json.load(open(path))
            return str(j.get("username") or ""), str(j.get("key") or "")
        except Exception:
            pass
    return "", ""


class KaggleAdapter:
    """The owner's own Kaggle account (official API, Basic auth with
    the username + API key from kaggle.json). One account per person
    is Kaggle's rule — there is deliberately NO multi-account rotation
    here; failover switches BETWEEN providers, never between accounts.
    Free tier: ~30 GPU-hours/week (P100 or T4 x2), 12 h sessions."""

    name = "kaggle"
    weight = 50
    max_lines = None

    def __init__(self, user="", key="", http=None, slug="julie-voice-batch",
                 timeout_s=2400):
        u, k = _kaggle_creds()
        self.user = (user or u).strip()
        self.key = (key or k).strip()
        self.slug = slug
        self.http = http
        self.timeout_s = timeout_s

    @property
    def ref(self):
        return f"{self.user}/{self.slug}"

    def health(self):
        if not self.user or not self.key:
            return False, "no Kaggle credentials (KAGGLE_USERNAME/KAGGLE_KEY or ~/.kaggle/kaggle.json)"
        return True, "credentials present"

    def _http(self):
        if self.http is None:
            self.http = _default_http()
        return self.http

    def _req(self, method, path, **kw):
        kw.setdefault("auth", (self.user, self.key))
        r = self._http().request(method, KAGGLE_API + path, **kw)
        if r.status_code in (401, 403):
            body = ""
            try:
                body = str(r.json().get("message") or "")
            except Exception:
                pass
            if r.status_code == 403 or is_limit_text(body):
                raise ProviderError("limit", f"HTTP {r.status_code}")
            raise ProviderError("error", f"HTTP {r.status_code} (credentials rejected)")
        if r.status_code == 429:
            raise ProviderError("limit", "HTTP 429")
        if r.status_code >= 400:
            raise ProviderError("error", f"HTTP {r.status_code}")
        return r

    def push_kernel(self, lines, lang, first_index):
        body = {
            "id": self.ref, "slug": self.ref,
            "newTitle": "Julie voice batch",
            "text": build_kernel_script(lines, lang, first_index),
            "language": "python", "kernelType": "script",
            "isPrivate": True, "enableGpu": True, "enableTpu": False,
            "enableInternet": True,
            "datasetDataSources": [], "competitionDataSources": [],
            "kernelDataSources": [], "modelDataSources": [],
            "categoryIds": [],
        }
        r = self._req("POST", "/kernels/push", json=body)
        try:
            j = r.json()
        except Exception:
            j = {}
        if isinstance(j, dict) and j.get("error"):
            msg = str(j.get("error"))[:200]
            if is_limit_text(msg):
                raise ProviderError("limit", msg)
            raise ProviderError("error", msg)
        return self.ref

    def status(self):
        r = self._req("GET", "/kernels/status",
                      params={"userName": self.user, "kernelSlug": self.slug})
        j = r.json()
        return str(j.get("status") or "").lower(), str(j.get("failureMessage") or "")

    def download_output(self):
        r = self._req("GET", "/kernels/output",
                      params={"userName": self.user, "kernelSlug": self.slug})
        return r.content

    def run_batch(self, items, lang, timeout_s=None, poll_s=20,
                  sleep=time.sleep, now=time.monotonic):
        if not items:
            return {}, None
        timeout_s = self.timeout_s if timeout_s is None else timeout_s
        first = items[0][0]
        self.push_kernel([t for _, t in items], lang, first)
        t0 = now()
        while True:
            st, fail_msg = self.status()
            if st == "complete":
                break
            if st in ("error", "failed", "cancelacknowledged", "cancelled"):
                if is_limit_text(fail_msg):
                    raise ProviderError("limit", fail_msg)
                raise ProviderError("error", fail_msg or f"kernel status {st}")
            if now() - t0 > timeout_s:
                raise ProviderError("timeout", f"kernel still {st or 'queued'} after {timeout_s}s")
            sleep(poll_s)
        done, qc = extract_batch_zip(self.download_output())
        if qc is None:
            raise ProviderError("no_qc", "kernel output has no batch.qc.json")
        return done, qc


# ------------------------------------------------------------------- Modal

class ModalAdapter:
    """Modal serverless GPU (Starter plan: $30/month compute credit,
    recurring; T4 ~$0.59/h -> ~50 T4-hours/month). API-first by
    design: the batch runs in the deployed app from
    gpupool/modal_app.py (`modal deploy gpupool/modal_app.py`, once).
    Health needs the modal SDK + a token (~/.modal.toml or
    MODAL_TOKEN_ID/MODAL_TOKEN_SECRET)."""

    name = "modal"
    weight = 30
    max_lines = None
    APP_NAME = "julie-voice-gpu"
    FN_NAME = "run_batch"

    def __init__(self, timeout_s=2400):
        self.timeout_s = timeout_s

    def health(self):
        try:
            import modal  # noqa: F401
        except Exception:
            return False, "modal SDK not installed (pip install modal)"
        if os.environ.get("MODAL_TOKEN_ID") or os.path.exists(
                os.path.expanduser("~/.modal.toml")):
            return True, "SDK + token present"
        return False, "no Modal token (~/.modal.toml or MODAL_TOKEN_ID/MODAL_TOKEN_SECRET)"

    def run_batch(self, items, lang, timeout_s=None, poll_s=15,
                  sleep=time.sleep, now=time.monotonic):
        if not items:
            return {}, None
        timeout_s = self.timeout_s if timeout_s is None else timeout_s
        import modal
        fn = modal.Function.from_name(self.APP_NAME, self.FN_NAME)
        call = fn.spawn(lines=[t for _, t in items], lang=lang,
                        first_index=items[0][0])
        t0 = now()
        while True:
            try:
                blob = call.get(timeout=0)
                break
            except TimeoutError:
                pass
            except Exception as e:  # remote failure / quota / credits out
                msg = str(e)[:200]
                if is_limit_text(msg):
                    raise ProviderError("limit", msg)
                raise ProviderError("error", msg)
            if now() - t0 > timeout_s:
                raise ProviderError("timeout", f"modal call still running after {timeout_s}s")
            sleep(poll_s)
        done, qc = extract_batch_zip(blob)
        if qc is None:
            raise ProviderError("no_qc", "modal output has no batch.qc.json")
        return done, qc


# -------------------------------------------------------------- HF Spaces

class HFSpacesAdapter:
    """IndicF5 on Hugging Face ZeroGPU, through the engine's own
    indicf5-space backend: the batch runs locally (engine + gates on
    CPU) while each generation call lands on the Space's GPU.

    Free-account ZeroGPU quota is 5 GPU-minutes/day (HF's own docs) —
    the measured wall from the turbo work. This adapter therefore
    carries a daily GPU-seconds budget (default 300 s) and an
    estimated per-line GPU cost (default 8 s, the Space probe
    measurement); max_lines is derived from the remaining budget and
    the charge is booked locally after each run. HF enforces the real
    quota server-side; if it dies mid-batch the run ships nothing and
    the scheduler fails the lines over (see run_batch)."""

    name = "hfspaces"
    weight = 10
    DEFAULT_BUDGET_S = 300
    DEFAULT_EST_S_PER_LINE = 8

    def __init__(self, budget_s=None, est_s_per_line=None, state_path=None,
                 timeout_s=3600):
        self.budget_s = int(budget_s if budget_s is not None
                            else os.environ.get("GPUPOOL_HF_BUDGET_S",
                                                self.DEFAULT_BUDGET_S))
        self.est_s = int(est_s_per_line if est_s_per_line is not None
                         else os.environ.get("GPUPOOL_HF_EST_S_PER_LINE",
                                             self.DEFAULT_EST_S_PER_LINE))
        self.state_path = state_path or os.path.expanduser(
            "~/.julie_gpupool_hf_budget.json")
        self.timeout_s = timeout_s

    def _used_today(self):
        try:
            j = json.load(open(self.state_path))
            if j.get("date") == time.strftime("%Y-%m-%d"):
                return int(j.get("gpu_seconds_used") or 0)
        except Exception:
            pass
        return 0

    def _charge(self, seconds):
        used = self._used_today() + int(seconds)
        try:
            with open(self.state_path, "w") as fh:
                json.dump({"date": time.strftime("%Y-%m-%d"),
                           "gpu_seconds_used": used}, fh)
        except Exception:
            pass

    @property
    def max_lines(self):
        remaining = self.budget_s - self._used_today()
        return max(0, remaining // max(1, self.est_s))

    def health(self):
        token = os.environ.get("HF_TOKEN") or os.environ.get(
            "HUGGING_FACE_HUB_TOKEN")
        if not token and not os.path.exists(os.path.expanduser(
                "~/.cache/huggingface/token")):
            return False, "no HF token (HF_TOKEN env or huggingface-cli login)"
        if self.max_lines <= 0:
            return False, f"daily ZeroGPU budget spent ({self.budget_s}s)"
        return True, f"token present, ~{self.max_lines} lines of budget left today"

    def run_batch(self, items, lang, timeout_s=None, poll_s=5,
                  sleep=time.sleep, now=time.monotonic):
        if not items:
            return {}, None
        if lang not in ("te", "hi"):
            raise ProviderError("error", "hfspaces adapter serves te/hi only (IndicF5 Space)")
        timeout_s = self.timeout_s if timeout_s is None else timeout_s
        import tempfile
        tmp = tempfile.mkdtemp(prefix="gpupool-hf-")
        lines_path = os.path.join(tmp, "lines.txt")
        with open(lines_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(t for _, t in items) + "\n")
        outdir = os.path.join(tmp, "out")
        env = dict(os.environ)
        env["JULIE_TTS_BACKEND"] = "indicf5-space"
        try:
            r = subprocess.run(
                [sys.executable, "engine.py", "--batch", lines_path,
                 "--lang", lang, "--outdir", outdir, "--jobs", "1",
                 "--rerolls", "2", "--first-index", str(items[0][0])],
                cwd=REPO_ROOT, env=env, capture_output=True, text=True,
                timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise ProviderError("timeout", f"local engine batch exceeded {timeout_s}s")
        self._charge(self.est_s * len(items))
        qc = None
        qc_path = os.path.join(outdir, "batch.qc.json")
        if os.path.exists(qc_path):
            try:
                qc = json.load(open(qc_path))
            except Exception:
                qc = None
        if qc is None:
            tail = (r.stderr or r.stdout or "")[-200:]
            if is_limit_text(tail):
                raise ProviderError("limit", tail)
            raise ProviderError("no_qc", "local engine batch produced no batch.qc.json")
        done = {}
        for idx, _ in items:
            p = os.path.join(outdir, f"{idx:03d}.mp3")
            if os.path.exists(p):
                done[idx] = open(p, "rb").read()
        if not done:
            # Zero shipped from a whole chunk almost always means the
            # Space quota died, not that every line failed the gates —
            # fail over instead of writing the lines off as gate fails.
            raise ProviderError("limit", "hf space shipped 0 lines (quota presumed)")
        return done, qc


# ----------------------------------------------------------------- Actions

class ActionsAdapter:
    """Final fallback leg: the engine repo's voice-batch.yml on
    GitHub Actions CPU runners (the proven route). The workflow reads
    its lines from a file inside the engine repo, written via the
    Contents API under jobs/<job>.txt and deleted when the run ends.
    The merged artifact's numbering is file-relative; this client
    remaps it to the job's global line indices by order."""

    name = "actions"
    weight = 20
    max_lines = None

    def __init__(self, token="", repo=ENGINE_REPO, http=None,
                 job_tag="gpupool", timeout_s=3600):
        self.token = (token or os.environ.get("GH_TOKEN") or "").strip()
        if not self.token:
            try:
                self.token = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True,
                    text=True, timeout=15).stdout.strip()
            except Exception:
                self.token = ""
        self.repo = repo
        self.job_tag = re.sub(r"[^a-zA-Z0-9_-]", "", str(job_tag))[:40] or "gpupool"
        self.http = http
        self.timeout_s = timeout_s

    def health(self):
        if not self.token:
            return False, "no GitHub token (GH_TOKEN env or gh auth)"
        return True, "token present"

    def _http(self):
        if self.http is None:
            self.http = _default_http()
        return self.http

    def _req(self, method, path, ok=(200,), **kw):
        headers = {"Authorization": f"token {self.token}",
                   "Accept": "application/vnd.github+json",
                   "User-Agent": "julie-gpupool"}
        r = self._http().request(method, GH_API + path, headers=headers, **kw)
        if r.status_code == 429 or (r.status_code == 403 and
                                    is_limit_text(_body_msg(r))):
            raise ProviderError("limit", f"HTTP {r.status_code}")
        if r.status_code not in ok:
            raise ProviderError("error", f"HTTP {r.status_code} on {method} {path.split('?')[0]}")
        return r

    def _put_lines_file(self, texts):
        import base64
        path = f"jobs/{self.job_tag}.txt"
        content = base64.b64encode(
            ("\n".join(texts) + "\n").encode("utf-8")).decode()
        r = self._req("PUT", f"/repos/{self.repo}/contents/{path}",
                      ok=(200, 201),
                      json={"message": f"voice batch lines ({self.job_tag})",
                            "content": content})
        return path, (r.json().get("content") or {}).get("sha", "")

    def _delete_lines_file(self, path, sha):
        try:
            self._req("DELETE", f"/repos/{self.repo}/contents/{path}",
                      ok=(200,),
                      json={"message": f"voice batch lines done ({self.job_tag})",
                            "sha": sha})
        except Exception:
            pass  # best-effort cleanup; a stale jobs/ file is litter

    def _latest_run_id(self):
        r = self._req("GET", f"/repos/{self.repo}/actions/workflows/voice-batch.yml/runs",
                      ok=(200,), params={"event": "workflow_dispatch",
                                         "per_page": "1"})
        runs = (r.json() or {}).get("workflow_runs") or []
        return runs[0]["id"] if runs else 0

    def _wait_run(self, after_id, timeout_s, poll_s, sleep, now):
        t0 = now()
        while True:
            r = self._req("GET", f"/repos/{self.repo}/actions/workflows/voice-batch.yml/runs",
                          ok=(200,), params={"event": "workflow_dispatch",
                                             "per_page": "10"})
            runs = (r.json() or {}).get("workflow_runs") or []
            run = next((x for x in runs if x.get("id", 0) > after_id), None)
            if run and run.get("status") == "completed":
                if run.get("conclusion") in ("success", "failure"):
                    # "failure" still uploads chunk artifacts (if: always)
                    # with every passing line — judge by artifact + qc.
                    return run["id"]
                raise ProviderError("error", f"run conclusion {run.get('conclusion')}")
            if now() - t0 > timeout_s:
                raise ProviderError("timeout", f"no completed run after {timeout_s}s")
            sleep(poll_s)

    def _download_artifact(self, run_id):
        r = self._req("GET", f"/repos/{self.repo}/actions/runs/{run_id}/artifacts",
                      ok=(200,), params={"per_page": "100"})
        arts = (r.json() or {}).get("artifacts") or []
        art = next((a for a in arts if a.get("name") == "julie-voice-batch-all"),
                   None)
        if not art:
            raise ProviderError("error", "merged artifact julie-voice-batch-all missing")
        dl = self._req("GET", f"/repos/{self.repo}/actions/artifacts/{art['id']}/zip",
                       ok=(200,))
        return dl.content

    def run_batch(self, items, lang, timeout_s=None, poll_s=20,
                  sleep=time.sleep, now=time.monotonic, chunks=10):
        if not items:
            return {}, None
        timeout_s = self.timeout_s if timeout_s is None else timeout_s
        texts = [t for _, t in items]
        path, sha = self._put_lines_file(texts)
        try:
            after = self._latest_run_id()
            self._req("POST", f"/repos/{self.repo}/actions/workflows/voice-batch.yml/dispatches",
                      ok=(204,), json={"ref": "main", "inputs": {
                          "lines_path": path, "lang": lang,
                          "chunks": str(max(1, min(10, int(chunks)))),
                          "rerolls": "2"}})
            run_id = self._wait_run(after, timeout_s, poll_s, sleep, now)
            blob = self._download_artifact(run_id)
        finally:
            self._delete_lines_file(path, sha)
        sub_done, qc = extract_batch_zip(blob)
        if qc is None:
            raise ProviderError("no_qc", "artifact has no batch.qc.json")
        done = {}
        for sub_idx, blob_bytes in sub_done.items():
            pos = sub_idx - 1
            if 0 <= pos < len(items):
                done[items[pos][0]] = blob_bytes
        return done, qc


def _body_msg(r):
    try:
        return str(r.json().get("message") or "")
    except Exception:
        return ""


# --------------------------------------------------------------- Lightning

class LightningAdapter:
    """Lightning AI — registered but NOT built. Its free credits are
    a one-time starter grant (5 on registration + 25 for adding a
    card, ~50-80 interruptible GPU-hours, expiring after 12 months),
    not a recurring tier, so it can only ever be burst capacity.
    Build this adapter against the Lightning SDK only if that burst
    is ever wanted; until then health() says so plainly and the
    scheduler treats it as absent."""

    name = "lightning"
    weight = 0
    max_lines = None

    def health(self):
        return False, "adapter not built (one-time credits only — see GPUPOOL.md)"

    def run_batch(self, items, lang, **kw):
        raise ProviderError("error", "lightning adapter not built")


# ------------------------------------------------------------------ factory

_ADAPTERS = {
    "kaggle": KaggleAdapter,
    "modal": ModalAdapter,
    "hfspaces": HFSpacesAdapter,
    "actions": ActionsAdapter,
    "lightning": LightningAdapter,
}

# Failover preference order: real GPUs first, Actions CPU last.
PROVIDER_ORDER = ["kaggle", "modal", "hfspaces", "actions", "lightning"]


def build_providers(names=None, config=None):
    """Instantiate adapters in failover order. `config` is an optional
    dict {name: {enabled: bool, weight: int, ...kwargs}}."""
    config = config or {}
    out = []
    for name in PROVIDER_ORDER:
        if names and name not in names:
            continue
        cfg = dict(config.get(name) or {})
        if cfg.pop("enabled", True) is False:
            continue
        weight = cfg.pop("weight", None)
        cls = _ADAPTERS[name]
        ad = cls(**cfg) if cfg else cls()
        if weight is not None:
            ad.weight = int(weight)
        out.append(ad)
    return out

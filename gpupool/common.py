"""Shared contract pieces for gpupool adapters.

The provider contract is the engine's batch contract, the same one
Julie's voicecompute.py proved against Kaggle + Actions:

  IN : a contiguous list of (global_index, text) items + a language.
  OUT: ({global_index: mp3_bytes}, batch_qc_dict) — one <nnn>.mp3 per
       line that passed the engine's gates, plus batch.qc.json.
  A run only counts as OK when it completes AND carries batch.qc.json.
  Lines missing under an OK run are GATE failures (the engine already
  re-rolled them internally) — the scheduler reports them, it never
  silently re-runs them on another provider.
  A provider-level failure raises ProviderError and IS failover
  eligible: its lines move to the next alive provider.
"""

import io
import json
import re
import zipfile

_LIMIT_WORDS = ("quota", "limit", "exceeded", "resource_exhausted",
                "too many", "rate")


class ProviderError(Exception):
    """A provider run failed in a failover-eligible way."""

    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason          # "limit" | "timeout" | "error" | "no_qc"
        self.detail = str(detail)[:200]


def is_limit_text(text):
    t = str(text or "").lower()
    return any(w in t for w in _LIMIT_WORDS)


def mp3_index(name):
    m = re.match(r"^(\d+)\.mp3$", name.rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None


def extract_batch_zip(blob):
    """Zip bytes -> ({index: mp3_bytes}, qc_dict_or_None).

    Accepts the gpu-pack shape (an outer zip containing out.zip, whose
    entries may sit under an out/ prefix) and the flat artifact shape
    (mp3s + batch.qc.json at the top level)."""
    def harvest(zf, done, qc_box):
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1]
            idx = mp3_index(name)
            if idx is not None:
                done[idx] = zf.read(name)
            elif base == "batch.qc.json" and qc_box[0] is None:
                try:
                    qc_box[0] = json.loads(zf.read(name).decode("utf-8"))
                except Exception:
                    pass

    done, qc_box = {}, [None]
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        harvest(zf, done, qc_box)
        for name in zf.namelist():
            if name.rsplit("/", 1)[-1] == "out.zip":
                try:
                    with zipfile.ZipFile(io.BytesIO(zf.read(name))) as inner:
                        harvest(inner, done, qc_box)
                except Exception:
                    pass
    return done, qc_box[0]

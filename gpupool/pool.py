"""gpupool scheduler — split one voice job across every alive
provider, fail over automatically, report honestly.

    python3 -m gpupool.pool lines.txt --lang te --outdir out/

lines.txt: one sentence per line (the engine's batch input shape).
Outputs land in --outdir as <nnn>.mp3 (one per shipped line, global
numbering) plus pool.qc.json:

    {lines: {idx: {status: shipped|gate_failed|provider_failed,
                    provider: name}},
     providers: {name: {health, shipped, error}},
     switches: [{from, to, reason}],            # one per failover
     shipped, gate_failed, provider_failed, sentences}

Exit code: 0 = every line shipped; 2 = anything missing (the QC
names it — same convention as engine.py --batch).

Rules (inherited from the proven voicecompute orchestration):
  * Split is weighted across ALIVE providers, honouring per-provider
    line caps (the HF ZeroGPU budget); overflow beyond all caps goes
    to uncapped providers, Actions last.
  * Providers run concurrently.
  * Lines missing under an OK provider run are GATE failures — they
    are reported, never re-run elsewhere.
  * A provider that raises ProviderError loses ALL its unfinished
    lines to the next alive provider, in failover order; each such
    move emits exactly ONE status line (on_switch) naming the reason.
  * If every provider is down, the job fails loudly (exit 2) — no
    partial result is ever presented as complete.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from gpupool.adapters import build_providers  # noqa: E402
from gpupool.common import ProviderError  # noqa: E402

_SWITCH_LINE = {
    "limit": "{frm} limit ayyindhi — migitha lines {to} meedha continue chesthunna.",
    "timeout": "{frm} slow ga undhi (time ayipoyindhi) — migitha lines {to} meedha continue chesthunna.",
    "error": "{frm} pani cheyyaledhu — migitha lines {to} meedha continue chesthunna.",
    "no_qc": "{frm} result sarigga raledhu — migitha lines {to} meedha continue chesthunna.",
}

_DISPLAY = {"kaggle": "Kaggle GPU", "modal": "Modal GPU",
            "hfspaces": "HF Space", "actions": "GitHub runners",
            "lightning": "Lightning"}


def split_items(items, providers):
    """items: [(idx, text)] in order. providers: alive adapters in
    failover order. Returns {name: [items]} — weighted split with
    per-provider caps; overflow flows to later uncapped providers."""
    assign = {p.name: [] for p in providers}
    if not items or not providers:
        return assign
    remaining = list(items)
    capped = [p for p in providers if p.max_lines is not None]
    uncapped = [p for p in providers if p.max_lines is None]
    total_weight = sum(max(0, p.weight) for p in providers) or 1
    # First pass: weighted shares, capped providers take at most cap.
    for p in providers:
        if not remaining:
            break
        share = int(round(len(items) * max(0, p.weight) / total_weight))
        if p.max_lines is not None:
            share = min(share, max(0, p.max_lines))
        take = remaining[:share]
        assign[p.name].extend(take)
        remaining = remaining[len(take):]
    # Overflow: uncapped providers in order take the rest, weighted
    # among themselves; if there are none, the last capped provider
    # with any cap left takes it, else the first provider (its cap is
    # a soft local budget — better than dropping lines silently; the
    # provider itself will limit-error and fail over if truly dry).
    if remaining and uncapped:
        wsum = sum(max(0, p.weight) for p in uncapped) or 1
        left = list(remaining)
        for i, p in enumerate(uncapped):
            if i == len(uncapped) - 1:
                take = left
            else:
                take = left[:int(round(len(remaining) *
                                       max(0, p.weight) / wsum))]
            assign[p.name].extend(take)
            left = left[len(take):]
        remaining = left
    if remaining:
        for p in capped:
            room = max(0, (p.max_lines or 0) - len(assign[p.name]))
            take = remaining[:room]
            assign[p.name].extend(take)
            remaining = remaining[len(take):]
            if not remaining:
                break
    if remaining:
        assign[providers[0].name].extend(remaining)
    # Keep each provider's chunk in global order.
    for name in assign:
        assign[name] = sorted(assign[name], key=lambda it: it[0])
    return assign


def run_pool(lines, lang, providers, on_status=None, on_switch=None,
             sleep=time.sleep, now=time.monotonic):
    """Voice every line on the pool. See module docstring for rules.

    lines: list[str] (global index = position + 1).
    providers: adapter objects (already constructed).
    Returns the QC dict (also what the CLI writes to pool.qc.json).
    """
    lines = [str(x) for x in lines]
    n = len(lines)
    qc = {"sentences": n, "shipped": 0, "gate_failed": 0,
          "provider_failed": 0, "lines": {}, "providers": {},
          "switches": []}
    if n == 0:
        return qc, {}

    health = {}
    alive = []
    for p in providers:
        try:
            ok, reason = p.health()
        except Exception as e:  # a broken health check = not alive
            ok, reason = False, f"health check error: {str(e)[:120]}"
        health[p.name] = (ok, reason)
        qc["providers"][p.name] = {"health": "ok" if ok else reason,
                                   "shipped": 0, "error": ""}
        if ok:
            alive.append(p)
    if not alive:
        for i in range(1, n + 1):
            qc["lines"][str(i)] = {"status": "provider_failed",
                                   "provider": "",
                                   "reason": "no provider alive"}
        qc["provider_failed"] = n
        return qc, {}

    by_name = {p.name: p for p in alive}
    items = [(i + 1, lines[i]) for i in range(n)]
    assign = split_items(items, alive)
    done = {}            # idx -> (mp3_bytes, provider_name)
    gate_failed = {}     # idx -> provider_name
    errors = {}          # provider name -> "reason: detail"

    def run_one(p, sub):
        if not sub:
            return ("ok", {}, None)
        try:
            d, q = p.run_batch(list(sub), lang, sleep=sleep, now=now)
            return ("ok", d, q)
        except ProviderError as e:
            return ("fail", {}, e)
        except Exception as e:  # transport trouble — failover-eligible
            return ("fail", {}, ProviderError("error", str(e)[:200]))

    def absorb(name, sub, state, d, payload):
        """Record one provider attempt. Returns the sub-items that
        failed at provider level (failover-eligible)."""
        if state == "ok":
            for idx, _ in sub:
                if idx in d:
                    done[idx] = (d[idx], name)
                    qc["providers"][name]["shipped"] += 1
                else:
                    gate_failed[idx] = name
            return []
        errors[name] = f"{payload.reason}: {payload.detail}".strip()
        qc["providers"][name]["error"] = errors[name]
        return list(sub)

    pending = [(by_name[name], sub) for name, sub in assign.items() if sub]
    failed_names = set()
    while pending:
        # Run this wave concurrently.
        results = {}
        if len(pending) == 1:
            p, sub = pending[0]
            results[p.name] = (sub,) + run_one(p, sub)
        else:
            with ThreadPoolExecutor(max_workers=len(pending)) as ex:
                futs = {ex.submit(run_one, p, sub): (p, sub)
                        for p, sub in pending}
                for fut, (p, sub) in futs.items():
                    state, d, payload = fut.result()
                    results[p.name] = (sub, state, d, payload)
        retry = []
        sources = []
        for name, (sub, state, d, payload) in results.items():
            retry.extend(absorb(name, sub, state, d, payload))
            if state != "ok":
                failed_names.add(name)
                sources.append((name, payload))
        if not retry:
            break
        # Failover: hand ALL provider-failed lines to the first alive
        # provider that has not itself failed (a provider that already
        # shipped its own chunk is a valid survivor), one switch line
        # per failed source. Each wave marks >=1 new provider failed,
        # so this loop always terminates.
        target = next((p for p in alive if p.name not in failed_names),
                      None)
        if target is None:
            for idx, _ in retry:
                qc["lines"][str(idx)] = {
                    "status": "provider_failed", "provider": "",
                    "reason": "all providers failed"}
            break
        for src_name, err in sources:
            qc["switches"].append({"from": src_name, "to": target.name,
                                   "reason": err.reason})
            if on_switch:
                line = _SWITCH_LINE.get(
                    err.reason, _SWITCH_LINE["error"]).format(
                    frm=_DISPLAY.get(src_name, src_name),
                    to=_DISPLAY.get(target.name, target.name))
                on_switch(line)
        if on_status:
            on_status(f"{_DISPLAY.get(target.name, target.name)} lo "
                      f"voice avthundhi…")
        pending = [(target, retry)]

    for idx, (blob, name) in done.items():
        qc["lines"][str(idx)] = {"status": "shipped", "provider": name}
    for idx, name in gate_failed.items():
        if str(idx) not in qc["lines"]:
            qc["lines"][str(idx)] = {"status": "gate_failed",
                                     "provider": name}
    qc["shipped"] = len(done)
    qc["gate_failed"] = sum(1 for v in qc["lines"].values()
                             if v["status"] == "gate_failed")
    qc["provider_failed"] = sum(1 for v in qc["lines"].values()
                                if v["status"] == "provider_failed")
    return qc, {idx: blob for idx, (blob, _) in done.items()}


def main():
    ap = argparse.ArgumentParser(
        description="Julie AI voice — free-GPU provider pool")
    ap.add_argument("lines", help="lines file, one sentence per line")
    ap.add_argument("--lang", default="te", choices=["en", "te", "hi"])
    ap.add_argument("--outdir", default="pool-out")
    ap.add_argument("--providers", default="",
                    help="comma list to restrict (default: all)")
    ap.add_argument("--config", default="",
                    help="providers.json overrides (weights/caps/enable)")
    a = ap.parse_args()

    config = {}
    cfg_path = a.config or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "providers.json")
    if os.path.exists(cfg_path):
        config = json.load(open(cfg_path))
    names = [s.strip() for s in a.providers.split(",") if s.strip()] or None
    providers = build_providers(names, config)

    lines = [ln.rstrip("\n") for ln in
             open(a.lines, encoding="utf-8") if ln.strip()]
    if not lines:
        print("ERROR: no lines in file", file=sys.stderr)
        return 2
    os.makedirs(a.outdir, exist_ok=True)

    def status(text):
        print(text, flush=True)

    qc, done = run_pool(lines, a.lang, providers, on_status=status,
                        on_switch=status)
    for idx, blob in sorted(done.items()):
        with open(os.path.join(a.outdir, f"{idx:03d}.mp3"), "wb") as fh:
            fh.write(blob)
    qc_path = os.path.join(a.outdir, "pool.qc.json")
    with open(qc_path, "w", encoding="utf-8") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    print(f"pool: {qc['shipped']}/{qc['sentences']} shipped, "
          f"{qc['gate_failed']} gate-failed, "
          f"{qc['provider_failed']} provider-failed — QC: {qc_path}")
    for name, info in qc["providers"].items():
        print(f"  {name}: health={info['health']} "
              f"shipped={info['shipped']}"
              + (f" error={info['error']}" if info["error"] else ""))
    return 0 if qc["provider_failed"] == 0 and qc["gate_failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

"""test_gpupool.py — scheduler/failover proof for gpupool with fake
adapters (no network, no credentials). Run: python3 test_gpupool.py

Covers: weighted split + caps, all-ok run, limit failover with
exactly one switch line, gate failures NOT requeued, capped-provider
overflow, every-provider-down loud failure, no-provider-alive, and
the real adapters' health honesty with nothing configured.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gpupool.common import ProviderError  # noqa: E402
from gpupool.pool import run_pool, split_items  # noqa: E402
from gpupool import adapters as ad  # noqa: E402


class Fake:
    def __init__(self, name, weight=50, max_lines=None, alive=True,
                 behavior="ok", gate_fail=()):
        self.name = name
        self.weight = weight
        self.max_lines = max_lines
        self._alive = alive
        self.behavior = behavior
        self.gate_fail = set(gate_fail)
        self.calls = []          # list of [global idx] per run_batch

    def health(self):
        return (True, "fake ok") if self._alive else (False, "fake down")

    def run_batch(self, items, lang, **kw):
        self.calls.append([i for i, _ in items])
        if self.behavior == "limit":
            raise ProviderError("limit", "quota exceeded")
        if self.behavior == "error":
            raise ProviderError("error", "boom")
        if self.behavior == "no_qc":
            raise ProviderError("no_qc", "no batch.qc.json")
        done = {i: b"MP3" for i, _ in items if i not in self.gate_fail}
        return done, {"fake": True}


def lines(n):
    return [f"line {i}" for i in range(1, n + 1)]


def items(n):
    return [(i, f"line {i}") for i in range(1, n + 1)]


def test_split_weighted_and_capped():
    a = Fake("kaggle", weight=50)
    b = Fake("modal", weight=30)
    c = Fake("hfspaces", weight=10, max_lines=3)
    d = Fake("actions", weight=20)
    asg = split_items(items(100), [a, b, c, d])
    total = sum(len(v) for v in asg.values())
    assert total == 100, total
    assert len(asg["hfspaces"]) <= 3, len(asg["hfspaces"])
    assert len(asg["kaggle"]) > len(asg["modal"]) > 0
    # every provider's chunk stays in global order
    for v in asg.values():
        idx = [i for i, _ in v]
        assert idx == sorted(idx)
    print("PASS split weighted + capped")


def test_all_ok():
    a, b = Fake("kaggle"), Fake("actions")
    qc, done = run_pool(lines(10), "te", [a, b])
    assert qc["shipped"] == 10 and qc["gate_failed"] == 0
    assert qc["provider_failed"] == 0 and qc["switches"] == []
    assert len(done) == 10
    print("PASS all ok")


def test_limit_failover_one_switch_line():
    a = Fake("kaggle", behavior="limit")
    b = Fake("modal")
    seen = []
    qc, done = run_pool(lines(10), "te", [a, b],
                        on_switch=seen.append)
    assert qc["shipped"] == 10, qc
    assert len(qc["switches"]) == 1, qc["switches"]
    assert qc["switches"][0] == {"from": "kaggle", "to": "modal",
                                 "reason": "limit"}
    assert len(seen) == 1 and "Kaggle GPU limit" in seen[0], seen
    # modal saw its own chunk first, then kaggle's lines as wave 2
    assert len(b.calls) == 2
    print("PASS limit failover, exactly one switch line")


def test_gate_failures_not_requeued():
    a = Fake("kaggle", gate_fail={1, 2})
    b = Fake("modal")
    qc, done = run_pool(lines(10), "te", [a, b])
    assert qc["gate_failed"] == 2, qc
    assert qc["shipped"] == 8
    flat_b = [i for call in b.calls for i in call]
    assert 1 not in flat_b and 2 not in flat_b, b.calls
    print("PASS gate failures reported, never requeued")


def test_all_providers_down():
    a = Fake("kaggle", behavior="error")
    b = Fake("modal", behavior="limit")
    qc, done = run_pool(lines(6), "te", [a, b])
    assert qc["provider_failed"] == 6 and qc["shipped"] == 0
    assert done == {}
    print("PASS all providers down -> loud failure, nothing shipped")


def test_no_provider_alive():
    a = Fake("kaggle", alive=False)
    qc, done = run_pool(lines(4), "te", [a])
    assert qc["provider_failed"] == 4
    assert qc["providers"]["kaggle"]["health"] == "fake down"
    print("PASS no provider alive")


def test_capped_provider_failover():
    hf = Fake("hfspaces", weight=10, max_lines=2, behavior="limit")
    a = Fake("actions", weight=20)
    qc, done = run_pool(lines(10), "te", [hf, a])
    assert qc["shipped"] == 10, qc
    assert qc["switches"][0]["from"] == "hfspaces"
    print("PASS capped provider failover")


def test_real_adapter_health_honesty():
    ok, reason = ad.LightningAdapter().health()
    assert ok is False and "not built" in reason
    ok, reason = ad.HFSpacesAdapter(
        state_path="/tmp/gpupool-test-nonexistent.json").health()
    assert isinstance(ok, bool) and isinstance(reason, str) and reason
    names = [p.name for p in ad.build_providers()]
    assert names == ["kaggle", "modal", "hfspaces", "actions",
                     "lightning"], names
    print("PASS real adapter health honesty + factory order")


def main():
    test_split_weighted_and_capped()
    test_all_ok()
    test_limit_failover_one_switch_line()
    test_gate_failures_not_requeued()
    test_all_providers_down()
    test_no_provider_alive()
    test_capped_provider_failover()
    test_real_adapter_health_honesty()
    print("test_gpupool: ALL PASS")


if __name__ == "__main__":
    main()

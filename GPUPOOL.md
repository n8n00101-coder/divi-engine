# GPUPOOL — free-GPU provider pool for the voice engine

Built 2026-11-16 on branch `feat/gpu-pool` (from main `b8bdb65`), in
answer to: *"Google Colab lo kuda GPU untadhi kadha — ila GPU free
tiers ichevi oka 10 add cheyu"* — for the production target of
**4 long videos/day × 15 min × 3 languages = 12 voice-overs/day
≈ 180 min narration ≈ 1,600+ sentences/day**, with no single-provider
disturbance.

**Honest headline: there are not 10 usable free-GPU providers. There
are 2 recurring pillars (Kaggle, Modal), 1 budget-capped micro-leg
(HF ZeroGPU), and 2 one-time bursts (Lightning, Fal). Everything else
surveyed is dead — no free tier, ToS-forbidden automation, signups
closed, or the API deprecated.** The pool is built so the viable ones
share the load and cover for each other; Actions CPU runners remain
the final fallback leg, exactly as before.

---

## Phase 1 — Survey (verified 2026-11-16 from each provider's own
pricing/docs pages; third-party roundups used only to find the page)

| Provider | Verdict | Free GPU | Automation | Signup needs |
|---|---|---|---|---|
| **Kaggle** | ✅ **VIABLE** | ~30 GPU-h/week ("sometimes higher" — Kaggle docs), 1× P100 or 2× T4, sessions ≤12 h, 20 GB output | **Official API** (`kaggle kernels push/status/output`) — headless is the sanctioned path | Account + **phone verification**; no card |
| **Modal** | ✅ **VIABLE** (conditional) | Starter = **$30/month recurring credit** ≈ ~50 T4-h/month (T4 $0.000164/s ≈ $0.59/h; A10 $1.10/h; A100-40 $2.10/h), 10 GPU concurrency | API/SDK-first, per-second billing — the cleanest automation of the list | Signup free; **payment method required for the full $30** (one checker reported $5/month without a card — sources conflict; treat card as required, set a $30 spend limit) |
| **HF Spaces ZeroGPU** | ⚠️ **MICRO-LEG** | Free account = **5 GPU-min/day** (2 min unauthenticated; PRO $9/mo = 40 min/day). RTX Pro 6000 Blackwell 48 GB | Gradio API / token calls — allowed | Account + verified email; account must be >30 days old + verified to *host* ZeroGPU Spaces |
| **Lightning AI** | ⚠️ **ONE-TIME** | 5 credits at registration + 25 for adding a card = 30 credits ≈ **50–80 interruptible GPU-h, ONE-TIME**, expires in 12 months (T4 on-demand $0.55/h) | Has an SDK ("automate with our SDK") | Signup; card for the +25 |
| **Fal** | ⚠️ **ONE-TIME** | **$20 signup credit** (business email; some reports say $10) — one-time, not recurring | API-first, serverless GPU (H100 from ~$1.89/h) | Business email |
| **Google Colab (free)** | ❌ **DEAD (ToS)** | T4, unpublished dynamic quota (~15–30 h/week reported), ≤12 h sessions, ~90 min idle disconnect | **ToS/FAQ explicitly prohibit** automated/programmatic use, bypassing the notebook UI, distributed-computing workers, and multiple accounts to dodge limits | — |
| **SageMaker Studio Lab** | ❌ **DEAD** | T4, 4 GPU-h/day | **Closed to new signups 2026-07-30** (AWS notice); browser JupyterLab, no headless API | Was approval + phone |
| **Paperspace Gradient** | ❌ **DEAD** | Free M4000 availability severely restricted since Nov 2023 | **Gradient API deprecated July 2026**; product sunset under DigitalOcean | — |
| **Replicate** | ❌ **DEAD** | **No free tier / no signup credit** (its own pricing + billing docs) | API-first but paid | Card/billing beyond demo runs |
| **DeepInfra** | ❌ **DEAD** | **No free credit — card or pre-pay before any use** (official pricing/docs) | API-first but paid | Card |
| **Salad** | ❌ **DEAD** | Official FAQ: *"Is there a free trial? No."* | — | — |
| **Beam** | ❌ **DEAD** | **$30/month free credit withdrawn Sep 2026** (removed from pricing/docs/homepage); now a $20/mo plan | — | — |
| **RunPod / Vast.ai** | ❌ **DEAD** | No free plan/trial on their pricing pages; RunPod's $10 credit unlocks only after a first $10 spend | — | — |
| **Oracle / GCP / Azure / AWS trials** | ❌ **DEAD as recurring GPU** | GCP Free Trial **forbids GPUs entirely** until paid upgrade; Oracle Always Free has **no GPU shapes** ($300 trial = 30 days, card, GPU eligibility not claimable); Azure $200/30 days with GPU quota behind PAYG upgrade; AWS free plan $100–200 credits, GPU unverified | All one-time, card-gated | Card |

**Recurring free supply, total: Kaggle ≈ 4.3 GPU-h/day + Modal
≈ 1.7 GPU-h/day + HF ≈ 0.08 GPU-h/day ≈ ~6 GPU-h/day.** Lightning
(~50–80 h) and Fal (~10 H100-h) are one-time bursts ≈ 2–3 days of
cover, not a supply.

---

## Phase 2 — What was built

New package `gpupool/` in this repo (branch `feat/gpu-pool`), plus
`test_gpupool.py`. Nothing else was touched — gates, phonetics and
`voice/settings.json` are byte-identical to main (the gate-2
recalibration is a separate task).

**The contract** (`gpupool/common.py`) is the engine's own batch
contract, the one Julie's voicecompute already proved against
Kaggle + Actions: in = contiguous (global index, text) items + lang;
out = one `<nnn>.mp3` per gate-passing line + `batch.qc.json`. A run
counts only if it completes AND carries the QC. Lines missing under
an OK run are **gate failures** (reported, never re-run elsewhere);
a provider-level failure raises `ProviderError` and **is** failover
eligible.

**Adapters** (`gpupool/adapters.py`) — each has `health()` (cheap,
local, credential-presence only), `weight`, `max_lines`, and
`run_batch(items, lang, ...)`:

| Adapter | Status | Notes |
|---|---|---|
| `KaggleAdapter` | **Built** | Port of the proven voicecompute kernel pattern: pushes a kernel (repo clone + CUDA flips, tolerant — replace-if-present, never crash on a moved line; te/hi also install `requirements-indicf5.txt`), polls status, downloads output. Creds from `KAGGLE_USERNAME`/`KAGGLE_KEY` or `~/.kaggle/kaggle.json`. One account — no rotation, by design. |
| `ModalAdapter` | **Built** | Real client code against the Modal SDK: `modal.Function.from_name("julie-voice-gpu", "run_batch").spawn(...)` + poll. Server half is `gpupool/modal_app.py` — deploy once with `modal deploy gpupool/modal_app.py` (T4 function that clones this repo, runs engine `--batch` on CUDA, returns the output zip). Health = SDK + token present. |
| `HFSpacesAdapter` | **Built** | Runs `engine.py --batch` locally with `JULIE_TTS_BACKEND=indicf5-space` (generation lands on the Space's ZeroGPU). Carries a **daily GPU-seconds budget** (default 300 s) in `~/.julie_gpupool_hf_budget.json`; `max_lines` derives from remaining budget at ~8 s/line (the measured Space probe). If a whole chunk ships 0 lines, it reports a limit failure so the scheduler fails over instead of writing the lines off as gate failures. te/hi only. |
| `ActionsAdapter` | **Built** | Port of the proven ActionsClient against `voice-batch.yml` (lines via Contents API under `jobs/`, artifact `julie-voice-batch-all`, file-relative numbering remapped to global). Token from `GH_TOKEN` or `gh auth token`. The final fallback leg. |
| `LightningAdapter` | **Registered, not built** | `health()` returns False with the reason (one-time credits only). No fake submit path. Build it only if the one-time burst is ever wanted. |

**Scheduler** (`gpupool/pool.py`) — CLI:
`python3 -m gpupool.pool lines.txt --lang te --outdir out/`
(writes `<nnn>.mp3`s + `pool.qc.json`; exit 0 = all shipped, 2 =
anything missing, same convention as the engine).

- Health-checks every adapter; dead ones are excluded and named in
  the QC with the reason.
- **Weighted contiguous split** across alive providers (defaults:
  kaggle 50 / modal 30 / actions 20 / hfspaces 10), honouring caps —
  HF takes only what its daily budget affords; overflow flows to
  uncapped providers, Actions last.
- Providers run **concurrently**.
- On a provider failure, ALL its unfinished lines move to the first
  alive provider that hasn't itself failed (a provider that already
  shipped its own chunk is a valid survivor), in failover order
  kaggle → modal → hfspaces → actions. **Exactly one status line per
  switch**, e.g. *"Kaggle GPU limit ayyindhi — migitha lines Modal
  GPU meedha continue chesthunna."*
- If every provider is down, the job fails loudly (exit 2, every
  line named `provider_failed`) — a partial result is never
  presented as complete.

**Proof status — stub-proven, not live.** No provider account exists
yet (see the account list), so no live run was possible.
`test_gpupool.py` passes 8/8 with fake adapters: weighted split +
caps, all-ok run, limit failover with exactly one switch line, gate
failures never requeued, capped-provider failover, all-providers-down
loud failure, no-provider-alive, and real-adapter health honesty.
The Kaggle and Actions adapters are ports of clients already proven
in Julie's voicecompute work; their live API shapes still need the
first real run to confirm (same open item as the Kaggle provider
build: push payload acceptance, status/output shapes, real quota
wording, end-to-end GPU timing).

---

## Phase 3 — Capacity math

**Load.** 12 voice-overs/day ≈ 180 min narration ≈ **1,600
sentences/day** (planning figure; the turbo proof script was 142
lines ≈ 20 min, i.e. ~130–145 lines per 20-min video).

**Takes per shipped sentence.** At the current ship rate (≈0.15 per
take, measured in the turbo proof: 849 takes / 108 shipped ≈ 7.9),
~**6.7 takes** must be generated per shipped sentence. Post-gate-fix
scenarios: ship 0.4 → 2.5 takes; ship 0.6 → 1.7 takes.

**GPU time per take.** ~**8 s measured** on the HF Space probe (RTX
Pro 6000). On Kaggle T4/P100 expect slower — **10–20 s/take
including on-GPU gate ASR is an estimate, not a measurement** (no
Kaggle account exists yet to measure with). The math below uses the
8 s anchor; double the hours if T4 lands at 16 s.

| Scenario | Takes/day | GPU-h/day needed | Covered by ~6 GPU-h/day free supply? |
|---|---|---|---|
| Current ship rate (~0.15) | ~10,700 | **~24 GPU-h/day** | ❌ No — ~4× short |
| Post-gate-fix ship 0.4 | ~4,000 | **~8.9 GPU-h/day** | ⚠️ GPU pool + Actions CPU tail together |
| Post-gate-fix ship 0.6 | ~2,700 | **~5.9 GPU-h/day** | ✅ Yes — Kaggle head + Modal + HF micro-leg |

**Conclusions.**
1. **At current ship rates the 12-video day is impossible on free
   supply** (~24 GPU-h/day needed vs ~6 available). The gate-2
   loanword recalibration (separate running task) is make-or-break —
   it, not more providers, is what closes the gap.
2. Post-gate-fix, the working combination is: **Kaggle as the head
   leg (~4.3 h/day), Modal second (~1.7 h/day), HF as a capped
   micro-leg, Actions CPU as the elastic tail** (95 s/take but ~20
   concurrent runners — the tail absorbs overflow and any GPU
   outage, at wall-clock cost, not correctness cost).
3. The ~10-min-per-20-min-video wall-clock class needs gate fix
   landed AND Kaggle + Modal both alive; with only one GPU leg up,
   long videos lean on the Actions tail and run slower. Shorts are
   comfortably inside target in all post-fix scenarios.
4. EN (Chatterbox) per-take GPU time differs from IndicF5 but is the
   same order of magnitude; the table uses the te/hi anchor for all
   three languages.

---

## Accounts Ajju must create himself (R18 — signup + phone/card
steps are his alone; everything downstream is built)

1. **Kaggle** — signup + phone verification + Settings → API →
   Create New Token (kaggle.json). *Unlocks ~30 GPU-h/week
   (P100/T4×2) — the pool's head leg, official API.*
2. **Modal** — signup (GitHub/Google) + add a payment method in
   Settings to unlock the full $30/month credit (set a $30 spending
   limit so nothing can charge beyond it). *Unlocks ~50 T4-h/month,
   API-first — the pool's second leg.*
3. **Hugging Face** — account + access token (email verification).
   *Unlocks his own 5 min/day ZeroGPU quota as a micro-leg + token
   priority on Spaces. Marginal but free.*
4. **Lightning AI (optional, one-time)** — signup; the +25 credits
   need a card. *Unlocks a one-time ~50–80 interruptible GPU-hour
   burst — launch-week cover, not supply.*
5. **GitHub** — already his. *The Actions fallback leg runs on this
   repo under his existing `gh` auth.*

**Do NOT create:** Colab (ToS bans this use), SageMaker Studio Lab
(signups closed), Paperspace / Replicate / DeepInfra / Salad / Beam
/ RunPod / Vast (no free tier), hyperscaler trials (card-gated,
GPU blocked or one-time).

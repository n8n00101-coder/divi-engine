"""Divi Engine — the self-healing repair loop (owner's law, 2026-11-16
20:19 IST): fail -> auto-check -> auto-fix -> deliver. "Ship nothing"
alone is rejected: pure failing wastes time and stalls work. The job
must complete, on time, with no mistakes in what it delivers.

This module is the playbook. It does not generate or gate anything
itself — engine.py executes the plans and records every step in the
QC report. Three rules govern everything here:

  1. CAUSE-SPECIFIC REPAIR. A blind re-roll is the weakest repair and
     is used only where it fits. The playbook per defect class:
       head grunt        -> deterministic mute at generation time
                            (acoustic_gates gate 6; NO re-roll spent)
       level jumps       -> deterministic gain match at assembly
                            (plain gain to the median; locked recipe)
       cut/detached end  -> seed re-rolls scored by final-word
                            completeness (gate 7 + last-word evidence)
       swallowed words   -> re-rolls scored by completeness
                            (gate 3 word probs/sims + gate 4 PHYS)
       pitch out of band -> best-of-N seed selection (score prefers
                            the band centre; never pitch-shifted)
       language / ghosts -> re-roll, then ESCALATE the sentence to
                            the alternate route / reference span
       identity / pace   -> best-of-N selection on the ship bar's own
                            margins (te/hi)
  2. BEST-OF-N BY DEFAULT. Every sentence gets N candidate takes per
     wave, generated in parallel (the same pool the speed law uses),
     all gated and SCORED; the best PASSING candidate ships. Repairs
     ride later waves of the same pool — they cost no extra
     wall-clock beyond the waves themselves.
  3. PER-SENTENCE INDEPENDENCE. A failing sentence never blocks the
     others or the job. Its escalation ladder runs: seed re-rolls ->
     wider best-of-N -> alternate backend route for that sentence ->
     alternate reference span where the recipe allows. Only when the
     whole ladder is exhausted does a sentence fail — and even then
     the job delivers everything else and NAMES the failed sentence
     in the QC report.

Repairs may vary SEED, ROUTE and REFERENCE SPAN only. Never tempo,
never a locked recipe value (the speed law is untouched by healing).
"""
import math

# Defect classes (strings used verbatim in QC repair logs).
GRUNT = "head_grunt"
CUT = "cut_word"
LANGUAGE = "language"
GHOST = "ghost_words"
PRON = "pronunciation"
SWALLOWED = "swallowed_words"
PITCH = "pitch"
IDENTITY = "identity"
PACE = "pace"
GENERATION = "generation_error"

# Clone routes per language for route escalation. Telugu has two
# clone routes of the SAME house voice (IndicF5 Space + OmniVoice);
# MMS is deliberately NOT in the ladder — it is a different speaker,
# so the identity bar would reject its takes anyway; it stays a
# diction tool, not a healing route for the house voice. English has
# one clone route (seed variants are its ladder). Hindi rides the
# IndicF5 route with alternate canonical reference spans.
CLONE_ROUTES = {
    "te": ["indicf5-space", "omnivoice"],
    "hi": ["indicf5-space"],
    "en": ["chatterbox"],
}
# Alternate reference spans (canonical refs.json keys; None = the
# default natspan2 reference). The recipe allows the canonical set.
REF_LADDER = [None, "natspan1", "natspan3"]
LOCAL_MODEL_BACKENDS = ("chatterbox", "mms")


def defect_classes(rep, ship_extra=None, gen_error=None):
    """The defect classes present in one gated candidate take."""
    if gen_error:
        return [GENERATION]
    if rep is None:
        return [GENERATION]
    out = []
    if not rep.get("gate1_nohint_language", {}).get("pass"):
        out.append(LANGUAGE)
    if not rep.get("gate2_ghost_words", {}).get("pass"):
        out.append(GHOST)
    if not rep.get("gate3_pronunciation", {}).get("pass"):
        out.append(PRON)
    if not rep.get("gate4_phys_swallowed", {}).get("pass"):
        out.append(SWALLOWED)
    if not rep.get("gate5_pitch", {}).get("pass"):
        out.append(PITCH)
    if not rep.get("gate6_head_grunt", {}).get("pass"):
        out.append(GRUNT)
    if not rep.get("gate7_cut_word", {}).get("pass"):
        out.append(CUT)
    if ship_extra:
        if ship_extra.get("identity_pass") is False:
            out.append(IDENTITY)
        if ship_extra.get("pace_pass") is False:
            out.append(PACE)
    return out


def take_score(rep, ship_extra=None):
    """A comparative quality score for one gated take (higher =
    better). Built ONLY from measured gate values: word-probability
    floor and phonetic similarity (diction), pitch centrality,
    and — for te/hi — the ship bar's identity/pace margins, minus
    hard penalties per defect. Used to pick the best PASSING take
    and to steer escalation; a failing take's score never ships it."""
    if rep is None:
        return -100.0
    g3 = rep.get("gate3_pronunciation", {})
    rows = g3.get("rows") or []
    sims = [r.get("sim") or 0.0 for r in rows]
    score = 30.0 * float(g3.get("min_prob") or 0.0)
    score += 20.0 * (sum(sims) / len(sims) if sims else 0.0)
    g5 = rep.get("gate5_pitch", {})
    f0 = g5.get("f0_med") or -1
    if f0 and f0 > 0:
        lo, hi = g5.get("band") or [185, 220]
        centre, half = (lo + hi) / 2.0, (hi - lo) / 2.0
        score += 10.0 * max(0.0, 1.0 - abs(f0 - centre) / half)
    if ship_extra:
        ident = ship_extra.get("identity")
        if isinstance(ident, (int, float)):
            score += 15.0 * max(0.0, min(1.0, (ident - 0.85) / 0.15))
        wps = ship_extra.get("pace_wps")
        if isinstance(wps, (int, float)):
            score += 10.0 * max(0.0, 1.0 - abs(wps - 2.2) / 0.3)
    score -= 8.0 * len(rep.get("gate4_phys_swallowed", {})
                       .get("fail_words") or [])
    score -= 10.0 * len(rep.get("gate2_ghost_words", {})
                        .get("ghosts") or [])
    if not rep.get("gate7_cut_word", {}).get("pass", True):
        score -= 15.0
    if not rep.get("gate6_head_grunt", {}).get("pass", True):
        score -= 20.0
    return round(score, 2)


def _spec(backend, ref, seed, action, defect):
    return {"backend": backend, "ref": ref, "seed": seed,
            "action": action, "defect": defect}


def candidate_plan(lang, primary_backend, wave, defects, n,
                   seed_base=0):
    """The candidate specs for one sentence's next wave.

    wave 1: N fresh candidates on the primary route (best-of-N by
            default — first-pass yield is the design goal).
    wave 2: defect-directed repair —
            language/ghost defects escalate the ROUTE first (te) or
            the REFERENCE SPAN (hi); generation defects (a route
            erroring) also move route; everything else gets wider
            seed re-rolls on the primary route, and te sentences
            also draw candidates from the alternate clone route in
            the same wave (parallel pool: no extra wall-clock).
    wave 3+: the full ladder — every clone route x reference span.
    Service backends (elevenlabs/http) have no clone ladder: their
    ladder is fresh candidates (each call is a new sample), and the
    plan says so honestly.
    """
    defects = defects or []
    routes = CLONE_ROUTES.get(lang, [])
    if primary_backend not in routes:
        # A service/operator backend: no clone ladder exists for it.
        return [_spec(primary_backend, None,
                      seed_base + 101 * (k + 1),
                      "fresh candidate (service backend — each call "
                      "is a new sample; no clone ladder)",
                      defects[0] if defects else None)
                for k in range(n)]
    specs = []
    if wave <= 1:
        for k in range(n):
            specs.append(_spec(
                primary_backend, None, seed_base + 101 * (k + 1),
                "best-of-N candidate (first-pass yield)",
                None))
        return specs
    escalate_route = any(d in defects for d in (LANGUAGE, GHOST,
                                                GENERATION))
    if wave == 2:
        if escalate_route and len(routes) > 1:
            alt = next(r for r in routes if r != primary_backend)
            for k in range(n):
                specs.append(_spec(
                    alt, None, seed_base + 401 * (k + 1),
                    f"route escalation {primary_backend} -> {alt} "
                    f"({'+'.join(defects)})",
                    defects[0]))
            return specs
        if escalate_route and lang == "hi":
            for k in range(n):
                specs.append(_spec(
                    primary_backend, REF_LADDER[1],
                    seed_base + 401 * (k + 1),
                    "alternate reference span natspan1 "
                    f"({'+'.join(defects)})",
                    defects[0]))
            return specs
        # Seed re-rolls on the primary route, scored by the defect's
        # own completeness measures; te also draws from the alternate
        # route in the same wave.
        main_n = n if len(routes) == 1 else max(1, math.ceil(n / 2))
        for k in range(main_n):
            specs.append(_spec(
                primary_backend, None, seed_base + 401 * (k + 1),
                f"seed re-roll, completeness-scored "
                f"({'+'.join(defects) or 'no defect recorded'})",
                defects[0] if defects else None))
        if len(routes) > 1:
            alt = next(r for r in routes if r != primary_backend)
            for k in range(n - main_n):
                specs.append(_spec(
                    alt, None, seed_base + 601 * (k + 1),
                    f"parallel alternate-route candidate {alt} "
                    f"({'+'.join(defects)})",
                    defects[0] if defects else None))
        return specs
    # wave >= 3: full ladder — routes x reference spans.
    combos = []
    for r in routes:
        if r == "indicf5-space":
            for ref in REF_LADDER:
                combos.append((r, ref))
        else:
            combos.append((r, None))
    for k in range(n):
        backend, ref = combos[k % len(combos)]
        specs.append(_spec(
            backend, ref, seed_base + 901 * (k + 1),
            f"full-ladder candidate ({backend}"
            + (f", ref {ref}" if ref else "") + ")",
            defects[0] if defects else None))
    return specs


def best_passing(candidates):
    """The best PASSING candidate record (highest score), or None.
    Records carry: ship (bool), score (float)."""
    passing = [c for c in candidates if c.get("ship")]
    if not passing:
        return None
    return max(passing, key=lambda c: c.get("score", 0.0))

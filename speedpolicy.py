"""Divi Engine speed policy — the single place tempo may change.

THE LAW (owner's order, 2026-11-16 20:07 IST): by default the engine
runs EXACTLY the locked settings — the voice recipes in
voice/settings.json and the locked routes (e.g. OmniVoice: natspan2
reference, generation speed 1.0, steps 32, guidance 2.0). The tool
must NEVER adjust speed on its own. A deviation from the locked speed
happens ONLY when the user explicitly requests it for that job (the
--speed CLI option), and the QC report must state the speed source:
LOCKED or USER-REQUESTED.

Three different things are called "speed" around this engine; the law
treats them differently, and this module keeps them separate:

  1. RECIPE TEMPO — a tempo factor that is part of a locked voice
     definition in voice/settings.json (today: Hindi's ONE atempo 1.20
     per take, the owner's approved +20% calibration, always logged).
     A recipe value is NOT an adjustment: it is the voice. It is read
     from settings here, nowhere else, and is reported as LOCKED.
  2. GENERATION-SIDE speed parameters — values a model takes at
     synthesis time (IndicF5 config.speed anchors per reference,
     OmniVoice's locked 1.0, MMS length scale). These are recipe /
     operator values fixed BEFORE generation; the tool never computes
     or adapts them per take. OmniVoice's is hard-locked in engine.py
     (OMNIVOICE_LOCKED); IndicF5's anchors live in settings.json.
  3. POST-GENERATION tempo alteration (atempo on a finished take) —
     the dangerous one, because it silently changes what the speaker
     sounds like. After the 2026-11-16 restructure there are exactly
     TWO legal callers, both in this module's care:
       a. the locked recipe tempo (Hindi 1.20, from settings), and
       b. an explicit user --speed factor for the job.
     The old third caller — the English pace guard's automatic
     atempo "nudge" (clamped to 1.12x) — is ABOLISHED: an out-of-band
     English take is now REJECTED and re-rolled, never stretched.
     pace_guard_decision() below has no atempo outcome at all.

Every QC report carries a "speed" block built by speed_block():
    {"source": "LOCKED" | "USER-REQUESTED",
     "user_factor": null | float,
     "recipe_tempo": float, "recipe_note": str}
so any shipped file can be audited for where its tempo came from.
"""
import subprocess

SOURCE_LOCKED = "LOCKED"
SOURCE_USER = "USER-REQUESTED"

# An explicit user factor outside this range is a typo, not a request:
# refuse it loudly rather than shipping a chipmunk / drawl.
USER_SPEED_MIN, USER_SPEED_MAX = 0.5, 2.0


class SpeedPolicyError(RuntimeError):
    """A speed request the policy refuses (out of range, or an attempt
    to change speed without an explicit user request)."""


def recipe_tempo(lang, settings):
    """The locked recipe tempo for a language: (factor, note).
    Hindi's +20% is part of its voice definition in settings.json —
    the owner's ear approved that pace as the Hindi voice's pace, so
    it applies on every Hindi take and is reported as LOCKED, never
    as an 'adjustment'. Every other language: 1.0 (no recipe tempo)."""
    if lang == "hi":
        pc = settings["hindi_indicf5"]["pace_calibration"]
        return float(pc["atempo"]), (
            "locked Hindi recipe: ONE atempo "
            f"{float(pc['atempo'])} per take (owner's +20% pace "
            "calibration, part of the voice definition in "
            "voice/settings.json)")
    return 1.0, "no recipe tempo for this language (factor 1.0)"


def resolve_user_speed(user_speed):
    """Validate an explicit --speed value (None = not requested).
    Returns the factor or None; raises SpeedPolicyError out of range."""
    if user_speed is None:
        return None
    f = float(user_speed)
    if not (USER_SPEED_MIN <= f <= USER_SPEED_MAX):
        raise SpeedPolicyError(
            f"--speed {f} is outside the sane range "
            f"[{USER_SPEED_MIN}, {USER_SPEED_MAX}] — refusing; if you "
            "really want that tempo, that is a new voice decision, "
            "not a job option")
    return f


def speed_block(lang, settings, user_speed):
    """The QC 'speed' block: where this job's tempo came from."""
    factor, note = recipe_tempo(lang, settings)
    return {"source": SOURCE_USER if user_speed is not None
            else SOURCE_LOCKED,
            "user_factor": user_speed,
            "recipe_tempo": factor,
            "recipe_note": note}


def apply_tempo(path, factor, why):
    """THE post-generation tempo function. Every atempo in the engine
    goes through here, and every call must name its legal basis in
    `why` ('recipe' or 'user'). There is deliberately no third basis:
    a caller that wants to 'correct', 'nudge' or 'normalise' a take's
    tempo has no function to call — it must reject the take instead.
    A factor of exactly 1.0 is a no-op (no ffmpeg run at all)."""
    if why not in ("recipe", "user"):
        raise SpeedPolicyError(
            f"apply_tempo called with basis {why!r} — the only legal "
            "bases are 'recipe' (a locked voice/settings.json value) "
            "and 'user' (an explicit --speed for this job). The tool "
            "never adjusts speed on its own (owner's order, "
            "2026-11-16).")
    if factor is None or float(factor) == 1.0:
        return False
    tmp = path + ".tempo.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-i", path,
                    "-af", f"atempo={float(factor)}", tmp, "-y"],
                   check=True)
    import os
    os.replace(tmp, path)
    return True


def pace_guard_decision(rate, ref_rate, band_frac):
    """The English pace guard, restructured under the speed law.
    Compares a take's onset rate with the reference's and returns:
      'ok'     — inside the locked band: ship-eligible, untouched;
      'regen'  — outside the band: ONE regeneration (a new take is
                 not a tempo change);
      'reject' — still outside after the regeneration: the take is
                 REJECTED and the caller's re-roll loop makes another
                 one. There is NO 'atempo' outcome — the pre-2026-11-16
                 guard stretched the take by up to 1.12x at exactly
                 this point, which is precisely the silent speed
                 change the law abolishes."""
    if ref_rate <= 0 or rate <= 0:
        return "reject"
    if abs(rate - ref_rate) / ref_rate <= band_frac:
        return "ok"
    return "regen"  # caller escalates a second 'regen' to 'reject'

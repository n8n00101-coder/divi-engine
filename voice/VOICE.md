# HOUSE VOICE — "Julie AI" (saved 2026-11-14 on Ajju's order)

PURPOSE: This is THE reference voice. When Ajju gives this voice to Hark (Blind)
for making videos, the returned videos must carry THIS EXACT voice, as-is.
Also Julie's house voice (v83 clone route) is built from this same sample.

CANONICAL SAMPLE (do not overwrite; keep forever):
- english-reference-sample.m4a (canonical sample, 25.0 s) — 25.0 s, md5 9814c79366152b3ff3977f69b75d19ba
  (a byte-identical duplicate was sent the same day)
- orig.wav — 24 kHz mono WAV render of the same sample (analysis/ref use)
- Provenance: female Indian-English narration voice of the WHO TAUGHT US team
  pipeline (Tab stack lists it as the ElevenLabs "Julie AI" voice); the sample
  was supplied by Ajju himself (2026-11-12/13, re-sent 2026-11-13 18:45 IST).

CONTENT: English documentary narration — "Is this entertainment or business?
So today we follow the money..." (women/college-safety explainer passage).

MEASURED DELIVERY PROFILE (2026-11-14, librosa + faster-whisper audit):
- Pitch (F0) median 221 Hz, range p10–p90 = 168–311 Hz (controlled, not dramatic)
- Pace: onset rate ≈ 5.24/s; overall ≈ 71 words / 25 s
- Style: emphasis by STRETCHING hinge words ("or" 0.68 s, "we" 0.64 s);
  function words reduced/softened; pauses only at phrase boundaries
  (0.66 s after a question); flowing, no mid-phrase gaps.

CLONE STATUS: Chatterbox zero-shot clone (Julie v83) — Ajju verdict
2026-11-14: "Voice ok". Known clone gaps being fixed: line-1 ~24% slow,
over-wide question pitch swing, extra mid-phrase pause, over-enunciated
function words. Proof files in ./proof/.

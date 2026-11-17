"""Cut a long reference clip down to a clean 6-11 s window that starts and
ends on whole sentences, with its exact transcript (faster-whisper word
timestamps). A reference that starts or ends mid-sentence makes OmniVoice
bleed the reference's words into short output sentences ("...part of the"
-> "of thee but be careful")."""
import re, sys, json
import numpy as np, soundfile as sf, librosa

def trim_ref(wav, out_wav, out_txt, lang="en", lo=6.0, hi=11.0, device="cuda"):
    from faster_whisper import WhisperModel
    y, sr = librosa.load(wav, sr=24000)
    y16 = librosa.resample(y, orig_sr=24000, target_sr=16000)
    try:
        m = WhisperModel("large-v3-turbo", device=device, compute_type="float16" if device == "cuda" else "int8")
        segs, _ = m.transcribe(y16, language=lang, word_timestamps=True, beam_size=5)
        words = [w for s in segs for w in s.words]
    except RuntimeError:
        m = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = m.transcribe(y16, language=lang, word_timestamps=True, beam_size=5)
        words = [w for s in segs for w in s.words]
    # sentence spans from punctuation on words
    sents, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w.word.strip()):
            sents.append(cur); cur = []
    # skip a first fragment that starts mid-sentence (lowercase start)
    best = None
    for i in range(len(sents)):
        if i == 0 and not sents[0][0].word.strip()[:1].isupper():
            continue
        for j in range(i, len(sents)):
            a, b = sents[i][0].start, sents[j][-1].end
            d = b - a
            if d > hi:
                break
            if d >= lo and (best is None or d > best[1] - best[0]):
                best = (a, b, i, j)
    if best is None:
        raise SystemExit("ref_trim: no clean window found")
    a, b, i, j = best
    a0, b0 = max(0, int((a - 0.08) * sr)), min(len(y), int((b + 0.15) * sr))
    clip = y[a0:b0].copy()
    f = int(0.01 * sr); clip[:f] *= np.linspace(0, 1, f); clip[-f:] *= np.linspace(1, 0, f)
    sf.write(out_wav, clip, sr)
    text = " ".join(w.word.strip() for s in sents[i:j + 1] for w in s)
    open(out_txt, "w", encoding="utf-8").write(text)
    print(json.dumps({"ref": out_wav, "seconds": round(len(clip) / sr, 2), "text": text}, ensure_ascii=False))

if __name__ == "__main__":
    trim_ref(*sys.argv[1:4], lang=sys.argv[4] if len(sys.argv) > 4 else "en")

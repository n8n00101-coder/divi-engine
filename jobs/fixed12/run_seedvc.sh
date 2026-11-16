#!/usr/bin/env bash
# fixed12: Seed-VC v2 conversion on a clean runner.
# Local VM findings baked in (2026-11-16):
#  - the seed-vc PyPI wheel's v2 modules are broken (bad relative import);
#    run inference_v2.py from the GitHub repo checkout instead.
#  - transformers must be 4.46.3 (voice-lib's 5.2.0 cannot import HubertModel
#    for the ASTRAL content extractor).
#  - torchvision must be absent (mismatched build breaks transformers imports;
#    the VC path does not need it).
#  - inference_v2.py hardcodes fp16, which is pathological on CPU -> patch to
#    fp32 when CUDA is absent.
set -eux
WS="$GITHUB_WORKSPACE"
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install seed-vc "transformers==4.46.3"
pip uninstall -y torchvision || true
git clone --depth 1 https://github.com/Plachtaa/seed-vc.git /tmp/seedvc-repo
sed -i 's/^dtype = torch.float16/dtype = torch.float16 if torch.cuda.is_available() else torch.float32/' /tmp/seedvc-repo/inference_v2.py
cd /tmp/seedvc-repo
python inference_v2.py --source "$WS/jobs/fixed12/src_mms_s2.wav" --target "$WS/jobs/fixed12/ref_gold_slice.wav" \
  --output "$WS/jobs/fixed12/out_gold" --diffusion-steps 10 --length-adjust 1.0
python inference_v2.py --source "$WS/jobs/fixed12/src_mms_s2.wav" --target "$WS/jobs/fixed12/ref_english.wav" \
  --output "$WS/jobs/fixed12/out_eng" --diffusion-steps 10 --length-adjust 1.0
ls -la "$WS/jobs/fixed12/out_gold" "$WS/jobs/fixed12/out_eng"

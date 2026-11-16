#!/bin/bash
cd ~/workspace/divi-engine-work
PY=~/workspace/.venv-voice/bin/python
for t in test_repair.py test_batch.py test_backends.py test_wholetake.py test_speedlock.py test_preflight.py proof_omnivoice_gates.py; do
  echo "===== $t =====" >> ~/workspace/divi-engine-work/.testlogs/rest.log
  $PY -u $t >> ~/workspace/divi-engine-work/.testlogs/rest.log 2>&1
  echo "----- $t exit: $? -----" >> ~/workspace/divi-engine-work/.testlogs/rest.log
done
echo ALLDONE >> ~/workspace/divi-engine-work/.testlogs/rest.log

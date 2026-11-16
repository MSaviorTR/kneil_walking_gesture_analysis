#!/bin/sh
# Host test (Linux/macOS/WSL with gcc): builds both models and runs the self-test vectors.
# Optional: pass a stream file (lines "ax ay az" in g at 50 Hz, device frame) to test the streaming path.
set -e
cd "$(dirname "$0")/.."
for M in forest tree; do
  DEF=""; [ "$M" = tree ] && DEF="-DKNEIL_MODEL_SMALL"
  gcc -O2 -std=c99 -Wall -Wno-unused-parameter $DEF -Iinclude src/kneil_features.c src/kneil_classifier.c \
      src/kneil_metrics.c src/kneil_selftest.c tests/host_test.c -o /tmp/kneil_host_test_$M -lm
  echo "[$M]"; /tmp/kneil_host_test_$M "$@"
done

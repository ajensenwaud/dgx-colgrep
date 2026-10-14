#!/usr/bin/env bash
# Build llama.cpp at colgrep's pinned release for the local GPU (default: GB10 / sm_121a, CUDA 13).
set -euo pipefail
. "$(dirname "$0")/env.sh"
OUT="$COLGREP_DIR/llama.cpp-$LLAMA_CPP_REL"
mkdir -p "$COLGREP_DIR"
if [ ! -e "$OUT/.git" ]; then
  git clone --depth 1 --branch "$LLAMA_CPP_REL" https://github.com/ggml-org/llama.cpp "$OUT"
fi
cd "$OUT"
export PATH="$CUDA_HOME/bin:$PATH"
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" -DGGML_NATIVE=ON \
  -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA_FA_ALL_QUANTS=ON
cmake --build build -j "$(nproc)" --target llama-server llama-bench llama-quantize
ls -la build/bin
echo BUILD_DONE

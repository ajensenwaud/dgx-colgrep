#!/usr/bin/env bash
# Fetch colgrep-agent-2B weights (GGUF first: the reference runtime's format) into $MODELS_DIR.
set -uo pipefail
. "$(dirname "$0")/env.sh"
D="$MODELS_DIR/colgrep-agent-2B"
mkdir -p "$D/gguf" "$D/hf"
get() { # url dest
  [ -s "$2" ] && { echo "have $2"; return; }
  curl -fL --retry 5 -C - -o "$2.part" "$1" && mv "$2.part" "$2" && echo "got $2"
}
G=https://huggingface.co/lightonai/colgrep-agent-2B-GGUF/resolve/c2e69958d03af9188af9ebf89582f8887f0bf534
H=https://huggingface.co/lightonai/colgrep-agent-2B/resolve/f798a61129c6decb5166864e0a3c98373e62c764
get $G/colgrep-agent-2B-Q8_0.gguf "$D/gguf/colgrep-agent-2B-Q8_0.gguf"
for f in config.json generation_config.json tokenizer.json tokenizer_config.json chat_template.jinja model.safetensors.index.json model-00002-of-00002.safetensors model-00001-of-00002.safetensors; do
  get $H/$f "$D/hf/$f"
done
get $G/colgrep-agent-2B-BF16.gguf "$D/gguf/colgrep-agent-2B-BF16.gguf"
echo FETCH_DONE

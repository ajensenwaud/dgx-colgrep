# Settings for the Spark-side scripts; override any of them in the environment.
COLGREP_DIR="${COLGREP_DIR:-$HOME/colgrep}"            # llama.cpp build, pid and log files
MODELS_DIR="${MODELS_DIR:-$HOME/models}"               # weights land in $MODELS_DIR/colgrep-agent-2B
LLAMA_CPP_REL="${LLAMA_CPP_REL:-b11476}"               # colgrep 1.8.5's pinned llama.cpp release
CUDA_ARCH="${CUDA_ARCH:-121a}"                          # GB10 (DGX Spark); 90 for H100, 89 for Ada, ...
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"

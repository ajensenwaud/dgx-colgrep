# Environment manifest (frozen for publication)

Recorded 2026-10-14 (AEDT). Every table in BENCHMARKS.md was produced on this stack.

## Hardware
| Role | Host | Detail |
|---|---|---|
| Agent-model server | DGX Spark-class box (ASUS Ascent GX10, NVIDIA GB10, 128 GB unified, CUDA 13.0 V13.0.88, driver 580.173.02) | single GPU, nothing else serving during measurements (GLM-5.3 stopped) |
| Coding agent + colgrep client + index | CPU-only workstation (AMD Ryzen 5 5500, 8 threads, 15 GB RAM, no GPU) | Hermes, colgrep CLI, ColBERT encoder on CPU (ONNX Runtime 1.23.0) |

## Software and model pins
| Component | Pin |
|---|---|
| ColGrep-Agent-2B (HF safetensors) | `lightonai/colgrep-agent-2B` @ `f798a61129c6decb5166864e0a3c98373e62c764` |
| ColGrep-Agent-2B GGUF | `lightonai/colgrep-agent-2B-GGUF` @ `c2e69958d03af9188af9ebf89582f8887f0bf534` (Q8_0 sha256 prefix `f238da91e6e95b1d`) |
| Local quants (Q6_K, Q5_K_M, Q4_K_M, IQ4_XS, Q4_0) | made from the BF16 GGUF with `llama-quantize`, no imatrix |
| ColBERT encoder | `lightonai/LateOn-Code-edge` @ `4bcdf5ed93f791259eb130b577a240f753d68dd8` |
| colgrep | 1.8.5, `lightonai/next-plaid` @ `c6c091d7ee14c81206bb28af90d8ff506fd0235e`, built from source (release, default features) |
| llama.cpp | `b11476` (`988190680d`), CUDA build, `CMAKE_CUDA_ARCHITECTURES=121a`, `GGML_CUDA_FA_ALL_QUANTS=ON` |
| Serving flags | `--special -ngl 999 -fa on --parallel 4 -c 65536 --cache-reuse 256` (`spark/serve_llamacpp.sh`) |
| colgrep agent settings | defaults (temperature 0.6, top-p 0.95, top-k 20, 10 turns, 2048 tok/turn, 16k context); seed 0 unless stated |
| Hermes Agent | `dce1e9b375`; batch 1 profile `colgrep-bench` (cloned from a personal profile), batch 2 profile `colgrep-clean` (fresh, no memory/persona/skills) |
| Coding model (A/B) | `claude-opus-5-5`, provider `anthropic`, Hermes default reasoning settings for the profile |
| Hermes plugin | `hermes-colgrep` (this repo), mode `agent`; 0.1.0 in batch 1 (reminder once per session), 0.2.0 in batch 2 (reminder on every grep-style call) |
| A/B tasks | batch 1: hermes-agent fix `f2d03c1f2a` at parent `3a8d95a93bdc`; batch 2: fix `bf7c716648` at parent `0b33ee88e4` |

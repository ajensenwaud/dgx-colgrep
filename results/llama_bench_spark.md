# llama-bench on the Spark (GB10), llama.cpp b11476 CUDA, flash attention on, all layers on GPU

Raw output as measured 2026-10-14. `pp` = prompt processing, `tg` = token generation (decode); `@ dN` = at N tokens of existing context.

## Q8_0 (shipped quant), 5 reps default
| test | t/s |
|---|---:|
| pp2048 | 8627.50 ± 155.14 |
| tg128 | 89.66 ± 0.35 |
| pp2048 @ d8192 | 6593.58 ± 124.65 |
| tg128 @ d8192 | 77.22 ± 0.42 |

## Quant ladder, `-p 1024 -n 64 -d 4096 -r 3`
| quant | size | pp1024 @ d4096 | tg64 @ d4096 |
|---|---:|---:|---:|
| BF16 | 4.69 GiB | 8044.22 ± 292.27 | 49.66 ± 0.26 |
| Q8_0 | 2.49 GiB | 7323.57 ± 289.50 | 83.00 ± 0.35 |
| Q6_K | 1.92 GiB | 6723.36 ± 234.45 | 93.54 ± 1.16 |
| Q5_K_M | 1.68 GiB | 7424.16 ± 155.56 | 106.10 ± 1.05 |
| Q4_K_M | 1.45 GiB | 7621.54 ± 252.11 | 113.82 ± 1.62 |
| IQ4_XS | 1.33 GiB | 8168.86 ± 353.75 | 121.78 ± 2.10 |
| Q4_0 | 1.38 GiB | 7994.79 ± 428.29 | 128.94 ± 1.34 |

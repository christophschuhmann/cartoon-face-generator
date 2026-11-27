# Local Gemma 4 26B-A4B for Robby

On 2026-11-20, Robby's default LLM was switched to a local, text-only
[Gemma 4 26B-A4B instruction QAT Q4_0 GGUF](https://huggingface.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf),
revision `d1c082be9cf3c8a514acf63b8761f4b41935842e`. It runs through
llama.cpp at `127.0.0.1:18826`; the browser talks to the existing Robby
server, not directly to llama.cpp. Qwen remains manually selectable. A one-time
local-storage migration changes the existing browser preference to Gemma;
subsequent user selections are retained. Local prompts are not sent to the
cloud model when Gemma is selected.

The target GGUF is 14,439,363,584 bytes; its SHA-256 was checked against the
model repository: `3eca3b8f6d7baf218a7dd6bba5fb59a56ee25fe2d567b6f5f589b4f697eca51d`.
The optional [QAT MTP draft](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF)
is pinned at `7b92b5b28818151e8669af2e45e88d6086f490dd`. It has SHA-256
`7272d97595f0d4c74bd7b623492b7dbdaafd8b7c72f329a8270ba4eca68f768a`.

## Host and configuration

Two RTX 3090s, 24 GB each; NVIDIA driver 550.54.15. GPU 1 is dedicated to
Gemma. Parakeet Ultra ASR, ECAPA speaker recognition, TTS and the Robby
backend use GPU 0, which also runs other existing services. Free GPU 0 memory
is limited; concurrent heavy workloads could still cause OOMs. The podcast
server was stopped at the owner's request. Gemma uses an 8192-token context,
one request slot, all target layers on GPU, Flash Attention, Q8 K/V cache,
batch 512 / microbatch 256, and currently one MTP draft token. That last
setting is experimental: the small comparison below does not demonstrate a
reliable benefit.

The active `llama-server` is built from llama.cpp commit `5d9e5ac` with CUDA
12.3 and Flash Attention. `--no-mmproj` is intentional: this Robby integration
is **text-only**. Although the upstream model supports vision, image input,
50k context, and the proposed school-grading use case were not evaluated here.
Model answers and tool calls can be wrong and need task-specific evaluation.

## Measurements on this host

These are small exploratory runs, not a broad benchmark. Four authored German
Robby prompts used approximately 2,181 system-prompt tokens, a loaded model,
temperature 0.7 and one request at a time. TTFT is server-side first token,
not audible response latency. Warm measurements reuse the prompt prefix.

| Mode | Cold prompt processing | Cold TTFT | Warm TTFT | Generated tokens/s |
|---|---:|---:|---:|---:|
| Flash Attention, no MTP | ~1.50 s (~1,452 tokens/s) | 1.59 s | 0.52–0.55 s | 87.5–97.3 |
| Flash Attention, MTP 1 | ~1.6 s | 1.68 s | ~0.50 s | 88.8–98.4 |
| Flash Attention, MTP 2 | ~1.61 s | 1.69 s | 0.49–0.51 s | 85.7–95.6 |

An earlier build with Flash Attention disabled took about 94–100 seconds to
prefill a comparable prompt and generated approximately 8–9 tokens/s. The
build flag made the important difference. Sampling and short output lengths
make the small MTP comparisons noisy; no general MTP speedup is established.
Run `/home/c4r33u19/moss15v2/.venv/bin/python benchmark_gemma26.py` from
this directory for the four authored prompts; the script prints generated text
and server timings. Run against one configuration at a time and distinguish
first-run prefix processing from subsequent prefix-cache hits.

### Prompt prefix reuse

A cold prompt means that the particular starting token sequence is not
available for reuse in the active llama.cpp slot. It does **not** mean that
the model weights must be reloaded or that the old Flash-Attention-disabled
build returns: the optimized GPU configuration processes the new prompt.
For a repeated, token-identical prefix, the slot can reuse its stored KV state
and prefill only the changed suffix. For example, an unchanged system prompt
followed by a new user question can still benefit; editing or inserting text
near the beginning invalidates reuse from the first changed token onward.
Actual reuse depends on chat-template formatting, memory/tool/context changes,
which request last occupied the slot, cache capacity and the 8192-token
context limit. It is not guaranteed across server restarts or concurrent
requests. The approximately 1.6-second cold and 0.5-second warm first-token
figures above apply to the specific small synthetic test, not all Robby turns.
The live server log also contained examples around 2.9–4.4 seconds LLM TTFT,
so full session latencies can be materially higher.

An HTTPS Playwright typed-message test used the real local model and TTS: first
server PCM was approximately 2.81 s after reply processing started, followed
by a complete response. A browser synthetic-microphone test exercised browser
capture, WebSocket, Parakeet, local Gemma and TTS; one final ASR pass took
approximately 228 ms. These numbers are separate stages, not an end-to-end
latency guarantee. A synthetic somersault request exercised actual animation
and speech. A weather-tool test used a mocked weather result; a banana
interruption-rule tool call was also tested. None is proof that all tools,
physical microphones, languages or long conversations are reliable.
The legacy enrolled-only gate is disabled in the current sentence mode, so
its corresponding browser-test branch is explicitly skipped; that skip does not
establish speaker-filter reliability. Sentence mode uses ECAPA voice labels
and separate wake/focus controls.

## Start and recovery

The launcher defaults to the RAM-backed `/dev/shm/robby-gemma`. Files there
are lost at reboot. The November 27 deployment uses a persistent NVMe
directory so future restarts can reuse the weights. Set `ROBO_GEMMA26_DIR`
to the same directory whenever you restart the service.

```sh
export ROBO_GEMMA26_DIR=/mnt/nvme/robby-gemma
/home/c4r33u19/moss15v2/.venv/bin/python start_gemma26.py --download
curl -fsS http://127.0.0.1:18826/health
```

The pinned target needs about 13.45 GiB plus the optional draft and at least
1 GiB spare. `--download` skips already present files. The launcher refuses to
replace a process on its port. Use `--drafts 0` for no MTP, `--drafts 1` for
the measured default, and `--engine /path/to/llama-server` to select another
compatible build. It is not configured to start automatically on reboot.
Restore the separately managed Robby, ASR, ECAPA and TTS services too if they
are down. Do not expose the unauthenticated LLM server directly to the network.

## Further optimization

[NInfer's Linux guide](https://github.com/iamwavecut/ninfer-all/blob/master/docs/build-linux.md)
requires CUDA toolkit 12.8 or newer for RTX 3090; its
[Gemma 4 guide](https://github.com/iamwavecut/ninfer-all/blob/master/docs/gemma4.md)
documents a separate converted model. Its reported timings are not our
measurements. CUDA 12.8 runtime initialization was tested successfully with
this driver, but the compatible 12.8 compiler, the NInfer engine and its
approximately 14.75 GiB artifact were not installed or benchmarked; a CUDA 13
runtime test failed with the current driver. Available persistent disk and
RAM-backed space are currently too limited for the extra model. Benchmark
NInfer only after provisioning space and its toolchain, using the same real
prompts, quality checks, streaming TTFT and full response measurements.

A separate build of a newer llama.cpp revision with Flash Attention was started
but stopped before completion to avoid continued background CPU load and disk
use on the nearly full host. It has not been benchmarked; the active build is
the older working Flash Attention build identified above.

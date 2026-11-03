# Robby inference on RTX 3090 (3 November 2026)

The active demo uses two RTX 3090 cards, 24 GiB each. Its default Humaneness Voice Small RL TTS runs on GPU 1; ASR, local LLM and lab services also occupy these GPUs. These measurements are from this host. The upstream `INFERENCE_OPTIMIZATIONS.md` describes a Jetson Thor, not this machine.

## Results and scope

The same authored German TTS request, reference voice, temperature 0.8 and CFG 2 was measured before and after the changes, with three warm seeds per condition. Initial results: first PCM 771 → 76 ms; last PCM 1.81 → 0.626 s; generated audio 4.64 → 4.80 s; simulated listener gaps 0 s in both conditions. The last production restart is checked separately in the linked raw report; small timing variations are expected. Different arithmetic and sampling streams can change duration and tokens.

First PCM may include initial silence. In three additional positive-temperature probes, the first nonquiet chunk arrived after approximately 127–139 ms. All four quality fixtures (neutral, playful, angry and temperature zero) were finite, audible and transcribed by Parakeet v3 with zero WER. This small check is not a systematic test of perceived naturalness or speaker similarity.

A Chrome test through the public HTTPS demo used three authored microphone fixtures. From the last audible input block to the first scheduled browser output, times were 1.15–1.71 s (median 1.398 s), with no playback underruns. Median components: final ASR text 306 ms after speech end, server first sentence 517 ms, server TTS first audio 101 ms, browser start reserve about 315 ms. Stages overlap and come from different clocks; do not add these medians as an exact total. Physical microphone, speaker and device latency are excluded. This session did not collect a before/after baseline for the whole pipeline.

See [the HTML report](static/rtx3090-speed.html) and [raw results](static/rtx3090-speed.json). The preliminary microphone measurement erroneously used an internal wake-phrase pause as the utterance end; it is superseded by the final fixture-aware measurement.

## What was enabled

The implementation comes from `LAION-AI/Humaneness-Voice` commit `d3d1045` (`playground/runtime/`). It includes:

- BF16 merged policy weights, replacing FP32 merged weights on this host.
- SHA-256 content keys and a bounded cache for encoded reference audio. Three fresh copies of one reference took 262.9 ms for the initial encode and 0.6 ms on cache hits.
- Early streaming release with fade-in and the existing final-word cutoff, with less alignment hold-back.
- Semantic CUDA graphs with compiled decode and 512-token capacity buckets.
- Triton codebook prediction and fused codec kernels, codec CUDA graphs, and growing 3→6→12→20-frame chunks.
- Stable prompt prefixes for local LLMs, and speculative final ASR reused only while the speech segment is unchanged. The latter was reused in two of three final browser runs.

On the installed PyTorch 2.6.0+cu124 / Triton 3.2.0, the upstream compiled local sampler failed with a scalar-capture error. `HVS_LOCAL_COMPILE=0` is therefore intentional. The separately supplied Triton local path works here. Its fallback needed a zero-temperature guard, supplied in `optimizations/tts-zero-temperature.patch`. A real temperature-zero request also passed the quality check.

The independent engine check compared BF16 waveforms at three fixed seeds: codec graph on/off yielded identical arrays. Its warm engine times were about 14.3–14.6 ms/frame without codec graphs and 7.1–7.2 ms/frame with graphs. These engine timings exclude HTTP, alignment and browser buffering. They must not be substituted for end-to-end latency.

No native FP8/NVFP4 hardware path is assumed for RTX 3090. No PyTorch/CUDA upgrade or model replacement was needed.

## Reproduce and restart

Use the pinned upstream TTS runtime and its existing dependencies and model assets. Copy `optimizations/rtx3090-speed.env` and `optimizations/start_rtx3090_tts.sh` into `playground/runtime/` (the live directory here is `/mnt/nvme/moss-15-v2/humaneness-small`). Apply the zero-temperature patch from that runtime directory with `git apply --unidiff-zero /path/to/tts-zero-temperature.patch`. Set `ROBBY_TTS_PYTHON` to the Python executable of the prepared environment, then run the start script. On this host that executable is `/home/c4r33u19/moss15v2/.venv/bin/python`.

The flags are explicit and reversible. The original experimental checkpoint CPU prefetch remains enabled in the final production configuration, retaining on-demand UI model choices; latency tests must still run while the GPU is otherwise idle. Allow compilation/warm-up before readiness; cold new prompt buckets can be much slower. Startup and test jobs are serialized. Do not start a second engine benchmark during a latency test.

Run the upstream `live_latency_benchmark.py --repeats 3`, then this repository's `rtx3090_quality_check.py`. `browser_mouth_to_ear.py --config 'optimized|https://YOUR_HOST|' --runs 1` measures three synthetic microphone requests. The fake microphone has no TTS echo, so its last audible block is the utterance end, even when it contains a long internal pause. The script has a decoder fallback for older SoundFile builds.

`browser_personality_speed_check.py` checks the more conversational persona, explicit sentence counts, actual speech packets and rendered anger pose. It uses typed requests and is not an ASR test. Both the streaming prompt and the tool-director policy now encourage two to four connected sentences for open questions, with vivid but fitting emotional acting cues. Explicit length requests, greetings and simple commands may remain brief.

## Remaining costs

Cloud LLM first-sentence latency varies, and the browser intentionally reserves about 300 ms for short first chunks. Reducing that reserve can save time but has previously caused gaps. More expensive model calls, speaker ambiguity, cold loads, news tools and concurrent lab analysis add latency. The report describes the tested warmed Small RL single-stream path, not every model, batch size or real room condition.

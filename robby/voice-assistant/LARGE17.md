# Switching Robby between Small and Large 1.7

The **Voice synthesis** selector beside the language-model controls chooses
Humaneness Small 1.1 Alpha RL or **Humaneness Voice Large 1.7**. Small remains
the default. The browser remembers an explicit choice. This selects the shared
server's TTS worker, not a private GPU instance for each browser tab.

Large uses the merged root release at
`laion/Humaneness-Voice-Large-1.7`, revision
`f008a7a685122b8d0e45f2c44f1912c93e29f352`, in BF16. Do not attach its training
adapter again. The compatible runtime, pinned hashes, optimized kernels,
reference handling and benchmark scripts live in
[Humaneness-Voice](https://github.com/LAION-AI/Humaneness-Voice/blob/main/docs/LARGE17_RTX3090.md).
Use the fixed Mira reference (10.26 seconds); Large accepts 5.04–14.96 seconds
of reference speech. Its reference waveform is cropped before tokenization.

## Request flow

1. `POST /api/tts/models` validates the choice, rejects a switch during an
   active reply, starts the swap and returns HTTP 202 promptly.
2. `GET /api/tts/models` reports selection, loading state and errors. The
   browser polls this short request, avoiding a Cloudflare timeout during
   loading or compilation. New turns wait on an asynchronous readiness event.
3. The TTS service keeps verified CPU weight copies and one selected GPU
   model. Small and Large share the audio codec but use their own processor
   and tokenizer. Common streaming shapes are warmed before the swap completes.
4. Sentence TTS and interjections carry the selected model ID. A returned
   model receipt is checked against the requested model and added to the
   turn's latency metrics (`tts_model`, `tts_actual_model`, `tts_revision`).
   Interjection caches include the model ID; old acknowledgment audio is cleared.

Existing ASR, Qwen/Luna selection, wake mode, memory, interruption logic, avatar
actions and face tracking remain in place. The optional continuous two-stage
reaction scheduler keeps its Small-only path. Large uses ordered sentence
streaming. The selector changes speech synthesis, not the conversational LLM.

## Measured results and limits

Open **Speed measurements** beside the selector, or
[`static/large17-speed.html`](static/large17-speed.html), for the English table,
component profile, synthetic listening clips and raw receipts. The report
distinguishes resident GPU inference, HTTP audio onset and the HTTPS browser
test. Cold model loading and compilation are not warm TTFA.

On the measured RTX 3090, the original Small optimization package gives Large
approximately 0.403 seconds to first PCM and RTF 0.275 for one short CFG-2
stream. The additional layerwise compiler gives similar warm speed while
reducing the compilation unit. A 16-candidate short offline batch reaches
aggregate RTF 0.065; its streaming counterpart reaches 0.090. The serving cap
is conservatively 8 to retain headroom for longer prompts and speech finishing.
Aggregate RTF divides by all candidates' duration; it is not individual-user
latency or a guarantee of 16 concurrent real-time conversations.

The benchmark uses synthetic prompts and references. ASR canaries and numerical
checks are not a blinded assessment of naturalness, emotion or cloning quality.
The default CFG remains 2, temperature 0.8. No quantization experiment silently
changes the model's weights or guidance settings.

The real HTTPS browser check passed all four typed turns: Small audio, Large
audio, Large audio with a spin action, then Small audio again. Both Large turns
reported the pinned Large checkpoint. No browser JavaScript errors occurred.
Later model swaps took 16.0 s to Large and 60.1 s back to Small; loading and
graph capture remain separate from speech TTFA. The matching local HTTP
first-PCM medians with alignment were 0.474 s (Large) and 0.403 s (Small).

## Reproduce the integration checks

Install the pinned TYGER dependency as described in the main setup guide, or
point `ROBO_TYGER_SOURCE` at an existing checkout. Then run:

```bash
python -m unittest -q test_tts_models test_bridge test_two_stage \
  test_avatar_commands test_quick_reactions
```

`experiments/large17/browser_check.py` drives the actual HTTPS demo with
Playwright and synthetic typed prompts. It switches Small → Large → Small,
checks actual checkpoint receipts and PCM, and verifies the spin action while
Large speaks. Override `ROBO_TEST_URL` to test another host. This requires the
configured conversation-model credentials on the server, never in the test.
It does not simulate a physical microphone. Test browser storage disables
memory, camera and idle behavior only in the isolated test profile.

The runtime repository also contains `api_check.py` for direct HTTP streaming,
`quality_check.py` for Parakeet transcription canaries and the full GPU timing
matrix. No private microphone audio, enrolled voiceprints, keys, downloaded
weights or compiler caches belong in either Git repository.

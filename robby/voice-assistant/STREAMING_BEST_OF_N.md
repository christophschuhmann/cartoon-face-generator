# Causal best-of-N streaming for Humaneness Voice

This documents the existing Voice Acting Studio search and Robby's new
reference-aware variant. Both keep one winner at each selection boundary;
this is a width-one, beam-like online search rather than complete-utterance
best-of-N. Once sent, audio cannot be revised.

## Algorithm

1. Pack the same prompt and fixed reference for N batched continuations.
2. Generate 10 frames (800 ms) or 20 frames (1,600 ms); decode the new frames
   incrementally and append them to each candidate's already generated prefix.
3. Transcribe each accumulated prefix in one batched ASR call. Intermediate
   edit distance compares against the best target prefix, without counting the
   as-yet-unspoken suffix as deletion; the terminal chunk uses full-target WER.
   Ignore the unstable last 100–120 ms when selecting partial words.
4. Score, select the best row, stream its newly committed audio, and clone its
   conditional/unconditional semantic KV cache, masks, acoustic tokens and
   streaming decoder state to N rows. Continue sampling independent children.
5. Reuse selection word timestamps to cut/fade boundaries, if enabled. Do not
   run a second, independent ASR output-verification pass.

The rolling ASR implementation keeps up to 12 s of recent speech, with a
three-word overlap and at most 27 s per decode, and retains older selected word
history. The WER is therefore a prefix-alignment surrogate, not a guaranteed
full-utterance WER. Decoder-state cloning and irreversible commit are in
`beam_search.py`; selection timestamps and fades are in `asr_chunk_search.py`.

## Scoring: what the historical code actually did

The older Studio `search_scoring.py` starts with:

```
gate = 1 - clamp(prefix_WER, 0, 1)
clap01 = clamp((VoiceCLAP_cosine + 1) / 2, 0, 1)
genuine01 = clamp(genuineness / 6, 0, 1)
blend01 = clamp(blend / 10, 0, 1)
reward = gate * (0.50 * clap01 + 0.25 * genuine01 + 0.25 * blend01)
```

When `combine_identity` enables the speaker reward, the historical default
**replaces** that quality blend rather than adding another hidden term:

```
speaker01 = clamp((ECAPA_cosine + 1) / 2, 0, 1)
reward = gate * (0.40 * clap01 + 0.60 * speaker01)
```

The older Robby `search_asr` path instead used
`(matched_words - 2 * edit_errors) / target_words`; it did not calculate
VoiceCLAP, ECAPA or genuineness. Its published throughput figures must not be
presented as measurements of the new quality-aware path.

## New Robby mode and rollback

`search_quality` applies the 40/60 Studio formula to the existing batched
`ASRSearchScorer`, reuses its timestamps for the edge fades and makes no extra
ASR verification pass. VoiceCLAP encodes candidate audio as a batch; the
already-running private ECAPA worker computes reference and candidate vectors.
To bound repeated work, VoiceCLAP and ECAPA inspect at most the most recent
15 s; ASR maintains its own rolling history. Reference identity uses the
actual selected TTS reference. N=4, 10 frames, Small RL are the requested
defaults. A score of zero on all candidates is possible, including silence;
prefix WER is not an independent assessment of speech quality.

In **Speed & verification**, unchecking Best-of-4 restores single-candidate
streaming and the existing selectable parallel/serial ASR checker. Settings
persist per browser. Unsupported models and optional idle/quick reactions keep
their existing single-stream paths. OOM before playback triggers one bounded
single-stream retry; after playback begins it never replays the whole sentence.
Missing scorer services and CUDA failures are surfaced rather than inventing
scores. The selected reference can be a cloned voice: similarity is a metric,
not proof of identity or perceptual fidelity.

## Validation and performance

Run `test_quality_chunk_search`, `test_asr_chunk_search`,
`test_tool_capabilities`, `test_speech_retry`, and an actual browser/audio
smoke test. Evaluate multiple seeds and held-out German/English utterances with
independent ASR and human listening. The previous `search_asr` pilot reported
0.867 s median first PCM and 0.558 median wall RTF for 12 warm cases on a
different two-GPU placement; it is not a benchmark of this new scorer. The
first N=4 graph compilation may take minutes and consumes additional VRAM.
Inspect `logs/` for current host measurements and OOMs before calling the new
mode faster. An 800-ms chunk denotes generated audio, not end-to-end latency.

### RTX 3090 pilot, 2026-11-25

One German sentence, seed 777, same 4.74 s decoded duration, Small 1.1 Alpha
RL, N=4 and 800 ms, GPU 0 shared with Robby's other components. First-ever
N=4 use after a restart compiled/captured new graphs: 523.6 s to first PCM and
529.8 s wall time. Once warm, the same case took **1.865 s to first PCM** and
6.193 s total (wall RTF 1.31). The previous verified single-stream path took
**0.713 s to first PCM**, 1.315 s total (wall RTF 0.28). These are individual
engineering measurements, not representative medians or quality evidence.

The warm N=4 search attributed 1.32 s to TTS/codec and 4.11 s to candidate
scoring; ASR and the four ECAPA/VoiceCLAP evaluations dominate. The first
warm search commit occurred at 0.98 s inside generation, but trimming and
HTTP playback delivery delayed first PCM. Consequently this configuration is
**slower**, not a demonstrated latency optimization. A cold first response
can exceed client timeouts and block other TTS jobs for minutes. Keep the
single-stream rollback available, prewarm in a controlled idle period after
restarts, and do not represent a cold service as ready for low-latency use.
See `logs/candidate-search/quality-n4-{cold,warm}/results.json` for local
per-step timing. Neither WER nor subjective voice quality was independently
evaluated here.

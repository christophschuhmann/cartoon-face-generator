# Batching unchanged 64-class groups — 9 November 2026

Public report: https://diane-asylum-understood-invoice.trycloudflare.com/audio-decision/batch64.html

This is an isolated GPU experiment. It does not change the deployed engine or page defaults.

## Question

Can the existing 64-class multi-label groups be processed together, without changing the prompts, class order, scene context or target interval? Nine groups cover the 527 classic AudioSet classes: eight groups of 64 and one of 15.

## Main result

527 classes, 10-second history, final 200 ms target; RTX 3090 GPU 1, BF16:

| Groups per GPU batch | Actual forwards | Warm median | Peak allocated tensors |
|---|---:|---:|---:|
| 1 | 9 | 2.091 s | 4.18 GiB |
| 2 | 5 | 1.732 s | 4.30 GiB |
| 4 | 3 | 1.736 s | 4.54 GiB |
| 8 | 2 | 1.676 s | 5.01 GiB |

Nine warm runs per configuration: three authored signals × three repetitions, with rotated ordering. Batch 8 saves 19.9% relative to the contemporaneous sequential control. Ranges overlap: batch 2 already achieves most of the benefit. These figures are not compared against yesterday's different-GPU timing to inflate the claimed improvement.

A separate final-beep-only follow-up used five warm repetitions each: sequential 2.204 s, batch 8 at 1.641 s, and all nine groups in a single measured forward at 1.572 s. All-nine peak allocation was 5.13 GiB. This follow-up's relative improvement is measured against its own control, not the main study's timing.

## Correctness and limits

- The experiment's batch-1 output exactly matches the deployed implementation: maximum absolute difference 0.0.
- All 527 scores are present, finite and between 0 and 1. They are mapped by official AudioSet ID.
- Main-study maximum score difference for batched shapes: 0.006158; zero threshold crossings at 0.5 on these inputs. Top-10 sets overlap by nine or ten classes. This is numerical consistency testing, not labeled recognition accuracy.
- The native API can batch several requests internally. `_slot_logits` instrumentation records actual forward rows and padded token counts, avoiding the mistaken inference that one API call always means one forward.
- The padded-token budget is 65,536 for this bounded experiment. The deployed engine remains at 4,096 and sequential group calls.
- Feature reuse verifies exact repeated log-mel/mask tensors and preserves clip order. It calls the audio encoder once per window rather than once per repeated request. A native batch-8 ablation without deduplication was also run; small BF16 batch-shape differences remain, so equivalence is not asserted bit-for-bit against that native multi-clip encoder path.
- A separate target-repeat test passed at batch 8, with maximum difference 0.005351 against its sequential reference. Only one timing pair was measured for that option.
- Input signals: final 200 ms 880 Hz beep, deterministic chirp plus Gaussian noise (seed 4271), and silence. No user microphone recordings or private voiceprints are used.
- No `torch.compile`, precision changes, retraining, different question groups, future audio or synthetic model outputs.
- Timing includes actual model invocation and result parsing, with CUDA synchronization. Warm-up/model load are separate. Tensor peak excludes cached reservations, CUDA-context overhead and other processes.
- Long scene context, 20-second history and sustained active TTS contention are not validated by this test. The existing temporal-localization counterexample is not solved by batching.

## Safety and reproduction on this host

Robby's inference services and the resident decision model on GPU 0 remain untouched. The experiment uses a separate process on GPU 1 and a dedicated lock. A 30% PyTorch per-process allocator limit leaves headroom for other resident models. Check available memory before running; the loader requires at least 6 GiB free. The process releases its model memory when it exits. Do not stop other users' jobs.

From `/mnt/nvme/moss-15-v2/robo-integration`:

```bash
AUDIO_DECISION_DEVICE=cuda:1 PYTHONPATH=/mnt/nvme/robby-audio-decision/env:. /home/c4r33u19/moss15v2/.venv/bin/python -m audio_decision.batch64_study
AUDIO_DECISION_DEVICE=cuda:1 PYTHONPATH=/mnt/nvme/robby-audio-decision/env:. /home/c4r33u19/moss15v2/.venv/bin/python -m audio_decision.batch64_nine
/home/c4r33u19/moss15v2/.venv/bin/python -m audio_decision.batch64_report
```

Run the two experiments sequentially. Raw scores, timings, initialization metadata, actual forward shapes, feature-reuse counters and memory peaks are saved in `batch64-result.json` and `batch64-nine-result.json` beside the scripts. The HTML report copies only those authored-input artifacts into the public static directory.

The checkpoint remains `LiquidAI/d1-Omni-2B`, revision `81222dae8bf8bdd7f903643b5b2a8803bf2e3176`; the isolated dependencies are the same as the existing lab. See `README.md` and `environment.json` for setup. No production restart is needed to publish the static report.

# Voice attribute display: verified normalization and proposed UI

Requested follow-up: a five-second trailing sliding window, Genuineness and
Vulnerability in addition to Warmth/Roughness, and a perceived vocal gender
indicator alongside the approximate vocal age. The exact target page still
needs identifying: Robby's current static UI does not contain the described
bottom-right Young Adult / Roughness panel. These notes are research findings,
not a claim that that panel has already been changed.

## Published reference statistics

Model repository: https://huggingface.co/laion/humaneness-ears-base-medium
Verified revision: `818506970d93c809a3295a0a02c40dee8ff2bfc3`.

The repository already publishes
[display_normalization.json](https://huggingface.co/laion/humaneness-ears-base-medium/blob/818506970d93c809a3295a0a02c40dee8ff2bfc3/display_normalization.json).
Its display formula is `(raw_prediction - training_median) / training_standard_deviation`.
This differs from `training_normalization.json` (model training transforms).
Never apply a model's training denormalization twice.

| Suggested display | Output key | Training median | Training standard deviation |
|---|---|---:|---:|
| Genuineness | genuineness_0_6 | 2.3320 | 1.6214 |
| Vulnerability | vn_VULN_reg | 2.6484 | 0.9842 |
| Warmth | vn_WARM_reg | 2.5781 | 0.9093 |
| Roughness | vn_ROUG_reg | 2.0332 | 0.8868 |
| Arousal / energy | vn_AROU_reg | 2.3594 | 1.1473 |
| Articulation clarity | vn_CLRT_reg | 2.0176 | 0.9447 |
| Vocal tension | vn_TENS_reg | 1.5586 | 0.8516 |

These statistics use 100,858 training examples, not a moving min/max over the
few current recordings. A Roughness score of 4.0 is about +2.22 SD above the
training median even though it is not near the nominal raw ceiling. A compact
bar could map z in [-3,+3] to its width while preserving raw and z in a tooltip;
label it “relative to training reference”, not probability or percentile.
Median plus SD is not an empirical CDF, and the reference distribution is not
necessarily Gaussian. Clipping the visualization must not alter the raw export.

## Proposed presentation

Keep the current design. Prefer Genuineness, Vulnerability, Warmth and Arousal as
primary tiles, with Roughness, Clarity and Tension optional. These are estimated
vocal qualities, not judgments of a person's honesty or actual mental state.

Use the last five seconds, updated around once per second, with shorter windows
clearly marked during startup. Do not pool different speakers into an identity
profile. A little display smoothing can reduce flicker, but retain raw values.

For perceived gender, keep the midpoint of the **semantic gender scale**, not
the training-population median: a dataset's gender balance must not redefine
neutral. Show an uncertain middle band, e.g. “ambiguous voice presentation”,
with blue/green/pink as requested. Labels should say “young-adult-sounding,
masculine/feminine voice” rather than claiming the person's actual age or gender.
This is a measurement indicator, not an editable control that changes the model.

The existing procedural captioner's VoiceNet GEND scale increases toward
masculine, decreases toward feminine, and has an androgynous band around 3.
A left-masculine/right-feminine indicator therefore needs its visual direction
reversed relative to the raw VoiceNet score. The EIV Gender scale instead runs
from negative masculine to positive feminine; never treat these two numeric
scales as interchangeable. Verify the actual selected output head in the target
UI before wiring the indicator.

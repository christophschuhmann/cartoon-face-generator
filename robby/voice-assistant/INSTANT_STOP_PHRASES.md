# Live spoken stop phrases

When Robby is speaking in sentence-stream mode, a fresh ASR partial containing
an explicit stop control cancels playback directly, without waiting for the
speaker-embedding check or the semantic Laya decision. It does not produce a
spoken acknowledgement or use the phrase to enroll a speaker. The microphone
remains active. Existing TYGER and semantic interruption paths remain in use.

Examples: `Stopp`, `Stopp Stopp`, `Stopp Robby`, `Robby halt`, `leise Robby`,
`Robbie quiet`, `Stop Robbie`, `Robby wait`, and `Hör bitte auf`. Matching is
case insensitive and recognizes explicit ASR spellings including Robby, Robbie,
Robbi, Robi, Robie, Roby, Rabi, Rabbi, Robo, Robot, Hobby, Hoppy, Wobby and Wobbly. The last
four are possible ASR confusions, not fuzzy matches. The full list and exclusions are in
`stop_commands.py`; it also recognizes Cyrillic `стоп`, which was observed in
a German stop test. Common negated and definitional phrases are excluded.
Partials may be revised, however, and no word-list matcher can perfectly infer
intent. Old recognition results are rejected using reply and age checks.

The direct path deliberately does **not** verify that the stop came from the
conversation owner. A background speaker or a playback echo may therefore
stop Robby. The text echo check and browser acoustic echo cancellation still
operate but do not guarantee separation. This is a tradeoff for responsiveness.
Likewise, the match only fires once actual ASR text arrives; microphone capture,
speech segmentation, GPU contention, recognition and network transport still
contribute latency. The separate `Stop reply` button is an immediate manual
fallback. Interruption is not speaker authentication.

When Parakeet Ultra is the active final recognizer, a short live stop probe can
use up to three seconds of already-received microphone audio during playback,
without waiting for the lagging TYGER hop clock. If another ASR model is selected,
the original recognition path remains. The probe is single-flight and falls
back to the existing path if the required microphone frames are unavailable.

## Tests

```sh
/home/c4r33u19/moss15v2/.venv/bin/python -m unittest \
  test_stop_commands test_sentence_reliability test_stop_feedback \
  test_speaker_session test_shared_turn
/home/c4r33u19/.local/bin/uv run --no-project --with playwright \
  --python /home/c4r33u19/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3 \
  browser_instant_stop_check.py --fixture christoph-stop
espeak-ng -v de -s 145 -w /tmp/robby-stop-pair.wav 'Stopp Robby'
# Repeat the browser command above with --fixture /tmp/robby-stop-pair.wav.
```

The browser test uses a synthetic prerecorded utterance mixed with delayed TTS
echo, the public HTTPS UI, actual ASR, LLM and TTS. It is not a physical-room
or multi-person test. Test output in `logs/` is local and excluded from exports.
On 2026-11-20 a short prerecorded synthetic `Stopp` stopped real TTS via the
direct path in 2,055 ms from the start of the 1.104-second fixture. The browser
received the stop-bearing ASR preview at 2,051 ms and cancellation at 2,055 ms.
Earlier single runs before the microphone-clock and Cyrillic-alias changes took
4,785 ms for this fixture and 5,260 ms for `Bitte hör auf zu sprechen`. These
isolated trials are not controlled latency distributions or a guarantee; actual
recognition may be slower, wrong or absent.
A separate browser run using an eSpeak synthetic “Stopp Robby” did not stop
within the 12-second deadline. A subsequent isolated Parakeet transcription
of that fixture returned “Stop hobby”; this led to the explicit `hobby` alias.
After adding it, another run stopped at 3,958 ms; its ASR had earlier produced
“Stop wobby” and “Stop wobbly”, so these observed spellings were also added.
In the final rerun the same synthetic two-word audio stopped playback after
1,993 ms, 3 ms after a `Stop.` preview. ASR did not emit the name in this run,
so it verifies the live short-stop path, not independent acoustic recognition
of the name variants. The spelling variants were separately unit-tested.

# Interrupting Robby while it speaks

What happens when you talk while Robby is still speaking, what was wrong, how the decision
model fixes it, how fast it is, and how to test it. Written for people new to voice assistants.

## The problem (October 31)

Robby has several ways to notice that you want to interrupt:

1. **Acoustic detector** (TYGER): a small model listens to the microphone and estimates "the
   user is taking the turn" (`yield_prob`). A speaker check then confirms it's the person
   Robby is talking to, not Robby's own voice from the loudspeaker or a TV.
2. **Literal stop words**: ASR text that exactly matches a stop command ("Stopp", "Hör auf").
3. **Decision model for agreed rules**: a language model checks live text against rules you
   agreed on ("interrupt me when I say banana"), but it only ran when a stop word was heard.

Everything else you said while Robby was talking was **queued until Robby had finished**. In a
browser test (a long story, then one interruption 7 s later):

| You say while Robby tells a story | Before |
|---|---|
| "Stopp, Robby, hör kurz auf." | **kept talking**: the ASR text "Stopp Robby, hör kurz auf!" did not match the strict stop pattern |
| "Moment mal, ich habe eine andere Frage." | stopped, but only because the acoustic detector happened to fire |
| "Mhm, ja." | kept talking (correct), but only because the voice check rejected it |
| "Robby, wie spät ist es eigentlich?" | **ignored**: queued until the end of the story |

## The fix: ask the decision model about every utterance during speech

When a complete utterance arrives while Robby speaks, and it has already passed the usual speaker
checks (wake word window, conversation focus, addressed speech), `sentence_session.py` asks the
decision model (`live_decisions.speech_turn_action`) for one of three actions:

| Action | When | What Robby does |
|---|---|---|
| `stop` | you want Robby to stop or pause: stop, wait, one moment, quiet, let me speak | stops playback |
| `answer` | you take the turn with something that needs a reply now: a new question or request, a topic change, a correction or objection | stops and answers your utterance |
| `continue` | backchannel or a reaction that needs no reply (mhm, ja, genau, wow, laughter), garbled fragments, or an echo of Robby's own words | keeps talking; the utterance is dropped |

Details:

* Clear stop phrases (`stop_commands.has_stop_intent`, e.g. "Stopp, …", "Warte mal …",
  "Hör auf") skip the model and stop immediately.
* The model sees your text, Robby's current reply (to recognize echo) and the last few turns.
  It answers with JSON, temperature 0, at most 20 tokens.
* Model: the configured decision endpoint (`ROBO_DECISION_BASE` / `ROBO_DECISION_MODEL`), else
  the local Bolt/Gemma model in bolt mode, else the dialogue provider (`DecisionClient.endpoint`).
  On this host that is Gemma 4 E4B NVFP4 on the local GPU: ~0.4–0.7 s per decision.
* If the model fails or takes longer than 2.5 s, the old behavior applies (queue until Robby
  finishes). `ROBO_SPEECH_TURN_DECISIONS=0` switches the feature off.
* The page receives a `speech_turn_decision` message with the text and chosen action (`queue`
  when the model was unavailable), so the decision is visible in the browser's event log.
* The acoustic detector and the literal stop path are unchanged and can still stop Robby earlier,
  while you are still speaking.

Direct check of the decision model with Robby telling a dragon story:

| Utterance | Decision | Time |
|---|---|---|
| "Stopp Robby, hör kurz auf!" / "Warte mal kurz." | stop (no model needed) | ~0 ms |
| "Moment mal, ich hab eine andere Frage." | stop | 702 ms |
| "Robbie, wie spät ist es eigentlich?" | answer | 480 ms |
| "Nein, das stimmt doch gar nicht, Drachen können nicht fliegen." | answer | 505 ms |
| "Erzähl lieber was über Hunde." | answer | 420 ms |
| "Mhm, ja." / "Wow, cool." / "Haha, lustig." | continue | 410–430 ms |
| "über das Tal" (echo of Robby's own words) | continue | 560 ms |

## Results in the browser

`browser_interruption_check.py` (same test as above, one run per case):

| Interruption | Expected | Result | Stop after you finish speaking |
|---|---|---|---|
| "Stopp, Robby, hör kurz auf." | stop | stopped | 0.32 s (stop phrase, no model) |
| "Moment mal, ich habe eine andere Frage." | stop | stopped (decision `stop`) | 2.1 s |
| "Mhm, ja." | keep talking | kept talking | – |
| "Robby, wie spät ist es eigentlich?" | stop and answer | stopped (decision `answer`) and answered | 2.5 s |

**Passed 4/4.** The decision path is still slow: the 2.1–2.5 s add up from the 300 ms
end-of-speech pause, the final transcription, the speaker checks, and the model decision. During
this test, a second live session was also using the same GPU. Ideas to make it faster:

* start the decision on a stable partial transcript instead of waiting for the end of the utterance;
* run the decision in parallel with the speaker checks instead of after them;
* lower Robby's volume as soon as an utterance from the conversation partner starts ("ducking"),
  so that a slow decision is less disruptive.

Limitations: the browser test uses a synthetic microphone, so Robby's voice does not come back
through a loudspeaker. In a real room, the existing echo and voice checks run before the decision,
and the model is told to treat echoed Robby words as `continue`.

## How to test

```bash
# separate test instance (Robby allows one live session per server)
ROBO_PORT=8893 ROBO_MOUTH_PORT=8895 ROBO_MEMORY_DIR=/tmp/robby-test python server.py
python browser_interruption_check.py --url http://127.0.0.1:8893 --runs 2
```

The script generates its spoken fixtures once with the local TTS (voice "Idris", not Robby's
"Mira") under `logs/interruptions/`. Unit tests: `test_pause_endpoint.SpeechTurnDecisionTests`.

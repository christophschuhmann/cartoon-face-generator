# Browser-local Buddy wakewords

Robby recognizes the three English commands in a dedicated browser CPU/WASM
worker. The worker shares one mel-spectrogram model and one speech-embedding
model across all three commands. It uses a two-second window on a 160-ms grid.
Overlapping windows reuse the embeddings for identical audio positions. When
the device falls behind, the worker picks up the latest window.

| Browser asset | Published variant | Size on disk |
| --- | --- | ---: |
| Hey Buddy | English Tiny | 121,243 bytes |
| Go Buddy | English Medium | 954,452 bytes |
| Stop Buddy | English Medium | 954,452 bytes |
| Shared mel and embedding models | LiveKit | 2,414,536 bytes |
| **Total ONNX models** | | **4,444,683 bytes** |

Tiny is available for Hey. Medium is the smallest published classifier for Go
and Stop at the pinned revision. The previous six Large heads and shared
models totalled 26,106,814 bytes. The three compact heads reduce the browser's
model payload by 83%. ONNX Runtime Web adds 11.72 MB of JavaScript and WASM
before HTTP compression on first load.

## Use

The guide below the call buttons stays visible during a turn. For example, say “Hey Buddy”, wait for the red recording indicator, say “Erzähl mir einen Witz”, then say “Go Buddy”. A pause leaves the recording open until a command or the 60-second limit.

1. Open the Robby page. Buddy wakewords are enabled by default. If the browser
   asks, allow microphone access. Browsers can also require a tap on **Enable
   microphone & sound** or **Start talking** before capture/playback starts;
   a website cannot bypass these browser permission and autoplay restrictions.
2. Wait until the Buddy status says **Listening locally**, then say **“Hey
   Buddy”**. A red recording indicator appears. Speak the request.
3. Say **“Go Buddy”** to upload and transcribe that recording and get a reply.
   Say **“Stop Buddy”** to discard it; during playback Stop also interrupts.
4. Say Hey again for another request. Uncheck the Buddy checkbox to use the
   existing Robby/ASR conversation mode. Your subsequent choice is saved.

Buddy mode always sends the original microphone recording. It pauses VoxLock
and Scicom and releases their GPU worker. A confirmed Go Buddy can start a
conversation with an unfamiliar speaker. Session speaker embeddings can still
supply a name. Switching back to normal listening restores the saved filter.
A recorded turn marked “Request transcribed” has finished ASR. The conversation
panel shows the reply and playback once the downstream stages complete.

The page keeps standby audio and the current recording in browser memory only.
When Go is detected, the bounded (maximum 60-second) recording is transferred
for server ASR, speaker handling and response generation. A short ASR hint, if
confirmation is uncertain, is returned only to that browser session. An
800-ms pre-roll reduces clipping after Hey. On a failed or uncertain Go check,
the local recording stays available so Go can be repeated. No ASR runs during
standby. Closing the page, disabling Buddy, or stopping the microphone discards
the local recording. A browser may suspend work in a background tab; this is
not a native background service.

## Sources and reproducible setup

The Flutter app's `lib/services/wakeword_service.dart` uses a 16-kHz, two-second
ring buffer and the same mel → embedding → three independent wakeword heads,
with a 500-ms timer, mutual exclusion, and desktop v3 models. Its Android
configuration uses smaller models to avoid native-runtime crashes. The
[Flutter project](https://github.com/LAION-AI/bud-e-flutter-openrouter) and
[LAION model repository](https://huggingface.co/laion/bud-e_wakeword-models_livekit-wakeword)
describe the original pipeline and per-command checkpoints. Robby uses a single
head per command. The two Medium heads sometimes both score highly on Stop,
so a strong Stop has priority and Go requires weak Stop evidence. The server
confirms Go with ASR after local detection. These thresholds are experimental.

```sh
python prepare_browser_buddy.py   # pinned models and Runtime, SHA-256 checked
python -m unittest test_buddy_wake
# Supply a directory with synthetic hey.wav, go.wav, stop.wav, request.wav,
# and go-bunny.wav; Chromium, ffmpeg and Python Playwright are required.
export BUDDY_FIXTURES=/path/to/synthetic-fixtures
# For a tunnel test, set this to the current public /desk-robot/ URL.
export ROBBY_DEMO_URL=http://127.0.0.1:8793/desk-robot/
python browser_buddy_model_check.py
python browser_buddy_check.py
BUDDY_TEST_ISOLATION=voxlock python browser_buddy_check.py  # saved normal-mode filter
python browser_buddy_autostart_check.py
```

Run microphone tests sequentially. The live pilot serves one microphone session
at a time.

Browser assets are served from `static/wake-models` and
`static/vendor/onnxruntime`. The LAION checkpoints are pinned to
`86020dab86d481b1cba9f4d0fd73a911ab87fc3a`. The mel and embedding models
are pinned to the LiveKit revision in `download_buddy_models.py`.
`prepare_browser_buddy.py` provisions just the browser models and ONNX
Runtime Web 1.20.1 (MIT). The server's legacy detector has a separate setup.

## Browser verification

On 2026-11-25 Chromium ran the real compact ONNX models against synthetic
Hey, Go and Stop audio. On a single 160-ms advance, the incremental worker
returned the same three scores as recomputing the complete window (maximum
absolute difference zero). One desktop run took 96 ms for the incremental
evaluation and 477 ms for full recomputation. These are worker CPU timings
on this host. Command recognition also depends on when the words occur in
the audio and on the device's processing speed.

The public HTTPS test exercised Hey → request → Stop (discard) and Hey →
request → Go (submit), received a response and scheduled playback. It also
checked zero standby microphone packets and switching back to normal ASR.
The sequence passed on desktop Chromium and in Pixel 5 Chromium emulation
with a second synthetic voice. The browser keeps 800 ms after a local Go
detection so the server can transcribe the complete command.
Local test receipts are under `logs/browser-buddy-smoke-*.json`. Physical
microphone, noise and accent coverage remain limited.

Wakeword classifiers are not secure authentication. A synthetic **“Go bunny”**
can score highly as Go Buddy, and even ASR has occasionally mistaken it for
Buddy. Go therefore is not guaranteed to reject similar phrases. Stop is
immediate and can also fire incorrectly. Use the microphone off control when
not actively using the demo. Browser autoplay and persistent microphone
permission behavior differ between platforms and cannot be overridden by this
application.

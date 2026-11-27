# Remote API for Gemma and Humaneness Voice

The optional HTTPS gateway uses the running Gemma and Humaneness Voice
services. Run it separately when you need remote API access. Obtain the host
name, TLS certificate and bearer token directly from the deployment operator.
Use the host name or IP address covered by the certificate.

```sh
export ROBBY_API_HOST='your-api-host.example'
scp "your-account@${ROBBY_API_HOST}:.config/robby-api/server.crt" ./robby-api.crt
scp "your-account@${ROBBY_API_HOST}:.config/robby-api/token" ./robby-api-token
chmod 600 ./robby-api-token
export ROBBY_API_KEY="$(cat ./robby-api-token)"
export ROBBY_API_BASE="https://${ROBBY_API_HOST}:18830/v1"
curl --cacert ./robby-api.crt "$ROBBY_API_BASE/models" -H "Authorization: Bearer $ROBBY_API_KEY"
```

## Chat: OpenAI-compatible responses

Use model `gemma-4-26b-a4b-q4`, an 8192-token context and the usual `messages`.
The default is non-streamed JSON. `"stream":true` yields OpenAI-style
`text/event-stream` `data:` records and `[DONE]`.

```sh
curl --cacert ./robby-api.crt "$ROBBY_API_BASE/chat/completions" \
  -H "Authorization: Bearer $ROBBY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"gemma-4-26b-a4b-q4","messages":[{"role":"user","content":"Hallo!"}],"max_tokens":128}'

curl -N --cacert ./robby-api.crt "$ROBBY_API_BASE/chat/completions" \
  -H "Authorization: Bearer $ROBBY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"gemma-4-26b-a4b-q4","messages":[{"role":"user","content":"Hallo!"}],"max_tokens":128,"stream":true}'
```

Reasoning is disabled by default for latency. Expert clients can explicitly
send `"chat_template_kwargs":{"enable_thinking":true}`; reasoning tokens then
consume the output budget and latency. The API is an OpenAI-compatible subset;
unsupported backend parameters can return a backend error.

## Speech: OpenAI-compatible request, explicit PCM streaming extension

Use `/v1/audio/speech`, model `humaneness-voice-small` and a voice such as
`mira`, `selma`, `idris`, `anton`, `robin`, `osku`, `cormac`, `rasmus`,
`nora`, or `bela` (`alloy` maps to Mira). The model is
[Humaneness-Voice-Small-1.1-Alpha-RL-r128-v1](https://huggingface.co/laion/Humaneness-Voice-Small-1.1-Alpha-RL-r128-v1).
Input is capped at 1,600 characters and 120 words. The optional `instructions`
field controls style. There is no input-text streaming or uploaded voice here.

```sh
curl --cacert ./robby-api.crt "$ROBBY_API_BASE/audio/speech" \
  -H "Authorization: Bearer $ROBBY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"humaneness-voice-small","voice":"mira","input":"Hallo, wie geht es dir?","response_format":"mp3"}' \
  --output speech.mp3

curl -N --cacert ./robby-api.crt "$ROBBY_API_BASE/audio/speech" \
  -H "Authorization: Bearer $ROBBY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"humaneness-voice-small","voice":"mira","input":"Hallo, wie geht es dir?","response_format":"pcm","stream":true}' \
  | ffplay -autoexit -nodisp -f s16le -ar 24000 -ac 1 -i -
```

Buffered responses support MP3, WAV and PCM. The `stream` request property is a
gateway extension; live streaming currently supports **only** raw 24-kHz mono
signed 16-bit little-endian PCM. Stream HTTP chunks are arbitrary byte blocks,
not individually playable WAV/MP3 files. The final MP3/WAV is buffered and sent
when generation is complete. ASR verification and fades come from the existing
TTS service and can delay first audio or fail. A failure after the streaming
headers have been sent terminates the stream; it cannot change the HTTP status.
The underlying single TTS service is shared with Robby; concurrent generation
can return HTTP 409 and callers should retry with backoff.

## Operator notes

The gateway binds `0.0.0.0:18830` with TLS and Bearer authentication; the
unprotected llama.cpp and TTS backends remain loopback-only. Certificate, TLS
private key and API token are in `/home/c4r33u19/.config/robby-api/` with
restricted permissions and are not included in source exports. The certificate
expires 2027-11-20; replacing it requires securely distributing the new public
certificate and updating the public `static/robby-api.crt` copy. A changed
public IP also requires an updated IP certificate.

```sh
cd /mnt/nvme/moss-15-v2/robo-integration
/home/c4r33u19/moss15v2/.venv/bin/python start_openai_gateway.py
/home/c4r33u19/moss15v2/.venv/bin/python check_openai_gateway.py
```

The gateway does not start automatically after reboot. For the Gemma weight directory and restart procedure, see [GEMMA26_LOCAL.md](GEMMA26_LOCAL.md) for its restart
and download instructions. Start the independently managed TTS service as well.
Logs do not intentionally contain tokens, prompts or audio. Never commit the
credential directory, and do not disable TLS certificate verification to
work around deployment issues.

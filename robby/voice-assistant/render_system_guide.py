"""Rebuild public capability docs and three native SVG diagrams from code enums."""
from pathlib import Path
import json,html
from avatar_actions import EMOTIONS,KINDS,VARIANTS,TOOL
from knowledge_tools import TOOLS
from interaction_policy import TOOLS as RULE_TOOLS
from tool_capabilities import ROUTE_TOOL
from emotion_recipes import GERMAN
ROOT=Path(__file__).parent;OUT=ROOT/'static'

def svg(name,title,subtitle,boxes,arrows,notes):
 parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 520" role="img" aria-labelledby="title desc"><title id="title">{html.escape(title)}</title><desc id="desc">{html.escape(subtitle)}</desc>',
 '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="#506678" stroke-width="1.5"/></marker></defs>',
 '<rect width="1000" height="520" rx="24" fill="#f5f8fb"/>',
 '<g font-family="system-ui, sans-serif" fill="#1d3346">',f'<text x="28" y="40" font-size="23" font-weight="700">{title}</text>',f'<text x="28" y="66" font-size="14" fill="#52687a">{subtitle}</text>']
 for x1,y1,x2,y2,label in arrows:
  parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#506678" stroke-width="2" fill="none" marker-end="url(#arrow)"/>')
  if label:parts.append(f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2-9}" text-anchor="middle" font-size="12">{html.escape(label)}</text>')
 for x,y,w,h,title,lines,color in boxes:
  parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{color}" stroke="#bccbd7"/><text x="{x+14}" y="{y+25}" font-size="16" font-weight="650">{html.escape(title)}</text>')
  for i,line in enumerate(lines):parts.append(f'<text x="{x+14}" y="{y+49+i*21}" font-size="13">{html.escape(line)}</text>')
 for i,note in enumerate(notes):parts.append(f'<text x="28" y="{465+i*21}" font-size="13" fill="#435c70">{html.escape(note)}</text>')
 parts.append('</g></svg>');(OUT/name).write_text(''.join(parts))

svg('system-conversation.svg','01 · From microphone to a spoken reply','Work overlaps where possible. The endpoint waits for an actual speech pause.',[
 (25,112,190,120,'Browser microphone',['Echo cancellation','Optional CUDA isolation','VoxLock / SciCom'], '#e1f1eb'),
 (255,112,210,120,'Listen + identify',['Nemotron live preview','TYGER / stop decisions','VAD + speaker matching'],'#e5edf9'),
 (505,112,215,120,'End of turn',['Speech-pause timer','Optional selected ASR','Ears tone hints in parallel'],'#e5edf9'),
 (760,112,215,120,'Conversation model',['Qwen / local selection','Relevant memory + tools','Sentence output streaming'],'#f6ead7'),
 (505,302,215,115,'Voice synthesis',['Humaneness Small / Large','Sentence in → PCM chunks','Optional parallel word check'],'#f6ead7'),
 (760,302,215,115,'Browser playback',['Playback-position clock','Face + gaze + screen tools','Cancelable audio queue'],'#e1f1eb'),
 (25,302,440,115,'Interruption side path stays live',['Microphone + playback reference → speaker-aware decision','Stop commands cancel pending speech and screen actions.','This path does not wait for the full LLM reply.'],'#ede8f6')],
 [(215,170,255,170,''),(465,170,505,170,''),(720,170,760,170,''),(864,232,620,302,'completed sentence'),(720,358,760,358,'PCM')],
 ['Camera landmarks and gaze stay in the browser; face identity and face-based VAD are optional.', 'Audio quality checks are not factual verification. A voice match is not secure authentication.'])
svg('system-tools.svg','02 · A request becomes an action','A spoken promise is not an executed tool. All actions pass validators.',[
 (25,113,270,105,'User + recent conversation',['“Mach ein ernstes Gesicht.”','“Kannst du das mal nachgucken?”'],'#e1f1eb'),
 (345,113,290,105,'Fast, unambiguous commands',['Validated direct screen action','Unique ID → one animation','No extra model call to recognize it'],'#e5edf9'),
 (345,280,290,130,'Model-driven interpretation',['Streaming model can request tools','Tool director resolves context','Real schemas, bounded arguments','Result → spoken acknowledgment'],'#f6ead7'),
 (700,113,275,105,'Avatar executor',['40 emotions + 8 grimaces','Body spin, somersault, nod…','Reduced motion / off respected'],'#e1f1eb'),
 (700,280,275,130,'Information + session tools',['News · weather · Wikipedia','Web search: retrieved extracts','Explicit interruption rules','Sources and timings in metadata'],'#ede8f6')],
 [(295,163,345,163,''),(160,218,345,325,'paraphrase / research'),(635,163,700,163,''),(635,345,700,345,''),(635,294,758,218,'avatar tool')],
 ['Quoted or negated commands do not trigger the fast action path; old topics do not force every turn through tools.', 'Web search uses OpenRouter / Exa with API charges. It is read-only retrieval, not an unrestricted browser.'])
svg('system-latency.svg','03 · What can delay the first sound?','Illustrative flow, not a to-scale timeline. Read the live timing cards for each turn.',[
 (25,112,290,130,'Input checks',['Speech pause: user-adjustable','Speaker identity: overlaps ASR','Second recognizer: optional','Off keeps native Nemotron + pause'],'#e5edf9'),
 (355,112,290,130,'Planning',['LLM time to first full sentence','Lookup: real network round trips','Memory: bounded context retrieval','Quick reply: optional extra stage'],'#f6ead7'),
 (685,112,290,130,'Output checks',['TTS computes PCM incrementally','Parallel ASR holds first target words','Playback queue smooths chunks','Sound starts after those dependencies'],'#e1f1eb'),
 (25,300,290,125,'Verified · default',['TTS + ASR run concurrently','Opening evidence, trailing cut + fade','Measured Nov 13: ~634–689 ms','TTS → first verified PCM (medians)'],'#e1f1eb'),
 (355,300,290,125,'Raw · user choice',['Skip output ASR hold/cut','Earlier first PCM, more artifacts','Historical test: ~259–275 ms','Different trade-off, not equal quality'],'#f6ead7'),
 (685,300,290,125,'Serial · comparison',['Pause TTS for verification','Normally slower than parallel','Historical test: ~864–877 ms','Bridge batch checker is separate'],'#ede8f6')],
 [(315,176,355,176,''),(645,176,685,176,'')],
 ['RTX 3090 figures are prior authored short-phrase tests, not end-to-end guarantees or measurements of this update.', 'GPU contention, utterance length, provider time and browser buffering vary. Disabling checks does not remove TTS work.'])

examples={
 'emotion':'Mach ein ernstes Gesicht. / Sei wütend. / Show awe.',
 'nod':'Nicke bitte. / Nod your head.', 'shake':'Schüttle den Kopf. / Shake your head.',
 'spin':'Dreh dich im Kreis, gegen den Uhrzeigersinn. / Spin around.',
 'somersault':'Mach einen Salto rückwärts. / Do a forward somersault.',
 'carousel':'Spiel Karussell. / Do an accelerating carousel.',
 'afterglow':'Smile euphorically after the carousel.', 'puppy':'Mach einen Hundeblick. / Give me puppy eyes.',
 'pet':'Mouse-drag the head, or ask for a contented petting expression.',
 'eye_roll':'Rolle mit den Augen. / Roll your eyes.', 'grimace':'Schneid eine Grimasse. / Make a silly face.',
 'wink':'Zwinkere bitte. / Wink.', 'curious':'Schau neugierig. / Give a curious look.'}
rows=''.join(f'<tr><td><code>{k}</code></td><td>{html.escape(examples[k])}</td></tr>' for k in KINDS)
emotions=''.join(f'<li><code>{e}</code> · {html.escape(GERMAN[e].split("|")[0])}</li>' for e in EMOTIONS)
tools=''.join(f'<tr><td><code>{t["function"]["name"]}</code></td><td>{html.escape(t["function"]["description"])}</td></tr>' for t in [TOOL,*TOOLS,*RULE_TOOLS])
fragment=f'''<section id="system-guide" aria-labelledby="system-guide-title">
 <p class="guide-kicker">A field guide to Robby</p><h2 id="system-guide-title">What happens between hearing and answering?</h2>
 <p>Explore the working components, the actual tool catalogue, and the latency trade-offs. This guide describes the screen demo, not a physical robot.</p>
 <nav><a href="#guide-actions">Commands &amp; expressions</a> · <a href="#guide-tools">Real tools</a> · <a href="#verification-controls">Speed switches ↑</a> · <a href="/static/parallel-tts-verification.html">Measured TTS study</a></nav>
 <figure><div class="guide-scroll"><img src="/static/system-conversation.svg" alt="Conversation pipeline: microphone, speaker identification, speech-pause ASR, LLM, TTS and playback; interruptions run concurrently."></div><figcaption>Generation streams sentence by sentence; audio streams within each sentence. Speaker checks and tone hints can overlap recognition.</figcaption></figure>
 <figure><div class="guide-scroll"><img src="/static/system-tools.svg" alt="Direct commands schedule validated avatar actions; an LLM tool router handles paraphrases and contextual public lookups."></div><figcaption>The fast reply and tool director share the same capability description. A model can request the tool path even when no keyword rule matches.</figcaption></figure>
 <figure><div class="guide-scroll"><img src="/static/system-latency.svg" alt="Input, planning and output dependencies; parallel verified, raw and serial checked audio modes."></div><figcaption>First PCM is a server metric. Audible response also includes transfer and browser playback buffering. The live dashboard separates these costs.</figcaption></figure>
 <details id="guide-actions"><summary>All 13 animation kinds, 40 emotions &amp; 8 cartoon faces</summary><p>Try German or English. “Noch mal” repeats the last explicit action request. For a sequence, say “Erst wütend, dann eine Grimasse” with a request verb such as “Zeig”. Serious is the authored concentration pose. Emojis such as “Mach so 😡” are also accepted. The renderer uses facial controls, not literal emoji pictures.</p>
 <div class="guide-scroll"><table><thead><tr><th>Animation</th><th>Example / trigger</th></tr></thead><tbody>{rows}</tbody></table></div>
 <p>Grimace variations: {', '.join(VARIANTS)}. Optional idle play and petting have their own switches. Six steps and 24 seconds maximum per performance. Large motion is suppressed by reduced-motion settings.</p>
 <ul class="emotion-grid">{emotions}</ul><p>Every listed emotion is an authored visual pose, not an inference about a person's mental state.</p></details>
 <details id="guide-tools"><summary>Actual tool schemas and how to ask for them</summary><div class="guide-scroll"><table><thead><tr><th>Tool</th><th>Capability</th></tr></thead><tbody>{tools}</tbody></table></div>
 <p>“Wer war Viktor Frankl?” followed by “Kannst du das mal nachgucken?” retains the topic. The model builds a short query. Web lookup uses the configured OpenRouter account and its paid Exa search plugin; no additional key is exposed to the browser. Search failures stay visible, with no invented sources. Only returned source annotations/extracts are used, not an uncited search model answer.</p>
 <p>“Unterbrich mich, wenn ich Bananen sage” installs an explicit session rule. “Stopp”, “Hör auf” and “Warte bitte” use the live interruption path. The internal use_tools helper only selects the validated tool director; it performs no action by itself. Settings, speaker enrollment, persistent memory and news-source links are separate systems; there is no unrestricted shell, motor or general browser-control tool.</p></details>
 <p><a href="/static/tool-catalogue.json">Machine-readable catalogue</a> · <a href="/static/tools-audit.html">Implementation and test report</a> · <a href="/static/whole-body-stunts.html">Whole-body animation tests</a></p>
</section>'''
(OUT/'system-guide-fragment.html').write_text(fragment)
(OUT/'tool-catalogue.json').write_text(json.dumps({'updated':'2026-11-14','animation_kinds':KINDS,'grimaces':VARIANTS,'emotions':EMOTIONS,'tools':[TOOL,*TOOLS,*RULE_TOOLS],'internal_routing_tool':ROUTE_TOOL,'examples':examples},indent=2,ensure_ascii=False))

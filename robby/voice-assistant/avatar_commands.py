"""Conservative, validated screen-action commands, independent of LLM JSON.

Only direct requests use this path. Quotes, conditions and explanations stay
with normal conversation/tools. No motor/device commands are ever produced.
"""
import re
from avatar_actions import VARIANTS,explicit_spin,validate
from performance import ALIASES
from emotion_recipes import GERMAN

_BLOCK=re.compile(r'\b(?:wenn|falls|if|example|beispiel|zitiere|quote|erklär\w*|explain|beschreib\w*|describe|warum|why)\b',re.I)
_SPEECH_ONLY=re.compile(r'^\s*(?:(?:(?:bitte|please)|(?:(?:kannst|könntest|würdest)\s+du|(?:can|could|would)\s+you)(?:\s+mir)?(?:\s+bitte|\s+please)?)\s+)?(?:sag(?:e|en)?|say|repeat|wiederhol\w*)\b',re.I)
_REQUEST=re.compile(r'\b(?:bitte|please|kannst\s+du|könntest\s+du|würdest\s+du|can\s+you|could\s+you|would\s+you)\b|^(?:(?:ja|okay|also|hey|robb[yi]|well|now|first|erst)\s*[,!:]?\s+){0,3}(?:mach\w*|schneid\w*|zieh\w*|zeig\w*|guck\w*|schau\w*|schiel\w*|nick(?:e|en)?|(?:zwinker|blinzel)\w*|schütt(?:el|l)\w*|shake|roll\w*|augenroll\w*|verdreh\w*|dreh\w*|grins\w*|pust\w*|nimm|sieh|demonstrier\w*|vollführ\w*|vollfuehr\w*|rotier\w*|führ\w*|fuehr\w*|stell\w*|spiel\w*|sei|wirke|werde|make|show|perform|demonstrate|do|look|act|be|nod|wink|cross|spin|rotate)\b',re.I)
_FACE=re.compile(r'\b(?:grim+ass\w*|grimm?ass\w*|grimace\w*|(?:funny|silly|cute|goofy|crazy)\s+faces?|fischgesicht|(?:lustig\w*|komisch\w*|verrückt\w*)\s+gesicht)\b',re.I)
_EMOTIONS={slug:re.compile(r'(?<!\w)(?:'+re.escape(slug)+'|'+aliases+'|'+GERMAN[slug]+r')(?:e|en|es|er|em)?(?!\w)',re.I) for slug,aliases in ALIASES.items()}

def unquoted(text):
    # A quoted command is data, but a quoted spoken phrase must not suppress
    # an independently requested action: 'Mach eine Grimasse und sag "Hallo"'.
    return re.sub(r'"[^"\n]*"|“[^”\n]*”|„[^“\n]*“|«[^»\n]*»|(?<!\w)\x27[^\x27\n]*\x27(?!\w)',' ',text)

def silent_requested(text):
    return bool(re.search(r'\b(?:stumm|lautlos|ohne\s+(?:etwas\s+)?(?:zu\s+)?(?:sagen|sprechen)|silent(?:ly)?|without\s+(?:speaking|talking)|no\s+speech)\b',unquoted(text),re.I))

def interjection_only(text):
    """A standalone laugh/whoop is not a verbal reaction to a requested trick.

    Optional idle/petting vocalizations and explicitly requested quoted words
    keep their own path. Normal first-person speech is never filtered here.
    """
    words=re.findall(r'[^\W\d_]+',text.casefold())
    return bool(words) and all(re.fullmatch(r'(?:ha|hi|he){2,}|h[aeiou]+|h+m+|m+h+m*|hui+|juhu+|woohoo+|yay+|wow+|oh+|ah+|uh+|ooh+|aah+',w) for w in words)

def normalize_command(text):
    if not isinstance(text,str):return ""
    return re.sub(r"^\s*(?:(?:hey|hi|hallo|hello|du)\s+)?robb(?:y|ie|i)\b[,!: ]*", "",text,flags=re.I).strip()

def command_intent(text):
    if not isinstance(text,str) or not 1<=len(text)<=1200:return False
    text=unquoted(normalize_command(text))
    if _BLOCK.search(text):return False
    if _SPEECH_ONLY.search(text):
        # "Say something funny AND make a face" has a real second action;
        # "Please say make a face" alone is only a request for words.
        later=re.split(r'\b(?:und|and|dann|then)\b',text,flags=re.I)[1:]
        return any(_REQUEST.search(clause.strip()) for clause in later)
    ellipse=bool(re.fullmatch(r'(?:(?:bitte|nochmal|noch mal|sich|dich)\s+)*(?:im\s+kreis|rundherum|einmal\s+herum|360\s*(?:grad|degrees|°))\s+(?:drehen|rotieren)(?:\s+bitte)?[.!?]*',text.strip(),re.I))
    direct_emotion=bool(re.search(r'\b(?:du\s+sollst|ich\s+(?:möchte|moechte|will)\s*[,]?\s*dass\s+du|(?:i\s+want\s+you\s+to)|tu\s+so\s+als\s+(?:wärst|waerst|ob\s+du)|pretend\s+(?:to\s+be|you\s+are))\b',text,re.I) and (any(pattern.search(text) for pattern in _EMOTIONS.values()) or bool(explicit_spin(text))))
    desire=bool(re.search(r'\b(?:ich\s+(?:möchte|will|würde\s+gerne)|i(?:.d|\s+would)\s+like|i\s+want)\b',text,re.I) and re.search(r'\b(?:sehen|vorführen|see|watch|show)\b',text,re.I) and re.search(r'\b(?:du|dich|dein\w*|you|your)\b',text,re.I))
    return bool(desire or _REQUEST.search(text) or _FACE.fullmatch(text.strip(' .!?')) or ellipse or direct_emotion)

def explicit_actions(text,variant_index=0,history=()):
    text=normalize_command(text)
    if re.fullmatch(r"(?:noch\s*mal|noch\s+einmal|again|do\s+that\s+again)(?:\s+bitte)?[.!?]*",text.strip(),re.I):
        for h in reversed(history[-8:]):
            if h.get("role")=="user":
                previous=explicit_actions(str(h.get("content","")),variant_index)
                if previous:return previous
                break
    if not command_intent(text):return []
    text=unquoted(text)
    for symbol,emotion in {'😡':'anger','😠':'anger','😢':'sadness','😭':'sadness','😲':'surprise','😍':'affection','🥺':'longing','😐':'concentration','😃':'elation','🤔':'contemplation'}.items():
        text=text.replace(symbol,' Gesichtsausdruck '+emotion+' ')
    whole_spin=explicit_spin(text)
    if whole_spin and not re.search(r'\b(?:und|and|dann|then|danach)\b',text,re.I):return validate({'steps':whole_spin})
    steps=[]
    pose_request=bool(re.search(r'\b(?:guck\w*|schau\w*|look|ausseh\w*|gesicht\w*|emotion\w*|ausdruck|expression|pose|show|demonstrate|sieh|nimm|demonstrier\w*|zeig\w*|stell\w*|spiel\w*|mach\w*|sei|sein|bist|wärst|waerst|wirke|wirken|werde|be|act)\b',text,re.I))
    normalized=re.sub(r'\b(roll\w*|schau\w*|guck\w*|mach\w*|make|look|show|schiel\w*|shake|schütt(?:el|l)\w*)\s+(?:dann|then)\b',r'\1',text,flags=re.I)
    clauses=re.split(r'[,;.!?]+|\b(?:und|and|dann|then|danach|erst|first|sondern|but)\b',normalized,flags=re.I)
    for clause in clauses:
        t=clause.casefold().strip()
        if not t or _SPEECH_ONLY.search(t) or re.search(r'\b(?:nicht|kein\w*|never|not|don.t|no)\b',t):continue
        spin=explicit_spin(t)
        if spin:steps.extend(spin)
        elif re.search(r'\b(?:salto(?:s)?|überschlag|ueberschlag|somersault(?:s)?|somer\s+salt|summer\s+salt|backflip|frontflip|back\s+flip|front\s+flip)\b',t):
            direction='backward' if re.search(r'\b(?:rückwärts|rueckwaerts|backward\w*|backflip|back\s+flip)\b',t) else 'forward'
            steps.append({'kind':'somersault','duration_s':4.8,'direction':direction})
        elif re.search(r'\b(?:karussell|carousel|quatsch|kunststück\w*|silly\s+trick)\b',t):
            steps.extend([{'kind':'carousel','duration_s':6.,'direction':'clockwise'},
                          {'kind':'afterglow','duration_s':6.}])
        elif re.search(r'\b(?:hundeblick|puppy\s+(?:dog\s+)?eyes)\b',t):steps.append({'kind':'puppy','duration_s':4.})
        elif re.search(r'\b(?:backen|wangen|cheeks)\b.*\b(?:auf|puff)|\b(?:pust\w*|puff)\b.*\b(?:backen|wangen|cheeks)\b',t):steps.append({'kind':'grimace','variant':'squishy','duration_s':3.})
        elif re.search(r'\b(?:schiel\w*|cross\w*\s+(?:your\s+)?eyes)\b',t):
            steps.append({'kind':'grimace','variant':'crossed','duration_s':3.})
        elif _FACE.search(t):
            variant=next((v for v in VARIANTS if re.search(r'\b'+re.escape(v)+r'\b',t)),None)
            if variant is None and re.search(r'\bfisch\w*',t):variant='fish'
            amount=2 if re.search(r'\b(?:grimassen|grimaces|mehrere|verschiedene|several)\b',t) else 1
            for offset in range(amount):
                steps.append({'kind':'grimace','variant':variant or VARIANTS[(variant_index+offset)%len(VARIANTS)],'duration_s':3.})
        elif re.search(r'\b(?:augen\s*roll\w*|(?:roll\w*|verdreh\w*)\b.*\b(?:augen|eyes)|eye\s+roll|(?:augen|eyes)\b.{0,50}\b(?:kreis\w*|circle\w*))\b',t):
            steps.append({'kind':'eye_roll','duration_s':3.})
        elif re.search(r'\b(?:(?:zwinker|blinzel)\w*|wink\w*)\b',t):steps.append({'kind':'wink','duration_s':2.5})
        elif re.search(r'\b(?:schütt(?:el|l)\w*|shake\w*)\b.*\b(?:kopf|head)\b|\b(?:kopf|head)\b.*\b(?:schütt(?:el|l)\w*|shake\w*)\b',t):steps.append({'kind':'shake','duration_s':2.5})
        elif re.search(r'\b(?:nick(?:e|en)?|nod)\b',t):steps.append({'kind':'nod','duration_s':2.5})
        elif pose_request and not re.search(r'\b(?:gedicht|geschichte|märchen|lied|song|poem|story|fairy\s+tale|film|buch|book)\b',t):
            found=[(m.start(), 'anger' if slug=='sourness' and re.search(r'\bsauer\w*\b',m.group(),re.I) else slug) for slug,pattern in _EMOTIONS.items() for m in [pattern.search(t)] if m and not (slug=='sourness' and re.search(r'\bsauer\w*\b',m.group(),re.I))]
            for label,slug in [('happy|fröhlich|glücklich|froh','elation'),('lustig|witzig|amüsiert','amusement'),('böse|boese','anger'),('frech','teasing'),('ernst|seriös|serioes|serious|stern','concentration'),('neutral|entspannt|relaxed','contentment')]:
                match=re.search(r'\b(?:'+label+r')(?:e|en|es|er|em)?\b',t)
                if match and not found:found=[(match.start(),slug)]
            if found:steps.append({'kind':'emotion','emotion':min(found)[1],'duration_s':3.})
        if len(steps)>=6:break
    if not steps:return []
    # The shared validator is the authority for all durations, kinds and fields.
    bounded=[];total=0.
    for step in steps[:6]:
        if total+step['duration_s']>24:break
        bounded.append(step);total+=step['duration_s']
    return validate({'steps':bounded})

"""Per-connection, explicit latency/quality choices. Never changes admission/VAD."""
DEFAULTS={'verify_tts':True,'verify_input':True,'serial_tts':False,'candidate_search':True}

def validated(raw):
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS) or any(type(v) is not bool for v in raw.values()):
        raise ValueError('Expected boolean verification settings')
    return {**DEFAULTS,**raw}

def tts_options(settings):
    s=validated(settings or {})
    return {'align':s['verify_tts'],'speech_verification':'serial' if s['serial_tts'] else 'parallel'}

def final_model(session):
    return session.asr.selected if getattr(session.c,'verification_settings',DEFAULTS)['verify_input'] else 'nemotron'

def search_options(settings,model='small_rl',eligible=True):
    if not validated(settings or {})['candidate_search'] or model!='small_rl' or not eligible:return {}
    return {'generation':'search_quality','search_n':4,'batch_size':4,'search_chunk_frames':10,'search_seconds':30.}

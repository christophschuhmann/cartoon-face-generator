"""Per-connection, explicit latency/quality choices. Never changes admission/VAD."""
DEFAULTS={'verify_tts':True,'verify_input':True,'serial_tts':False,'candidate_search':False}

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
    return {'generation':'search_asr','search_n':3,'batch_size':3,'search_chunk_frames':12,'search_seconds':30.}

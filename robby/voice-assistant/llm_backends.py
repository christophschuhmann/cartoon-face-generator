"""Allowlisted language models, actual OpenRouter endpoint tags and transport.

Public metadata has no keys, credential ciphertexts or arbitrary endpoint URLs.
"""
import asyncio,contextvars,json,logging,os,re,time
from pathlib import Path
import httpx
from contextlib import asynccontextmanager
from credential_store import store

OPENROUTER='https://openrouter.ai/api/v1'
QWEN='qwen/qwen3.8-27b'
MODELS={'qwen':{'label':'Qwen 3.8 27B · OpenRouter','model':QWEN},
        'gemma26':{'label':'Gemma 4 26B-A4B Q4 · local GPU','model':'gemma-4-26b-a4b-q4'},
        'gemma12':{'label':'Gemma 4 12B Q4 · local GPU','model':'gemma-4-12b-q4'},
        'local':{'label':'Nemotron Bolt E4B · local GPU','model':'nemotron-bolt'}}
DEFAULT_QWEN_PROVIDER='nebius/fp4'
_providers={DEFAULT_QWEN_PROVIDER:{'id':DEFAULT_QWEN_PROVIDER,'label':'Nebius · FP4','parameters':['tools','tool_choice']},
            'cerebras/fp16':{'id':'cerebras/fp16','label':'Cerebras · FP16','parameters':['tools','tool_choice']}}
_updated=0.
log=logging.getLogger('robo.llm')
rate_limit_notice=contextvars.ContextVar('llm_rate_limit_notice',default=None)
_RATE_SOURCES={'openrouter_free_tier_per_minute','upstream_provider_shared_pool',
               'openrouter_in_flight_budget','openrouter_key_limit','openrouter_credits'}

async def rate_limited(response,attempt,delay):
    """Record only an allowlisted classification; never retain provider bodies."""
    source='not_supplied'
    try:
        raw=await response.aread()
        if len(raw)<=16384:
            value=((json.loads(raw).get('error') or {}).get('metadata') or {}).get('limit_source')
            if value in _RATE_SOURCES:source=value
    except Exception:pass  # Do not block a retry on optional diagnostics.
    log.warning('rate_limit status=429 source=%s attempt=%s retry_delay_ms=%s',source,attempt,round(delay*1000))
    callback=rate_limit_notice.get()
    if callback is not None:
        await callback({'stage':'llm_rate_limit','text':f'The selected language-model endpoint is busy (HTTP 429). Retrying in {delay:g} seconds.',
                        'attempt':attempt,'max_attempts':3,'delay_ms':round(delay*1000),'limit_source':source})

async def refresh_providers(client=None):
    global _providers,_updated
    if time.monotonic()-_updated<300:return
    async def fetch(c):
        response=await c.get(OPENROUTER+'/models/'+QWEN+'/endpoints',timeout=10);response.raise_for_status()
        result={}
        for row in response.json()['data']['endpoints']:
            tag=row.get('tag','')
            if row.get('status',-1)<0 or not re.fullmatch(r'[a-z0-9_.-]+(?:/[a-z0-9_.-]+)*',tag):continue
            result[tag]={'id':tag,'label':row['provider_name']+' · '+row.get('quantization','unknown').upper(),
                'parameters':row.get('supported_parameters',[])}
        return result
    if client is not None:result=await fetch(client)
    else:
        async with httpx.AsyncClient() as c:result=await fetch(c)
    if result:_providers=result;_updated=time.monotonic()

def default_selection():
    return {'model':'gemma26','provider':'local'}

def selection(value=None):
    value=value if value is not None else default_selection()
    if not isinstance(value,dict) or set(value)-{'model','provider'}:raise ValueError('Invalid language model selection')
    model=value.get('model');provider=value.get('provider',DEFAULT_QWEN_PROVIDER if model=='qwen' else 'local')
    if model not in MODELS or (model=='qwen' and provider not in _providers) or (model!='qwen' and provider!='local'):
        raise ValueError('Language model or provider is not available')
    return {'model':model,'provider':provider}

def catalog():
    providers=sorted(_providers.values(),key=lambda r:(r['id']!=DEFAULT_QWEN_PROVIDER,r['label']))
    return {'models':[{'id':key,**spec} for key,spec in MODELS.items()],
        'providers':[{'id':r['id'],'label':r['label']} for r in providers],
        'default':default_selection(),'server_key_available':store().configured(),
        'provider_recovery':os.environ.get('ROBO_LLM_PROVIDER_RECOVERY','0')=='1',
        'privacy':'OpenRouter mode sends conversation text to OpenRouter and the selected provider. The server key is never sent to your browser.'}

def config(value=None,credential=None):
    chosen=selection(value)
    if chosen['model']=='gemma26':
        return {'selection':chosen,'url':'http://127.0.0.1:18826/v1/chat/completions',
            'model':MODELS['gemma26']['model'],'headers':{},'remote':False}
    if chosen['model']=='gemma12':
        return {'selection':chosen,'url':'http://127.0.0.1:18812/v1/chat/completions',
            'model':MODELS['gemma12']['model'],'headers':{},'remote':False}
    if chosen['model']=='local':
        from bolt_director import local_config
        base,model=local_config()
        return {'selection':chosen,'url':base+'/v1/chat/completions','model':model,'headers':{},'remote':False}
    vault=store();key=vault.open(credential) if credential else vault.owner()
    return {'selection':chosen,'url':OPENROUTER+'/chat/completions','model':QWEN,
        'headers':{'Authorization':'Bearer '+key,'X-OpenRouter-Title':'Robby Voice Demo'},'remote':True,
        'parameters':_providers[chosen['provider']]['parameters']}

def request_body(config,body):
    body=dict(body);body['model']=config['model']
    # llama.cpp's JSON grammar suppresses tool-call tokens for Gemma. Let the
    # chat template emit real tool calls; the director validates its result.
    if config['selection']['model'] in ('gemma12','gemma26') and body.get('tools') and body.get('tool_choice')!='none':
        body.pop('response_format',None)
    if not config['remote']:return body
    body.pop('chat_template_kwargs',None);body.pop('reasoning_effort',None);body.pop('parallel_tool_calls',None)
    if 'max_completion_tokens' in body:body['max_tokens']=body.pop('max_completion_tokens')
    body['reasoning']={'enabled':False,'exclude':True}
    body['provider']={'only':[config['selection']['provider']],'allow_fallbacks':False}
    if 'response_format' not in config['parameters']:body.pop('response_format',None)
    return body

def metrics(config):
    return {'llm_model':config['model'],'llm_provider':config['selection']['provider'],
        'llm_backend':'OpenRouter' if config['remote'] else 'Local GPU'}

def check_response(response):
    if getattr(response,'status_code',200)>=400:
        # No raw provider error body / headers / credential can enter the UI.
        # Keep status/response type for the existing bounded transient-error
        # retry policy, without putting provider bodies or credentials in logs.
        raise httpx.HTTPStatusError('Language model request failed (HTTP '+str(response.status_code)+')',
                                    request=response.request,response=response)

def retry_delay(response):
    # Respect a bounded provider cooldown instead of immediately repeating a
    # rate-limited call. A prolonged outage remains an explicit error.
    try:return min(8.,max(1.,float(response.headers.get('retry-after','1'))))
    except (ValueError,AttributeError):return 1.

def recovery_body(cfg,body):
    """Same Qwen model on another registered OpenRouter endpoint after 429.

    Never applied to authentication errors or a local model. The operator may
    pin a provider strictly with ROBO_LLM_PROVIDER_RECOVERY=0.
    """
    if not cfg.get('remote') or os.environ.get('ROBO_LLM_PROVIDER_RECOVERY','0')!='1':return None
    alternatives=[p for p in _providers if p!=cfg['selection']['provider']]
    if not alternatives:return None
    request=request_body(cfg,body)
    request['provider']={'only':alternatives,'allow_fallbacks':True,'sort':'latency'}
    return request

@asynccontextmanager
async def completion_stream(client,cfg,body,metrics):
    request=request_body(cfg,body)
    for attempt in range(3):
        async with client.stream('POST',cfg['url'],json=request,headers=cfg['headers'],timeout=30.) as response:
            if cfg['remote'] and getattr(response,'status_code',200)==429 and attempt<2:
                delay=retry_delay(response);metrics['llm_rate_limit_retries']=attempt+1
                if attempt==1 and (fallback:=recovery_body(cfg,body)):
                    request=fallback;metrics.update(llm_provider_recovery=True,llm_preferred_provider=cfg['selection']['provider'])
                metrics.setdefault('llm_rate_limit_wait_ms',0.)
                metrics['llm_rate_limit_wait_ms']+=round(delay*1000,2)
                await rate_limited(response,attempt+1,delay)
            else:
                if getattr(response,'status_code',200)==429:metrics['llm_recovery_exhausted']=True
                check_response(response);yield response;return
        await asyncio.sleep(delay)

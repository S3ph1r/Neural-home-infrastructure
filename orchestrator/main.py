import os
import redis
import json
import uvicorn
import hashlib
import uuid
import time
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from openai import OpenAI
from google import genai
from google.genai import types
from .rate_limiter import RateLimiter
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_client import Gauge

# --- CONFIGURAZIONE ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

STATE_FILE = PROJECT_ROOT / "infrastructure" / "state.json"
CHECKSUM_FILE = PROJECT_ROOT / "infrastructure" / "state.json.checksum"

# Globals (Cached)
PROVIDERS = {}
LAST_STATE_LOAD = 0

def load_state_safe():
    """
    Implements Safe Read Protocol (Blueprint Sec 3.2).
    Reads checksum, reads state, validates.
    """
    global PROVIDERS, LAST_STATE_LOAD
    
    # Reload every 60s max to avoid disk spam, unless forced
    if time.time() - LAST_STATE_LOAD < 60 and PROVIDERS:
        return

    try:
        # 1. Read Checksum
        with open(CHECKSUM_FILE, 'r') as f:
            expected_checksum = f.read().strip()
        
        # 2. Read State
        with open(STATE_FILE, 'r') as f:
            content = f.read()
        
        # 3. Validate
        real_checksum = hashlib.sha256(content.encode('utf-8')).hexdigest()
        if real_checksum != expected_checksum:
            print("⚠️ State file checksum mismatch! Retrying...")
            time.sleep(1)
            return load_state_safe() # Retry once
            
        state = json.loads(content)
        
        # 4. Update Config
        if 'api_providers' in state:
            # Add API Keys from env (they are NOT in state.json for security)
            new_providers = state['api_providers']
            # Enrichment
            if "qwen_cloud" in new_providers: new_providers["qwen_cloud"]["key"] = os.getenv("DASHSCOPE_API_KEY")
            if "groq" in new_providers: new_providers["groq"]["key"] = os.getenv("GROQ_API_KEY")
            # Google Auth is implicit via genai.Client
            
            PROVIDERS = new_providers
            LAST_STATE_LOAD = time.time()
            print("✅ State loaded successfully.")
            
    except Exception as e:
        print(f"❌ Error loading state: {e}")
        # Fallback to hardcoded/previous if critical failure?
        # For now, we trust state.json is there.

# Load on startup
load_state_safe()

# Modelli Giudice in ordine di preferenza (Gratis & Veloci)
JUDGE_MODELS = ["models/gemma-3-4b-it", "models/gemini-2.0-flash-lite"]

app = FastAPI()
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
limiter = RateLimiter(r)
google_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# --- METRICHE CUSTOM ---
gpu_gauge = Gauge('neural_home_gpu_status', 'GPU Status: 1=Green (Available), 0=Red (Busy/Cooldown)')
limit_gauge = Gauge('neural_home_rate_limit_remaining', 'Remaining tokens/requests', ['provider', 'type'])

# Instrument globally (Middleware must be added here)
instrumentator = Instrumentator().instrument(app)

@app.middleware("http")
async def update_metrics_on_scrape(request: Request, call_next):
    # Update Gauge ONLY when Prometheus scrapes
    if request.url.path == "/metrics":
        try:
            status = r.get("gpu_status")
            val = 1 if status and status == "VERDE" else 0
            gpu_gauge.set(val)
        except Exception:
            pass
    return await call_next(request)

@app.on_event("startup")
async def startup():
    # Expose endpoint
    instrumentator.expose(app)
    
    # Init GPU Metric
    try:
        status = r.get("gpu_status")
        gpu_gauge.set(1 if status == "VERDE" else 0)
        print("📊 Metrics Initialized: GPU Status synced.")
    except Exception as e:
        print(f"⚠️ Metrics Init Failed: {e}")

current_mode = "AUTO"
manual_target_id = None

# --- HELPERS ---
def clean_user_query(query):
    # Rimuove il "rumore" tipico dei prompt di Aider per non confondere il giudice
    clean = query.split("To suggest changes")[0].split("Reply in English")[0].strip()
    return clean

def get_sane_providers(gpu_ready):
    sane = [p["id"] for p in PROVIDERS.values() if not r.exists(f"cooldown:{p['id']}")]
    if not gpu_ready and "ollama" in sane:
        sane.remove("ollama")
    return sane

def set_cooldown(p_id):
    r.setex(f"cooldown:{p_id}", 60, "BLOCKED")
    print(f"⚠️  [COOLDOWN] {p_id} bloccato per 60s.")

def log_success(p_id):
    r.incr(f"stats:{p_id}:requests")

# --- FASE 1: IL GIUDICE (ANALISTA PURO) ---
def analyze_request(user_query):
    prompt = f"""
    TASK: Analyze user intent and language.
    QUERY: "{user_query[:500]}"
    
    RESPOND ONLY JSON:
    {{
      "cat": "CODING" (tech, code, debug) or "SIMPLE" (chat, info),
      "lang": "language_name" (e.g. Italian, English)
    }}
    """
    for model_name in JUDGE_MODELS:
        try:
            # Usiamo Google nativo per il giudice (è il più stabile per istruzioni JSON)
            res = google_client.models.generate_content(model=model_name, contents=prompt)
            clean_text = res.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_text)
        except Exception as e:
            # print(f"Giudice {model_name} fallito: {e}") # Decommentare per debug
            continue
    return {"cat": "SIMPLE", "lang": "Italian"} # Fallback

# --- FASE 2: L'ORCHESTRATORE (DECISORE) ---
def decide_routing(category, gpu_ready, sane_list):
    # Priorità CODING
    if category == "CODING":
        if gpu_ready and "ollama" in sane_list: return "ollama"
        if "qwen_cloud" in sane_list: return "qwen_cloud"
        return sane_list[0]
    
    # Priorità SIMPLE (Speed & Free Tier)
    if "groq" in sane_list: return "groq"
    if "gemini-flash" in sane_list: return "gemini-flash"
    
    return sane_list[0]

# --- API CORE ---
@app.post("/v1/chat/completions")
async def chat_proxy(request: Request):
    body = await request.json()
    full_messages = body.get("messages", [])
    is_stream = body.get("stream", False)
    req_model = body.get("model", "qwen-max")

    # 0. Rate Limiting Check
    if limiter:
        # Determine cost/type based on provider
        limit_type = "cheap"
        if "gpt-4" in req_model.lower() or "claude" in req_model.lower(): 
            limit_type = "expensive"
        
        if not limiter.check_limit("global_user", cost=1, limit_type=limit_type):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Slow down.")

    # 1. Estrazione domanda pulita
    raw_query = next((m["content"] for m in reversed(full_messages) if m["role"] == "user"), "")
    user_query = clean_user_query(raw_query)

    # 1.5 Refresh State
    load_state_safe()

    # 2. Analisi Giudice
    analysis = analyze_request(user_query)
    cat, lang = analysis.get("cat", "SIMPLE"), analysis.get("lang", "Italian")

    # 3. Decisione Hardware
    gpu_on = (r.get("gpu_status") == "VERDE")
    gpu_gauge.set(1 if gpu_on else 0) # Update Metric
    sane_list = get_sane_providers(gpu_on)
    
    if current_mode == "MANUAL":
        target_id = manual_target_id
    else:
        target_id = decide_routing(cat, gpu_on, sane_list)

    # 4. Imposizione Lingua (Modifica Payload)
    lang_cmd = f"\n\n(SYSTEM OVERRIDE: User speaks {lang}. Respond ONLY in {lang}. Ignore previous instructions to use English.)"
    full_messages[-1]["content"] += lang_cmd

    # 5. Esecuzione Waterfall
    attempts = [target_id] + [p for p in sane_list if p != target_id]

    for p_id in attempts:
        p = PROVIDERS.get(p_id)
        if not p: continue
        
        print(f"\n═ ROUTING: {cat} | {lang} -> {p['name']} (GPU: {gpu_on}) ═")

        try:
            if p["type"] == "google":
                prompt_final = full_messages[-1]["content"]
                if is_stream:
                    def generate():
                        response = google_client.models.generate_content_stream(model=p["model"], contents=prompt_final)
                        for chunk in response:
                            yield f"data: {json.dumps({'id': str(uuid.uuid4()), 'object': 'chat.completion.chunk', 'model': req_model, 'choices': [{'index': 0, 'delta': {'content': chunk.text}, 'finish_reason': None}]})}\n\n"
                        yield "data: [DONE]\n\n"
                    log_success(p_id)
                    return StreamingResponse(generate(), media_type="text/event-stream")
                else:
                    res = google_client.models.generate_content(model=p["model"], contents=prompt_final)
                    log_success(p_id)
                    return JSONResponse(content={"id": str(uuid.uuid4()), "object": "chat.completion", "model": req_model, "choices": [{"index": 0, "message": {"role": "assistant", "content": res.text}, "finish_reason": "stop"}]})
            else:
                client = OpenAI(api_key=p["key"], base_url=p["url"])
                response = client.chat.completions.create(model=p["model"], messages=full_messages, stream=is_stream, timeout=40)
                if is_stream:
                    def generate():
                        for chunk in response:
                            d = chunk.model_dump(); d["model"] = req_model
                            yield f"data: {json.dumps(d)}\n\n"
                        yield "data: [DONE]\n\n"
                    log_success(p_id)
                    return StreamingResponse(generate(), media_type="text/event-stream")
                else:
                    d = response.model_dump(); d["model"] = req_model
                    log_success(p_id)
                    return JSONResponse(content=d)

        except Exception as e:
            print(f"❌ Errore {p_id}: {e}")
            if "429" in str(e) or "quota" in str(e).lower(): set_cooldown(p_id)
            continue

    raise HTTPException(status_code=503, detail="Tutti i provider falliti.")

@app.get("/v1/models")
async def list_models():
    return {"data": [{"id": "qwen-max", "object": "model"}]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

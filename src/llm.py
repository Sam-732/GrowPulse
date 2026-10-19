"""Groq chat client: every response cached to cache/, 429s retried with backoff."""
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
CACHE = Path(__file__).resolve().parents[1] / "cache"
CACHE.mkdir(exist_ok=True)


def chat(messages: list[dict], *, json_mode: bool = True, temperature: float = 0.0,
         max_tokens: int = 2500, nocache_salt: str = "", model: str = "") -> str:
    model = model or MODEL
    """Return the assistant text. Same inputs -> served from cache, no API call."""
    key = hashlib.sha256(json.dumps([model, messages, json_mode, temperature, max_tokens,
                                     nocache_salt], sort_keys=True).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["text"]

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is empty. Put it in .env (never in code).")
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "reasoning_effort": "low"}
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    delay = 5.0
    for attempt in range(10):
        r = httpx.post(URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            wait = float(r.headers.get("retry-after", delay))
            print(f"  [groq {r.status_code}] backing off {wait:.0f}s (attempt {attempt + 1})", flush=True)
            time.sleep(wait + 1)
            delay = min(delay * 2, 60)
            continue
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        path.write_text(json.dumps({"text": text}), encoding="utf-8")
        return text
    raise RuntimeError("Groq kept rate-limiting; try again in a few minutes (cache keeps progress).")


def chat_json(messages: list[dict], **kw) -> dict:
    return json.loads(chat(messages, json_mode=True, **kw))

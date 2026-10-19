"""Phase 0 sanity check: key present, Groq reachable, core imports load."""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
k = os.getenv("GROQ_API_KEY", "")
print("GROQ_API_KEY set:", bool(k), "| starts with gsk_:", k.startswith("gsk_"))
r = httpx.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {k}"},
    json={"model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
          "messages": [{"role": "user", "content": "Reply with the word OK."}],
          "max_tokens": 200},
    timeout=30,
)
print("Groq status:", r.status_code, "|",
      r.json()["choices"][0]["message"]["content"] if r.is_success else r.text[:200])

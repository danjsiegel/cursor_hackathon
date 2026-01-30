#!/usr/bin/env python3
"""
Test MiniMax API key using the native Text API (chat completion).
Run from repo root: uv run python scripts/test_minimax_key.py
Requires .env with MINIMAX_API_KEY set (or pass as env var).
"""
import os
import sys

# Load .env from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import requests

# Native MiniMax Text API (chat + image). Same key works; path is NOT under /anthropic.
# See https://platform.minimax.io/docs/api-reference/text-post
NATIVE_BASE = "https://api.minimax.io"
CHAT_URL = f"{NATIVE_BASE}/v1/text/chatcompletion_v2"

def test_minimax_key():
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key or api_key.strip() == "":
        print("ERROR: MINIMAX_API_KEY not set. Copy .env.example to .env and set MINIMAX_API_KEY=your_key")
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "MiniMax-M2.1",
        "messages": [
            {"role": "user", "content": "Reply with exactly: OK"}
        ],
        "max_tokens": 50,
    }

    try:
        r = requests.post(CHAT_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                err = e.response.json()
                print(f"Response: {err}")
            except Exception:
                print(f"Response text: {e.response.text[:500]}")
        return False

    status = data.get("base_resp", {}).get("status_code")
    status_msg = data.get("base_resp", {}).get("status_msg", "")

    if status == 0:
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        print(f"MiniMax API key is valid. Response: {content[:200]}")
        return True

    if status == 1008:
        print("MiniMax API key is valid, but account has insufficient balance.")
        print("Add credit at https://platform.minimax.io (Billing / Recharge) to call the API.")
        return True  # key works; only balance is missing

    print(f"API error: status_code={status}, status_msg={status_msg}")
    return False

if __name__ == "__main__":
    ok = test_minimax_key()
    sys.exit(0 if ok else 1)

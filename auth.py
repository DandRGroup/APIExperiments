# app/crm/auth.py
import json
import os, time, requests
from typing import Optional, Dict, Any

import os
from pathlib import Path
from dotenv import load_dotenv

# Calculate forecast close date: last day of month, or next month if in last week
from datetime import datetime, timedelta
from calendar import monthrange

TOP = Path(__file__).resolve().parent
load_dotenv(TOP / "instance" / ".env")

WG_BASE = "https://api.workguru.io/"
TOKEN_CACHE_FILE = TOP / "instance" / "token_cache.json"

TENANTS = {
    "CP": {
        "key": os.getenv("CP_KEY"),
        "secret": os.getenv("CP_SECRET"),
        "token": None,  # optional pre-set token
    },
    "DR": {
        "key": os.getenv("DR_KEY"),
        "secret": os.getenv("DR_SECRET"),
        "token": None,  # optional pre-set token
    },
}

def _now() -> int:
    return int(time.time())

import requests
import traceback


def _load_token_cache():
    """Load cached tokens from disk into TENANTS on startup."""
    if not TOKEN_CACHE_FILE.exists():
        return
    try:
        cache = json.loads(TOKEN_CACHE_FILE.read_text())
        for tenant, data in cache.items():
            if tenant in TENANTS and data.get("token") and data.get("token_exp", 0) > _now():
                TENANTS[tenant]["token"] = data["token"]
                TENANTS[tenant]["token_exp"] = data["token_exp"]
                print(f"[token cache] Loaded cached token for {tenant}")
    except Exception as e:
        print(f"[token cache] Failed to load cache: {e}")


def _save_token_cache():
    """Persist current in-memory tokens to disk."""
    try:
        cache = {
            t: {"token": d.get("token"), "token_exp": d.get("token_exp", 0)}
            for t, d in TENANTS.items()
            if d.get("token")
        }
        TOKEN_CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        print(f"[token cache] Failed to save cache: {e}")


def invalidate_token(tenant: str):
    """Clear the cached token for a tenant so the next call fetches a fresh one."""
    print(f"[token cache] Invalidating token for {tenant}")
    TENANTS[tenant]["token"] = None
    TENANTS[tenant]["token_exp"] = 0
    _save_token_cache()


def _log_wg_payload(label: str, payload: dict):
    try:
        print(f"\n========== {label} ==========")
        print(json.dumps(payload, indent=2, default=str))
        print("======================================\n")
    except Exception as exc:
        print(f"[workGuru] Failed to log payload for {label}: {exc}")

def _fetch_access_token(tenant: str):
    print("\n========== FETCHING NEW WORKGURU TOKEN ==========")
    print(f"Tenant: {tenant}")

    creds = TENANTS.get(tenant)
    if not creds:
        raise RuntimeError(f"No credentials configured for tenant '{tenant}'")

    base = WG_BASE.rstrip("/")  # e.g. "https://api.workguru.io"
    url = f"{base}/api/ClientTokenAuth/Authenticate/api/client/v1/tokenauth"
    print(f"Auth URL: {url}")

    payload = {
        "apiKey": creds["key"],
        "secret": creds["secret"],
    }
    print("Payload keys present:", {
        "apiKey": bool(creds.get("key")),
        "secret": bool(creds.get("secret")),
    })

    try:
        res = requests.post(url, json=payload, timeout=20)

        # Debug info
        print("Auth status code:", res.status_code)
        try:
            # First 500 chars of body so logs don't explode
            print("Auth response body preview:")
            print((res.text or "")[:500])
        except Exception:
            print("Could not read response text")

        res.raise_for_status()
        data = res.json()

    except Exception as e:
        # This is what you're seeing now in the traceback
        print("\n!!!!!! ERROR WHILE FETCHING WORKGURU TOKEN !!!!!!")
        print("Tenant:", tenant)
        print("Exception:", repr(e))
        print("Traceback:")
        traceback.print_exc()
        print("--------------------------------------------------")
        raise RuntimeError(
            f"Failed to fetch WorkGuru token for tenant '{tenant}'. "
            f"HTTP status: {getattr(res, 'status_code', 'unknown')}. "
            f"See logs above for full response."
        ) from e

    access = data.get("accessToken")
    if not access:
        raise RuntimeError(
            f"WorkGuru token response did not contain 'accessToken' for tenant '{tenant}'. "
            f"Raw response: {data}"
        )

    # Common fields in WG token responses: accessToken, expiresInSeconds
    expires_in = int(data.get("expiresInSeconds", data.get("expires_in", 3600)))
    exp = _now() + max(60, expires_in - 30)

    TENANTS[tenant]["token"] = access
    TENANTS[tenant]["token_exp"] = exp
    _save_token_cache()

    print("Token fetched OK for tenant", tenant)
    print("Token expires at:", exp)
    print("==================================================\n")

    return access



# Load any previously cached tokens when the module is imported
_load_token_cache()


def get_access_token(tenant: str) -> str:
    print(f"Getting access token for tenant: {tenant}")

    cached = TENANTS[tenant].get("token")
    exp = TENANTS[tenant].get("token_exp", 0)

    if cached and exp > _now():
        print(f"[token cache] Using cached token for {tenant}")
        return cached

    _fetch_access_token(tenant)
    return TENANTS[tenant]["token"]

def warm_crm_token(*tenants: str) -> None:
    """Optional: prefetch tokens at startup."""
    targets = tenants or list(TENANTS.keys())
    for t in targets:
        try:
            get_access_token(t)
        except Exception as e:
            # non-fatal warmup
            print(f"[workGuru] Warmup failed for {t}: {e}")

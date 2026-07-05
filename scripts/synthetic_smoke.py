#!/usr/bin/env python3
"""
Post-deploy smoke test for the Magpie FastAPI server.

Magpie is SSO-only (CLAUDE.md §2) — there is no /auth/register or /auth/login to script
against, unlike the sibling apps' synthetic smokes. Instead: mint a suite-audience token from
dragonfly-id's dedicated smoke client (POST https://id.dragonflymedia.org/smoke/token, enabled
by SMOKE_CLIENTS — a separate, revocable credential from the real `magpie` OAuth client), trade
it for a Magpie session via POST /auth/suite (exactly what a real sign-in does), then exercise
create -> read -> delete on a manual cash transaction. A non-zero exit fails the deploy run.
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

MAGPIE_URL = os.environ.get("MAGPIE_URL", "http://127.0.0.1:8005")
DRAGONFLY_ID_URL = os.environ.get("DRAGONFLY_ID_URL", "https://id.dragonflymedia.org")
SMOKE_CLIENT_ID = os.environ.get("SMOKE_CLIENT_ID")
SMOKE_CLIENT_SECRET = os.environ.get("SMOKE_CLIENT_SECRET")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "magpie-smoke@dragonflymedia.org")


def request(method, url, body=None, token=None, form=False):
    data = None
    # Cloudflare (fronting id.dragonflymedia.org) blocks urllib's default User-Agent as a bot
    # signature (error 1010) — a real browser-ish UA clears it.
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MagpieSyntheticSmoke/1.0)"}
    if body is not None:
        if form:
            data = "&".join(f"{k}={v}" for k, v in body.items()).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()
            try:
                return response.getcode(), json.loads(content)
            except json.JSONDecodeError:
                return response.getcode(), content.decode("utf-8")
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content)
        except json.JSONDecodeError:
            return e.code, content.decode("utf-8")


def main():
    if not SMOKE_CLIENT_ID or not SMOKE_CLIENT_SECRET:
        print("[FAIL] SMOKE_CLIENT_ID/SMOKE_CLIENT_SECRET not set")
        sys.exit(1)

    # Step a: mint a suite-audience token from dragonfly-id's smoke client.
    status, result = request(
        "POST",
        f"{DRAGONFLY_ID_URL}/smoke/token",
        body={
            "client_id": SMOKE_CLIENT_ID,
            "client_secret": SMOKE_CLIENT_SECRET,
            "subject_email": SMOKE_EMAIL,
        },
        form=True,
    )
    if status != 200:
        print(f"[FAIL] mint smoke token: HTTP {status} {str(result)[:200]}")
        sys.exit(1)
    suite_token = result.get("access_token")
    if not suite_token:
        print("[FAIL] smoke token response had no access_token")
        sys.exit(1)
    print("[ok] minted suite-audience smoke token")

    # Step b: trade it for a Magpie session — exactly what a real sign-in does.
    status, result = request(
        "POST", f"{MAGPIE_URL}/auth/suite", body={"suite_token": suite_token}
    )
    if status != 200:
        print(f"[FAIL] /auth/suite: HTTP {status} {str(result)[:200]}")
        sys.exit(1)
    access_token = result.get("access_token")
    if not access_token:
        print("[FAIL] /auth/suite response had no access_token")
        sys.exit(1)
    print("[ok] traded for a Magpie session")

    # Step c: ensure an account exists to attach the smoke transaction to (idempotent — reuse
    # one already named this on repeat runs rather than growing forever).
    status, result = request("GET", f"{MAGPIE_URL}/accounts", token=access_token)
    if status != 200:
        print(f"[FAIL] list accounts: HTTP {status} {str(result)[:200]}")
        sys.exit(1)
    account = next((a for a in result if a.get("name") == "Smoke Test Account"), None)
    if account is None:
        status, account = request(
            "POST",
            f"{MAGPIE_URL}/accounts",
            body={"name": "Smoke Test Account", "institution": "Smoke Bank", "type": "depository"},
            token=access_token,
        )
        if status != 201:
            print(f"[FAIL] create account: HTTP {status} {str(account)[:200]}")
            sys.exit(1)
    account_id = account["id"]
    print(f"[ok] smoke account ready ({account_id})")

    # Step d: create a manual cash transaction.
    merchant = "smoke-" + uuid.uuid4().hex[:8]
    status, txn = request(
        "POST",
        f"{MAGPIE_URL}/transactions",
        body={
            "account_id": account_id,
            "amount": -100,
            "date": "2026-01-01",
            "merchant_raw": merchant,
            "kind": "spend",
        },
        token=access_token,
    )
    if status != 201:
        print(f"[FAIL] create transaction: HTTP {status} {str(txn)[:200]}")
        sys.exit(1)
    txn_id = txn["id"]
    print(f"[ok] created transaction {merchant}")

    # Step e: read it back — verifies the write actually persisted, not just a 201.
    status, fetched = request(
        "GET", f"{MAGPIE_URL}/transactions/{txn_id}", token=access_token
    )
    if status != 200 or fetched.get("merchant_raw") != merchant:
        print(f"[FAIL] read-back mismatch: HTTP {status} {str(fetched)[:200]}")
        sys.exit(1)
    print("[ok] write verified")

    # Cleanup: delete the smoke transaction so prod doesn't accumulate one per deploy.
    status, _ = request("DELETE", f"{MAGPIE_URL}/transactions/{txn_id}", token=access_token)
    print(f"[ok] cleaned up (HTTP {status})" if status == 204 else f"[warn] cleanup HTTP {status}")

    print("SMOKE_PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()

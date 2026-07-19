# Phase 4 — Production Posture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address the cheap correctness items from the architecture review: audit the async/threading patterns for silent failures and unbounded growth, and replace the weak encryption key derivation with a proper KDF.

**Architecture:** Two focused changes. (1) Async audit: fix the deprecated `get_event_loop()` pattern, add bounded executor, add error logging to async paths. (2) KDF: replace `get_encryption_key` with HKDF-based derivation, add key versioning for rotation support. No Celery, no Postgres, no Docker — those are YAGNI for a personal app.

**Tech Stack:** Python 3.13, Django, cryptography (HKDF), asyncio, Django Channels.

## Global Constraints

- **Branch:** `phase4/production-posture` (from phase3/typescript — has all prior work).
- **Protected code:** `users/models.py` is protected. The KDF change requires PR with approval. The async audit touches `services/importer.py` (also protected per the Phase 1 updated globs).
- **No schema changes that break existing data.** The KDF change MUST be backward-compatible — existing encrypted tokens must still decrypt.
- **Backend commands:** `cd backend && uv run <cmd>`.

---

## Task 1: Async/threading audit and fixes

**Files:**
- Modify: `backend/services/importer.py` (fix deprecated `get_event_loop`, add bounded executor)
- Modify: `backend/services/annual_performance.py` (review retry logic)
- Review: `backend/database/consumers.py`, `backend/transactions/consumers.py` (error handling in async consumers)

### Findings from exploration

The app does NOT use `threading.Thread`. All async work is:
1. **Django Channels consumers** (WebSocket + SSE) — managed by the ASGI server (Uvicorn/Daphne), not custom threads
2. **`asyncio.run_in_executor`** in `services/importer.py:805` — runs yfinance blocking calls in the default ThreadPoolExecutor
3. **`database_sync_to_async`** wrappers — standard Channels pattern for ORM access in async context
4. **SQLite "database is locked" retries** in `services/annual_performance.py` — retry loop with `asyncio.sleep`

### Issues to fix

#### 1.1: Deprecated `asyncio.get_event_loop()` in importer.py

**Location:** `services/importer.py` ~line 805
**Current:**
```python
loop = asyncio.get_event_loop()
ticker = await loop.run_in_executor(None, yf.Ticker, security.yahoo_symbol)
```
**Problem:** `asyncio.get_event_loop()` is deprecated in Python 3.12+ and will be removed. In an async context, use `asyncio.get_running_loop()` instead.
**Fix:**
```python
loop = asyncio.get_running_loop()
```

#### 1.2: Unbounded executor for yfinance calls

**Location:** `services/importer.py` ~line 805
**Current:** `run_in_executor(None, ...)` uses the default ThreadPoolExecutor which has an unbounded number of threads.
**Problem:** If many price imports run concurrently, unbounded threads can exhaust system resources.
**Fix:** Use a module-level bounded ThreadPoolExecutor:
```python
from concurrent.futures import ThreadPoolExecutor

# Bounded executor for blocking I/O calls (yfinance, requests, etc.)
_blocking_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="blocking-io")
```
Then: `await loop.run_in_executor(_blocking_executor, ...)`

#### 1.3: Audit async consumer error handling

**Location:** `database/consumers.py`, `transactions/consumers.py`
**Check:** Do the consumers catch and log exceptions in their main processing loops? If an exception propagates uncaught, the WebSocket/SSE connection drops silently from the user's perspective.
**Fix:** Ensure every `async for` / `while` loop in consumer `process_*` methods has a top-level try/except that logs the error and sends an error message to the client before closing.

### Steps

- [ ] **Step 1: Fix `get_event_loop` → `get_running_loop` in importer.py**

Grep for all occurrences:
```bash
cd backend && grep -rn "get_event_loop" --include='*.py' . | grep -v '.venv'
```
Replace each with `asyncio.get_running_loop()` (safe because they're all inside async functions).

- [ ] **Step 2: Add bounded ThreadPoolExecutor in importer.py**

Add a module-level `_blocking_executor` and replace `run_in_executor(None, ...)` calls with `run_in_executor(_blocking_executor, ...)`.

- [ ] **Step 3: Audit consumer error handling**

Read `database/consumers.py` and `transactions/consumers.py`. For each consumer's main processing method, verify:
- There's a try/except around the main loop body
- Exceptions are logged (not silently swallowed)
- An error message is sent to the client before disconnecting

If any consumer lacks this, add it. Document what was already correct.

- [ ] **Step 4: Run full test suite**

```bash
cd backend && uv run python -m pytest -q --no-cov
```
Expected: 948 passed, 6 skipped, 0 failed.

- [ ] **Step 5: Verify no schema change**

```bash
cd backend && uv run python manage.py makemigrations --check --dry-run
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "fix: async audit — replace deprecated get_event_loop, bound executor, verify consumer error handling

- Replace asyncio.get_event_loop() with get_running_loop() (Python 3.12+)
- Add bounded ThreadPoolExecutor(max_workers=4) for blocking I/O (yfinance)
- Audit async consumers for error handling (logged + client-notified)"
```

---

## Task 2: Fix encryption KDF

**Files:**
- Modify: `backend/users/models.py` (replace `get_encryption_key` with HKDF-based derivation + key versioning)
- Create: `backend/tests/unit/test_encryption.py` (tests for the new KDF)
- Create: `backend/users/migrations/0022_*` (if schema change needed for key versioning)

### Current state (the problem)

```python
def get_encryption_key(user):
    key_material = f"{settings.SECRET_KEY}_{user.id}"
    key = base64.urlsafe_b64encode(key_material.encode()[:32].ljust(32, b"0"))
    return key
```

Issues:
1. **Not a KDF**: truncates/pads key material to 32 bytes — no diffusion, no salt
2. **No per-token salt**: all tokens for a user use the same key
3. **No key versioning**: rotating `SECRET_KEY` makes ALL tokens unrecoverable
4. **Weak derivation**: the first 32 bytes of `f"{SECRET_KEY}_{user_id}"` are used directly — if SECRET_KEY is short or predictable, the key is weak

### Target design

```python
import hashlib
import hmac
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# Key versioning: store a key_version on each token.
# Version 1 = old truncation scheme (backward compat).
# Version 2 = HKDF-based derivation.

ENCRYPTION_KEY_VERSION = 2

def _derive_key_v1(user):
    """Legacy key derivation (backward compatibility for existing tokens)."""
    key_material = f"{settings.SECRET_KEY}_{user.id}"
    return base64.urlsafe_b64encode(key_material.encode()[:32].ljust(32, b"0"))

def _derive_key_v2(user, salt=None):
    """HKDF-based key derivation.

    Uses HMAC-SHA256 to derive a 32-byte key from SECRET_KEY + user ID.
    An optional salt allows per-token key derivation.
    """
    # Input keying material: SECRET_KEY + user ID
    ikm = f"{settings.SECRET_KEY}:{user.id}".encode()

    # Use HKDF to derive a 32-byte key
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,  # None is fine for HKDF (uses internal salt)
        info=b"portfolio-management-token-encryption-v2",
    )
    raw_key = hkdf.derive(ikm)
    return base64.urlsafe_b64encode(raw_key)

def get_encryption_key(user, version=ENCRYPTION_KEY_VERSION, salt=None):
    """Get the encryption key for a user.

    Supports key versioning for forward migration.
    """
    if version == 1:
        return _derive_key_v1(user)
    return _derive_key_v2(user, salt)
```

### Backward compatibility strategy

**Existing tokens were encrypted with v1.** They MUST still decrypt. The approach:
1. Add a `key_version` field to `BaseApiToken` (default=1 for existing rows)
2. On `set_token`: encrypt with the current version (v2), store `key_version=2`
3. On `get_token`: read `key_version`, use the matching derivation function
4. Existing tokens (key_version=1) decrypt with v1; new tokens use v2
5. Optional future migration: re-encrypt all v1 tokens with v2 (not in this task)

### Steps

- [ ] **Step 1: Write tests for the new KDF (TDD)**

Create `backend/tests/unit/test_encryption.py`:
- Test that v2 key derivation is deterministic (same input → same key)
- Test that v2 keys differ between users
- Test that v1 keys still work (backward compat)
- Test that a v1-encrypted token decrypts with v1 key
- Test that a v2-encrypted token decrypts with v2 key
- Test that v1 and v2 keys are different for the same user
- Test set_token/get_token round-trip with v2

- [ ] **Step 2: Add key_version field to BaseApiToken**

Add to `BaseApiToken` in `users/models.py`:
```python
key_version = models.IntegerField(default=1, help_text="Encryption key version")
```

- [ ] **Step 3: Create migration**

```bash
cd backend && uv run python manage.py makemigrations users
```

- [ ] **Step 4: Replace get_encryption_key with versioned HKDF**

Implement the `_derive_key_v1`, `_derive_key_v2`, and `get_encryption_key(user, version, salt)` functions as described above.

- [ ] **Step 5: Update set_token and get_token**

In `BaseApiToken`:
```python
def set_token(self, token_value, user):
    from users.encryption import ENCRYPTION_KEY_VERSION
    key = get_encryption_key(user, version=ENCRYPTION_KEY_VERSION)
    f = Fernet(key)
    self.encrypted_token = f.encrypt(token_value.encode())
    self.key_version = ENCRYPTION_KEY_VERSION
    self.save()

def get_token(self, user=None):
    if not user:
        raise ValueError("User is required to decrypt token")
    key = get_encryption_key(user, version=self.key_version)
    f = Fernet(key)
    if not self.encrypted_token:
        raise ValueError("No token stored")
    return f.decrypt(self.encrypted_token).decode()
```

- [ ] **Step 6: Run tests**

```bash
cd backend && uv run python -m pytest tests/unit/test_encryption.py -v --no-cov
cd backend && uv run python -m pytest -q --no-cov  # full suite
```

- [ ] **Step 7: Verify migration applies cleanly**

```bash
cd backend && uv run python manage.py migrate
cd backend && uv run python manage.py makemigrations --check --dry-run
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "security: replace weak key derivation with HKDF + key versioning

- Replace truncation-based get_encryption_key with HKDF-SHA256 derivation
- Add key_version field to BaseApiToken (default=1 for backward compat)
- Existing tokens (v1) decrypt with legacy derivation; new tokens use v2
- Enables future key rotation without losing existing encrypted tokens"
```

---

## Final Verification

- [ ] **Step 1: Full backend test suite**
```bash
cd backend && uv run python -m pytest -q --no-cov
```

- [ ] **Step 2: Django check + migrations**
```bash
cd backend && uv run python manage.py check
cd backend && uv run python manage.py makemigrations --check --dry-run
```

- [ ] **Step 3: Frontend still builds + type-checks**
```bash
cd frontend && npm run build && npm run type-check && npm run test:unit
```

- [ ] **Step 4: Verify no deprecated asyncio patterns remain**
```bash
cd backend && grep -rn "get_event_loop" --include='*.py' . | grep -v '.venv'
```
Expected: no output.

---

## What's deliberately NOT in this phase (YAGNI for personal app)

- Celery / Redis (the async consumers + run_in_executor work fine)
- Managed Postgres (SQLite is fine for a personal app)
- Docker / containerization
- CI/CD for deployment
- `.env.production` / nginx / reverse proxy config
- Sentry / Prometheus / Grafana monitoring
- Rate limiting / API throttling

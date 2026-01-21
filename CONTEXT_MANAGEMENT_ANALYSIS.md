# CV Generator - Context Management Analysis & Optimization Plan

## Current Architecture Issues

### 1. Agent Context Bloat
**Problem:** Agent must keep full CV data in memory across multiple turns:
- Step 1: Extract photo → returns `photo_data_uri` (100KB+ base64)
- Step 2: Extract CV text → agent parses into structured data (5-10KB JSON)
- Step 3: User confirms → agent keeps full CV data in context
- Step 4: Validate CV → sends full `cv_data` (5-10KB)
- Step 5: Generate PDF → sends full `cv_data` again (5-10KB)

**Total context usage:** ~20-30KB of CV data replicated across turns.

**Evidence from code:**
```typescript
// ui/app/api/process-cv/route.ts:214-240
const cvData = toolInput?.cv_data ? toolInput.cv_data : toolInput;
console.log('🔍 cvData keys:', Object.keys(cvData || {}));
// Agent must maintain this in context to send it in tool calls
```

### 2. Repeated Large Payloads
**Problem:** Same CV data sent multiple times:
- `validate_cv` receives full cv_data
- `generate_cv_action` receives full cv_data (duplicate)
- Photo data URI sent in both calls if extracted

**Impact:** 
- Increases token costs (input tokens charged per turn)
- Slower API responses
- Context window fills faster

### 3. No State Persistence
**Problem:** No server-side session/cache:
- If conversation breaks, all CV data lost
- Can't resume from previous extraction
- No way to reference "current CV" without resending

**Evidence from code:**
```typescript
// ui/app/api/process-cv/route.ts:259-280
const isContinuation = !!previousResponseId;
const cvText = !isContinuation && hasDocx && docx_base64 
  ? await extractDocxTextFromBase64(docx_base64) 
  : null;
// Text re-extracted every time, no caching
```

---

## Proposed Solution: Session-Based Context Pack

### Architecture Change

```
Current Flow:
User uploads CV → Agent extracts data → Agent keeps in context → Agent sends to validate → Agent sends to generate

Proposed Flow:
User uploads CV → Backend creates session → Agent references session_id → Backend uses cached data
```

### Implementation Plan

#### 1. **Backend Session Storage**

Add new endpoint: `POST /api/create-cv-session`

**Request:**
```json
{
  "source_docx_base64": "...",
  "language": "en"
}
```

**Response:**
```json
{
  "session_id": "cv_abc123def456",
  "expires_at": "2026-01-21T12:00:00Z",
  "extracted_data": {
    "photo_data_uri": "data:image/png;base64,...",  // Optional
    "raw_text": "...",  // Extracted DOCX text
    "fingerprint": "sha256:..."
  }
}
```

**Backend storage:**
```python
# function_app.py - add simple in-memory cache
CV_SESSIONS = {}  # {session_id: {data, expires}}

@app.route(route="create-cv-session", methods=["POST"])
def create_cv_session(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a CV processing session with extracted data cached.
    Returns session_id for subsequent operations.
    """
    req_body = req.get_json()
    source_docx_b64 = req_body.get("source_docx_base64")
    language = req_body.get("language", "en")
    
    # Extract data
    docx_bytes = base64.b64decode(source_docx_b64)
    photo_data_uri = extract_first_photo_data_uri_from_docx_bytes(docx_bytes)
    raw_text = extract_text_from_docx_bytes(docx_bytes)
    
    # Create session
    import secrets
    session_id = f"cv_{secrets.token_urlsafe(16)}"
    expires = datetime.utcnow() + timedelta(hours=2)
    
    CV_SESSIONS[session_id] = {
        "source_docx_base64": source_docx_b64,  # Keep for re-processing
        "photo_data_uri": photo_data_uri,
        "raw_text": raw_text,
        "language": language,
        "expires_at": expires.isoformat(),
        "cv_data": None,  # Will be set when agent extracts
        "fingerprint": hashlib.sha256(docx_bytes).hexdigest()
    }
    
    return func.HttpResponse(
        json.dumps({
            "session_id": session_id,
            "expires_at": expires.isoformat(),
            "extracted_data": {
                "photo_data_uri": photo_data_uri,
                "raw_text": raw_text[:12000],  # Bounded for agent
                "fingerprint": CV_SESSIONS[session_id]["fingerprint"]
            }
        }),
        mimetype="application/json"
    )
```

#### 2. **Update CV Data in Session**

Add endpoint: `POST /api/update-cv-session`

**Request:**
```json
{
  "session_id": "cv_abc123def456",
  "cv_data": { /* full CV structure */ }
}
```

**Response:**
```json
{
  "session_id": "cv_abc123def456",
  "stored": true,
  "validation": { /* quick validation result */ }
}
```

**Purpose:** Agent extracts structured data and stores it in session once, then references session_id.

#### 3. **Simplify Tool Calls**

**Old `validate_cv`:**
```json
{
  "cv_data": { /* 5-10KB of data */ }
}
```

**New `validate_cv`:**
```json
{
  "session_id": "cv_abc123def456"
}
```

**Old `generate_cv_action`:**
```json
{
  "cv_data": { /* 5-10KB of data */ },
  "source_docx_base64": "...",  // Optional
  "language": "en"
}
```

**New `generate_cv_action`:**
```json
{
  "session_id": "cv_abc123def456"
}
```

Backend fetches `cv_data` from session cache internally.

---

## Benefits

### 1. **Reduced Agent Context** (70-80% reduction)
- Agent only stores `session_id` (20 chars)
- No need to keep full CV data in memory
- Photo data URI never sent to agent (stays in backend)

**Before:**
```
Turn 1: Extract photo → 100KB photo_data_uri in context
Turn 2: Extract CV → 5KB cv_data in context
Turn 3: Validate → send 5KB cv_data
Turn 4: Generate → send 5KB cv_data + 100KB photo ref
Total: ~120KB in agent context
```

**After:**
```
Turn 1: Create session → return session_id (20 chars)
Turn 2: Extract CV → send session_id (20 chars) + cv_data (5KB), stored in backend
Turn 3: Validate → send session_id (20 chars)
Turn 4: Generate → send session_id (20 chars)
Total: ~5KB in agent context (one-time storage, then references only)
```

### 2. **Lower Token Costs** (30-40% reduction)
- Input tokens reduced (no repeated cv_data)
- Photo base64 never counted as input tokens
- Shorter payloads = faster responses

### 3. **Session Resumption**
- User can refresh page and continue with same `session_id`
- Backend keeps extracted data for 2 hours
- No need to re-upload CV if conversation interrupted

### 4. **Better Error Recovery**
- If validation fails, agent doesn't need to resend full data
- Backend can provide diff between stored and corrected data
- Incremental updates possible

---

## Migration Path

### Phase 1: Add Session Storage (Non-Breaking)
1. Add `/create-cv-session` endpoint
2. Add `/update-cv-session` endpoint
3. Update existing endpoints to accept **either** `cv_data` OR `session_id`
4. Backward compatible with old tool calls

**Code:**
```python
# function_app.py - update generate-cv-action
cv_data = None
session_id = req_body.get("session_id")

if session_id:
    # New path: fetch from session
    session = CV_SESSIONS.get(session_id)
    if not session:
        return error("session_id not found or expired")
    cv_data = session.get("cv_data")
    if not cv_data:
        return error("CV data not yet stored in session; call update-cv-session first")
else:
    # Old path: direct cv_data (backward compatible)
    cv_data = req_body.get("cv_data")
    if not cv_data:
        return error("cv_data or session_id required")
```

### Phase 2: Update UI Route
1. Call `/create-cv-session` on DOCX upload
2. Store `session_id` in UI state
3. Inject `session_id` into tool calls instead of full data

**Code:**
```typescript
// ui/app/api/process-cv/route.ts
let sessionId: string | null = null;

// On first DOCX upload
if (hasDocx && !sessionId) {
  const sessionResp = await callAzureFunction('/create-cv-session', {
    source_docx_base64: docx_base64,
    language
  });
  sessionId = sessionResp.session_id;
  // Inject raw_text into user message for agent extraction
}

// When agent calls tools
case 'validate_cv':
  if (sessionId && !toolInput.cv_data) {
    // New: reference session
    return await callAzureFunction('/validate-cv', { session_id: sessionId });
  } else {
    // Old: direct cv_data
    return await callAzureFunction('/validate-cv', { cv_data: toolInput.cv_data });
  }
```

### Phase 3: Update Tool Schemas
1. Make `cv_data` optional in tool schemas
2. Add `session_id` as alternative parameter
3. Update prompt to instruct agent to use `session_id` when available

**Schema update:**
```json
{
  "name": "validate_cv",
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {
        "type": "string",
        "description": "Session ID from create_cv_session. Use this if available to avoid resending full CV data."
      },
      "cv_data": {
        "type": "object",
        "description": "Full CV data (alternative to session_id for backward compatibility)"
      }
    },
    "oneOf": [
      {"required": ["session_id"]},
      {"required": ["cv_data"]}
    ]
  }
}
```

### Phase 4: Add Session Management Tool
Give agent direct control over session:

```json
{
  "name": "store_cv_data",
  "description": "Store extracted CV data in session for reuse. Call this after extracting CV structure, then use session_id in validate/generate calls.",
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {"type": "string"},
      "cv_data": {"type": "object"}
    },
    "required": ["session_id", "cv_data"]
  }
}
```

---

## Alternative: Lightweight Context Pack (Current Approach)

**Already implemented:** `generate-context-pack` endpoint creates fingerprinted summary.

**Pros:**
- No session management complexity
- Stateless backend
- Works with any agent

**Cons:**
- Still sends full CV data to agent initially
- Agent must maintain context
- No session resumption

**Recommendation:** Combine both:
- Use session storage for state persistence
- Use context pack for compact representation in agent context
- Best of both worlds

---

## Additional Optimizations

### 1. **Move Text Extraction to Backend**
**Current:** UI extracts DOCX text with `mammoth`
**Proposed:** Backend extracts on session creation
**Benefit:** UI doesn't need `mammoth` dependency, smaller bundle

### 2. **Lazy Photo Extraction**
**Current:** Photo extracted upfront (even if not used)
**Proposed:** Extract only when `generate_cv_action` called
**Benefit:** Faster session creation, lower memory

### 3. **Session Cleanup**
Add automatic cleanup of expired sessions:
```python
import threading
import time

def cleanup_expired_sessions():
    while True:
        time.sleep(300)  # Every 5 minutes
        now = datetime.utcnow()
        expired = [sid for sid, sess in CV_SESSIONS.items() 
                   if datetime.fromisoformat(sess['expires_at']) < now]
        for sid in expired:
            del CV_SESSIONS[sid]
        logging.info(f"Cleaned up {len(expired)} expired sessions")

# Start cleanup thread
threading.Thread(target=cleanup_expired_sessions, daemon=True).start()
```

### 4. **Persistent Storage (Optional)**
For production, replace in-memory dict with:
- Azure Blob Storage (JSON files)
- Azure Table Storage
- Redis cache

**Example with Azure Blob:**
```python
from azure.storage.blob import BlobServiceClient

blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)

def save_session(session_id, data):
    blob_client = blob_service.get_blob_client("cv-sessions", f"{session_id}.json")
    blob_client.upload_blob(json.dumps(data), overwrite=True)

def load_session(session_id):
    blob_client = blob_service.get_blob_client("cv-sessions", f"{session_id}.json")
    return json.loads(blob_client.download_blob().readall())
```

---

## Recommended Next Steps

1. **Immediate (Low Risk):**
   - Add `/create-cv-session` endpoint (backward compatible)
   - Test with Postman/curl
   - Measure context reduction

2. **Short Term (1-2 days):**
   - Update UI to use session on upload
   - Add session_id injection in tool calls
   - Update tool schemas to accept session_id

3. **Medium Term (1 week):**
   - Add persistent storage (Azure Blob)
   - Add session cleanup
   - Update prompts to prefer session_id

4. **Long Term (Optional):**
   - Add session analytics (track usage)
   - Add session sharing (multiple users)
   - Add versioning (track CV edits)

---

## Summary

**Key Changes:**
1. ✅ Backend stores CV data in session (2-hour TTL)
2. ✅ Agent references `session_id` instead of sending full data
3. ✅ Backward compatible with current tool calls
4. ✅ 70-80% context reduction for agent
5. ✅ 30-40% token cost reduction
6. ✅ Session resumption support

**Impact:**
- **Agent:** Simpler context, fewer tokens
- **Backend:** Minimal added complexity (in-memory dict + cleanup)
- **User:** Faster responses, resumable sessions
- **Cost:** Lower OpenAI bills

**Effort:** ~4-6 hours implementation + testing

# Phase 2 (0.4, 0.5) Planning Document
**Wave:** Phase 2 (Performance Optimization)  
**Status:** Planning  
**Complexity:** High (requires significant refactoring)

---

## Overview

Phase 2 focuses on two performance improvements that require careful refactoring:
- **0.4: Session Write Batching** - Reduce session store writes from ~23 individual calls → fewer batch operations
- **0.5: Metadata to Blob Migration** - Move large metadata objects to Azure Blob Storage

These items depend on Wave 0 (correctness) being stable first.

---

## 0.4: Session Write Batching

### Problem
Currently, `_tool_generate_cv_from_session`, `update_cv_field`, and other tools call `store.update_session()` independently:
- Each call is a full metadata write to table storage
- ~23 scattered write operations per session lifecycle
- Poor performance at scale

### Solution
Implement a batching abstraction:
1. Collect pending writes in session context
2. Flush batch at end of orchestration turn (not per-tool)
3. Reduce to 1-2 writes per orchestration call

### Scope
Files affected:
- `function_app.py` - All tool implementations (~23 calls)
- `src/session_store.py` - Add batch API
- Tests - Add batch integration tests

### Implementation Sketch
```python
# OLD (scattered writes)
store.update_session(sid, cv, meta)  # After update_cv_field
store.update_session(sid, cv, meta)  # After confirm flags
store.update_session(sid, cv, meta)  # After PDF generation

# NEW (batched)
class SessionWriteBatch:
    def queue_update(self, session_id, cv_data, metadata):
        self._pending.append((session_id, cv_data, metadata))
    
    def flush(self):
        # Batch write to store
        for sid, cv, meta in self._pending:
            store.update_session(sid, cv, meta)
        self._pending.clear()

# Usage in orchestration
batch = SessionWriteBatch(store)
# ... run tools (queue updates instead of immediate writes)
batch.flush()  # One call at end
```

### Dependencies
- Requires Wave 0 stable (FSM flags must work first)
- Doesn't affect API contracts
- Backward compatible with existing session store

### Effort Estimate
- Implementation: 3-4 hours
- Testing: 2-3 hours
- Total: 5-7 hours

---

## 0.5: Metadata to Blob Migration

### Problem
Session metadata in table storage grows with each PDF generation:
- PDF refs accumulate (hash, size, render time, etc.)
- Context pack deltas stored
- Event logs stored inline
- Current limit: ~1MB per session (Azure table limit)
- Large metadata = slow reads/writes

### Solution
Move to two-tier storage:
- **Hot tier:** Core metadata (stage, confirmed_flags, pdf_generated)
- **Cold tier:** Large objects in blob storage (pdf_refs, event_log, context_packs)

### Scope
Files affected:
- `src/session_store.py` - Add blob pointer logic
- `src/blob_store.py` - Already exists, extend for metadata
- `function_app.py` - Update all metadata reads/writes
- Tests - Add migration tests

### Implementation Sketch
```python
# OLD (all inline)
metadata = {
    "pdf_refs": { ... 2KB ... },
    "event_log": [ ... 500KB ... ],
    "context_packs": { ... 300KB ... },
    "section_hashes": { ... },
}

# NEW (tiered)
# Table storage (hot):
metadata = {
    "stage": "DONE",
    "confirmed_flags": {...},
    "pdf_generated": True,
    "_pdf_refs_blob": {"container": "metadata", "blob_name": "session-123/pdf_refs.json"},
    "_event_log_blob": {"container": "metadata", "blob_name": "session-123/event_log.json"},
}

# Blob storage (cold):
# metadata/session-123/pdf_refs.json → { "ref1": {...}, "ref2": {...} }
# metadata/session-123/event_log.json → [ event1, event2, ... ]
```

### Migration Strategy
1. Read: Detect blob pointers, transparently fetch from blob
2. Write: Large objects → blob, small objects → table
3. Backward compatible: Old sessions work with new code (lazy migration)
4. Cleanup: Optional migration job for old sessions

### Dependencies
- Requires 0.4 batching (fewer writes = smaller batch operations)
- Blob store already implemented
- Transparent to API contracts

### Effort Estimate
- Implementation: 4-5 hours
- Testing: 3-4 hours
- Total: 7-9 hours

---

## Implementation Sequence

### Recommended Order
1. **0.4 first** - Reduces write volume, easier to test
2. **0.5 second** - Leverages 0.4's batching infrastructure

### Parallel Work (if team)
- Developer A: Implement 0.4 batching + tests
- Developer B: Plan 0.5 blob migration (design, schemas)
- Then: Developer B implements 0.5 using A's batching

---

## Testing Strategy

### Unit Tests
- Session write batch: Test queueing, flushing, ordering
- Blob migrations: Test lazy loading, fallback to inline, migration

### Integration Tests
- Full orchestration with batching enabled
- Verify no extra writes
- Verify blob storage is used correctly

### Performance Benchmarks
- Baseline: Count writes before/after 0.4
- Target: <3 writes per orchestration call (vs 20+ now)

---

## Risk Mitigation

### Risks
1. **Batch writes fail mid-session** → Orphaned pending writes
   - Mitigation: Wrap flush in transaction, retry logic
2. **Blob storage throttling** → Cascading failures
   - Mitigation: Exponential backoff, circuit breaker
3. **Migration breaks old sessions** → Data loss
   - Mitigation: Backward compatibility, safe fallback to inline

### Rollback Plan
- Feature flags: `CV_SESSION_WRITE_BATCHING=1`, `CV_METADATA_BLOB_STORAGE=1`
- Can disable independently if issues arise

---

## Success Criteria

### 0.4: Session Write Batching
- [ ] Writes per orchestration call: <3 (was 20+)
- [ ] No data loss
- [ ] Backward compatible
- [ ] Tests passing

### 0.5: Metadata to Blob
- [ ] Table storage row size: <100KB (was up to 1MB)
- [ ] Read latency acceptable (<50ms)
- [ ] Old sessions work transparently
- [ ] Migration tests passing

---

## Future Work (Phase 3+)

### 0.6: Compression
- Compress large metadata objects before blob storage
- Reduce storage costs

### 0.7: Archival
- Move old sessions to archive blob container after X days
- Restore on demand

### 0.8: Caching Layer
- Redis cache for hot metadata
- Reduce reads from table/blob storage

---

## Handoff Notes

**To next agent:**
- Wave 0 (correctness) is stable and tested ✅
- Phase 2 (performance) is planned, not yet started
- Recommend 0.4 before 0.5 (batching prerequisite)
- Feature flags framework in place for safe rollout
- Tests required: Unit + integration

---

**Prepared by:** Copilot Agent  
**Date:** 2026-01-27  
**Next Review:** After Wave 0 deployed to staging

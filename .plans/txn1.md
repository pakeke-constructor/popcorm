# txn1: buffered writes + periodic flush (group commit)

## Motivation
User wants fast reads/writes AND multithreading. "its fine to lose 0.2s of writes as long as we have flushing."
Database must NEVER be corrupted (agents.md ideology).

Measured (Windows, 16B rows, py-lmdb 3.0.0 / LMDB 0.9.36):
- short write txn per op, sync on: ~1250 us/write (fsync dominated)
- short write txn per op, sync=False: ~17 us/write, but power loss / OS crash can corrupt (LMDB docs: needs FS write ordering; NTFS doesn't guarantee). Rejected.
- batched writes in one txn: ~0.72 us/write
- short read txn per get: ~1.6 us (py-lmdb has no txn reset/renew)

So: buffer writes in memory, commit them in batches with full sync. Every LMDB commit stays fully durable+atomic,
so the only failure mode is losing <= ~0.2s of unflushed writes. Never corruption.

Not a WAL: no log file. LMDB stays the only on-disk store. A WAL would only add process-crash durability; not worth the code.

## Design
State on `DB` (single source of truth for unflushed data):
- `_pending: dict[(dbi, key)] -> bytes | TOMBSTONE`
- `_inflight: dict | None` (batch currently being committed)
- `_lock` (small; guards `_pending` / `_inflight` swaps + lookups)
- `_flush_lock` (held across swap + commit; serializes flushes so older batches can't overwrite newer ones)

Ops:
- `save(obj)` / `delete(id)`: write into `_pending` under `_lock`. delete writes TOMBSTONE. ~1 us, any thread.
- `get(id)`: `_pending` -> `_inflight` -> LMDB short read txn (copy via `from_buffer_copy`). TOMBSTONE -> None.
- `flush()`: the ONLY commit path. Under `_flush_lock`: swap `_pending` into `_inflight`, open write txn, put/delete all,
  commit (synced), THEN clear `_inflight`. (commit before clear => a value is never missing from all three places.)
  Write txn opened and committed in one call, so LMDB's txn-is-thread-bound rule never matters; any thread can call it.
- Timer: daemon thread, `while True: event.wait(0.2); flush()`. Just a trigger, not a worker/queue.
  Needed so writes before an idle period still land within ~0.2s.
- `atexit` -> `flush()`. User can call `db.flush()` explicitly.
- `atomic()`: context manager collecting writes in a local dict. `get` inside the block checks local dict first.
  On exit, merge into `_pending` in one step under `_lock` => whole block lands in one commit (all-or-nothing, even on power loss).
  On exception, discard local dict.
  All-or-nothing only, NOT isolated: read-modify-write across threads can race. Possible later: `db.run(fn)` running fn inside a real write txn.

Threads / handles:
- One LMDB env shared across threads. All txns are short-lived (open+close within one call).
- Multi-thread read txns worked in testing (believed to be py-lmdb's default MDB_NOTLS; confirm).

Zero-copy: mostly dropped. Pending values are owned bytes; LMDB reads copy (copy cost is noise for small rows vs txn overhead).

## Open questions
- How saves/gets inside `atomic()` find the block's local dict: explicit `txn=txn` arg (current agents.md API) or thread-local "current block"?
- Commit failure (e.g. MAP_FULL). Suggested: put batch back into `_pending` without overwriting newer keys, store the error,
  re-raise on next `flush()`. Also need some map_size strategy (set_mapsize needs no active txns in-process).
- Multi-process: in scope or not? Unflushed writes are per-process; other processes don't see them; last flush wins.

## Files
- popcorm.py (DB, Row.save/get, add delete/flush/atomic)
- tests.py
- agents.md (API section mentions `atomic() as txn` + `txn=txn` args; this design replaces that)

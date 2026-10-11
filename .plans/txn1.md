# txn1: buffered writes + periodic flush (group commit)

## Motivation
User wants fast reads/writes AND multithreading. "its fine to lose 0.2s of writes as long as we have flushing."
Database must NEVER be corrupted (agents.md ideology). Multi-process is in scope.

Measured (Windows, 16B rows, py-lmdb 3.0.0 / LMDB 0.9.36):
- short write txn per op, sync on: ~1250 us/write (fsync dominated)
- short write txn per op, sync=False: ~17 us/write, but power loss / OS crash can corrupt (LMDB docs: needs FS write ordering; NTFS doesn't guarantee). Rejected.
- batched writes in one txn: ~0.72 us/write
- short read txn per get: ~1.6 us (py-lmdb has no txn reset/renew)

So: buffer writes in memory, commit them in batches with full sync. Every LMDB commit stays fully durable+atomic,
so the only failure mode is losing <= ~0.2s of unflushed writes. Never corruption.

Not a WAL: no log file. LMDB stays the only on-disk store. A WAL would only add process-crash durability; not worth the code.

## Design
State on `DB` (single source of truth for unflushed data, per process):
- `_pending: dict[(dbi, key)] -> bytes | TOMBSTONE`
- `_inflight: dict | None` (batch currently being committed)
- `_lock` (small; guards `_pending` / `_inflight` swaps + lookups)
- `_flush_lock` (held across swap + commit; serializes flushes so older batches can't overwrite newer ones)

No sequencer thread: in-process, the shared `_pending` dict + `_lock` IS the sequencer. The timer thread only triggers `flush()`.

Ops:
- `save(obj)` / `delete(id)`: write into `_pending` under `_lock`. delete writes TOMBSTONE. ~1 us, any thread.
- `get(id)`: `_pending` -> `_inflight` -> LMDB short read txn (copy via `from_buffer_copy`). TOMBSTONE -> None.
- `flush()`: the ONLY buffered commit path. Under `_flush_lock`: swap `_pending` into `_inflight`, open write txn, put/delete all,
  commit (synced), THEN clear `_inflight`. (commit before clear => a value is never missing from all three places.)
  Write txn opened and committed in one call, so LMDB's txn-is-thread-bound rule never matters; any thread can call it.
- Timer: daemon thread, `while True: event.wait(0.2); flush()`. Just a trigger, not a worker/queue.
  Needed so writes before an idle period still land within ~0.2s.
- `atexit` -> `flush()`. User can call `db.flush()` explicitly.
- `atomic()`: context manager yielding a local dict ("txn"). Saves/gets find it via explicit `txn=txn` arg (matches agents.md API; no hidden thread-local state).
  `get(..., txn=txn)` checks the local dict first.
  On exit, merge into `_pending` in one step under `_lock` => whole block lands in one commit (all-or-nothing, even on power loss).
  On exception, discard local dict.
  All-or-nothing only, NOT isolated: read-modify-write across threads/processes can race. Use `run_atomic` for that.
- `db.run_atomic(fn)`: runs `fn` inside a real LMDB write txn (synced commit, ~1.25 ms). Atomic AND isolated across threads and processes
  (LMDB's single-writer lock is cross-process). For counters / read-modify-write. Must flush or overlay `_pending` first so fn sees this process's buffered writes. (detail TBD)

Multi-process:
- Each process has its own buffer + 0.2s flush; LMDB serializes commits across processes. No socket/IPC sequencer.
- Accepted semantics: other processes see writes up to ~0.2s late; same key written by two processes => last flush wins (even if its write was older).
- `run_atomic` is the escape hatch when that isn't acceptable.
- Rejected: socket sequencer. Every read-your-writes get becomes an IPC round trip (~20-100 us vs ~1.6 us), needs host election/handover
  (host exit loses everyone's buffer) or a daemon (= server DB, not embedded), plus port/lock-file discovery. No AF_UNIX on Windows CPython.

Commit failure (e.g. MAP_FULL): best effort, then raise, like malloc OOM.
- Put failed batch back into `_pending` without overwriting newer keys, store the error, re-raise on next `flush()` / `save()`.
  Note: error surfaces on a later call, not the save that caused it.
- map_size: possible Windows issue, unconfirmed. LMDB 0.9 on Windows may grow the data file to the full map_size straight away, so "just set it huge" may not work.
  Verify first. Growing needs set_mapsize with no active txns in-process; other processes get MDB_MAP_RESIZED and must handle it.

Threads / handles:
- One LMDB env shared across threads. All txns are short-lived (open+close within one call).
- Multi-thread read txns worked in testing (believed to be py-lmdb's default MDB_NOTLS; confirm).

Zero-copy: mostly dropped. Pending values are owned bytes; LMDB reads copy (copy cost is noise for small rows vs txn overhead).

## Open questions
- `run_atomic(fn)`: what does fn receive (txn handle to pass as `txn=`?), and flush-first vs overlay `_pending`.
- map_size strategy on Windows (pending the check above).

## Files
- popcorm.py (DB, Row.save/get, add delete/flush/atomic/run_atomic)
- tests.py
- agents.md (API section: `atomic() as txn` + `txn=txn` kept; add `run_atomic`, `flush`, `delete`)

"""
popcORM: a minimal key-value ORM on LMDB.

Fields:
    Each annotation type maps (via FIELDS) to a Field(name, ctype, is_valid).
    - name:     goes into the schema string; identifies the storage layout.
    - ctype:    fixed-size ctypes type. Rows are flat ctypes structs.
    - is_valid: runs on every assignment (Row.__setattr__), so bad values error where they're set.
                Must check on assignment: ctypes silently truncates out-of-range ints when stored.
                Changing is_valid does NOT change the schema (layout is unchanged).
    Deferred: custom-field syntax (annotation vs default value), and ser/deser
    (would need per-field properties, losing direct ctypes attribute access).
"""
import atexit, ctypes, lmdb, threading, time
from collections import namedtuple
from contextlib import contextmanager

Field = namedtuple("Field", "name ctype is_valid")
FIELDS = {int: Field("i64", ctypes.c_int64, lambda x: type(x) is int and -2**63 <= x < 2**63)}


def _key(id):
    return bytes(ctypes.c_uint64(id + 2**63))  # bias i64 -> u64 so LMDB integerkey sorts signed ids correctly


class Row(ctypes.Structure):
    def __setattr__(self, k, v):
        f = self._types.get(k)
        if f and not f.is_valid(v):
            raise ValueError(f"{type(self).__name__}.{k}: invalid {f.name} value {v!r}")
        super().__setattr__(k, v)

    @classmethod
    def save(cls, obj, txn=None):
        cls._db._write(cls._tree, _key(obj.id), bytes(obj), txn)

    @classmethod
    def delete(cls, id, txn=None):
        cls._db._write(cls._tree, _key(id), None, txn)

    @classmethod
    def get(cls, id, txn=None):
        v = cls._db._read(cls._tree, _key(id), txn)
        return None if v is None else cls.from_buffer_copy(v)


class DB:
    """
    Writes are buffered in `_pending` and committed in batches (synced) by `flush()`, every ~0.2s and at exit.
    `_pending` / `_inflight` / atomic() dicts map (tree, key) -> bytes, or None for a delete.
    `txn` args are either an atomic() dict, or a raw lmdb.Transaction inside run_atomic().
    """
    def __init__(self, path, **kw):
        self.env = lmdb.open(path, subdir=False, max_dbs=256, metasync=False, **kw)
        self.schema = self.env.open_db(b"schema")
        self.buckets, self._trees = {}, {}
        self._pending, self._inflight, self._error = {}, None, None
        self._lock, self._flush_lock = threading.Lock(), threading.Lock()
        threading.Thread(target=self._flush_loop, daemon=True).start()
        atexit.register(self.flush)

    def _flush_loop(self):
        while True:
            time.sleep(0.2)
            try:
                self.flush()
            except Exception as e:
                self._error = e  # re-raised by the next save() / atomic()

    def _write(self, tree, k, v, txn):
        if isinstance(txn, lmdb.Transaction):
            if v is None:
                txn.delete(k, db=tree)
            else:
                txn.put(k, v, db=tree)
        elif txn is not None:
            txn[(tree, k)] = v
        else:
            if self._error:
                raise self._error
            with self._lock:
                self._pending[(tree, k)] = v

    def _read(self, tree, k, txn):
        if isinstance(txn, lmdb.Transaction):
            return txn.get(k, db=tree)
        if txn is not None and (tree, k) in txn:
            return txn[(tree, k)]
        with self._lock:
            for buf in (self._pending, self._inflight or {}):
                if (tree, k) in buf:
                    return buf[(tree, k)]
        with self.env.begin() as t:
            return t.get(k, db=tree)

    @contextmanager
    def atomic(self):
        local = {}
        yield local
        if self._error:
            raise self._error
        with self._lock:
            self._pending.update(local)

    def flush(self):
        if self._pending:
            self.run_atomic()

    def run_atomic(self, fn=lambda txn: None):
        """Commits pending writes, and runs fn(txn) in the same LMDB write txn. Isolated across threads & processes."""
        with self._flush_lock:
            with self._lock:
                self._inflight, self._pending = self._pending, {}
            try:
                with self.env.begin(write=True) as t:
                    for (tree, k), v in self._inflight.items():
                        self._write(tree, k, v, t)
                    result = fn(t)
            except BaseException:
                with self._lock:
                    self._pending, self._inflight = {**self._inflight, **self._pending}, None
                raise
            with self._lock:
                self._inflight = None
            self._error = None
            return result

    def get_bucket(self, name):
        return self.buckets[name]

    def Bucket(self, cls):
        ann = cls.__annotations__
        types = {k: FIELDS.get(t) for k, t in ann.items()}
        if ann.get("id") is not int or None in types.values():
            raise TypeError(f"{cls.__name__}: needs an int `id` field, and all field types must be in popcorm.FIELDS")
        fields = ",".join(f"{k}:{f.name}" for k, f in types.items()).encode()
        prefix = cls.__name__.encode() + b"."
        with self.env.begin(write=True) as t:
            versions = {v: int(k[len(prefix):]) for k, v in t.cursor(self.schema) if k.startswith(prefix)}
            name = prefix + str(versions.get(fields, max(versions.values(), default=-1) + 1)).encode()
            t.put(name, fields, db=self.schema)
            if name not in self._trees:  # py-lmdb returns a new (unequal) handle per open_db; _pending keys need one
                self._trees[name] = self.env.open_db(name, txn=t, integerkey=True)
        self.buckets[cls.__name__] = type(cls.__name__, (cls, Row), {
            "__module__": cls.__module__,
            "_fields_": [(k, f.ctype) for k, f in types.items()],
            "_types": types,
            "_db": self,
            "_tree": self._trees[name],
        })
        return self.buckets[cls.__name__]

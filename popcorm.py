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
import ctypes, lmdb
from collections import namedtuple

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
    def save(cls, obj):
        with cls._env.begin(write=True) as t:
            t.put(_key(obj.id), bytes(obj), db=cls._dbi)

    @classmethod
    def get(cls, id):
        with cls._env.begin(buffers=True) as t:
            v = t.get(_key(id), db=cls._dbi)
            return None if v is None else cls.from_buffer_copy(v)


class DB:
    def __init__(self, path, **kw):
        self.env = lmdb.open(path, subdir=False, max_dbs=256, metasync=False, **kw)
        self.schema = self.env.open_db(b"schema")
        self.buckets = {}

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
            dbi = self.env.open_db(name, txn=t, integerkey=True)
        self.buckets[cls.__name__] = type(cls.__name__, (cls, Row), {
            "__module__": cls.__module__,
            "_fields_": [(k, f.ctype) for k, f in types.items()],
            "_types": types,
            "_env": self.env,
            "_dbi": dbi,
        })
        return self.buckets[cls.__name__]

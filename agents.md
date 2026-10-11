
# popcORM:
A simple key-value ORM db using LMDB under the hood.


## Architecture:
- popcorm.py (main file, everything here)
- tests.py
- benchmark.py

Implementation is deliberately simple: everything contained in the `popcorm.py` file.
Less lines of code is best. Lets try keep this under a few hundred lines of code; super concise.

Tests are inside `tests.py`.
(MAKE SURE TESTS ARE EXTREMELY CONCISE AND SIMPLE TOO; we don't need to test every case.)
If you want to run a smoke-test, create a `smoke_test.py` file, run it, and then delete it after.

Benchmark benchmarks this against pickle, SQLite, and other dbs.



## API:
```py
import popcorm

db = popcorm.DB("file.db")

@db.Bucket
class User:
    id: str # `id` is a special reserved field, the primary key.
    # it can be int or str. (in this case, it is the user's email)
    name: str
    age: int # i64
    favorite_number: Optional[int]


# save/get classmethods are defined
User.save(User(...))
user = User.get(6)


assert db.get_bucket("User") == User


User.delete(6)
# writes are buffered in memory, and flushed (synced commit) every ~0.2s + at exit.
# a crash can lose the last ~0.2s of writes, but never corrupts the db.
db.flush() # force a flush now


# can do atomic: (all-or-nothing, lands in one commit. NOT isolated)
with db.atomic() as txn:
    User.save(User(...), txn=txn)
    User.save(User(...), txn=txn)
    user = User.get(5, txn=txn)


# run_atomic: fn runs inside a real LMDB write txn (atomic AND isolated, across threads + processes).
# for read-modify-write. slower (~1ms, fsync). don't call flush/run_atomic inside fn (deadlock).
def incr(txn):
    c = Counter.get(1, txn=txn)
    c.n += 1
    Counter.save(c, txn=txn)
db.run_atomic(incr)

```

## How it works:
There is an extra named DB called `schema` that encodes the current schema.
this is mostly hidden from the user, and serves only as metadata. (however user can still obviously inspect the metadata and stuff)
(The LMDB main DB can't hold this: its values for named DBs are LMDB-internal records.)

Then, each @Bucket entry get's it's own b+ tree, keyed `Name.{integer}`. integer can just increase indefinitely.
(`.` isnt valid python identifier char so it works as seperator.)
The fields (exact name and exact type) are stored inside of the value, in the `schema` DB.
If schema is changed -> a new bucket is created; old bucket is made unable to be accessed.
If schema is changed back to an old one -> the old bucket is reused.
So for example:
```py
# day 1:
@db.Bucket
class User:
    id: int; foo: str
# schema {
#     User.0: (id=int, foo=str)
# }
```
```py
# day 2:
# we change the User bucket;
@db.Bucket
class User:
    id: int
    foo: int; bar: int
# schema {
#     User.0: (id=int, foo=str)
#     User.1: (id=int, foo=int, bar=int)
# }
```
This makes it very easy and clear to see orphaned data.
However, it means that users will need to be much more aware of migrations. More on that below.


Use ctypes under the hood so reading/writing from the mmap'ed memory is zero overhead.

NOTE (zero-copy): mostly dropped (see .plans/txn1.md). `get()` copies the record (`from_buffer_copy`);
pending values are owned bytes, and copy cost is noise vs txn overhead for small rows.


## Indexing:
No built in special DB indexing.
Users maintain their own references using primary-keys.


## Migrations:
DB migrations are the tricky bit: None of it is automatic; it's all implicit.
This makes it slightly harder for the user; but it also makes it WAY clearer what's actually happening.
We also expose a classmethod, `MyBucket.migrate_orphan_buckets()`.
This collects all schema-buckets that are called `MyBucket`, then sweeps all entries in orphaned buckets to do a "best attempt" at migrating stuff over.
Maybe we could pass values into args (callback handling orphaned vals, another callback handling new vals, and a final callback handling change in type for a field?)


## IDEOLOGY:
- simplicity is best
- less lines of code is better
- readability is very important. Don't do list-comprehensions for the sake of brevity, and don't write unreadable code for the sake of reducing line-count.
- atomicity is OFF by default; user can bundle writes together if they want.
- dont need double fsyncs, keep it fast
- database should NEVER be able to be corrupted


## AGENT GUIDELINES:
It is **SUPER IMPORTANT** that you don't hack together something that is poorly designed.

Since this project is just beginning, I expect a lot of the initial work to be design-based.
That is, going back/forth and having a discussion about how best to implement things.

Not neccessarily coding; just discussing and planning.
Reminder: You are working with an experienced engineer, if there's a roadblock, no matter how small, do NOT hack around it; voice your concern instead.


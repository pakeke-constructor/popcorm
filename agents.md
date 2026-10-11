
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


# can do atomic:
with db.atomic() as txn:
    User.save(User(...), txn=txn)
    User.save(User(...), txn=txn)
    user = User.get(5, txn=txn)

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

NOTE (zero-copy): `get()` currently copies the record out of the mmap (`from_buffer_copy`),
since mmap'd memory is only valid while the read txn is open.
True zero-copy views are only possible once `atomic()` exists and the caller holds the txn open.


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
- atomicity is OFF by default; user can bundle writes together if they want.
- dont need double fsyncs, keep it fast
- database should NEVER be able to be corrupted


## AGENT GUIDELINES:
It is **SUPER IMPORTANT** that you don't hack together something that is poorly designed.

Since this project is just beginning, I expect a lot of the initial work to be design-based.
That is, going back/forth and having a discussion about how best to implement things.

Not neccessarily coding; just discussing and planning.
Reminder: You are working with an experienced engineer, if there's a roadblock, no matter how small, do NOT hack around it; voice your concern instead.


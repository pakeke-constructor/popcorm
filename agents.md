
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

@db.Table
class User:
    id: str # `id` is a special reserved field, the primary key.
    # it can be int or str. (in this case, it is the user's email)
    name: str
    age: int # u64
    favorite_number: Optional[int]


# set/get classmethods are defined
User.save(User(...))
user = User.get(6)

# can do atomic:
with db.atomic() as txn:
    User.set(User(...), txn=txn)
    User.set(User(...), txn=txn)
    user = User.get(5, txn=txn)

```

## How it works:
There is one "main" implicit B+ that encodes the current schema.
this is mostly hidden from the user, and serves only as metadata. (however user can still obviously inspect the metadata and stuff)

Then, each @Table entry get's it's own b+ tree. Hash the fields by exact name and exact type.
If schema is changed -> a new table is created; old table is made unable to be accessed.
So for example:
```py
# day 1:
@db.Table
class User:
    id: int; foo: str
# db {
#     schema(User, (id=int, foo=str))
# }
```
```py
# day 2:
# we change the User table;
@db.Table
class User:
    id: int
    foo: int; bar: int
# db {
# schema(User, (id=int, foo=str))
# schema(User, (id=int, foo=int, bar=int))
# }
```
This makes it very easy and clear to see orphaned data.
However, it means that users will need to be much more aware of migrations. More on that below.


Use ctypes under the hood so reading/writing from the mmap'ed memory is zero overhead.


## Indexing:
No built in special DB indexing.
Users maintain their own references using primary-keys.


## Migrations:
DB migrations are the tricky bit: None of it is automatic; it's all implicit.
This makes it slightly harder for the user; but it also makes it WAY clearer what's actually happening.
We also expose a classmethod, `MyTable.migrate_orphan_tables()`.
This collects all schema-tables that are called `MyTable`, then sweeps all entries in orphaned tables to do a "best attempt" at migrating stuff over.
Maybe we could pass values into args (callback handling orphaned vals, another callback handling new vals, and a final callback handling change in type for a field?)


## IDEOLOGY:
- simplicity is best
- less lines of code is better
- atomicity is OFF by default; user can bundle writes together if they want.
- dont need double fsyncs, keep it fast
- database should NEVER be able to be corrupted

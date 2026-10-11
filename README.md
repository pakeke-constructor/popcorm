# popcORM

A simple key-value ORM database using LMDB under the hood.

## API:

```py
import popcorm


db = popcorm.DB("file.db")


@db.Bucket
class User:
    id: int  # special reserved field, used as the primary key
    age: int


User.save(User(id=5, age=30))

user = User.get(5)

assert User.get(6) is None
assert db.get_bucket("User") is User
```

Values are checked when assigned. Integers must fit into a signed 64-bit value.

```py
user = User(id=1, age=20)
user.age = 30
User.save(user)
```

`str`, `Optional`, custom field types, and explicit atomic transactions are planned, but are not part of the current API yet. The intended transaction API is:

```py
with db.atomic() as txn:
    User.save(User(id=1, age=20), txn=txn)
    User.save(User(id=2, age=30), txn=txn)
    user = User.get(1, txn=txn)
```

## How it works

There is an extra named database called `schema` that stores schema metadata. Each `@db.Bucket` gets its own B+ tree, named `Name.{integer}`.

The exact field names and types are stored in the `schema` database. If a schema changes, a new bucket is created and the old bucket is no longer accessed by that class. If the schema changes back to an old one, the old bucket is reused.

For example:

```py
# User.0
@db.Bucket
class User:
    id: int
    age: int
```

Changing the schema creates another bucket:

```py
# User.1
@db.Bucket
class User:
    id: int
    score: int
```

Changing it back to `id` and `age` reuses `User.0`. This makes orphaned data easy to see and keeps migrations explicit.

Rows are flat `ctypes.Structure` values. `get()` currently copies a record out of LMDB's memory map because that memory is only valid while the read transaction is open. True zero-copy views will be possible when the caller can keep an explicit atomic transaction open.

## Indexing
No special built-in indexing. Users maintain their own references using primary keys.

## Migrations
Migrations are intentionally not automatic. This makes more work for the user, but makes it much clearer what is actually happening to orphaned schemas.

A helper for migrating orphaned buckets is planned.

## Project goals
- Simplicity is best.
- Keep the implementation small and readable.
- Atomicity is off by default. Users can bundle writes when they need to.
- The database should never be able to be corrupted.

Most of the implementation lives in `popcorm.py`. Tests are in `tests.py`, and benchmarks belong in `benchmark.py`.

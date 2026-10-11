
# popcORM:
A simple key-value ORM db using LMDB under the hood.


## Architecture:
- popcorm.py
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

@popcorm.Table
class User:
    id: str # `id` is a special reserved field, the primary key.
    name: str
    age: int # u64
    favorite_number: Optional[int]


# set/get classmethods are defined
User.save(User(...))
user = User.get(6)

# can do atomic:
with popcorm.atomic() as txn:
    User.set(User(...), txn=txn)
    User.set(User(...), txn=txn)
    user = User.get(5, txn=txn)

```

## How it works:
There is one "main" implicit B+ that encodes the current schema.
this is mostly hidden from the user, and serves only as metadata. (however user can still obviously inspect the metadata and stuff)
Eg
Then, each @Table entry get's it's own b+ tree. Hash the fields by exact name and exact type.
If schema is changed -> 


## IDEOLOGY:
- simplicity is best
- less lines of code is better
- atomicity is OFF by default; user can bundle writes together if they want.
- dont need double fsyncs, keep it fast
- database should NEVER be able to be corrupted

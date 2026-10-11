import os, tempfile, popcorm


def make_db():
    return popcorm.DB(os.path.join(tempfile.mkdtemp(), "t.db"))


def test_save_get():
    db = make_db()

    @db.Bucket
    class User:
        id: int
        age: int

    User.save(User(id=5, age=30))
    User.save(User(id=-5, age=-1))
    assert User.get(5).age == 30
    assert User.get(-5).age == -1
    assert User.get(6) is None
    assert db.get_bucket("User") is User


def test_schema_versions():
    db = make_db()

    class V0:
        id: int
        age: int

    class V1:
        id: int
        score: int

    V0.__name__ = V1.__name__ = "User"
    U0 = db.Bucket(V0)
    U0.save(U0(id=1, age=2))
    assert db.Bucket(V1).get(1) is None
    assert db.Bucket(V0).get(1).age == 2  # old schema reuses old bucket
    with db.env.begin() as t:
        assert list(t.cursor(db.schema)) == [(b"User.0", b"id:i64,age:i64"), (b"User.1", b"id:i64,score:i64")]


def test_rejects_non_int():
    db = make_db()
    try:
        @db.Bucket
        class User:
            id: int
            name: str
    except TypeError:
        return
    assert False


def test_is_valid_on_assign():
    db = make_db()

    @db.Bucket
    class User:
        id: int
        age: int

    for bad in [lambda: User(id=1, age=2**63), lambda: User(1, "x"), lambda: setattr(User(id=1), "age", -2**63 - 1)]:
        try:
            bad()
        except ValueError:
            continue
        assert False


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    print("ok")

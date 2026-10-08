"""The short-term store that holds replies and songs for a few minutes."""

from hum.engine.talk.store import KEEP_SECONDS, ShortTermStore


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_keeps_things_for_a_few_minutes():
    clock = Clock()
    store = ShortTermStore(keep_at_most=10, clock=clock)
    item_id = store.put("hello")
    clock.now = KEEP_SECONDS - 1
    assert store.get(item_id) == "hello"
    clock.now = KEEP_SECONDS + 1
    assert store.get(item_id) is None


def test_forgets_the_oldest_when_full():
    store = ShortTermStore(keep_at_most=2, clock=Clock())
    first, second, third = store.put(1), store.put(2), store.put(3)
    assert (store.get(first), store.get(second), store.get(third)) == (None, 2, 3)


def test_ids_are_unguessable():
    store = ShortTermStore(keep_at_most=10)
    assert len({store.put("x") for _ in range(50)}) == 50
    assert store.get("0") is None

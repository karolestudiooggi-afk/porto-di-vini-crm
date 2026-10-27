from sync.state import DEFAULT_STATE, SyncStateStore


def test_state_round_trip(tmp_path):
    store = SyncStateStore(str(tmp_path / "state.json"))
    state = store.reset()
    state["contacts"]["next_page"] = 3
    state["contacts"]["processed"] = 200
    store.save(state)

    assert store.load()["contacts"] == {"next_page": 3, "processed": 200}


def test_state_merge_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"contacts":{"next_page":2}}')

    loaded = SyncStateStore(str(path)).load()

    assert loaded["contacts"] == {"next_page": 2, "processed": 0}
    assert loaded["labels"] == DEFAULT_STATE["labels"]

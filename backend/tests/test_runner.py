import pytest

from sync.runner import SyncRunner
from sync.state import SyncStateStore


class FakeLabelsClient:
    def __init__(self, *, fail_label_id: int | None = None):
        self.fail_label_id = fail_label_id

    def fetch_all_labels(self):
        return [
            {"id": 1, "name": "VIP"},
            {"id": 2, "name": "NEWSLETTER"},
        ]

    def iter_contacts_by_label_pages(self, label_id, *, start_page=1, max_items=None):
        assert start_page == 1
        assert max_items is None
        if label_id == 1:
            yield 1, [{"user_ns": "u2"}, {"user_ns": "u1"}]
            yield 2, [{"user_ns": "u1"}]
            return
        if self.fail_label_id == label_id:
            raise RuntimeError("falha simulada na API")
        yield 1, [{"user_ns": "u3"}]


def test_labels_sao_lidas_antes_da_substituicao_atomica(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "sync.runner.replace_all_labels",
        lambda assignments: calls.append(assignments),
    )
    store = SyncStateStore(str(tmp_path / "state.json"))
    runner = SyncRunner(FakeLabelsClient(), store)

    processed = runner.run_labels()

    assert processed == 3
    assert calls == [{"VIP": ["u1", "u2"], "NEWSLETTER": ["u3"]}]
    assert store.load()["labels"] == {
        "label_index": 2,
        "next_page": 1,
        "processed": 3,
    }


def test_falha_na_api_nao_toca_nas_etiquetas_do_banco(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "sync.runner.replace_all_labels",
        lambda assignments: calls.append(assignments),
    )
    runner = SyncRunner(
        FakeLabelsClient(fail_label_id=2),
        SyncStateStore(str(tmp_path / "state.json")),
    )

    with pytest.raises(RuntimeError, match="falha simulada"):
        runner.run_labels()

    assert calls == []

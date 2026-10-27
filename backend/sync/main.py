"""Entrypoint do sync diário Domani -> `crm.contatos`."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from sync.domani_client import DomaniClient
from sync.runner import SyncRunner
from sync.state import SyncStateStore


def _optional_positive_int(name: str) -> int | None:
    raw = os.getenv(name)
    if not raw:
        return None
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} deve ser maior que zero")
    return value


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv()
    logger = logging.getLogger(__name__)

    max_items = _optional_positive_int("DOMANI_SYNC_LIMIT")
    include_labels = os.getenv("DOMANI_INCLUDE_LABELS", "true").lower() == "true"
    reset_state = os.getenv("DOMANI_RESET_STATE", "true").lower() == "true"

    if max_items is not None and include_labels:
        include_labels = False
        logger.warning(
            "DOMANI_SYNC_LIMIT=%s: etiquetas puladas para evitar reconciliação parcial.",
            max_items,
        )

    store = SyncStateStore()
    if reset_state:
        store.reset()

    with DomaniClient() as client:
        runner = SyncRunner(client, store, max_items=max_items)
        contacts = runner.run_contacts()
        labels = 0
        if include_labels:
            logger.info("Lendo todas as etiquetas antes da reconciliação atômica.")
            labels = runner.run_labels()

    print(f"Sync Domani concluído. contatos={contacts} etiquetas={labels}")


if __name__ == "__main__":
    run()

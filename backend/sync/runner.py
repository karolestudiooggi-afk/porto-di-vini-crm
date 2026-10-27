"""Orquestra contatos e etiquetas com checkpoint por página."""

from __future__ import annotations

import logging

from sync.db import replace_all_labels, upsert_contacts
from sync.domani_client import DomaniClient
from sync.state import SyncStateStore
from sync.transformers import normalize_contact

logger = logging.getLogger(__name__)


class SyncRunner:
    def __init__(
        self,
        client: DomaniClient,
        state_store: SyncStateStore,
        *,
        max_items: int | None = None,
    ) -> None:
        self.client = client
        self.state_store = state_store
        self.max_items = max_items
        self.state = state_store.load()

    def run_contacts(self) -> int:
        processed = self.state["contacts"]["processed"]
        start_page = self.state["contacts"]["next_page"]
        remaining = self._remaining(processed)
        logger.info("Contatos a partir da página %s.", start_page)

        for page, raw_items in self.client.iter_contact_pages(
            start_page=start_page,
            max_items=remaining,
        ):
            normalized = [
                normalize_contact(self.client.raw_to_contact(raw))
                for raw in raw_items
            ]
            written = upsert_contacts(normalized)
            processed += written
            self.state["contacts"]["processed"] = processed
            self.state["contacts"]["next_page"] = page + 1
            self.state_store.save(self.state)
            logger.info(
                "Página %s: %s contato(s) gravado(s), total=%s.",
                page,
                written,
                processed,
            )
            if written != len(normalized):
                logger.warning(
                    "Página %s: recebidos=%s, gravados=%s.",
                    page,
                    len(normalized),
                    written,
                )
            if self._remaining(processed) == 0:
                break

        return processed

    def run_labels(self) -> int:
        """Lê todas as associações antes de substituir as etiquetas no banco.

        A fase de leitura não altera o banco. Só depois de todas as páginas da API
        responderem com sucesso o reset e os sets rodam em uma única transação.
        """
        labels = self.client.fetch_all_labels()
        logger.info("Etiquetas disponíveis: %s.", len(labels))
        assignments: dict[str, set[str]] = {}
        processed = 0

        for label in labels:
            label_id = label.get("id")
            label_name = label.get("name") or ""
            if label_id is None or not label_name:
                continue

            members = assignments.setdefault(label_name, set())
            for page, raw_items in self.client.iter_contacts_by_label_pages(
                int(label_id),
                start_page=1,
            ):
                user_ns_list = {
                    item.get("user_ns")
                    for item in raw_items
                    if item.get("user_ns")
                }
                members.update(user_ns_list)
                logger.info(
                    "Etiqueta %r, página %s: %s contato(s).",
                    label_name,
                    page,
                    len(user_ns_list),
                )

        normalized = {
            label_name: sorted(user_ns_list)
            for label_name, user_ns_list in assignments.items()
        }
        processed = sum(len(user_ns_list) for user_ns_list in normalized.values())
        replace_all_labels(normalized)
        self.state["labels"] = {
            "label_index": len(labels),
            "next_page": 1,
            "processed": processed,
        }
        self.state_store.save(self.state)
        return processed

    def _remaining(self, processed: int) -> int | None:
        if self.max_items is None:
            return None
        return max(self.max_items - processed, 0)

"""Cliente da API Domani com paginação e rate-limit defensivo."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Contato:
    user_ns: str
    user_id: str | None = None
    channel: str | None = None
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    locale: str | None = None
    language: str | None = None
    profile_pic: str | None = None
    status: str | None = None
    subscribed: str | None = None
    last_interaction: str | None = None
    last_message_at: str | None = None
    last_message_type: str | None = None
    opt_in_email: Any = None
    opted_in_email: Any = None
    opted_in_through: str | None = None
    tags: list[str] = field(default_factory=list)
    user_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DomaniAPIError(Exception):
    """Erro de comunicação ou contrato da API Domani."""


class DomaniClient:
    DEFAULT_PAGE_SIZE = 100
    MAX_PAGES = 1000
    CONTACTS_PATH = "/subscribers"
    LABELS_PATH = "/team/labels"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 6,
        retry_backoff: float = 1.0,
        request_interval: float = 0.75,
    ) -> None:
        api_url = api_url or os.environ["DOMANI_API_URL"]
        api_key = api_key or os.environ["DOMANI_API_KEY"]
        if not api_url or not api_key:
            raise ValueError("api_url e api_key são obrigatórios")

        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.request_interval = request_interval

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DomaniClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _get(self, path: str, params: dict | None = None) -> dict:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._client.get(path, params=params or {})
                time.sleep(self.request_interval)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else max(
                        5.0,
                        self.retry_backoff * (2 ** (attempt - 1)),
                    )
                    raise httpx.HTTPStatusError(
                        f"Erro 429 em {path}; retry em {wait:.1f}s",
                        request=response.request,
                        response=response,
                    )
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Erro {response.status_code} em {path}",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise DomaniAPIError(f"Resposta inválida em GET {path}")
                return payload
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                wait = self.retry_backoff * (2 ** (attempt - 1))
                if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                    if exc.response.status_code == 429:
                        retry_after = exc.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait = float(retry_after)
                            except ValueError:
                                wait = max(wait, 5.0)
                        else:
                            wait = max(wait, 5.0)
                logger.warning(
                    "Tentativa %d/%d falhou em GET %s: %s; retry em %.1fs",
                    attempt,
                    self.max_retries,
                    path,
                    exc,
                    wait,
                )
                time.sleep(wait)

        raise DomaniAPIError(
            f"Falha após {self.max_retries} tentativas em GET {path}: {last_exc}"
        ) from last_exc

    def _iter_pages(
        self,
        path: str,
        params: dict | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_page: int = 1,
        max_items: int | None = None,
    ) -> Iterator[tuple[int, list[dict]]]:
        params = dict(params or {})
        params["limit"] = page_size
        yielded = 0

        for page in range(start_page, self.MAX_PAGES + 1):
            params["page"] = page
            payload = self._get(path, params=params)
            items = payload.get("data") or []
            if not isinstance(items, list):
                raise DomaniAPIError(f"Campo data inválido em GET {path}, página {page}")
            if not items:
                return
            if max_items is not None:
                remaining = max_items - yielded
                if remaining <= 0:
                    return
                items = items[:remaining]
            yield page, items
            yielded += len(items)
            if max_items is not None and yielded >= max_items:
                return
            if len(items) < page_size:
                return

        raise DomaniAPIError(
            f"Paginação excedeu o limite de {self.MAX_PAGES} páginas em {path}"
        )

    def _paginate(
        self,
        path: str,
        params: dict | None = None,
        *,
        start_page: int = 1,
        max_items: int | None = None,
    ) -> Iterator[dict]:
        for _, items in self._iter_pages(
            path,
            params=params,
            start_page=start_page,
            max_items=max_items,
        ):
            yield from items

    def fetch_all_labels(self) -> list[dict]:
        return list(self._paginate(self.LABELS_PATH))

    def iter_contact_pages(
        self,
        *,
        start_page: int = 1,
        max_items: int | None = None,
    ) -> Iterator[tuple[int, list[dict]]]:
        yield from self._iter_pages(
            self.CONTACTS_PATH,
            start_page=start_page,
            max_items=max_items,
        )

    def iter_contacts_by_label_pages(
        self,
        label_id: int,
        *,
        start_page: int = 1,
        max_items: int | None = None,
    ) -> Iterator[tuple[int, list[dict]]]:
        yield from self._iter_pages(
            self.CONTACTS_PATH,
            params={"label_id": label_id},
            start_page=start_page,
            max_items=max_items,
        )

    @staticmethod
    def _parse_user_field_value(value: Any, var_type: str | None) -> Any:
        if value is None or value == "":
            return None
        if var_type == "number":
            try:
                raw = str(value)
                return float(raw) if "." in raw else int(raw)
            except (TypeError, ValueError):
                return value
        if var_type == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("true", "1", "yes")
        if var_type == "array":
            if isinstance(value, (list, dict)):
                return value
            try:
                return json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return value
        return value

    def raw_to_contact(self, raw: dict) -> Contato:
        user_fields: dict[str, Any] = {}
        for user_field in raw.get("user_fields") or []:
            name = user_field.get("name")
            if not name:
                continue
            user_fields[name] = self._parse_user_field_value(
                user_field.get("value"),
                user_field.get("var_type"),
            )

        tag_names = [
            tag.get("name", "")
            for tag in (raw.get("tags") or [])
            if isinstance(tag, dict) and tag.get("name")
        ]

        return Contato(
            user_ns=raw.get("user_ns") or "",
            user_id=raw.get("user_id"),
            channel=raw.get("channel"),
            name=raw.get("name"),
            first_name=raw.get("first_name"),
            last_name=raw.get("last_name"),
            phone=raw.get("phone"),
            email=raw.get("email"),
            gender=raw.get("gender"),
            locale=raw.get("locale"),
            language=raw.get("language"),
            profile_pic=raw.get("profile_pic"),
            status=raw.get("status"),
            subscribed=raw.get("subscribed"),
            last_interaction=raw.get("last_interaction"),
            last_message_at=raw.get("last_message_at"),
            last_message_type=raw.get("last_message_type"),
            opt_in_email=raw.get("opt_in_email"),
            opted_in_email=raw.get("opted_in_email"),
            opted_in_through=raw.get("opted_in_through"),
            tags=tag_names,
            user_fields=user_fields,
        )

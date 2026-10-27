"""Transforma campos nativos do Domani no contrato de `crm.contatos`."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from dateutil import parser as date_parser

from sync.domani_client import Contato


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_datetime(value: Any) -> datetime | None:
    raw = text_or_none(value)
    if raw is None:
        return None
    try:
        return date_parser.isoparse(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value in (0, 1):
            return bool(value)
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "sim"}:
        return True
    if normalized in {"false", "0", "no", "nao", "não"}:
        return False
    return None


def normalize_text_array(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        normalized = value
        for separator in (";", "|"):
            normalized = normalized.replace(separator, ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value).strip()
    return [normalized] if normalized else []


def resolve_nome(native: dict[str, Any]) -> str | None:
    full_name = text_or_none(native.get("name"))
    if full_name:
        return full_name
    first = text_or_none(native.get("first_name")) or ""
    last = text_or_none(native.get("last_name")) or ""
    if first and first == last:
        return first
    composed = " ".join(part for part in (first, last) if part)
    return composed or None


def resolve_telefone(native: dict[str, Any]) -> str | None:
    """Nunca interpreta identificador de rede social como telefone."""
    channel = (text_or_none(native.get("channel")) or "").lower()
    phone = text_or_none(native.get("phone"))
    user_id = text_or_none(native.get("user_id"))
    if channel.startswith("waapi") or channel.startswith("whatsapp"):
        return user_id or phone
    return phone


def normalize_contact(contact: Contato) -> dict[str, Any]:
    native = contact.to_dict()
    return {
        "user_ns": text_or_none(contact.user_ns),
        "domani_user_id": text_or_none(contact.user_id),
        "canal": text_or_none(contact.channel),
        "telefone": resolve_telefone(native),
        "email": text_or_none(contact.email),
        "nome": resolve_nome(native),
        "primeiro_nome": text_or_none(contact.first_name),
        "sobrenome": text_or_none(contact.last_name),
        "genero": text_or_none(contact.gender),
        "locale": text_or_none(contact.locale),
        "idioma": text_or_none(contact.language),
        "url_foto_perfil": text_or_none(contact.profile_pic),
        "status": text_or_none(contact.status),
        "subscribed": parse_datetime(contact.subscribed),
        "last_interaction": parse_datetime(contact.last_interaction),
        "last_message_at": parse_datetime(contact.last_message_at),
        "last_message_type": text_or_none(contact.last_message_type),
        "opt_in_email": parse_bool(contact.opt_in_email),
        "opted_in_email": parse_bool(contact.opted_in_email),
        "opted_in_through": text_or_none(contact.opted_in_through),
        "tags": normalize_text_array(contact.tags),
        "origem": "Domani",
    }

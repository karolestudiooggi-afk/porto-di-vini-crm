from datetime import datetime, timezone

from sync.domani_client import Contato
from sync.transformers import (
    normalize_contact,
    parse_bool,
    parse_datetime,
    resolve_nome,
    resolve_telefone,
)


def _instagram_contact(**overrides) -> Contato:
    base = {
        "user_ns": "f000000u123",
        "user_id": "17841400000000000",
        "channel": "instagram",
        "name": "Cliente Exemplo",
        "first_name": "Cliente",
        "last_name": "Exemplo",
        "phone": None,
        "email": None,
        "language": "pt",
        "status": "subscribed",
        "subscribed": "2026-08-01T10:00:00Z",
        "last_interaction": "2026-08-14T12:30:00Z",
        "last_message_at": "2026-08-14T12:30:00Z",
        "last_message_type": "text",
        "tags": ["cliente"],
    }
    base.update(overrides)
    return Contato(**base)


def test_instagram_user_id_nao_vira_telefone():
    assert resolve_telefone(
        {"channel": "instagram", "user_id": "178414000", "phone": None}
    ) is None


def test_whatsapp_user_id_pode_ser_telefone():
    assert resolve_telefone(
        {"channel": "waapi", "user_id": "5521999999999", "phone": None}
    ) == "5521999999999"


def test_nome_prefere_name_nativo():
    assert resolve_nome(
        {"name": "Nome público", "first_name": "Nome", "last_name": "Completo"}
    ) == "Nome público"


def test_nome_compoe_first_last_quando_name_vazio():
    assert resolve_nome(
        {"name": "", "first_name": "Nome", "last_name": "Completo"}
    ) == "Nome Completo"


def test_parse_datetime_iso():
    assert parse_datetime("2026-08-14T12:30:00Z") == datetime(
        2026, 8, 14, 12, 30, tzinfo=timezone.utc
    )
    assert parse_datetime("inválida") is None


def test_parse_bool_domani():
    assert parse_bool(True) is True
    assert parse_bool("false") is False
    assert parse_bool("1") is True
    assert parse_bool(None) is None
    assert parse_bool("talvez") is None


def test_normaliza_campos_nativos_cliente_exemplo():
    normalized = normalize_contact(_instagram_contact())

    assert normalized == {
        "user_ns": "f000000u123",
        "domani_user_id": "17841400000000000",
        "canal": "instagram",
        "telefone": None,
        "email": None,
        "nome": "Cliente Exemplo",
        "primeiro_nome": "Cliente",
        "sobrenome": "Exemplo",
        "genero": None,
        "locale": None,
        "idioma": "pt",
        "url_foto_perfil": None,
        "status": "subscribed",
        "subscribed": datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        "last_interaction": datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc),
        "last_message_at": datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc),
        "last_message_type": "text",
        "opt_in_email": None,
        "opted_in_email": None,
        "opted_in_through": None,
        "tags": ["cliente"],
        "origem": "Domani",
    }


def test_valor_vazio_nao_apaga_identidade_com_none():
    normalized = normalize_contact(
        _instagram_contact(name=" ", first_name=" ", last_name=" ", email=" ")
    )
    assert normalized["nome"] is None
    assert normalized["email"] is None

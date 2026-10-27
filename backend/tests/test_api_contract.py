import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.auth import _decode
from app.config import settings
from app.main import app
from app.routers.contatos import _build_filters
from sync.db import UPSERT_CONTACT_SQL


@pytest.mark.asyncio
async def test_health_e_openapi_expostos_sem_banco():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        openapi = await client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert openapi.status_code == 200


def test_openapi_documenta_rotas_iniciais():
    paths = app.openapi()["paths"]
    esperadas = {
        "/health",
        "/usuarios/me",
        "/usuarios",
        "/auditoria",
        "/contatos",
        "/contatos/stats",
        "/contatos/filtros",
        "/contatos/import",
        "/contatos/export",
        "/contatos/{contato_id}",
        "/contatos/{contato_id}/timeline",
        "/dashboard/resumo",
        "/dashboard/distribuicoes",
        "/dashboard/atividade",
    }
    assert esperadas <= set(paths)
    assert "delete" in paths["/contatos/{contato_id}"]
    assert "post" in paths["/contatos/import"]


def test_openapi_marca_rotas_protegidas_com_bearer():
    operations = app.openapi()["paths"]["/contatos"]
    assert operations["get"]["security"] == [{"HTTPBearer": []}]


def test_filtros_usam_parametros_e_nao_interpolam_busca():
    filtros = _build_filters(
        busca="Ana",
        canal="instagram",
        tags=["vip"],
        com_email=True,
        com_telefone=False,
    )
    assert "Ana" not in filtros.sql
    assert "deleted_at IS NULL" in filtros.sql
    assert filtros.args == ["%Ana%", "%Ana%", "%Ana%", "%Ana%", "instagram", ["vip"]]
    assert "tags_manuais" in filtros.sql
    assert "email_norm IS NOT NULL" in filtros.sql
    assert "telefone_norm IS NULL" in filtros.sql


def test_decode_valida_jwt_hs256(monkeypatch):
    secret = "segredo-de-teste-com-mais-de-32-bytes"
    monkeypatch.setattr(settings, "supabase_jwt_secret", secret)
    token = jwt.encode(
        {"sub": "123", "email": "dev@example.com"},
        secret,
        algorithm="HS256",
    )
    assert _decode(token)["sub"] == "123"


def test_decode_rejeita_assinatura_invalida(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "segredo-correto-com-mais-de-32-bytes")
    token = jwt.encode(
        {"sub": "123"},
        "outro-segredo-com-mais-de-32-bytes",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        _decode(token)
    assert exc.value.status_code == 401


def test_sync_vincula_por_email_e_so_reativa_com_nova_atividade():
    assert "candidate_by_email" in UPSERT_CONTACT_SQL
    assert "email_norm = crm.fn_email_norm(%(email)s)" in UPSERT_CONTACT_SQL
    assert "GREATEST(" in UPSERT_CONTACT_SQL
    assert "deleted_at = CASE" in UPSERT_CONTACT_SQL

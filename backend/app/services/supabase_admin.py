"""Criação de conta no Supabase Auth pela service role.

Usado só no aceite do convite: a pessoa define a senha e a conta nasce já
confirmada, sem depender do e-mail de confirmação do Supabase (que exige SMTP
configurado lá dentro — e o nosso SMTP está aqui, não lá).

A service role é chave de superusuário: ela ignora RLS e pode tudo. Por isso
nunca sai do backend e não aparece em nenhuma resposta.
"""

import httpx

from app.config import settings


class ErroSupabase(Exception):
    pass


async def criar_usuario(email: str, senha: str) -> str:
    """Cria a conta e devolve o id. Se já existir, devolve o id existente."""
    if not settings.supabase_service_role_key:
        raise ErroSupabase("SUPABASE_SERVICE_ROLE_KEY não configurada.")

    base = settings.supabase_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post(
            f"{base}/auth/v1/admin/users",
            headers=headers,
            json={"email": email, "password": senha, "email_confirm": True},
        )
        if r.status_code in (200, 201):
            return r.json()["id"]

        # 422 = e-mail já cadastrado. Acontece quando a pessoa foi criada à mão
        # antes do convite; buscamos o id em vez de falhar.
        if r.status_code == 422:
            existente = await _buscar_por_email(cli, base, headers, email)
            if existente:
                await cli.put(
                    f"{base}/auth/v1/admin/users/{existente}",
                    headers=headers,
                    json={"password": senha, "email_confirm": True},
                )
                return existente

        raise ErroSupabase(f"Falha ao criar a conta ({r.status_code}).")


async def _buscar_por_email(cli, base: str, headers: dict, email: str) -> str | None:
    r = await cli.get(
        f"{base}/auth/v1/admin/users", headers=headers, params={"page": 1, "per_page": 200}
    )
    if r.status_code != 200:
        return None
    for u in r.json().get("users", []):
        if (u.get("email") or "").lower() == email.lower():
            return u["id"]
    return None

"""Upload de imagem para o editor de e-mail.

O CRM não guarda arquivo: ele usa o Storage do próprio Supabase, que já está no
servidor. A imagem precisa de URL pública porque quem vai buscá-la é o cliente de
e-mail do destinatário — que não tem sessão nem token nenhum.
"""

import logging
import mimetypes
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BUCKET = "email-assets"

# Só imagem, e só formato que cliente de e-mail renderiza. SVG fica de fora de
# propósito: aceita script embutido e nem todo cliente mostra.
TIPOS_OK = {"image/png", "image/jpeg", "image/gif", "image/webp"}
TAMANHO_MAX = 5 * 1024 * 1024  # 5 MB — acima disso o e-mail fica pesado demais


class ErroUpload(Exception):
    pass


async def _garantir_bucket(cliente: httpx.AsyncClient, headers: dict) -> None:
    """Cria o bucket público na primeira vez. Idempotente."""
    r = await cliente.post(
        f"{settings.supabase_url}/storage/v1/bucket",
        headers=headers,
        json={"id": BUCKET, "name": BUCKET, "public": True},
    )
    # 409 = já existe, que é o caso normal a partir do segundo upload.
    if r.status_code not in (200, 201, 409):
        logger.warning("Bucket não criado (%s): %s", r.status_code, r.text[:200])


async def enviar_imagem(conteudo: bytes, nome: str, tipo: str) -> str:
    """Sobe a imagem e devolve a URL pública."""
    if tipo not in TIPOS_OK:
        raise ErroUpload(
            "Formato não aceito. Use PNG, JPG, GIF ou WEBP — são os que os "
            "clientes de e-mail exibem de forma confiável."
        )
    if len(conteudo) > TAMANHO_MAX:
        raise ErroUpload("Imagem acima de 5 MB. Reduza antes de subir.")
    if not settings.supabase_service_role_key:
        raise ErroUpload("Storage não configurado (falta SUPABASE_SERVICE_ROLE_KEY).")

    ext = mimetypes.guess_extension(tipo) or ".bin"
    caminho = f"{uuid.uuid4().hex}{ext}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }

    async with httpx.AsyncClient(timeout=30) as cliente:
        await _garantir_bucket(cliente, headers)
        r = await cliente.post(
            f"{settings.supabase_url}/storage/v1/object/{BUCKET}/{caminho}",
            headers={**headers, "Content-Type": tipo},
            content=conteudo,
        )
        if r.status_code not in (200, 201):
            raise ErroUpload(f"Falha ao subir a imagem ({r.status_code}).")

    return f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{caminho}"

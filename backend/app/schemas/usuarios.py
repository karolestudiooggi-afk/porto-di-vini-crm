from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UsuarioMe(BaseModel):
    id: str
    email: str
    papel: str
    permissoes: list[str]


class Usuario(BaseModel):
    id: str
    nome: str | None
    email: str
    papel: str
    status: str
    ultimo_acesso: datetime | None


class AuditoriaItem(BaseModel):
    id: int
    usuario_id: str | None
    acao: str
    recurso: str
    detalhe: dict | None
    created_at: datetime


class ConviteIn(BaseModel):
    email: EmailStr
    papel: str


class ConviteOut(BaseModel):
    id: int
    email: str
    papel: str
    status: str
    created_at: datetime
    expira_em: datetime


class UsuarioPatch(BaseModel):
    """Só papel e status. Nome e e-mail vêm do Auth e não se editam por aqui."""

    papel: str | None = None
    status: str | None = Field(default=None, pattern="^(ativo|inativo)$")

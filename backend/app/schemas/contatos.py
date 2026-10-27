from datetime import datetime

from pydantic import BaseModel, Field


class ContatoListItem(BaseModel):
    id: int
    nome: str | None
    telefone: str | None
    email: str | None
    canal: str | None
    status: str | None
    origem: str | None
    tags: list[str]
    etiquetas: list[str]
    last_interaction: datetime | None
    url_foto_perfil: str | None


class ContatoDetail(ContatoListItem):
    telefone_norm: str | None
    email_norm: str | None
    user_ns: str | None
    domani_user_id: str | None
    origens: list[str]
    tags_domani: list[str]
    tags_manuais: list[str]
    primeiro_nome: str | None
    sobrenome: str | None
    genero: str | None
    locale: str | None
    idioma: str | None
    subscribed: datetime | None
    last_message_at: datetime | None
    last_message_type: str | None
    opt_in_email: bool | None
    opted_in_email: bool | None
    opted_in_through: str | None
    observacoes: str | None
    domani_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ContatoStats(BaseModel):
    total: int
    com_telefone: int
    com_email: int
    com_interacao: int
    com_opt_in_email: int


class ContatoFiltros(BaseModel):
    canais: list[str]
    status: list[str]
    origens: list[str]
    idiomas: list[str]
    tags: list[str]
    etiquetas: list[str]


class ContatoPatch(BaseModel):
    observacoes: str | None = Field(default=None, max_length=10_000)


class TimelineItem(BaseModel):
    quando: datetime
    fonte: str
    tipo: str
    descricao: str


class ImportReport(BaseModel):
    total_linhas: int
    criados: int
    atualizados: int
    restaurados: int
    ignorados: int
    erros: list[str]

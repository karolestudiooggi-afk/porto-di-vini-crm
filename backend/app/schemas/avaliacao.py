"""Schemas do módulo de avaliação/NPS."""

from datetime import datetime

from pydantic import BaseModel, Field


class AvaliacaoIn(BaseModel):
    """Payload que o cliente final envia da tela pública /avaliar/{slug}."""
    slug: str
    nota: int = Field(ge=1, le=5)
    comentario: str = ""
    nome: str | None = None
    whatsapp: str | None = None
    # quem atendeu (opcional): permite o NPS por colaborador, que é o corte que
    # importa numa barbearia — a nota é do profissional, não só da unidade.
    colaborador: str | None = None


class AvaliacaoOut(BaseModel):
    """Resposta ao cliente: para onde mandar (Google se promotor, senão obrigado)."""
    ok: bool
    categoria: str            # promotor|neutro|detrator
    rota: str                 # google|obrigado
    google_url: str | None = None


class ContaPublica(BaseModel):
    """Dados da unidade que a tela pública pode ver (sem webhook/google).

    `colaboradores` alimenta o seletor "quem te atendeu?": lista fechada em vez de
    campo livre, senão o nome vem sujo e o NPS por profissional não agrupa.
    """
    slug: str
    nome: str
    colaboradores: list[str] = []


class RespostaItem(BaseModel):
    id: str
    slug: str
    nota: int
    categoria: str
    comentario: str
    nome: str | None
    whatsapp: str | None
    colaborador: str | None = None
    created_at: datetime


class UnidadeNps(BaseModel):
    slug: str
    nome: str
    nps: int
    total: int
    promotores: int
    neutros: int
    detratores: int


class ColaboradorNps(BaseModel):
    """NPS por profissional — o corte que interessa numa barbearia."""
    colaborador: str
    nps: int
    total: int
    promotores: int
    neutros: int
    detratores: int


class NpsResumo(BaseModel):
    """Painel de gestão: NPS geral + distribuição + por unidade + últimas respostas."""
    nps: int
    total: int
    promotores: int
    neutros: int
    detratores: int
    por_unidade: list[UnidadeNps]
    por_colaborador: list[ColaboradorNps]
    ultimas: list[RespostaItem]

"""Entradas do módulo de integrações (iFood e Google Meu Negócio).

As saídas são dicionários montados nos routers — o formato comum de uma
avaliação está documentado em `frontend/src/lib/api-types.ts` (AvaliacaoExterna).
"""

from typing import Literal

from pydantic import BaseModel, Field

Origem = Literal["ifood", "google"]


class ConfigPatch(BaseModel):
    ativo: bool | None = None
    modo: Literal["manual", "automatico"] | None = None
    tom: str | None = Field(default=None, max_length=300)
    assinatura: str | None = Field(default=None, max_length=120)
    prompt: str | None = Field(default=None, max_length=8000)
    nota_minima: int | None = Field(default=None, ge=1, le=5)
    webhook_url: str | None = Field(default=None, max_length=500)
    # Chave e modelo da OpenAI NÃO entram aqui: ficam só no .env do servidor
    # (OPENAI_API_KEY, OPENAI_MODEL). Nenhuma chave de API passa pela tela.
    observacoes: str | None = Field(default=None, max_length=4000)


# As lojas/unidades são cadastradas no servidor (migration SQL), não pela tela:
# a API só as lista. Ver backend/sql/017_lojas_no_servidor.sql.


class RespostaIn(BaseModel):
    # Sem limite de tamanho aqui, de propósito: no iFood o texto segue como
    # está e quem valida é a API (ver ifood.responder_sem_validar).
    texto: str = ""

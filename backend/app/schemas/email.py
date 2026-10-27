"""Contrato do módulo de e-mail."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

#: Cada aba do e-mail. "clientes" é a base de crm.contatos; "parceiros" é a base
#: de email.parceiros, com remetente próprio. (Não confundir com `publico`, que
#: na campanha é a CONTAGEM de destinatários.)
Lista = Literal["clientes", "parceiros"]


class TemplateIn(BaseModel):
    nome: str
    assunto: str = ""
    html: str = ""
    design: dict | None = None
    lista: Lista = "clientes"


class TemplateOut(BaseModel):
    id: str
    nome: str
    assunto: str
    html: str
    design: dict | None
    lista: Lista = "clientes"
    created_at: datetime
    updated_at: datetime


class Segmento(BaseModel):
    """Filtros do público.

    Todos opcionais: sem nenhum, o público é a base elegível inteira. As regras
    de consentimento e supressão são aplicadas sempre e NÃO são parâmetro —
    ver app/services/segmentos.py.
    """

    canal: str | None = None
    status: str | None = None
    idioma: str | None = None
    origem: str | None = None
    tags: list[str] | None = None
    etiquetas: list[str] | None = None
    interagiu_dias: int | None = Field(default=None, ge=1, le=3650)
    #: Exclui quem recebeu campanha nos últimos N dias. Quem nunca recebeu entra.
    sem_email_dias: int | None = Field(default=None, ge=1, le=365)
    ids: list[int] | None = None


class CampanhaIn(BaseModel):
    nome: str
    template_id: str
    assunto: str = ""
    segmento: Segmento = Field(default_factory=Segmento)
    #: Ignorado: o remetente sai da lista (ver sender.texto_da_lista). Fica
    #: aceito para não quebrar quem ainda manda o campo.
    remetente: str | None = None
    agendada_para: datetime | None = None
    lista: Lista = "clientes"


class CampanhaStats(BaseModel):
    """Métricas da campanha.

    As taxas usam ENVIADOS como base — quem não recebeu não pode abrir. Vêm nulas
    quando não houve envio: a tela mostra "—" em vez de 0%, que afirmaria que
    ninguém abriu.
    """

    enviados: int
    publico: int = 0
    pendentes: int
    #: Reservados por um disparo em curso — a tela usa para travar o botão.
    processando: int = 0
    suprimidos: int
    falhas: int
    aberturas: int
    cliques: int
    bounce_hard: int = 0
    bounce_soft: int = 0
    descadastros: int = 0

    taxa_abertura: Decimal | None = None
    taxa_clique: Decimal | None = None
    taxa_bounce_hard: Decimal | None = None
    taxa_bounce_soft: Decimal | None = None
    taxa_descadastro: Decimal | None = None


class CampanhaOut(BaseModel):
    id: str
    nome: str
    assunto: str
    status: str
    lista: Lista = "clientes"
    remetente: str | None = None
    segmento_label: str | None
    template_nome: str | None
    publico: int
    com_email: int
    enviados: int
    agendada_para: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    stats: CampanhaStats | None = None


class PreviaSegmento(BaseModel):
    total: int
    com_email: int
    label: str
    amostra: list[dict]
    excluidos: dict


class ResultadoEnvio(BaseModel):
    enviados: int
    falhas_temporarias: int
    suprimidos: int
    restantes: int
    concluida: bool
    simulado: bool
    aviso: str | None


class CotaOut(BaseModel):
    """Consumo de envio.

    Com provedor externo o teto é um PLANO comprado, e a janela é o MÊS. Ao voltar
    para o disparador próprio, passa a ser a capacidade da infraestrutura e a
    janela vira o DIA (ver docs/DISPARADOR-PROPRIO.md).
    """

    enviados_hora: int
    enviados_dia: int
    enviados_mes: int
    limite_hora: int
    limite_dia: int
    limite_mes: int
    resta_hora: int
    resta_dia: int
    resta_mes: int
    disponivel: int
    #: "hora" | "dia" | "mes" | None
    bloqueio: str | None


class DisparoIniciado(BaseModel):
    """Resposta do POST /campanhas/{id}/enviar.

    O envio roda em segundo plano, então a resposta diz o que foi COLOCADO EM
    MARCHA — não o que já saiu. O relatório da campanha é quem mostra o
    progresso, atualizando sozinho enquanto o status é `enviando`.
    """

    iniciado: bool
    #: Quantos estão na fila desta campanha agora.
    na_fila: int
    #: Quantos cabem na janela atual de cota. O resto sai quando ela abrir.
    cabe_agora: int
    #: true = EMAIL_DRY_RUN ligado; nada sai de verdade.
    simulado: bool


# ------------------------------- Parceiros ---------------------------------

class ParceiroIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    nome: str | None = Field(default=None, max_length=200)
    empresa: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    cargo: str | None = Field(default=None, max_length=120)
    cidade: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list)
    observacoes: str | None = Field(default=None, max_length=4000)


class ParceiroPatch(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    nome: str | None = Field(default=None, max_length=200)
    empresa: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    cargo: str | None = Field(default=None, max_length=120)
    cidade: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None
    observacoes: str | None = Field(default=None, max_length=4000)


class ParceiroOut(BaseModel):
    id: int
    nome: str | None
    empresa: str | None
    email: str
    telefone: str | None
    cargo: str | None
    cidade: str | None
    tags: list[str]
    observacoes: str | None
    origem: str | None
    #: recebe | descadastrou (saiu da lista de parceiros) | bloqueado (bounce,
    #: spam ou descadastro de cliente — vale para o endereço inteiro)
    situacao: Literal["recebe", "descadastrou", "bloqueado"]
    ultimo_envio: datetime | None
    created_at: datetime
    updated_at: datetime


class ParceirosPagina(BaseModel):
    items: list[ParceiroOut]
    total: int
    page: int
    page_size: int


class ParceirosNumeros(BaseModel):
    total: int
    recebem: int
    descadastrados: int
    bloqueados: int


class ImportacaoParceiros(BaseModel):
    total_linhas: int
    criados: int
    atualizados: int
    ignorados: int
    descadastrados: int
    erros: list[str]

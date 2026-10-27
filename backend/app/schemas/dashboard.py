from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import CountByValue


class DashboardResumo(BaseModel):
    total_contatos: int
    contatos_com_telefone: int
    contatos_com_email: int
    contatos_com_interacao: int
    contatos_com_opt_in_email: int
    interacoes_ultimos_30_dias: int
    domani_ultima_sincronizacao: datetime | None
    fontes_ativas: list[str]

    # --- Consumo (Alpha Code) ---
    # Nulos enquanto o PDV não enviar nada. Null é ausência de dado; zero
    # afirmaria que não houve faturamento, o que é diferente.
    pedidos_total: int = 0
    pedidos_30_dias: int = 0
    faturamento_total: Decimal | None = None
    faturamento_30_dias: Decimal | None = None
    ticket_medio: Decimal | None = None
    clientes_com_pedido: int = 0
    ultimo_pedido: datetime | None = None


class DashboardDistribuicoes(BaseModel):
    por_canal: list[CountByValue]
    por_status: list[CountByValue]
    por_origem: list[CountByValue]
    por_idioma: list[CountByValue]


class AtividadePonto(BaseModel):
    data: date
    total: int


class DashboardAtividade(BaseModel):
    dias: int
    serie: list[AtividadePonto]


class ConsumoPonto(BaseModel):
    data: date
    pedidos: int
    faturamento: Decimal | None


class ItemVendido(BaseModel):
    nome: str
    quantidade: Decimal | None
    faturamento: Decimal | None


class DashboardConsumo(BaseModel):
    dias: int
    serie: list[ConsumoPonto]
    itens: list[ItemVendido]

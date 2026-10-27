"""Cota de envio e classificação de erro do disparador.

Cada teste aqui nasceu de um problema real, não de hipótese.
"""

import inspect

from app.services.cota import Cota, mensagem_de_bloqueio
from app.services.campanhas import disparar


def _cota(hora=0, dia=0, mes=0):
    return Cota(enviados_hora=hora, enviados_dia=dia, enviados_mes=mes,
                limite_hora=2500, limite_dia=800, limite_mes=10_000, margem=50)


# --------------------------------- Cota ------------------------------------

def test_base_limpa_libera_o_menor_dos_tetos():
    """Com tudo zerado, vale o limite mais apertado dos três.

    Aqui é o diário (800), abaixo do horário (2.500) e do mensal (10.000).
    """
    assert _cota().disponivel == 800


def test_cota_mensal_aperta_no_fim_do_ciclo():
    """Perto do teto do mês, é ele que limita — não a hora."""
    assert _cota(hora=0, mes=9_930).disponivel == 20


def test_bloqueio_mensal_tem_prioridade():
    """Se os dois estouraram, o mensal manda: não passa nem na próxima hora."""
    c = _cota(hora=2500, mes=10_000)
    assert c.bloqueio == "mes"
    assert "mensal" in mensagem_de_bloqueio(c)


def test_bloqueio_horario_avisa_que_retoma_sozinho():
    c = _cota(hora=2500, mes=10)
    assert c.bloqueio == "hora"
    assert "continua" in mensagem_de_bloqueio(c)


def test_nunca_devolve_negativo():
    """Envio fora do CRM pode ter estourado o teto; não vira dívida."""
    assert _cota(hora=9999, mes=99_999).disponivel == 0


def test_margem_protege_a_janela_horaria():
    """A margem evita brigar com envio manual que o CRM não contabiliza."""
    assert _cota(hora=2450).resta_hora == 0


def test_limite_mensal_vem_do_ambiente(monkeypatch):
    """O teto mensal é COMERCIAL, não técnico.

    É o que o cliente contratou. Quando ele quiser mais, o valor sobe pelo .env e
    a API reinicia — sem deploy.
    """
    from app.config import Settings

    # `_env_file=None` e sem a variável no ambiente: o teste mede o PADRÃO DO
    # CÓDIGO. Sem isso, na VPS ele lia o .env real (4.500) e falhava — acusando
    # erro onde só havia uma configuração legítima do cliente.
    monkeypatch.delenv("SMTP_LIMITE_MES", raising=False)
    padrao = Settings(_env_file=None, database_url="x", supabase_jwt_secret="y")
    assert padrao.smtp_limite_mes == 10_000

    ajustado = Settings(_env_file=None, database_url="x", supabase_jwt_secret="y",
                        smtp_limite_mes=25_000)
    assert ajustado.smtp_limite_mes == 25_000


def test_intervalo_evita_rajada():
    """2.500/h dá uma a cada 1,44s; a pausa precisa cobrir isso com folga."""
    from app.config import Settings

    assert Settings(_env_file=None, database_url="x", supabase_jwt_secret="y").smtp_intervalo_seg >= 1.5


# ------------------------ Classificação de erro SMTP ------------------------

def test_cota_do_provedor_nao_vira_supressao():
    """`554 quota exceeded` é problema NOSSO, não do destinatário.

    Tratar como permanente bloquearia o endereço para sempre por uma falha que
    não era dele. Aconteceu em produção.
    """
    from app.services.sender import ErroTemporario, _classificar

    class _Resp(Exception):
        smtp_code = 554
        smtp_error = b"5.9.3 Sending quota exceeded."

    assert isinstance(_classificar(_Resp()), ErroTemporario)


def test_caixa_inexistente_continua_permanente():
    """O caso legítimo de supressão não pode ter sido afrouxado junto."""
    from app.services.sender import ErroPermanente, _classificar

    class _Resp(Exception):
        smtp_code = 550
        smtp_error = b"5.1.1 User unknown"

    assert isinstance(_classificar(_Resp()), ErroPermanente)



def test_disparo_responde_sem_esperar_o_envio():
    """A tela não pode ficar presa até a última mensagem sair.

    Com pausa entre e-mails para proteger a reputação, uma base de 10 mil leva
    horas. Prender o navegador esse tempo é inviável, e qualquer timeout de proxy
    derrubaria a conexão no meio sem ninguém saber se saiu ou não.
    """
    from app.routers.email import enviar_campanha

    fonte = inspect.getsource(enviar_campanha)
    assert "tarefas.add_task" in fonte
    assert "disparar_em_background" in fonte
    # e NÃO pode chamar o disparo direto, que bloquearia o request
    assert "await svc.disparar(" not in fonte


def test_erros_previsiveis_aparecem_antes_do_background():
    """Campanha já enviada, sem cota ou sem público viram erro NA HORA.

    Se fossem descobertos só no background, a pessoa veria "envio iniciado" e
    nada aconteceria — sem nenhuma pista do motivo.
    """
    from app.routers.email import enviar_campanha

    fonte = inspect.getsource(enviar_campanha)
    for validacao in ("já foi enviada", "ninguém na fila", "envio em andamento"):
        assert validacao in fonte


def test_background_abre_a_propria_conexao():
    """A conexão do request morre quando ele termina."""
    from app.services.campanhas import disparar_em_background

    fonte = inspect.getsource(disparar_em_background)
    assert "AsyncConnection.connect" in fonte


def test_cota_diaria_bloqueia_mesmo_com_hora_e_mes_livres():
    """O caso real do aquecimento.

    A cliente mandou os 50 do dia. Uma hora depois a janela horária zerou e o mês
    seguia folgado (57 de 1.500) — e o sistema deixava mandar mais 50. Sem teto
    diário, a cota do mês inteiro sairia em algumas horas, que é o oposto de
    aquecer o domínio.
    """
    c = Cota(enviados_hora=0, enviados_dia=50, enviados_mes=57,
             limite_hora=50, limite_dia=50, limite_mes=1_500, margem=0)
    assert c.bloqueio == "dia"
    assert c.disponivel == 0
    assert "meia-noite" in mensagem_de_bloqueio(c)


def test_disponivel_considera_as_tres_janelas():
    """O teto real é sempre o mais apertado dos três."""
    c = Cota(enviados_hora=0, enviados_dia=30, enviados_mes=0,
             limite_hora=2500, limite_dia=50, limite_mes=10_000, margem=0)
    assert c.disponivel == 20  # sobra do dia, não da hora


def test_ordem_do_bloqueio_diz_o_pior_primeiro():
    """Mês só abre no ciclo seguinte; dia à meia-noite; hora em minutos.

    Dizer "espere uma hora" quando na verdade acabou o mês seria falsa esperança.
    """
    c = Cota(enviados_hora=999, enviados_dia=999, enviados_mes=99_999,
             limite_hora=50, limite_dia=50, limite_mes=1_500, margem=0)
    assert c.bloqueio == "mes"


# ------------------------- Métricas da campanha -----------------------------

def test_taxas_usam_enviados_como_base():
    """Quem não recebeu não pode abrir.

    Dividir pelo público total inflaria o denominador e faria toda campanha
    parecer pior do que foi — principalmente as que ainda têm gente na fila.
    """
    sql = open("sql/012_metricas_campanha.sql").read()
    assert "nullif(b.enviados, 0)" in sql
    assert "taxa_abertura" in sql


def test_aberturas_contam_pessoas_nao_eventos():
    """A mesma pessoa abrindo três vezes conta uma.

    Sem DISTINCT, a taxa passa de 100% e ninguém entende o número.
    """
    sql = open("sql/012_metricas_campanha.sql").read()
    assert "count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'open')" in sql


def test_bounce_hard_e_soft_sao_distintos():
    """Exigem reações opostas: um suprime, o outro volta para a fila.

    Insistir num hard queima a reputação; suprimir por um soft perde um contato
    válido que só estava com a caixa cheia.
    """
    sql = open("sql/012_metricas_campanha.sql").read()
    assert "'bounce_hard'" in sql and "'bounce_soft'" in sql


def test_descadastro_vira_evento_da_campanha():
    """É o sinal mais direto de que o conteúdo ou a frequência incomodaram.

    Sem o evento ligado ao destinatário, o descadastro ficaria só na tabela de
    supressões — sem dizer QUAL campanha o causou.
    """
    import inspect
    from app.routers import tracking

    fonte = inspect.getsource(tracking._descadastrar)
    assert "'unsubscribe'" in fonte


def test_exclusao_por_periodo_nao_barra_quem_nunca_recebeu():
    """Quem nunca recebeu campanha precisa entrar sempre.

    Com EXISTS negado, ausência de registro passa — que é o comportamento certo.
    """
    import inspect
    from app.services import segmentos

    fonte = inspect.getsource(segmentos._where)
    assert "sem_email_dias" in fonte
    assert "NOT EXISTS" in fonte
    assert "r.status = 'enviado'" in fonte


def test_campanha_agendada_nao_dispara_antes_da_hora():
    """O botão "Disparar" não pode antecipar uma campanha agendada.

    Aconteceu em produção: a campanha de quarta foi criada com data para o dia
    seguinte e disparada 9 segundos depois, por hábito. O botão ignorava o
    agendamento e 16 pessoas receberam o e-mail de quarta na terça.
    """
    import inspect
    from app.routers import email

    fonte = inspect.getsource(email.enviar_campanha)
    assert 'camp["status"] == "agendada"' in fonte
    assert "sai sozinha" in fonte


def test_grafico_recebe_um_ponto_por_dia_com_zero_nos_vazios():
    """Dia sem venda precisa aparecer como zero, não sumir.

    O gráfico espaça os pontos por igual. Só com os dias que tinham pedido, o
    webhook parado de 25/09 a 07/10 virava uma linha contínua — e o buraco de 12
    dias, que é exatamente o que o gráfico deveria mostrar, ficava invisível.
    """
    from datetime import date
    from app.routers.dashboard import _completar_dias

    rows = [{"data": date(2026, 10, 5), "pedidos": 2, "faturamento": 100}]
    serie = _completar_dias(rows, date(2026, 10, 7), 3, {"pedidos": 0, "faturamento": 0})
    assert [p["data"] for p in serie] == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    assert [p["pedidos"] for p in serie] == [2, 0, 0]


def test_grafico_sem_nenhum_dado_continua_vazio():
    """Sem PDV ligado a tela mostra "aguardando", não uma linha zerada."""
    from datetime import date
    from app.routers.dashboard import _completar_dias

    assert _completar_dias([], date(2026, 10, 7), 30, {"total": 0}) == []


def test_data_sem_hora_e_lida_como_dia_local_no_front():
    """"2026-10-07" lido como UTC vira 06/10 no Brasil — o pedido do dia 7 aparecia
    rotulado como dia 6."""
    fmt = open("../frontend/src/lib/format.ts").read()
    assert "export function lerData" in fmt
    for arq in ("consumo-curva.tsx", "atividade-curva.tsx"):
        assert "lerData(iso)" in open(f"../frontend/src/components/dashboards/{arq}").read()

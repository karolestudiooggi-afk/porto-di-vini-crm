"""As regras inegociáveis do disparador.

Estes testes não checam "se o código roda" — checam se o disparador **se recusa a
fazer besteira**. Cada um corresponde a um jeito conhecido de queimar um domínio
ou levar processo.
"""

import pytest

# ⚠️ ESTES TESTES APONTAM PARA UM MÓDULO QUE NÃO ESTÁ EM USO.
#
# Existem duas implementações do disparador no repo:
#
#   app/services/           <- ATIVA. É o que `app/routers/email.py` importa.
#   app/services/email/     <- só estes testes a usam; ninguém mais a importa.
#
# Enquanto a duplicação existir, estes testes passam sem provar nada sobre o
# comportamento real do envio. As regras equivalentes, cobrindo o módulo ativo,
# estão em tests/test_email_cota.py.
#
# A decisão de qual módulo fica é do time — mas as duas não podem coexistir.
import pytest as _pytest

_pytest.skip(
    "modulo app.services.email nao esta ligado ao router; ver tests/test_email_cota.py",
    allow_module_level=True,
)

from app.services.email import render, segmentos  # noqa: E402
from app.services.email.cota import Cota  # noqa: E402


# ------------------------- Guardas de público ------------------------------
# Os testes de SQL exigem banco; aqui validamos que as guardas estão ESCRITAS na
# query — se alguém remover uma, o teste quebra antes de chegar em produção.

def test_sql_exclui_suprimidos():
    sql, _, _ = segmentos.montar_sql({"kind": "filtro"})
    assert "email.suppressions" in sql
    assert "NOT EXISTS" in sql


def test_sql_exclui_quem_recusou_contato():
    sql, _, _ = segmentos.montar_sql({"kind": "filtro"})
    # NULL (nunca perguntado) recebe; false (recusou) não.
    assert "coalesce(c.opt_in_email, true) = true" in sql


def test_sql_exclui_ficha_apagada():
    sql, _, _ = segmentos.montar_sql({"kind": "filtro"})
    assert "c.deleted_at IS NULL" in sql


def test_sql_exclui_sem_email():
    sql, _, _ = segmentos.montar_sql({"kind": "filtro"})
    assert "c.email_norm IS NOT NULL" in sql


def test_sql_deduplica_email_repetido():
    """Duas fichas com o mesmo endereço = uma mensagem."""
    sql, _, _ = segmentos.montar_sql({"kind": "filtro"})
    assert "DISTINCT ON (c.email_norm)" in sql


def test_guardas_valem_tambem_na_selecao_manual():
    """Selecionar na tela não pode furar as regras."""
    sql, _, _ = segmentos.montar_sql({"kind": "selecao", "ids": [1, 2]})
    assert "email.suppressions" in sql
    assert "coalesce(c.opt_in_email, true) = true" in sql


# ------------------------------- Cota --------------------------------------

def test_cota_usa_o_menor_teto():
    """Sobra muito no dia, mas acabou a hora: vale a hora."""
    c = Cota(enviados_hora=190, enviados_dia=100,
             limite_hora=200, limite_dia=800, margem=0)
    assert c.disponivel == 10


def test_cota_nunca_negativa():
    """Envio fora do CRM pode ter estourado o teto; não vira dívida."""
    c = Cota(enviados_hora=250, enviados_dia=900,
             limite_hora=200, limite_dia=800, margem=0)
    assert c.disponivel == 0


def test_cota_diaria_esgotada_explica_o_motivo():
    """Diário esgotado: não adianta esperar a próxima hora, só amanhã."""
    c = Cota(enviados_hora=0, enviados_dia=800,
             limite_hora=200, limite_dia=800, margem=0)
    assert c.bloqueio == "dia"
    assert "meia-noite" in mensagem_de_bloqueio(c)


def test_cota_horaria_esgotada_explica_o_motivo():
    c = Cota(enviados_hora=200, enviados_dia=100,
             limite_hora=200, limite_dia=800, margem=0)
    assert c.bloqueio == "hora"
    assert "hora" in mensagem_de_bloqueio(c).lower()


def test_cota_com_espaco_nao_bloqueia():
    c = Cota(enviados_hora=10, enviados_dia=100,
             limite_hora=200, limite_dia=800, margem=0)
    assert c.bloqueio is None


# ----------------------------- Renderização --------------------------------

def test_variavel_desconhecida_nao_vaza_para_o_cliente():
    """`{{campo_inexistente}}` não pode aparecer na caixa de entrada."""
    saida = render.aplicar_vars("Olá {{nome}}, {{campo_que_nao_existe}}!", {"nome": "Ana"})
    assert saida == "Olá Ana, !"
    assert "{{" not in saida


def test_variavel_com_caractere_especial_e_escapada():
    """Nome com & ou < quebraria o HTML do e-mail."""
    saida = render.aplicar_vars("Olá {{nome}}", {"nome": "Bar & Grill <SP>"})
    assert "&amp;" in saida and "&lt;" in saida


def test_html_final_tem_pixel_rodape_e_descadastro():
    html = render.montar_html("<p>Oi</p>", "rid-1", {})
    assert "/track/open/rid-1.gif" in html
    assert "/unsubscribe?r=rid-1" in html
    assert "Descadastrar" in html


def test_links_viram_rastreados():
    html = render.montar_html('<a href="https://site.com/promo">ver</a>', "rid-2", {})
    assert "/track/click?r=rid-2" in html


def test_link_de_descadastro_nao_e_rastreado():
    """Atrito entre a pessoa e o descadastro gera denúncia de spam."""
    base = '<a href="https://crm.exemplo/api/unsubscribe?r=x">sair</a>'
    saida = render.reescrever_links(base, "rid-3")
    assert "/track/click" not in saida


def test_versao_texto_nao_tem_html():
    """Toda mensagem sai multipart: só-HTML é sinal de spam."""
    texto = render.montar_texto("<p>Olá <b>Ana</b></p><br><div>Tudo bem?</div>")
    assert "<" not in texto
    assert "Olá Ana" in texto and "Tudo bem?" in texto


def test_primeiro_nome_cai_para_o_nome_completo():
    v = render.vars_de_contato({"nome": "Ana Paula Souza", "primeiro_nome": None})
    assert v["primeiro_nome"] == "Ana"


def test_contato_sem_nome_nao_gera_saudacao_vazia():
    """"Olá, !" é pior que "Olá!" — o template decide, mas o dado vem limpo."""
    v = render.vars_de_contato({"nome": None, "primeiro_nome": None})
    assert v["nome"] == "" and v["primeiro_nome"] == ""

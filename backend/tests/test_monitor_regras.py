"""Leitura dos e-mails de notificação do Tripadvisor e do Reclame Aqui.

Os e-mails daqui são MODELOS montados a partir do formato público das
notificações das duas plataformas — não são cópias de e-mails reais de
nenhum cliente. Quando chegar o primeiro e-mail de verdade, ele deve virar um caso aqui
(com nome e e-mail do cliente trocados), para a regra nunca regredir.
"""

from email.message import EmailMessage

from app.services.integracoes import email_bruto, monitor_regras as regras

from tests.amostras_monitor import (  # noqa: F401
    NEWSLETTER, RA_LEMBRETE, RA_NOVA, RA_RESULTADO, TA_EN_RASTREIO, TA_PT, UNIDADES, _eml,
)


def test_tripadvisor_em_portugues():
    e = email_bruto.ler(TA_PT)
    assert regras.origem_de(e) == "tripadvisor"
    it = regras.tripadvisor(e, UNIDADES)
    assert it["tipo"] == "avaliacao"
    assert it["externo_id"] == "987654321"
    assert it["loja_id"] == "2343434"
    assert it["nota"] == 2
    assert it["titulo"] == "Pizza fria e demora"
    assert it["texto"].startswith("Pedimos uma pizza e demorou")
    assert it["autor"] == "Joana M."
    assert it["unidade"] == "Unidade Sul"
    assert "ShowUserReviews" in it["link"]
    assert regras.nivel(it) == "negativa"
    assert regras.palavras_criticas(it["texto"], ["cabelo", "procon"]) == ["cabelo"]
    assert regras.faltando(it | {"origem": "tripadvisor"}) == []


def test_tripadvisor_em_ingles_com_link_de_rastreio():
    e = email_bruto.ler(TA_EN_RASTREIO)
    it = regras.tripadvisor(e, UNIDADES)
    assert it["externo_id"] == "555666777"
    assert it["loja_id"] == "11111111"
    assert it["nota"] == 5
    assert it["titulo"] == "Best pizza in Rio"
    assert it["texto"].startswith("Amazing burrata pizza")
    assert it["autor"] == "TravelerAnn"
    assert it["unidade"] == "PracaCentralHall"
    assert regras.nivel(it) == "positiva"


def test_reclame_aqui_reclamacao_nova():
    e = email_bruto.ler(RA_NOVA)
    assert regras.origem_de(e) == "reclameaqui"
    it = regras.reclameaqui(e, UNIDADES)
    assert it["tipo"] == "reclamacao"
    assert it["externo_id"] == "Xk9aBcD3eFgH1jK"
    assert it["titulo"] == "Pedido não entregue e cobrança indevida"
    assert it["autor"] == "Carlos Pereira"
    assert it["cidade"] == "Niterói - RJ"
    assert it["texto"].startswith("Fiz um pedido na unidade Paraíso")
    assert it["unidade"] == "Paraíso"
    assert regras.nivel(it) == "negativa"
    assert regras.palavras_criticas(it["texto"], ["procon", "processo"]) == ["procon"]


def test_reclame_aqui_resultado_com_nota_de_0_a_10():
    it = regras.reclameaqui(email_bruto.ler(RA_RESULTADO), UNIDADES)
    assert it["tipo"] == "resultado"
    assert it["nota"] == 9 and it["nota_maxima"] == 10
    assert it["externo_id"] == "AbC123dEf456"
    assert "resolvida: Sim" in it["titulo"]
    assert it["unidade"] == "Unidade Sul"
    assert regras.nivel(it) == "positiva"


def test_aviso_que_nao_e_reclamacao_e_ignorado():
    assert regras.reclameaqui(email_bruto.ler(RA_LEMBRETE), UNIDADES) is None


def test_email_de_fora_nao_e_de_plataforma():
    e = email_bruto.ler(NEWSLETTER)
    assert regras.origem_de(e) is None
    assert not regras.parece_da_plataforma(e.remetente, e.assunto)


def test_encaminhado_como_anexo_usa_o_original():
    fwd = EmailMessage()
    fwd["From"] = "Ana <ana@seucliente.com.br>"
    fwd["Subject"] = "Fwd: Nova reclamação"
    fwd["Message-ID"] = "<fwd1@seucliente>"
    fwd.set_content("segue")
    import email as _email
    from email import policy
    fwd.add_attachment(_email.message_from_bytes(RA_NOVA, policy=policy.default))
    e = email_bruto.ler(fwd.as_bytes())
    assert e.remetente == "naoresponda@reclameaqui.com.br"
    assert e.message_id == "<fwd1@seucliente>"
    assert regras.reclameaqui(e, UNIDADES)["autor"] == "Carlos Pereira"


def test_encaminhado_no_corpo_reconhece_pelos_links():
    fwd = _eml("Ana <ana@seucliente.com.br>", "Fwd: olha isso",
               texto="---------- Forwarded message ---------\n" + email_bruto.ler(RA_NOVA).texto)
    assert regras.origem_de(email_bruto.ler(fwd)) == "reclameaqui"


def test_palavra_critica_pelo_comeco_sem_acento_e_nao_no_meio():
    t = "Fui INTOXICADO e vou entrar com processos. A mesa envidraçada estava ótima."
    assert regras.palavras_criticas(t, ["intoxica", "processo", "vidro"]) == ["intoxica", "processo"]
    assert regras.palavras_criticas("passei   mal depois", ["passei mal"]) == ["passei mal"]


def test_unidade_mais_longa_vence_e_ignora_parenteses():
    assert regras.casar_unidade("Shopping Centro em Recife", UNIDADES) == "Shopping Centro (Recife)"
    assert regras.casar_unidade("loja do Mesa Shopping", UNIDADES) == "MesaShopping"
    assert regras.casar_unidade("nada a ver", UNIDADES) is None


def test_sem_message_id_o_conteudo_vira_a_identidade():
    bruto = _eml("x@tripadvisor.com", "a", texto="b", msgid="")
    bruto = bruto.replace(b"Message-ID: \n", b"")
    e1, e2 = email_bruto.ler(bruto), email_bruto.ler(bruto)
    assert e1.message_id.startswith("sha1:") and e1.message_id == e2.message_id


def test_ia_so_completa_com_o_que_esta_no_email(monkeypatch):
    """A IA preenche o que faltou, mas só aceita trecho que existe no e-mail:
    texto inventado é descartado, e o que o leitor achou nunca é trocado."""
    import asyncio
    import json

    from app.config import settings
    from app.services.integracoes import monitor

    monkeypatch.setattr(settings, "openai_api_key", "sk-teste")
    e = email_bruto.ler(RA_NOVA)
    item = regras.reclameaqui(e, UNIDADES)
    item["texto"] = None
    item["autor"] = None
    resposta = {"tipo": "reclamacao", "texto": "Fiz um pedido na unidade Paraíso pelo app, paguei",
                "autor": "Fulano Inventado", "titulo": "outro título", "nota": None,
                "unidade": "Paraíso", "cidade": None}

    class _R:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(resposta)}}]}

    class _Http:
        async def post(self, *a, **k):
            return _R()

    novo = asyncio.run(monitor.completar_com_ia(None, "reclameaqui", e, item, UNIDADES, _Http()))
    assert novo["texto"].startswith("Fiz um pedido")      # está no e-mail: aceito
    assert novo["autor"] is None                          # não está: descartado
    assert novo["titulo"] == "Pedido não entregue e cobrança indevida"  # já tinha: mantido


def test_regra_de_aviso():
    from datetime import datetime, timedelta, timezone

    from app.services.integracoes.monitor import deve_avisar

    agora = datetime.now(timezone.utc)
    cfg = {"aviso": "negativos", "webhook_url": "https://x"}
    neg = {"nivel": "negativa", "critico": False, "ocorrido_em": agora}
    pos_critico = {"nivel": "positiva", "critico": True, "ocorrido_em": agora}
    pos = {"nivel": "positiva", "critico": False, "ocorrido_em": agora}
    assert deve_avisar(cfg, neg) and deve_avisar(cfg, pos_critico) and not deve_avisar(cfg, pos)
    assert not deve_avisar(cfg | {"aviso": "criticos"}, neg)
    assert deve_avisar(cfg | {"aviso": "todos"}, pos)
    assert not deve_avisar(cfg | {"webhook_url": ""}, neg)
    assert not deve_avisar(cfg, neg | {"ocorrido_em": agora - timedelta(days=5)})

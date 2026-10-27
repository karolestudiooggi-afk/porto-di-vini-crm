"""Monitor de reputação de ponta a ponta, num Postgres de verdade.

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_monitor_banco.py

Sem isso é pulado. Nunca aponte para produção: o teste APAGA as tabelas do
monitor no começo e no fim.
"""

from __future__ import annotations

import asyncio
import io
import os
import zipfile
from datetime import datetime, timezone
from email.utils import format_datetime

import pytest

from tests.amostras_monitor import (
    NEWSLETTER, RA_LEMBRETE, RA_NOVA, RA_RESULTADO, TA_EN_RASTREIO, TA_PT, ta_pt,
)
from tests.test_parceiros_banco import ADMIN, _sql

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_TESTE_BANCO") != "1",
    reason="precisa de CRM_TESTE_BANCO=1 e DATABASE_URL de um banco de teste",
)


def _limpar():
    _sql("DELETE FROM integra.monitor_itens")
    _sql("DELETE FROM integra.monitor_emails")
    _sql("DELETE FROM integra.monitor_unidades")
    _sql("UPDATE integra.monitor_caixa SET ultimo_uid = 0, uidvalidity = NULL, lendo_desde = NULL,"
         " ultima_leitura = NULL, ultimo_erro = NULL")
    _sql("UPDATE integra.monitor_config SET aviso = 'negativos', webhook_url = NULL, ativo = true")


@pytest.fixture(autouse=True)
def banco_limpo():
    _limpar()
    _sql("""INSERT INTO integra.lojas (origem, loja_id, nome) VALUES
            ('google', '1000000000000000013', 'Unidade Sul'), ('google', '1000000000000000010', 'Paraíso'),
            ('google', '1000000000000000001', 'PracaCentralHall')
            ON CONFLICT DO NOTHING""")
    yield
    _limpar()


@pytest.fixture()
def cliente():
    from fastapi.testclient import TestClient

    from app.auth import current_user
    from app.main import app

    app.dependency_overrides[current_user] = lambda: ADMIN
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _subir(cliente, *arquivos):
    r = cliente.post("/monitor/importar",
                     files=[("arquivos", (nome, conteudo, "message/rfc822")) for nome, conteudo in arquivos])
    assert r.status_code == 200, r.text
    return r.json()


def test_importar_eml_vira_item_e_nao_duplica(cliente):
    rel = _subir(cliente, ("ta.eml", TA_PT), ("ra.eml", RA_NOVA), ("lembrete.eml", RA_LEMBRETE),
                 ("promo.eml", NEWSLETTER))
    assert (rel["novos"], rel["ignorados"], rel["criticos"]) == (2, 2, 2)

    # Mesmo arquivo de novo: nada novo.
    assert _subir(cliente, ("ta.eml", TA_PT))["repetidos"] == 1

    # O lembrete da MESMA avaliação (outro Message-ID) também não duplica.
    lembrete = ta_pt(msgid="<lembrete@teste>")
    assert _subir(cliente, ("lembrete-ta.eml", lembrete))["repetidos"] == 1

    itens = cliente.get("/monitor/tripadvisor/itens").json()
    assert itens["total"] == 1
    it = itens["items"][0]
    assert (it["unidade"], float(it["nota"]), it["critico"], it["palavras"]) == ("Unidade Sul", 2.0, True, ["cabelo"])

    ra = cliente.get("/monitor/reclameaqui/itens?pendente=true").json()["items"][0]
    assert ra["tipo"] == "reclamacao" and ra["unidade"] == "Paraíso" and "procon" in ra["palavras"]

    ign = cliente.get("/monitor/emails").json()
    motivos = {e["assunto"]: e["motivo"] for e in ign}
    assert "não é do Tripadvisor" in motivos["50% OFF hoje"]
    assert "não é avaliação nem reclamação" in motivos["Você tem 3 reclamações sem resposta"]


def test_painel_e_situacao(cliente):
    _subir(cliente, ("1.eml", TA_PT), ("2.eml", TA_EN_RASTREIO), ("3.eml", RA_NOVA),
           ("4.eml", RA_RESULTADO))
    p = cliente.get("/monitor/tripadvisor/painel?dias=60").json()
    assert p["numeros"]["total"] == 2
    assert float(p["numeros"]["media"]) == 3.5
    assert p["numeros"]["negativas"] == 1 and p["numeros"]["criticos"] == 1
    assert {u["unidade"] for u in p["unidades"]} == {"Unidade Sul", "PracaCentralHall"}
    assert p["palavras"] == [{"palavra": "cabelo", "total": 1}]
    assert sum(s["total"] for s in p["semanas"]) == 2
    # Semanas sem nada aparecem com zero (o gráfico não emenda buracos).
    assert any(s["total"] == 0 for s in p["semanas"])

    s = cliente.get("/monitor").json()
    assert s["caixa"]["configurada"] is False
    assert s["origens"]["tripadvisor"]["itens"] == 2
    assert s["origens"]["reclameaqui"]["pendentes"] == 1
    assert "procon" in s["palavras"]


def test_tratar_corrigir_unidade_e_ensinar_o_local(cliente):
    _subir(cliente, ("ta.eml", TA_PT))
    item = cliente.get("/monitor/tripadvisor/itens").json()["items"][0]
    d = cliente.patch(f"/monitor/itens/{item['id']}",
                      json={"tratado": True, "unidade": "Shopping Leste", "observacao": "ligamos"}).json()
    assert d["tratado_em"] and d["unidade"] == "Shopping Leste" and d["observacao"] == "ligamos"
    assert "Pedimos uma pizza" in d["email_texto"]
    assert _sql("SELECT unidade FROM integra.monitor_unidades WHERE loja_id = '2343434'")[0]["unidade"] \
        == "Shopping Leste"

    # Outra avaliação do mesmo local já chega com a unidade corrigida.
    outra = ta_pt(msgid="<outra@teste>", review="111222333")
    _subir(cliente, ("outra.eml", outra))
    unidades = {i["unidade"] for i in cliente.get("/monitor/tripadvisor/itens").json()["items"]}
    assert unidades == {"Shopping Leste"}
    assert cliente.get("/monitor/tripadvisor/itens?pendente=true").json()["total"] == 1


def test_trocar_palavras_recalcula_o_historico(cliente):
    originais = cliente.get("/monitor").json()["palavras"]
    _subir(cliente, ("ta.eml", TA_PT), ("ra.eml", RA_NOVA))
    r = cliente.put("/monitor/palavras", json={"palavras": ["garçom", "Garcom", "  "]}).json()
    assert r["palavras"] == ["garçom"]
    ta = cliente.get("/monitor/tripadvisor/itens").json()["items"][0]
    ra = cliente.get("/monitor/reclameaqui/itens").json()["items"][0]
    assert ta["palavras"] == ["garçom"] and ra["critico"] is False
    # Devolve a lista que estava no banco.
    cliente.put("/monitor/palavras", json={"palavras": originais})


def test_reprocessar_mantem_o_que_a_equipe_marcou(cliente):
    _subir(cliente, ("ta.eml", TA_PT))
    item = cliente.get("/monitor/tripadvisor/itens").json()["items"][0]
    cliente.patch(f"/monitor/itens/{item['id']}", json={"tratado": True, "observacao": "ok"})
    _sql("UPDATE integra.monitor_itens SET titulo = 'estragado' WHERE id = %s", (item["id"],))
    rel = cliente.post("/monitor/reprocessar").json()
    assert rel["atualizados"] == 1
    depois = cliente.get(f"/monitor/itens/{item['id']}").json()
    assert depois["titulo"] == "Pizza fria e demora"
    assert depois["tratado_em"] and depois["observacao"] == "ok"


def test_aviso_vai_para_o_webhook_so_quando_a_regra_manda():
    from app.config import settings
    from app.services.integracoes import monitor
    import psycopg
    from psycopg.rows import dict_row

    enviados = []

    class _Resp:
        status_code = 200

    class _Http:
        async def post(self, url, json=None, **_):
            enviados.append((url, json))
            return _Resp()

    agora = format_datetime(datetime.now(timezone.utc))
    recente_ta = ta_pt(msgid="<recente@teste>", review="222", data=agora)
    recente_bom = TA_EN_RASTREIO.replace(b"Wed, 07 Oct 2026 21:14:00 -0300", agora.encode()) \
                                .replace(b"<abc@teste>", b"<bom@teste>")
    _sql("UPDATE integra.monitor_config SET webhook_url = 'https://exemplo.test/hook', aviso = 'negativos'")

    async def rodar():
        async with await psycopg.AsyncConnection.connect(settings.database_url, row_factory=dict_row) as c:
            a = await monitor.processar_bruto(c, recente_ta, "imap", http=_Http())
            b = await monitor.processar_bruto(c, recente_bom, "imap", http=_Http())
            # Antigo (junho): histórico não dispara alarme.
            velho = await monitor.processar_bruto(
                c, ta_pt(msgid="<velho@teste>", review="333", data="Mon, 01 Jun 2026 10:00:00 -0300"),
                "imap", http=_Http())
            assert velho["resultado"] == "novo"
            return a, b

    a, b = asyncio.run(rodar())
    assert a["resultado"] == b["resultado"] == "novo"
    assert len(enviados) == 1  # só a negativa recente
    url, corpo = enviados[0]
    assert corpo["critico"] is True and corpo["nivel"] == "negativa" and corpo["unidade"] == "Unidade Sul"
    assert corpo["link"].endswith(f"item={a['item_id']}")
    assert _sql("SELECT avisado_em FROM integra.monitor_itens WHERE id = %s", (a["item_id"],))[0]["avisado_em"]


def test_leitura_da_caixa_imap(monkeypatch):
    """A caixa é aberta só para leitura, baixa inteiro só o que é das
    plataformas e anda o marcador: a segunda passada não relê nada."""
    import imaplib

    from app.config import settings
    from app.services.integracoes import monitor
    import psycopg
    from psycopg.rows import dict_row

    caixa = {101: TA_PT, 102: NEWSLETTER, 103: RA_NOVA}
    chamadas = []

    class _Fake:
        def __init__(self, host, porta, timeout=None):
            pass

        def login(self, u, s):
            chamadas.append(("login", u))

        def select(self, pasta, readonly=False):
            chamadas.append(("select", pasta, readonly))
            return "OK", [b"3"]

        def response(self, code):
            return code, [b"777"]

        def uid(self, cmd, *args):
            if cmd == "SEARCH":
                chamadas.append(("search",) + args[1:])
                if args[1] == "UID":
                    piso = int(args[2].split(":")[0])
                    return "OK", [" ".join(str(u) for u in caixa if u >= piso).encode() or b"103"]
                return "OK", [b"101 102 103"]
            uids, item = args
            if "HEADER.FIELDS" in item:
                saida = []
                for u in uids.split(","):
                    import email as _e
                    m = _e.message_from_bytes(caixa[int(u)])
                    cab = f"From: {m['From']}\r\nSubject: {m['Subject']}\r\n\r\n".encode()
                    saida += [(f"{u} (UID {u} BODY[HEADER.FIELDS (FROM SUBJECT)] {{{len(cab)}}}".encode(), cab), b")"]
                return "OK", saida
            chamadas.append(("fetch", uids))
            return "OK", [(f"{uids} (UID {uids} BODY[] {{1}}".encode(), caixa[int(uids)]), b")"]

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _Fake)
    monkeypatch.setattr(settings, "monitor_imap_host", "imap.teste")
    monkeypatch.setattr(settings, "monitor_imap_usuario", "avaliacoes@seucliente.com.br")
    monkeypatch.setattr(settings, "monitor_imap_senha", "x")

    async def rodar():
        async with await psycopg.AsyncConnection.connect(settings.database_url, row_factory=dict_row) as c:
            return await monitor.ler_caixa(c), await monitor.ler_caixa(c)

    primeira, segunda = asyncio.run(rodar())
    assert (primeira["vistos"], primeira["novos"], primeira["fora"]) == (3, 2, 1)
    assert ("select", "INBOX", True) in chamadas  # só leitura
    assert ("fetch", "102") not in chamadas  # a promoção não foi baixada inteira
    assert segunda["vistos"] == 0
    estado = _sql("SELECT ultimo_uid, uidvalidity, ultima_leitura FROM integra.monitor_caixa")[0]
    assert (estado["ultimo_uid"], estado["uidvalidity"]) == (103, 777)


def test_arquivos_mbox_e_zip():
    from app.services.integracoes import monitor

    mbox = b"From x@x Wed Oct  7 21:14:00 2026\n" + TA_PT + b"\n\nFrom y@y Wed Oct  7 21:15:00 2026\n" + RA_NOVA
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.eml", TA_EN_RASTREIO)
        z.writestr("leia-me.txt", "nada")
    brutos, erros = monitor.abrir_arquivos([("exportado.mbox", mbox), ("emails.zip", buf.getvalue()),
                                            ("planilha.xlsx", b"x")])
    assert len(brutos) == 3
    assert erros and "planilha.xlsx" in erros[0]

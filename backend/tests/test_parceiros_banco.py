"""Aba Parceiros de ponta a ponta, num Postgres de verdade.

Roda só quando há banco de teste com as migrations aplicadas:

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_parceiros_banco.py

Sem isso é pulado — a suíte normal não toca banco. Nunca aponte para o banco
de produção: o teste apaga o que cria, mas cria campanha e parceiro.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_TESTE_BANCO") != "1",
    reason="precisa de CRM_TESTE_BANCO=1 e DATABASE_URL de um banco de teste",
)

ADMIN = {
    "id": str(uuid.UUID(int=1)), "email": "teste@crm.local", "papel": "admin",
    "permissoes": {"campanhas:manage", "campanhas:send", "contatos:read",
                   "integracoes:manage", "integracoes:config"},
}

PLANILHA = (
    "Empresa;Contato;E-mail;Cargo;Tags;Aceita email\n"
    "Hotel Copacabana;Ana Souza;ana@hotelcopa-teste.com.br;Gerente;teste-hotel,zona sul;sim\n"
    "Agência Rio;Bruno Lima;BRUNO@agenciario-teste.com;Diretor;teste-agencia;\n"
    "Coworking X;Carla;carla@cowork-teste.com;;teste-hotel;não\n"
    "Sem Email;Davi;;;;\n"
    "Erro;Eva;email-invalido;;;\n"
    "Hotel Copacabana 2;Ana S.;Ana@HotelCopa-teste.com.br;;vip;\n"
).encode("utf-8")

EMAILS = ("ana@hotelcopa-teste.com.br", "bruno@agenciario-teste.com",
          "carla@cowork-teste.com", "cliente@cliente-teste.com")


@pytest.fixture()
def cliente(monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth import current_user
    from app.config import settings
    from app.main import app

    # O template não traz remetente: cada cliente põe o seu no .env.
    monkeypatch.setattr(settings, "campanha_from_email", "Cliente Exemplo <contato@seucliente.com.br>")
    monkeypatch.setattr(settings, "campanha_from_email_parceiros",
                        "Cliente Exemplo Parcerias <parcerias@seucliente.com.br>")

    app.dependency_overrides[current_user] = lambda: ADMIN
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _sql(q: str, args=()):
    """Consulta direta, fora da API, para conferir o que ficou gravado."""
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as c:
        cur = c.execute(q, args)
        return cur.fetchall() if cur.description else None


def _limpar():
    _sql("DELETE FROM email.campaigns WHERE nome LIKE 'TESTE %%'")
    _sql("DELETE FROM email.templates WHERE nome LIKE 'TESTE %%'")
    _sql("DELETE FROM email.parceiros WHERE email_norm = ANY(%s)", (list(EMAILS),))
    _sql("DELETE FROM email.supressoes_lista WHERE email = ANY(%s)", (list(EMAILS),))
    _sql("DELETE FROM email.suppressions WHERE email = ANY(%s)", (list(EMAILS),))
    _sql("DELETE FROM crm.contatos WHERE email_norm = ANY(%s)", (list(EMAILS),))


@pytest.fixture(autouse=True)
def banco_limpo():
    _limpar()
    yield
    _limpar()


def _importar(cliente):
    r = cliente.post("/email/parceiros/import",
                     files={"arquivo": ("parceiros.csv", PLANILHA, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_importacao_atualiza_pelo_email_e_respeita_recusa(cliente):
    rel = _importar(cliente)
    assert (rel["criados"], rel["atualizados"], rel["ignorados"]) == (3, 1, 2)
    assert rel["descadastrados"] == 1

    ana = _sql("SELECT * FROM email.parceiros WHERE email_norm = %s", (EMAILS[0],))[0]
    # A segunda linha da Ana somou a tag e trocou o nome pelo da planilha.
    assert set(ana["tags"]) == {"teste-hotel", "zona sul", "vip"}

    # Subir de novo não duplica.
    rel2 = _importar(cliente)
    assert rel2["criados"] == 0
    assert _sql("SELECT count(*) AS n FROM email.parceiros WHERE email_norm = ANY(%s)",
                (list(EMAILS),))[0]["n"] == 3


def _base(cliente) -> dict:
    """A prévia da base inteira ANTES do teste: o banco de teste pode ter outros
    parceiros, e os números aqui são relativos a eles."""
    return cliente.post("/email/segmentos/previa?lista=parceiros", json={}).json()


def test_campanha_de_parceiro_sai_so_para_parceiros_pelo_remetente_proprio(cliente):
    antes = _base(cliente)
    _importar(cliente)
    # Um cliente, para provar que ele NÃO entra na campanha de parceiros.
    _sql("INSERT INTO crm.contatos (nome, email) VALUES ('Cliente Teste', %s)", (EMAILS[3],))

    previa = cliente.post("/email/segmentos/previa?lista=parceiros", json={}).json()
    assert previa["total"] == antes["total"] + 2  # a Carla recusou na planilha
    assert previa["excluidos"]["recusou"] == antes["excluidos"]["recusou"] + 1
    assert cliente.post("/email/segmentos/previa?lista=parceiros",
                        json={"tags": ["teste-agencia"]}).json()["total"] == 1

    tpl_cliente = cliente.post("/email/templates", json={
        "nome": "TESTE cliente", "assunto": "Oi", "html": "<p>oi</p>"}).json()
    tpl = cliente.post("/email/templates", json={
        "nome": "TESTE parceiro", "assunto": "Proposta para {{empresa}}",
        "html": "<p>Olá {{primeiro_nome}}, da {{empresa}}</p>", "lista": "parceiros"}).json()
    assert tpl["lista"] == "parceiros"

    # Cada aba só vê os seus templates.
    nomes = {t["nome"] for t in cliente.get("/email/templates?lista=parceiros").json()}
    assert "TESTE parceiro" in nomes and "TESTE cliente" not in nomes

    # Template de cliente não serve para campanha de parceiro.
    r = cliente.post("/email/campanhas", json={
        "nome": "TESTE errada", "template_id": tpl_cliente["id"], "lista": "parceiros"})
    assert r.status_code == 422

    camp = cliente.post("/email/campanhas", json={
        "nome": "TESTE parceiros", "template_id": tpl["id"], "assunto": tpl["assunto"],
        "lista": "parceiros", "segmento": {"tags": ["teste-hotel", "teste-agencia"]}}).json()
    assert camp["lista"] == "parceiros"
    assert "parcerias@seucliente.com.br" in camp["remetente"]
    assert camp["publico"] == 2

    dest = _sql("SELECT email, parceiro_id, contato_id, vars FROM email.recipients "
                "WHERE campaign_id = %s ORDER BY email_norm", (camp["id"],))
    assert [d["email"].lower() for d in dest] == [EMAILS[0], EMAILS[1]]
    assert all(d["parceiro_id"] and d["contato_id"] is None for d in dest)
    assert dest[0]["vars"]["empresa"] == "Hotel Copacabana 2"

    # A visão geral mostra as duas listas; o filtro, só a da aba.
    todas = cliente.get("/email/campanhas").json()
    assert any(c["id"] == camp["id"] and c["lista"] == "parceiros" for c in todas)
    so_clientes = cliente.get("/email/campanhas?lista=clientes").json()
    assert all(c["id"] != camp["id"] for c in so_clientes)

    # Disparo simulado (EMAIL_DRY_RUN) percorre o caminho inteiro.
    from app.services import campanhas as svc
    from app.config import settings
    import psycopg
    from psycopg.rows import dict_row

    async def disparar():
        async with await psycopg.AsyncConnection.connect(
                settings.database_url, row_factory=dict_row) as conn:
            return await svc.disparar(conn, camp["id"], ADMIN["id"])

    r = asyncio.run(disparar())
    assert r["enviados"] == 2 and r["concluida"]


def test_descadastro_de_parceiro_vale_so_para_a_lista_e_sobrevive_a_reimportacao(cliente):
    _importar(cliente)
    tpl = cliente.post("/email/templates", json={
        "nome": "TESTE parceiro", "html": "<p>x</p>", "lista": "parceiros"}).json()
    camp = cliente.post("/email/campanhas", json={
        "nome": "TESTE parceiros", "template_id": tpl["id"], "lista": "parceiros",
        "segmento": {"tags": ["teste-hotel", "teste-agencia"]}}).json()
    rid = _sql("SELECT id FROM email.recipients WHERE campaign_id = %s AND email_norm = %s",
               (camp["id"], EMAILS[0]))[0]["id"]

    assert cliente.get(f"/unsubscribe?r={rid}").status_code == 200

    assert _sql("SELECT 1 FROM email.supressoes_lista WHERE lista='parceiros' AND email=%s",
                (EMAILS[0],))
    # Não vira bloqueio global: se a Ana também for cliente, continua recebendo.
    assert not _sql("SELECT 1 FROM email.suppressions WHERE email=%s", (EMAILS[0],))

    pagina = cliente.get("/email/parceiros?situacao=descadastrou").json()
    assert EMAILS[0] in [p["email"].lower() for p in pagina["items"]]

    # Apagar a ficha e importar de novo NÃO reinscreve.
    pid = _sql("SELECT id FROM email.parceiros WHERE email_norm=%s", (EMAILS[0],))[0]["id"]
    assert cliente.delete(f"/email/parceiros/{pid}").status_code == 204
    _importar(cliente)
    previa = cliente.post("/email/segmentos/previa?lista=parceiros",
                          json={"tags": ["teste-hotel", "teste-agencia"]}).json()
    assert previa["total"] == 1  # só o Bruno


def test_cadastro_e_edicao_validam_email(cliente):
    r = cliente.post("/email/parceiros", json={"email": "nao-e-email", "empresa": "X"})
    assert r.status_code == 422
    novo = cliente.post("/email/parceiros", json={
        "email": EMAILS[1], "empresa": "Agência", "tags": ["agencia", " agencia "]}).json()
    assert novo["tags"] == ["agencia"] and novo["situacao"] == "recebe"
    dup = cliente.post("/email/parceiros", json={"email": EMAILS[1].upper()})
    assert dup.status_code == 422
    ed = cliente.patch(f"/email/parceiros/{novo['id']}", json={"cargo": "Diretor"}).json()
    assert ed["cargo"] == "Diretor"
    num = cliente.get("/email/parceiros/numeros").json()
    assert num["total"] >= 1

"""O que chega do NichoChat na busca do Google: leitura do corpo, sem banco.

O corpo de referência é o JSON que o fluxo "Buscar Novos comentários" devolveu
no teste do fluxo. O caminho com banco está em
test_leitura_google_banco.py.
"""

import json
from datetime import datetime, timezone

import pytest

from app.services.integracoes import leitor_google as leitor

ITEM = {
    "unidade": "UnidadeSul", "idUnidade": "1000000000000000013",
    "comentario": "(Translated by Google) The pizza arrived cold and the order took more than "
                  "an hour.\n\n(Original)\nA pizza chegou fria e o pedido demorou mais de uma hora.",
    "notaReview": "ONE", "reviewId": "TESTE_UNIDADESUL_DENTRO",
    "displayName": "Cliente Teste Unidade Sul", "dataHora": "2026-10-13T15:05:00.000000Z",
}


def test_acha_a_lista_venha_como_vier():
    saida_do_js = {"status": "ok", "result": [ITEM], "executionTime": "2ms"}
    assert leitor.itens_do_corpo(saida_do_js) == [ITEM]
    assert leitor.itens_do_corpo([ITEM]) == [ITEM]
    assert leitor.itens_do_corpo({"avaliacoes": [ITEM]}) == [ITEM]
    # Variável do NichoChat serializada como texto — às vezes duas vezes.
    assert leitor.itens_do_corpo(json.dumps(saida_do_js)) == [ITEM]
    assert leitor.itens_do_corpo(json.dumps(json.dumps(saida_do_js))) == [ITEM]
    assert leitor.itens_do_corpo({"result": "[]"}) == []


@pytest.mark.parametrize("corpo", [None, "", "  ", b"", "[]", [], {"result": None}])
def test_corpo_vazio_e_busca_sem_novidade(corpo):
    # O fluxo manda o bloco vazio quando não achou nada: a leitura rodou.
    assert leitor.itens_do_corpo(corpo) == []


@pytest.mark.parametrize("corpo", [
    {"status": "ok"}, "isto não é json", 42, {"result": {"reviewId": "x"}},
])
def test_corpo_sem_lista_explica(corpo):
    with pytest.raises(ValueError):
        leitor.itens_do_corpo(corpo)


# ------------------------- comentário em pedaços ----------------------------

@pytest.mark.parametrize("item,esperado", [
    ({"parte": 2, "totalPartes": 3}, (2, 3)),
    ({"parte": "1", "totalPartes": "2"}, (1, 2)),
    ({"parte": 1, "totalPartes": 1}, None),   # inteiro
    ({}, None),
    ({"parte": 4, "totalPartes": 3}, None),
    ({"parte": "x", "totalPartes": 2}, None),
])
def test_pedaco(item, esperado):
    assert leitor.pedaco(item) == esperado


def test_pedacos_viram_um_comentario_so_em_qualquer_ordem():
    texto = ITEM["comentario"]
    corte = [texto[:30], texto[30:90], texto[90:]]
    partes = [{"parte": i + 1, "total": 3,
               "item": {**ITEM, "comentario": c, "parte": i + 1, "totalPartes": 3}}
              for i, c in enumerate(corte)]
    item, completo = leitor.juntar_pedacos([partes[2], partes[0], partes[1]])
    assert completo and item["comentario"] == texto
    assert "parte" not in item and "totalPartes" not in item
    assert leitor.normalizar_item(item)["comentario"] == \
        "A pizza chegou fria e o pedido demorou mais de uma hora."

    item, completo = leitor.juntar_pedacos(partes[:2])
    assert not completo and item["comentario"] == texto[:90]


# ------------------------------ o timer -------------------------------------

def test_proximo_disparo_conta_do_ultimo(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "google_leitura_intervalo_min", 29)
    assert leitor.espera_seg({"minutos": None}) == 0
    assert leitor.espera_seg({"minutos": 10.0, "ultimo_disparo_erro": None}) == 19 * 60
    assert leitor.espera_seg({"minutos": 29.5, "ultimo_disparo_erro": None}) == 0
    # Disparo que falhou é repetido em 1 minuto, não em 29.
    assert leitor.espera_seg({"minutos": 0.5, "ultimo_disparo_erro": "HTTP 500"}) == 30
    # Teto de 30: o fluxo só olha 30 minutos para trás.
    monkeypatch.setattr(settings, "google_leitura_intervalo_min", 60)
    assert leitor.intervalo_min() == 30


def test_padrao_e_29_minutos():
    from app.config import Settings

    assert Settings.model_fields["google_leitura_intervalo_min"].default == 29


def test_item_vira_avaliacao_da_fila():
    av = leitor.normalizar_item(ITEM)
    assert av["id"] == "TESTE_UNIDADESUL_DENTRO" and av["nota"] == 1
    assert av["comentario"] == "A pizza chegou fria e o pedido demorou mais de uma hora."
    assert av["autor"] == "Cliente Teste Unidade Sul"
    assert av["criada_em"] == datetime(2026, 10, 13, 15, 5, tzinfo=timezone.utc)
    assert av["respostas"] == []
    assert leitor.normalizar_item({**ITEM, "resposta": " Sentimos muito "})["respostas"][0]["texto"] \
        == "Sentimos muito"


@pytest.mark.parametrize("valor,esperado", [
    ("ONE", 1), ("FIVE", 5), ("four", 4), (3, 3), ("2", 2), ("", 0), ("SIX", 0), (9, 0), (True, 0),
])
def test_nota(valor, esperado):
    assert leitor.nota(valor) == esperado


@pytest.mark.parametrize("no_fluxo,no_crm", [
    ("ShoppingDMaria", "Shopping D. Maria"),
    ("Paraiso", "Paraíso"),
    ("CasaMesa", "Casa&Mesa"),
    ("ShoppingCentroRecife", "Shopping Centro (Recife)"),
    ("UnidadeSul", "Unidade Sul"),
])
def test_nome_da_unidade_no_fluxo_bate_com_o_do_crm(no_fluxo, no_crm):
    assert leitor.chave_de_nome(no_fluxo) == leitor.chave_de_nome(no_crm)


# ------------------------- confirmação da resposta --------------------------

AVISO = {"reviewId": "abc", "idUnidade": "1000000000000000013", "resposta": "Obrigado!"}


def test_aviso_de_confirmacao_venha_como_vier():
    assert leitor.confirmacoes_do_corpo(AVISO) == [AVISO]
    assert leitor.confirmacoes_do_corpo([AVISO, AVISO]) == [AVISO, AVISO]
    assert leitor.confirmacoes_do_corpo({"status": "ok", "result": AVISO}) == [AVISO]
    assert leitor.confirmacoes_do_corpo(json.dumps(AVISO)) == [AVISO]


def test_aviso_com_json_quebrado_pela_resposta_vale_pelo_review_id():
    # Como o fluxo monta o corpo: a resposta colada entre aspas, com quebra de
    # linha e aspas dentro.
    corpo = ('{\n  "reviewId": "AbFvOqn2",\n  "idUnidade": "1000000000000000009",\n'
             '  "resposta": "Obrigado!\nA "Casa" agradece."\n}')
    assert leitor.confirmacoes_do_corpo(corpo) == [
        {"reviewId": "AbFvOqn2", "idUnidade": "1000000000000000009", "_texto_do_crm": True}]
    falha = '{"reviewId": "AbFvOqn2", "status": "erro", "erro": "review not found", "resposta": "a\nb"}'
    item = leitor.confirmacoes_do_corpo(falha)[0]
    assert leitor._falhou(item) and item["erro"] == "review not found"
    # O nome do campo do NichoChat também serve de chave.
    assert leitor._primeiro({"review_id_resposta": "x"}, *leitor._CHAVES_REVIEW) == "x"


@pytest.mark.parametrize("corpo", ["não é json", [1, 2], 42])
def test_aviso_sem_objeto_explica(corpo):
    with pytest.raises(ValueError):
        leitor.confirmacoes_do_corpo(corpo)


@pytest.mark.parametrize("item,falhou", [
    ({"status": "erro"}, True), ({"status": "ERROR"}, True), ({"ok": False}, True),
    ({"status": "ok"}, False), ({}, False),
])
def test_reconhece_aviso_de_falha(item, falhou):
    assert leitor._falhou(item) is falhou


async def test_laco_dispara_quando_da_a_hora_e_nao_fica_girando(monkeypatch):
    from app.services.integracoes import nichochat

    esperas = iter([0.0, 120.0, 30.0, 0.0, 999.0])
    disparos: list[int] = []
    dormidas: list[float] = []

    async def proxima():
        return next(esperas)

    async def rodar():
        disparos.append(len(dormidas))

    class Fim(Exception):
        pass

    async def dormir(seg):
        dormidas.append(seg)
        if len(dormidas) > 5:
            raise Fim

    monkeypatch.setattr(nichochat, "busca_configurada", lambda: True)
    monkeypatch.setattr(leitor, "_proxima_espera", proxima)
    monkeypatch.setattr(leitor, "rodar_na_api", rodar)
    monkeypatch.setattr(leitor.asyncio, "sleep", dormir)
    with pytest.raises(Fim):
        await leitor.agendar()
    # 45 s de partida; dispara; 1 min de folga; dorme no máximo 1 min por vez
    # (um "Ler agora" no meio recomeça a contagem); dispara de novo na hora.
    assert dormidas == [45, 60, 60, 30, 60, 60]
    assert disparos == [1, 4]

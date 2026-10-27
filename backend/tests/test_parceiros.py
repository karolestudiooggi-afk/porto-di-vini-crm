"""Aba Parceiros — o que dá para provar sem banco.

O caminho completo (importar, montar campanha, disparar, descadastrar) está em
test_parceiros_banco.py, que roda contra um Postgres de teste.
"""

import io

import pytest
from openpyxl import Workbook

from app.config import settings
from app.services import parceiros, render
from app.services.sender import remetente_da_campanha


@pytest.fixture(autouse=True)
def remetentes(monkeypatch):
    # O template não traz remetente: cada cliente põe o seu no .env.
    monkeypatch.setattr(settings, "campanha_from_email", "Cliente Exemplo <contato@seucliente.com.br>")
    monkeypatch.setattr(settings, "campanha_from_email_parceiros",
                        "Cliente Exemplo Parcerias <parcerias@seucliente.com.br>")
    monkeypatch.setattr(settings, "cliente_nome", "Cliente Exemplo")


def test_cada_lista_sai_pelo_seu_remetente():
    assert remetente_da_campanha(None, "parceiros").email == "parcerias@seucliente.com.br"
    assert remetente_da_campanha(None, "clientes").email == "contato@seucliente.com.br"


def test_remetente_gravado_na_campanha_vale_e_lixo_cai_no_da_lista():
    r = remetente_da_campanha("Outro Nome <outro@seucliente.com.br>", "clientes")
    assert (r.nome, r.email) == ("Outro Nome", "outro@seucliente.com.br")
    assert remetente_da_campanha("sem arroba", "parceiros").email == "parcerias@seucliente.com.br"


def test_rodape_do_parceiro_nao_diz_que_ele_e_cadastrado():
    """Dizer "você está cadastrado" para quem nunca se cadastrou é o atalho para
    o botão de spam."""
    _, corpo_parceiro = render.montar("<p>x</p>", "a", {}, "rid", "parceiros")
    _, corpo_cliente = render.montar("<p>x</p>", "a", {}, "rid")
    assert "lista de parceiros" in corpo_parceiro
    assert "cadastrado em Cliente Exemplo" not in corpo_parceiro
    assert "cadastrado em Cliente Exemplo" in corpo_cliente
    assert "parceiros de Cliente Exemplo" in corpo_parceiro
    # O descadastro continua no rodapé dos dois.
    assert "/unsubscribe?r=rid" in corpo_parceiro


def test_variavel_empresa_no_template_de_parceiro():
    vars_ = render.variaveis_de(parceiros.variaveis(
        {"nome": "Ana Souza", "email": "ana@x.com", "empresa": "Hotel Copa"}))
    assunto, _ = render.montar("<p/>", "Proposta para {{empresa}}, {{primeiro_nome}}", vars_, "r")
    assert assunto == "Proposta para Hotel Copa, Ana"


def test_planilha_csv_com_cabecalho_de_comercial():
    csv = ("Razão Social;Nome do contato;E-mail corporativo;Função;Segmento;Obs\n"
           "Hotel Copa;Ana;ana@copa.com;Gerente;hotel|zona sul;ligou em set\n").encode("latin-1")
    [linha] = parceiros.ler_arquivo(csv, "base.csv")
    assert linha["empresa"] == "Hotel Copa"
    assert linha["nome"] == "Ana"
    assert linha["email"] == "ana@copa.com"
    assert linha["cargo"] == "Gerente"
    assert linha["tags"] == ["hotel", "zona sul"]
    assert linha["observacoes"] == "ligou em set"


def test_planilha_xlsx_e_recusa_de_email():
    wb = Workbook()
    ws = wb.active
    ws.append(["Empresa", "Email", "Aceita email"])
    ws.append(["Agência", "b@ag.com", "não"])
    ws.append([None, None, None])  # linha em branco no fim da planilha
    buf = io.BytesIO()
    wb.save(buf)
    linhas = parceiros.ler_arquivo(buf.getvalue(), "base.xlsx")
    assert len(linhas) == 1
    assert linhas[0]["opt_in_email"] is False


def test_formato_errado_e_recusado():
    import pytest

    with pytest.raises(ValueError):
        parceiros.ler_arquivo(b"x", "base.pdf")


def test_segmento_de_parceiro_sempre_aplica_as_regras():
    where, args, label = parceiros._where({})
    assert "supressoes_lista" in where and "email.suppressions" in where
    assert label == "Toda a base de parceiros"
    where, args, label = parceiros._where({"tags": ["hotel"], "ids": [3, "4"]})
    assert args == [["hotel"], [3, 4]]
    assert "seleção manual (2)" in label

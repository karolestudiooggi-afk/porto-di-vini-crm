import io

import pytest
from openpyxl import Workbook

from app.services.importacao import MAX_FILE_SIZE, parse_upload


def test_parse_csv_com_aliases_e_tags():
    rows = parse_upload(
        "Nome completo;Celular;E-mail;Tags;Observação\n"
        "Ana Lima;(21) 99999-0000;ANA@EXAMPLE.COM;vip|newsletter;Cliente antiga\n".encode(),
        "contatos.csv",
    )
    assert rows == [
        {
            "nome": "Ana Lima",
            "telefone": "(21) 99999-0000",
            "email": "ANA@EXAMPLE.COM",
            "primeiro_nome": None,
            "sobrenome": None,
            "genero": None,
            "locale": None,
            "idioma": None,
            "status": None,
            "observacoes": "Cliente antiga",
            "tags": ["newsletter", "vip"],
            # Sem coluna de consentimento no arquivo, fica desconhecido — o import
            # não inventa autorização (ver test_importacao_consentimento.py).
            "opt_in_email": None,
        }
    ]


def test_parse_xlsx():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["nome", "telefone", "email", "tags"])
    sheet.append(["Bruno", "5521999990000", "bruno@example.com", "lead, evento"])
    binary = io.BytesIO()
    workbook.save(binary)

    rows = parse_upload(binary.getvalue(), "contatos.xlsx")

    assert rows[0]["nome"] == "Bruno"
    assert rows[0]["tags"] == ["evento", "lead"]


def test_rejeita_formato_e_tamanho_invalidos():
    with pytest.raises(ValueError, match="formato inválido"):
        parse_upload(b"x", "contatos.txt")
    with pytest.raises(ValueError, match="10 MB"):
        parse_upload(b"x" * (MAX_FILE_SIZE + 1), "contatos.csv")

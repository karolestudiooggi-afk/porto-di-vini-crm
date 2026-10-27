"""Convite de acesso: é a única porta de entrada do CRM."""

import inspect

from app import auth
from app.routers import acesso, usuarios


def test_conta_criada_sozinha_nao_da_acesso():
    """Criar usuário no Supabase Auth por fora não basta.

    O convite é consumido no PRIMEIRO LOGIN, não na criação da senha — é isso que
    mantém o CRM fechado. Quem tem login válido e nenhum convite recebe 403.
    """
    fonte = inspect.getsource(auth)
    assert "_aceitar_convite" in fonte
    assert "acesso não autorizado (sem convite)" in fonte


def test_convite_e_reivindicado_atomicamente():
    """Dois cliques simultâneos não podem criar dois usuários."""
    fonte = inspect.getsource(auth._aceitar_convite)
    assert "status='aceito'" in fonte
    assert "AND status = 'pendente' RETURNING" in fonte


def test_token_e_de_uso_unico():
    """O token é zerado ao criar a senha; o link não serve duas vezes."""
    fonte = inspect.getsource(acesso.salvar)
    assert "SET token = NULL" in fonte


def test_pagina_de_senha_escapa_entrada():
    """E-mail e token vão para o HTML: sem escape, viram injeção."""
    fonte = inspect.getsource(acesso)
    assert "html_lib.escape" in fonte


def test_admin_nao_desativa_a_si_mesmo():
    """Senão dá para ficar sem nenhum admin, e só por SQL para voltar."""
    fonte = inspect.getsource(usuarios.editar_usuario)
    assert "não pode desativar a própria conta" in fonte


def test_reconvidar_cancela_o_convite_anterior():
    """Dois links válidos para a mesma pessoa só criam confusão."""
    fonte = inspect.getsource(usuarios.convidar)
    assert "status='cancelado'" in fonte


def test_convite_sobrevive_a_falha_de_email():
    """Se o SMTP falhar, o link vai na mensagem de erro para envio manual."""
    fonte = inspect.getsource(usuarios.convidar)
    assert "Envie este link à pessoa" in fonte


def test_config_do_email_transacional_existe():
    """Este teste nasceu de um bug em produção.

    O código do convite usava `settings.default_from_email`, que não existia
    neste projeto — o convite era criado e o e-mail falhava com AttributeError.
    Um teste que só monta a config teria pego antes de chegar ao cliente.
    """
    from app.config import settings

    cfg = settings.smtp_transacional()
    for chave in ("host", "port", "use_tls", "user", "password", "from_email"):
        assert chave in cfg


def test_transacional_cai_no_smtp_de_campanha_quando_vazio():
    """Com um provedor só configurado, o convite ainda tem que sair."""
    from app.config import settings

    cfg = settings.smtp_transacional()
    if not settings.email_host:
        assert cfg["host"] == settings.campanha_smtp_host
        assert cfg["from_email"] == settings.campanha_from_email


def test_envio_transacional_usa_a_config_resolvida():
    """Não pode voltar a ler settings.email_host direto — quebra o fallback."""
    import inspect
    from app.services import email_transacional

    fonte = inspect.getsource(email_transacional.enviar)
    assert "settings.smtp_transacional()" in fonte
    assert "settings.email_host" not in fonte

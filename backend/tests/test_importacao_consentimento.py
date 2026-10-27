"""Importação: codificação, consentimento e limpeza de valores vazios.

Estes testes nasceram de uma base real de 24 mil leads exportada do RD Station,
em que 4.194 pessoas tinham marcado que NÃO queriam receber e-mail. O importador
antigo ignorava essa coluna: as 4.194 entrariam como "nunca foi perguntado" e
receberiam campanha. É violação de LGPD, não detalhe de implementação.
"""

from app.services.importacao import _consentimento, _decodificar, _normalize_row


def test_le_utf16_do_rd_station():
    """O RD Station exporta em UTF-16; ler como UTF-8 corrompe tudo em silêncio."""
    texto = "Email\tNome\nana@x.com\tAna\n"
    assert _decodificar(texto.encode("utf-16")) == texto


def test_le_utf8_com_bom_e_latin1():
    assert _decodificar("Nome\nAna\n".encode("utf-8-sig")) == "Nome\nAna\n"
    assert "Ação" in _decodificar("Ação".encode("latin-1"))


def test_recusa_explicita_e_reconhecida():
    for valor in ("false", "FALSE", "Recusado", "não", "opt-out", "unsubscribed"):
        assert _consentimento(valor) is False, valor


def test_consentimento_e_reconhecido():
    for valor in ("true", "Consentimento", "sim", "opt-in"):
        assert _consentimento(valor) is True, valor


def test_vazio_vira_desconhecido_nao_autorizacao():
    """Ausência de informação não pode virar 'pode enviar'."""
    for valor in ("", "-", None, "talvez"):
        assert _consentimento(valor) is None


def test_recusa_em_qualquer_coluna_prevalece():
    """Se o status diz sim mas a base legal diz recusado, vale o não."""
    linha = _normalize_row({
        "Email": "a@x.com",
        "Status para comunicação por email": "true",
        "Base legal para comunicação": "Recusado",
    })
    assert linha["opt_in_email"] is False


def test_consentimento_quando_ambos_confirmam():
    linha = _normalize_row({
        "Email": "a@x.com",
        "Status para comunicação por email": "true",
        "Base legal para comunicação": "Consentimento",
    })
    assert linha["opt_in_email"] is True


def test_sem_coluna_de_consentimento_fica_nulo():
    """Planilha simples, sem a coluna: o CRM decide, o import não inventa."""
    linha = _normalize_row({"Email": "a@x.com", "Nome": "Ana"})
    assert linha["opt_in_email"] is None


def test_literal_none_nao_vira_nome():
    """Exportações trazem o texto 'None'; sem tratar, vira 'Olá None' no e-mail."""
    linha = _normalize_row({"Email": "a@x.com", "Nome": "None", "Sobrenome": "-"})
    assert linha["nome"] is None
    assert linha["sobrenome"] is None


def test_celular_entra_quando_telefone_vem_vazio():
    """Duas colunas de telefone: vale a que tem número.

    Numa base real de 24 mil contatos, a coluna "Telefone" vinha vazia e a
    "Celular" preenchida. Como as duas mapeavam para o mesmo campo, o vazio
    sobrescrevia o número e TODOS foram importados sem telefone.
    """
    linha = _normalize_row({"Email": "a@x.com", "Telefone": "", "Celular": "21999990000"})
    assert linha["telefone"] == "21999990000"


def test_telefone_tem_precedencia_quando_ambos_existem():
    linha = _normalize_row({"Telefone": "2133334444", "Celular": "21999990000"})
    assert linha["telefone"] == "2133334444"


def test_whatsapp_conta_como_celular():
    linha = _normalize_row({"Email": "a@x.com", "WhatsApp": "21988887777"})
    assert linha["telefone"] == "21988887777"


def test_filtro_da_tela_usa_a_mesma_regra_do_disparo():
    """"Recebe campanha?" na tela precisa bater com quem a campanha alcança.

    Se as duas regras divergirem, a tela mostra 500 pessoas e a campanha sai para
    430 — e ninguém entende de onde saiu a diferença.
    """
    import inspect
    from app.routers import contatos
    from app.services import segmentos

    tela = inspect.getsource(contatos._build_filters)
    disparo = segmentos._REGRAS

    for regra in ("email_norm IS NOT NULL",
                  "coalesce(opt_in_email, true) IS TRUE",
                  "email.suppressions"):
        assert regra in tela, f"falta na tela: {regra}"

    # o disparo qualifica com o alias `c.`; a comparação é do conteúdo
    assert "email_norm IS NOT NULL" in disparo
    assert "opt_in_email, true) IS TRUE" in disparo
    assert "email.suppressions" in disparo


def test_todas_as_rotas_conseguem_montar_o_filtro():
    """As duas funções de filtro precisam aceitar os mesmos parâmetros.

    Nasceu de um 500 em produção: `recebe_email` foi acrescentado na CHAMADA de
    `_filters_from_params` mas não na assinatura dela. A lista inteira de
    contatos parou, e a suíte passou — porque nenhum teste chamava a função com
    todos os argumentos.
    """
    import inspect
    from app.routers.contatos import _build_filters, _filters_from_params

    de_params = set(inspect.signature(_filters_from_params).parameters)
    de_build = set(inspect.signature(_build_filters).parameters)
    assert de_params == de_build, f"divergência: {de_params ^ de_build}"

    # e a chamada posicional precisa funcionar de verdade
    filtros = _filters_from_params(
        None, None, None, None, None, None, None, None, None, True
    )
    assert any("suppressions" in w for w in filtros.where)


def test_filtro_de_historico_conta_so_o_que_saiu():
    """"Já recebeu" precisa olhar quem foi ENVIADO, não quem está na fila.

    Quem está pendente ou falhou ainda não recebeu nada e deve continuar
    disponível para o próximo envio — senão a pessoa some da base sem nunca ter
    sido alcançada.
    """
    import inspect
    from app.routers import contatos

    fonte = inspect.getsource(contatos._build_filters)
    assert "r.status = 'enviado'" in fonte
    assert "email.recipients r" in fonte


def test_nunca_recebeu_exclui_quem_esta_agendado():
    """Campanhas montadas no mesmo dia não podem pegar as mesmas pessoas.

    O caso real: montar na segunda as campanhas de terça, quarta e quinta. Se o
    filtro olhasse só `enviado`, nenhuma teria saído ainda — as três seleções
    trariam o mesmo público, e cada pessoa receberia três vezes.
    """
    import inspect
    from app.routers import contatos

    fonte = inspect.getsource(contatos._build_filters)
    assert "'pendente', 'processando'" in fonte


def test_campanha_cancelada_nao_exclui_ninguem():
    """Quem estava numa campanha cancelada não recebeu nada.

    Se contasse como "já recebeu", essa pessoa ficaria fora de toda seleção
    futura sem nunca ter sido alcançada.
    """
    import inspect
    from app.routers import contatos

    fonte = inspect.getsource(contatos._build_filters)
    assert "NOT IN ('cancelada', 'falhou')" in fonte


def test_exclusao_por_periodo_tambem_considera_agendados():
    """O filtro da nova campanha tem o mesmo cuidado."""
    import inspect
    from app.services import segmentos

    fonte = inspect.getsource(segmentos)
    assert "'pendente', 'processando'" in fonte


def test_publico_e_congelado_na_criacao():
    """Sem fila na criação, o filtro de agendados não teria o que excluir.

    Campanhas criadas na segunda para terça, quarta e quinta só ganhavam
    destinatários na hora do disparo. Até lá, as três seleções enxergavam o
    mesmo público "que nunca recebeu" — e a pessoa receberia três vezes.
    """
    import inspect
    from app.routers import email

    assert "svc.materializar" in inspect.getsource(email.criar_campanha)

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ENV, extra="ignore")

    database_url: str
    supabase_url: str = ""
    supabase_jwt_secret: str
    supabase_service_role_key: str = ""
    cors_origins: str = "*"

    # URL pública do CRM. Entra no pixel de abertura, na reescrita dos links e no
    # rodapé de descadastro — errada aqui, os links do e-mail não voltam.
    app_url: str = "http://localhost:3000"

    # --- SMTP do provedor de campanha (SendPulse) --------------------------
    # Separado de qualquer SMTP transacional: provedor de marketing tem
    # reputação e limites próprios, e misturar os dois derruba os dois.
    # Os nomes seguem o padrão CAMPANHA_SMTP_* usado no .env dos outros CRMs, com
    # alias para SMTP_* (como estava aqui antes) — os dois funcionam.
    campanha_smtp_host: str = Field(default="smtp-pulse.com", validation_alias=AliasChoices("CAMPANHA_SMTP_HOST", "SMTP_HOST"))
    campanha_smtp_port: int = Field(default=587, validation_alias=AliasChoices("CAMPANHA_SMTP_PORT", "SMTP_PORT"))
    campanha_smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("CAMPANHA_SMTP_USE_TLS", "SMTP_USE_TLS"))
    campanha_smtp_user: str = Field(default="", validation_alias=AliasChoices("CAMPANHA_SMTP_USER", "SMTP_USER"))
    campanha_smtp_password: str = Field(default="", validation_alias=AliasChoices("CAMPANHA_SMTP_PASSWORD", "SMTP_PASSWORD"))

    # Remetente. IMPORTANTE: o domínio daqui é o que precisa de SPF/DKIM/DMARC no
    # DNS — e não o domínio do login SMTP. São coisas diferentes, e é a confusão
    # entre elas que manda campanha para o spam.
    # Ex.: "Cliente Exemplo <contato@seucliente.com.br>". Obrigatório para enviar.
    campanha_from_email: str = ""
    # Remetente das campanhas da aba Parceiros. Mesma conta SMTP (e mesma cota),
    # outro endereço: quem recebe proposta de parceria não confunde com a
    # newsletter de cliente, e o descadastro de um não mexe no outro.
    # Ex.: "Cliente Exemplo Parcerias <parcerias@seucliente.com.br>".
    campanha_from_email_parceiros: str = ""

    # --- SMTP transacional (convite de acesso, recuperação de senha) -------
    # Separado do de campanha porque são coisas diferentes: transacional é uma
    # mensagem por vez, para quem está esperando por ela, e precisa chegar. Se
    # cair no spam junto com a promocional, a pessoa fica sem conseguir entrar.
    #
    # Vazio? cai no SMTP de campanha (ver smtp_transacional()), para o convite
    # funcionar mesmo com um provedor só configurado.
    email_host: str = ""
    email_port: int = 587
    email_use_tls: bool = True
    email_host_user: str = ""
    email_host_password: str = ""
    default_from_email: str = ""

    # --- Webhooks de parceiros ---------------------------------------------
    # Chave que o parceiro envia no cabeçalho X-API-Key. Vazia = webhook recusa
    # tudo (401), que é o padrão seguro: melhor a integração não funcionar do que
    # aceitar POST de qualquer origem gravando na base do cliente.
    webhook_alphacode_key: str = ""

    # --- Disparador próprio (DESATIVADO) ------------------------------------
    # O envio voltou ao SMTP do SendPulse enquanto o IP do disparador próprio é
    # aquecido. Estas variáveis ficam aqui, sem uso, para a volta ser rápida:
    # ver docs/DISPARADOR-PROPRIO.md.
    disparador_url: str = "https://disparador.estudiodomaniai.com.br"
    disparador_api_key: str = ""

    # --- Limites do plano contratado ----------------------------------------
    # Estourar faz o provedor recusar a conexão no meio do disparo. O envio para
    # ANTES de bater o teto, e a campanha retoma na janela seguinte.
    #
    # O teto MENSAL é o CONTRATADO PELO CLIENTE, não capacidade técnica: quando
    # ele quiser mais, o plano é ajustado e este número sobe junto — por isso vem
    # do .env, para não precisar de deploy por decisão comercial.
    smtp_limite_mes: int = 10_000
    # Teto por hora, imposto pelo provedor.
    smtp_limite_hora: int = 2_500
    # Teto DIÁRIO. É o que controla o ritmo durante o aquecimento de domínio: a
    # regra é subir o volume dia a dia, e sem este limite a cota do mês inteiro
    # poderia sair em algumas horas.
    smtp_limite_dia: int = 800
    # Margem de segurança: nunca usar os últimos N da janela. Protege contra
    # envio manual/transacional concorrente que o CRM não contabiliza.
    smtp_margem: int = 50
    # Pausa entre mensagens. 2.500/h dá uma a cada 1,44s; 1,5s deixa folga e
    # evita que o provedor trate a rajada como abuso.
    #
    # Ao voltar para o disparador próprio, isto sobe para 15s (ele entrega ~4/min
    # no total, somando todos os clientes).
    smtp_intervalo_seg: float = 1.5

    # Segurança: com true (padrão) o disparo é simulado — materializa o público,
    # renderiza e marca "enviado", mas NÃO abre conexão SMTP. Vire para false
    # conscientemente, e só depois de conferir o preview.
    email_dry_run: bool = True

    # --- Integrações: avaliações do iFood e do Google ----------------------
    # Ver docs/INTEGRACOES.md. Tudo vazio = a aba Integrações abre, mas mostra
    # cada integração como "não configurada" em vez de quebrar.
    #
    # Nome do cliente: vai no remetente padrão e no rodapé dos e-mails, no aviso
    # enviado ao NichoChat, no prompt da IA e no título da API.
    cliente_nome: str = "Cliente Exemplo"

    # iFood: credenciais do aplicativo no Developer Portal (client_credentials).
    ifood_client_id: str = ""
    ifood_client_secret: str = ""

    # Google Meu Negócio: conexão DIRETA com o Google, OPCIONAL. As avaliações
    # chegam e as respostas saem pelo NichoChat (ver mais abaixo); isto só
    # serve para conferir uma avaliação no Google na hora em que ela é aberta.
    # O refresh_token não vem do ambiente — nasce quando um admin clica em
    # "Conectar conta Google".
    google_client_id: str = ""
    google_client_secret: str = ""
    # Endereço de retorno cadastrado no Google Cloud. Vazio = derivado de
    # APP_URL (ver google_callback_url). Tem de bater letra por letra com o
    # que está no console, senão o Google recusa com redirect_uri_mismatch.
    google_redirect_uri: str = ""

    # Leitura automática das avaliações do Google: de quantos em quantos
    # minutos o CRM pede ao NichoChat as avaliações novas (5 a 30). Com o fluxo
    # de lá olhando os últimos 30 minutos, 29 faz cada avaliação cair em uma
    # busca só — e um alerta de negativa feito no fluxo não sai dobrado.
    google_leitura_intervalo_min: int = 29

    # IA que escreve a sugestão de resposta.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1/chat/completions"

    # Webhook do NichoChat usado como RESERVA no aviso de avaliação do iFood,
    # quando a tela de configuração não tem um endereço próprio.
    nichochat_webhook_url: str = ""

    # API do NichoChat (Domani). A MESMA chave da sincronização de contatos;
    # precisa do escopo "Manage Flow" para disparar subfluxo. Só no servidor.
    domani_api_url: str = ""
    domani_api_key: str = ""

    # Os contatos do NichoChat em que o CRM dispara os subfluxos do Google. O
    # user_id vai SEM "+": é assim que a API do NichoChat guarda o contato (com
    # "+" ela responde "subscriber not found"). Contato que não existe lá é
    # criado pelo CRM na primeira vez. Vazios = a integração fica desligada.
    # Busca das avaliações novas (ex.: 5521999990000).
    nichochat_contato_user_id: str = Field(
        default="", validation_alias=AliasChoices("NICHOCHAT_CONTATO_USER_ID"))
    # Resposta das avaliações (pode ser o mesmo contato da busca).
    nichochat_resposta_contato_user_id: str = Field(
        default="",
        validation_alias=AliasChoices("NICHOCHAT_RESPOSTA_CONTATO_USER_ID",
                                      "NICHOCHAT_RESPOSTA_GOOGLE_USER_ID"))

    # Leitura do Google: a cada GOOGLE_LEITURA_INTERVALO_MIN o CRM dispara este
    # subfluxo ("Buscar Novos comentários"), que lê as unidades pela conexão
    # Google do NichoChat e devolve as avaliações novas por POST ao CRM.
    # O ns do subfluxo no canal do cliente (ex.: f000000s0000001).
    nichochat_busca_google_subfluxo: str = ""
    # Chave que o NichoChat manda no cabeçalho X-API-Key ao entregar as
    # avaliações. Vazia = o CRM recusa tudo (401), o padrão seguro.
    webhook_google_key: str = ""

    # Resposta de avaliação do Google: o CRM não publica direto no Google. Grava
    # ID_localizacao_resposta, review_id_resposta e resposta_comentario no contato acima
    # e dispara este subfluxo ("Responder Comentários - Google My Business"),
    # que publica pela conexão Google de lá.
    nichochat_resposta_google_subfluxo: str = ""
    # Intervalo mínimo entre dois envios. O contato é o mesmo para todas as
    # respostas: sem esta folga, a segunda poderia trocar os campos antes de o
    # fluxo ler a primeira. Se o fluxo demorar mais que isso, aumente.
    nichochat_resposta_intervalo_seg: float = 10.0

    # --- Monitor de reputação: Tripadvisor e Reclame Aqui -----------------
    # Ver docs/MONITOR-REPUTACAO.md. O CRM lê uma caixa de e-mail que recebe as
    # notificações das duas plataformas. Vazio = a aba aparece, explica como
    # ligar e aceita e-mails enviados à mão (.eml), mas não lê caixa nenhuma.
    monitor_imap_host: str = ""
    monitor_imap_porta: int = 993
    monitor_imap_usuario: str = ""
    # Senha de APP (Gmail/Google Workspace exigem; a senha normal é recusada).
    monitor_imap_senha: str = ""
    monitor_imap_pasta: str = "INBOX"
    monitor_intervalo_min: int = 10
    # Na primeira leitura (ou se a caixa for recriada), quantos dias para trás
    # buscar. É o que traz o histórico para os gráficos já no primeiro dia.
    monitor_historico_dias: int = 180

    @property
    def monitor_caixa_configurada(self) -> bool:
        return bool(self.monitor_imap_host and self.monitor_imap_usuario
                    and self.monitor_imap_senha)

    # Agente do iFood. Igual ao painel de origem: roda SOZINHO dentro da API, a
    # cada 15 minutos, sem timer nem cron. Qualquer valor aqui desliga — útil
    # nas gravações de homologação, para sobrar avaliação pendente na fila.
    worker_desligado: str = ""

    @property
    def agente_ligado(self) -> bool:
        return not self.worker_desligado.strip()

    @property
    def google_callback_url(self) -> str:
        """Para onde o Google devolve o admin depois do consentimento.

        A API fica atrás do nginx em /api/, então o endereço público do
        callback é APP_URL + /api/integracoes/google/callback.
        """
        if self.google_redirect_uri:
            return self.google_redirect_uri
        return f"{self.app_url.rstrip('/')}/api/integracoes/google/callback"

    def smtp_transacional(self) -> dict:
        """Config efetiva do e-mail transacional, com fallback para o de campanha.

        Assim o convite de acesso funciona mesmo quando só o SMTP de campanha
        está preenchido — que é o caso quando se usa um provedor só.
        """
        return {
            "host": self.email_host or self.campanha_smtp_host,
            "port": self.email_port or self.campanha_smtp_port,
            "use_tls": self.email_use_tls,
            "user": self.email_host_user or self.campanha_smtp_user,
            "password": self.email_host_password or self.campanha_smtp_password,
            "from_email": self.default_from_email or self.campanha_from_email,
        }

    @property
    def allowed_origins(self) -> list[str]:
        values = [value.strip() for value in self.cors_origins.split(",")]
        return [value for value in values if value] or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()

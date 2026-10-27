"""E-mails de notificação de EXEMPLO, montados a partir do formato público das
notificações do Tripadvisor e do Reclame Aqui. Não são e-mails reais.

Quando chegar o primeiro e-mail de verdade de cada plataforma, ele entra aqui
(com nome e contato do cliente trocados) e vira teste — é o que impede uma
mudança de regra de quebrar a leitura de novo.
"""

from email.message import EmailMessage

UNIDADES = [
    "PracaCentralHall", "Shopping da Serra", "Shopping Leste", "Shopping Oeste",
    "ShoppingNorte", "Shopping Centro (Recife)", "Shopping Sol", "Casa&Mesa",
    "Shopping Orla", "Paraíso", "Shopping D. Maria", "Design Mall",
    "Unidade Sul", "MesaShopping",
]


def _eml(remetente: str, assunto: str, html: str | None = None, texto: str | None = None,
         msgid: str = "<abc@teste>") -> bytes:
    m = EmailMessage()
    m["From"] = remetente
    m["To"] = "avaliacoes@seucliente.com.br"
    m["Subject"] = assunto
    m["Date"] = "Wed, 07 Oct 2026 21:14:00 -0300"
    m["Message-ID"] = msgid
    if texto is not None:
        m.set_content(texto)
    if html is not None:
        if texto is None:
            m.set_content("versão em texto")
        m.add_alternative(html, subtype="html")
    return m.as_bytes()


def ta_pt(msgid: str = "<abc@teste>", review: str = "987654321",
          data: str = "Wed, 07 Oct 2026 21:14:00 -0300") -> bytes:
    """Avaliação do Tripadvisor em português, com id e data trocáveis."""
    bruto = _eml(
    "Tripadvisor <noreply@tripadvisor.com>",
    "Cliente Exemplo - Unidade Sul recebeu uma nova avaliação",
    msgid=msgid,
    html="""<html><head><style>p{color:red}</style></head><body>
<p>Olá, Cliente Exemplo - Unidade Sul</p>
<p>Um viajante escreveu uma nova avaliação sobre a sua empresa.</p>
<table><tr><td><img src="https://static.tacdn.com/img2/ratings/traveler/ss2.0.svg" alt="2 de 5 bolhas"></td></tr></table>
<p><b>“Pizza fria e demora”</b></p>
<p>Pedimos uma pizza e demorou mais de uma hora. Chegou fria e o garçom foi grosseiro. Achei um cabelo na massa.</p>
<p>Escrita por Joana M. em 7 de outubro de 2026</p>
<a href="https://www.tripadvisor.com.br/ShowUserReviews-g303506-d2343434-r{review}-Cliente_Exemplo_Unidade_Sul-Rio_de_Janeiro.html">Ler avaliação completa</a>
<a href="https://www.tripadvisor.com.br/ManagementCenter-d2343434">Responder a esta avaliação</a>
<p>© 2026 Tripadvisor LLC Todos os direitos reservados.</p>
</body></html>""".replace("{review}", review))
    return bruto.replace(b"Wed, 07 Oct 2026 21:14:00 -0300", data.encode())


TA_PT = ta_pt()


TA_EN_RASTREIO = _eml(
    "Tripadvisor <MemberServices@e.tripadvisor.com>",
    "New review of Cliente Exemplo PracaCentral Hall",
    msgid="<ta-en@teste>",
    html="""<p>Hi Cliente Exemplo,</p>
<p>A traveler wrote a review of your business.</p>
<span class="ui_bubble_rating bubble_50"></span>
<p>"Best pizza in Rio"</p>
<p>Amazing burrata pizza, friendly staff and great wine list. We will come back!</p>
<p>Written by TravelerAnn on October 6, 2026</p>
<a href="https://www.tripadvisor.com/ls/click?url=https%3A%2F%2Fwww.tripadvisor.com%2FShowUserReviews-g303506-d11111111-r555666777-Cliente_Exemplo.html%3Fm%3D1">Read the full review</a>
""")

RA_NOVA = _eml(
    "Reclame AQUI <naoresponda@reclameaqui.com.br>",
    "Nova reclamação: Pedido não entregue e cobrança indevida",
    msgid="<ra-nova@teste>",
    texto="""Olá, Cliente Exemplo!

Você recebeu uma nova reclamação.

Título: Pedido não entregue e cobrança indevida
Consumidor: Carlos Pereira
Cidade: Niterói - RJ
Reclamação: Fiz um pedido na unidade Paraíso pelo app, paguei e nunca chegou. Ninguém atende. Vou acionar o PROCON.

Responder reclamação: https://www.reclameaqui.com.br/cliente-exemplo/pedido-nao-entregue-e-cobranca-indevida_Xk9aBcD3eFgH1jK/

Reclame AQUI - não responda este e-mail.
""")

RA_RESULTADO = _eml(
    "Reclame AQUI <naoresponda@reclameaqui.com.br>",
    "O consumidor avaliou a reclamação",
    msgid="<ra-resultado@teste>",
    texto="""O consumidor avaliou o atendimento da reclamação "Pizza errada no Unidade Sul".
Nota: 9
Resolvida: Sim
Voltaria a fazer negócio: Sim
https://www.reclameaqui.com.br/cliente-exemplo/pizza-errada-no-unidade-sul_AbC123dEf456/
""")

RA_LEMBRETE = _eml(
    "Reclame AQUI <naoresponda@reclameaqui.com.br>",
    "Você tem 3 reclamações sem resposta",
    msgid="<ra-lembrete@teste>",
    texto="Responda dentro do prazo para melhorar sua reputação.")

NEWSLETTER = _eml("Loja X <promo@lojax.com>", "50% OFF hoje", texto="Promoção imperdível.",
                  msgid="<promo@teste>")



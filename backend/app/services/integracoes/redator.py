"""Redige a resposta pública a partir da nota e do comentário.

A resposta é pública — e no iFood é definitiva. As proibições dos prompts não
são preferência de estilo: existem para a IA não criar obrigação que a casa não
autorizou (cupom, reembolso) nem deixar rastro permanente de texto ruim.

O provedor está isolado neste arquivo. Trocar de fornecedor mexe só aqui: o
resto do sistema não sabe quem gera o texto.

Dois prompts padrão, um por origem, porque as regras das plataformas diferem:

  - iFood:  até 300 caracteres, sem emoji. Veio do Domani Avaliações.
  - Google: 2 a 4 frases, em nome do cliente (CLIENTE_NOME) e no tom da
            configuração. Para a voz da marca (quem é, expressões, emojis),
            escreva um prompt próprio na tela — de preferência o mesmo da
            resposta automática do NichoChat, se o cliente tiver uma.

Preencher o prompt na tela de configuração substitui o padrão **por inteiro**,
inclusive as proibições.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.services.integracoes import google, ifood

TOM_PADRAO = "cordial e profissional"

_PROMPT_IFOOD = """Você escreve respostas públicas de um restaurante às avaliações recebidas no iFood.

Regras obrigatórias:
- Entre 40 e 280 caracteres. Nunca ultrapasse 300.
- Português do Brasil, tom {tom}.
- Varie a estrutura e as palavras a cada resposta. Respostas idênticas em sequência ficam visíveis no perfil público e passam impressão de robô.
- Nunca prometa reembolso, cupom, desconto, brinde ou qualquer compensação.
- Nunca peça para o cliente refazer a avaliação ou alterar a nota.
- Nunca cite nome de funcionário, endereço, telefone ou link.
- Não invente fatos sobre o pedido que não estejam no comentário.
- Se a nota for 3 ou menos: reconheça o problema de forma específica, lamente e diga que vai apurar internamente. Sem desculpa genérica.
- Se a nota for 4 ou 5: agradeça de forma específica ao que a pessoa elogiou. Se não houver comentário, agradeça a nota de forma curta.
- Sem emoji.
- Responda apenas com o texto final da resposta. Sem aspas, sem explicação, sem preâmbulo."""

_PROMPT_GOOGLE = """Você é responsável por responder avaliações do Google em nome de {nome}.

# TOM DE VOZ
- Tom {tom}, acolhedor e humano. O cliente deve se sentir ouvido.
- Educado e natural, sem formalidade excessiva.
- A resposta deve parecer escrita por alguém da equipe, nunca por uma inteligência artificial.

# REGRAS
- Sempre agradeça pela avaliação.
- Responda em português brasileiro.
- Personalize a resposta com base no que o cliente escreveu.
- Respostas curtas e objetivas: de 2 a 4 frases.
- Nunca invente informações, produtos, nomes, fatos ou detalhes que o cliente não mencionou.
- Nunca ofereça desconto, cupom, brinde, cortesia, reembolso ou qualquer compensação, e não cite preços, valores ou promoções.
- Não prometa ações específicas (ex.: "vamos trocar o atendente"). Pode dizer que o feedback será levado à equipe.
- Não peça dados pessoais nem telefone na resposta pública.
- Emojis com moderação: no máximo 1, e só quando deixar a mensagem mais calorosa.
- Se a avaliação não tiver texto (apenas estrelas), responda com um agradecimento curto, sem inventar detalhes da experiência.

# COMO RESPONDER
Avaliação positiva:
- Demonstre alegria genuína pelo elogio.
- Valorize de forma natural o que o cliente elogiou.
- Convide para voltar.

Avaliação neutra:
- Agradeça e mostre que o retorno ajuda a melhorar.
- Convide para uma nova visita.

Avaliação negativa:
- Demonstre empatia sincera e peça desculpas quando apropriado.
- Mostre que o feedback será levado à equipe para melhorar a experiência.
- Nunca seja defensivo, irônico, nem discuta ou contradiga o cliente.
- Não use humor em respostas a reclamações.

Retorne apenas o texto da resposta."""

# Sampling por origem. No iFood a temperatura é alta de propósito: respostas
# parecidas em sequência ficam visíveis no perfil público da loja.
_AJUSTE = {
    "ifood": {"max_tokens": 200, "temperature": 0.9},
    "google": {"max_tokens": 500, "temperature": 0.5},
}


class ErroRedator(Exception):
    pass


def prompt_padrao(origem: str, tom: str | None = None) -> str:
    """Exposto para a tela mostrar como ponto de partida de um prompt próprio."""
    tom = (tom or "").strip() or TOM_PADRAO
    if origem == "google":
        return _PROMPT_GOOGLE.format(nome=settings.cliente_nome, tom=tom)
    return _PROMPT_IFOOD.format(tom=tom)


def acabamento(origem: str, texto: str, assinatura: str | None = None) -> str:
    """Guarda de segurança depois da IA: nunca confie só no prompt.

    Tira aspas que o modelo às vezes põe em volta, acrescenta a assinatura se
    couber e garante o limite da plataforma.
    """
    texto = (texto or "").strip().strip('"').strip()
    assinatura = (assinatura or "").strip()

    if origem == "ifood":
        if assinatura and len(texto) + len(assinatura) + 1 <= ifood.MAX_CARACTERES:
            texto = f"{texto} {assinatura}"
        if len(texto) > ifood.MAX_CARACTERES:
            texto = texto[: ifood.MAX_CARACTERES - 3].strip() + "..."
        if len(texto) < ifood.MIN_CARACTERES:
            raise ErroRedator("a resposta gerada ficou curta demais")
        return texto

    if assinatura:
        texto = f"{texto}\n{assinatura}"
    # O limite do Google é em bytes. Uma resposta de 2 a 4 frases nunca chega
    # perto; o corte existe para um prompt próprio que saia do controle.
    while len(texto.encode("utf-8")) > google.MAX_BYTES:
        texto = texto[:-50].rstrip()
    if not texto:
        raise ErroRedator("a IA não devolveu nenhum texto")
    return texto


async def escrever(origem: str, cfg: dict, nota: int, comentario: str,
                   assinatura: str | None = None,
                   http: httpx.AsyncClient | None = None) -> str:
    """Gera a resposta para uma avaliação.

    `cfg` é a linha de `integra.config` daquela origem. `assinatura` é a efetiva
    (a da loja, ou a da config quando a loja não tem a própria).
    """
    # Chave e modelo vêm SÓ do .env do servidor. Nenhuma chave de API é
    # digitada, guardada no banco ou devolvida para a tela.
    chave = settings.openai_api_key
    if not chave:
        raise ErroRedator(
            "a sugestão por IA está desligada: falta OPENAI_API_KEY no .env do servidor")

    instrucoes = (cfg.get("prompt") or "").strip() or prompt_padrao(origem, cfg.get("tom"))
    modelo = settings.openai_model
    comentario = (comentario or "").strip() or "(sem comentário)"

    payload = {
        "model": modelo,
        **_AJUSTE[origem],
        "messages": [
            {"role": "system", "content": instrucoes},
            {"role": "user",
             "content": f"Nota: {nota} de 5\nComentário do cliente: {comentario}"},
        ],
    }
    cabecalhos = {"Authorization": f"Bearer {chave}"}

    try:
        if http is not None:
            res = await http.post(settings.openai_base_url, json=payload, headers=cabecalhos)
        else:
            async with httpx.AsyncClient(timeout=60) as cli:
                res = await cli.post(settings.openai_base_url, json=payload, headers=cabecalhos)
    except httpx.HTTPError as exc:
        raise ErroRedator(f"não foi possível falar com a IA: {exc}") from exc

    try:
        corpo = res.json()
    except ValueError as exc:
        raise ErroRedator(f"resposta ilegível da IA (HTTP {res.status_code})") from exc

    erro = corpo.get("error") if isinstance(corpo, dict) else None
    if isinstance(erro, dict) and erro.get("message"):
        raise ErroRedator(erro["message"])
    if res.status_code != 200:
        raise ErroRedator(f"a IA respondeu HTTP {res.status_code}")

    escolhas = corpo.get("choices") or []
    if not escolhas:
        raise ErroRedator("a IA não devolveu nenhum texto")

    texto = ((escolhas[0].get("message") or {}).get("content") or "")
    return acabamento(origem, texto, assinatura)

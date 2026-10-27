"""Do e-mail de notificação para a avaliação/reclamação.

Cada plataforma tem um leitor (`tripadvisor`, `reclameaqui`) que devolve um
dicionário com o que conseguiu achar. O que não achou fica `None` — nada é
inventado. Quando falta o essencial (o texto, a nota), o item sai marcado como
parcial e, se houver chave da OpenAI, a IA completa a partir do mesmo e-mail
(ver `monitor.completar_com_ia`). O e-mail original fica guardado: melhorar
uma regra aqui e reprocessar corrige o histórico inteiro.

As regras procuram padrão em português E em inglês: a conta do Tripadvisor
pode estar configurada em qualquer um dos dois, e o layout muda sem aviso.
"""

from __future__ import annotations

import re
import unicodedata

from app.config import settings
from app.services.integracoes.email_bruto import Email

ORIGENS = ("tripadvisor", "reclameaqui")
NOME = {"tripadvisor": "Tripadvisor", "reclameaqui": "Reclame Aqui"}


# --------------------------------- texto ------------------------------------

def normalizar(texto: str | None) -> str:
    """minúsculo, sem acento, espaços simples — para comparar e procurar."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def palavras_criticas(texto: str, palavras: list[str]) -> list[str]:
    """Quais palavras de crise aparecem no texto.

    Pelo começo da palavra e sem acento: "procon" pega "PROCON", "intoxica"
    pega "intoxicação", "processo" pega "processos". Não pega no meio da
    palavra ("vidro" não acende em "envidraçado").
    """
    alvo = normalizar(texto)
    achadas: list[str] = []
    for p in palavras:
        n = normalizar(p)
        if not n:
            continue
        padrao = r"(?<![a-z0-9])" + r"\s+".join(re.escape(x) for x in n.split())
        if re.search(padrao, alvo) and p not in achadas:
            achadas.append(p)
    return achadas


def sem_nome_do_cliente(nome_local: str) -> str:
    """O nome do local sem o nome do cliente na frente (CLIENTE_NOME):
    "Cliente Exemplo - Unidade Centro" vira "Unidade Centro"."""
    palavras = [re.escape(p) for p in settings.cliente_nome.split()]
    if not palavras:
        return nome_local
    padrao = r"(?i)^" + r"\s*".join(palavras) + r"\s*[-–|:]?\s*"
    return re.sub(padrao, "", nome_local).strip() or nome_local


def casar_unidade(texto: str, unidades: list[str]) -> str | None:
    """A unidade citada no texto, entre as cadastradas. A mais longa vence
    ("Shopping Centro" antes de "Centro"). Compara também sem espaço, porque o
    cadastro pode ter "UnidadeCentro" e o e-mail escrever "Unidade Centro".
    """
    alvo = normalizar(texto)
    alvo_junto = alvo.replace(" ", "")
    melhor: tuple[int, str] | None = None
    for u in unidades:
        base = normalizar(re.sub(r"\(.*?\)", "", u))  # "Unidade Centro (Rio)"
        if len(base) < 4:
            continue
        junto = base.replace(" ", "").replace("&", "")
        achou = (re.search(r"(?<![a-z0-9])" + re.escape(base) + r"(?![a-z0-9])", alvo)
                 or (len(junto) >= 8 and junto in alvo_junto.replace("&", "")))
        if achou and (melhor is None or len(base) > melhor[0]):
            melhor = (len(base), u)
    return melhor[1] if melhor else None


# Linhas que são da plataforma, não do cliente. Usadas para achar o texto da
# avaliação por exclusão quando o layout não traz rótulo.
_RODAPE = (
    "tripadvisor", "management center", "gerenciamento", "©", "copyright",
    "privacidade", "privacy", "cancelar inscri", "unsubscribe", "descadastr",
    "preferencias de e-mail", "preferencias de email", "email preferences",
    "este e-mail foi", "este email foi", "this email was", "this e-mail was",
    "clique aqui", "click here", "baixe o app", "download the app", "app store",
    "google play", "termos de uso", "terms of use", "enviado para", "sent to",
    "ler mais", "read more", "leia mais", "todos os direitos", "rights reserved",
    "central de ajuda", "help center", "reclameaqui", "hugme", "nao responda",
    "do not reply", "voce recebeu este", "you received this", "voce esta recebendo",
    "you are receiving", "escreveu uma avaliacao", "wrote a review",
    "nova avaliacao", "new review", "recebeu uma nova reclamacao",
    "recebeu uma reclamacao",
)


def _paragrafos_do_cliente(e: Email, ignorar: list[str]) -> list[str]:
    ignorar_n = {normalizar(x) for x in ignorar if x}
    saida = []
    for linha in e.texto.splitlines():
        l = linha.strip().strip("“”\"'")
        n = normalizar(l)
        if len(n) < 25 or n in ignorar_n:
            continue
        if any(m in n for m in _RODAPE):
            continue
        if re.match(r"^(https?://|www\.)", n):
            continue
        saida.append(l)
    return saida


def _limpar_trecho(t: str | None) -> str | None:
    if not t:
        return None
    t = re.sub(r"\s*(\.{3}|…)?\s*(ler mais|leia mais|read more|mais)\s*$", "…", t.strip(), flags=re.I)
    t = t.strip().strip("“”\"'").strip()
    return t or None


def _rotulo(texto: str, *rotulos: str) -> str | None:
    """Valor depois de "Rótulo:" numa linha ("Consumidor: Carlos")."""
    for r in rotulos:
        m = re.search(rf"(?im)^\s*{r}\s*[:\-–]\s*(.+?)\s*$", texto)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _primeiro_link(e: Email, *trechos: str) -> str | None:
    for _, url in e.links:
        if url.lower().startswith("http") and all(t in url.lower() for t in trechos):
            return url
    return None


# --------------------------------- origem -----------------------------------

def origem_de(e: Email) -> str | None:
    """De qual plataforma é o e-mail — pelo remetente; se encaminhado, pelo
    conteúdo (o encaminhamento troca o remetente, mas os links continuam)."""
    rem = e.remetente
    if "tripadvisor" in rem:
        return "tripadvisor"
    if "reclameaqui" in rem or "hugme" in rem:
        return "reclameaqui"
    corpo = (e.texto + " " + " ".join(u for _, u in e.links)).lower()
    ta = corpo.count("tripadvisor.")
    ra = corpo.count("reclameaqui.com.br") + corpo.count("hugme")
    if ta == ra == 0:
        assunto = normalizar(e.assunto)
        if "tripadvisor" in assunto:
            return "tripadvisor"
        if "reclame aqui" in assunto or "reclameaqui" in assunto:
            return "reclameaqui"
        return None
    return "tripadvisor" if ta > ra else "reclameaqui"


def parece_da_plataforma(remetente: str, assunto: str) -> bool:
    """Triagem pelo cabeçalho, antes de baixar o e-mail inteiro do IMAP."""
    r, a = remetente.lower(), normalizar(assunto)
    return (any(x in r for x in ("tripadvisor", "reclameaqui", "hugme"))
            or any(x in a for x in ("tripadvisor", "reclame aqui", "reclameaqui",
                                     "avaliacao", "reclamacao", "review")))


# ------------------------------- Tripadvisor --------------------------------

_TA_AVALIACAO = ("nova avaliacao", "new review", "escreveu uma avaliacao", "wrote a review",
                 "recebeu uma avaliacao", "recebeu uma nova avaliacao", "avaliacao de",
                 "avaliacao sobre", "review of", "review for", "postou uma avaliacao",
                 "posted a review", "nova opiniao", "new rating", "avaliou")


def _nota_tripadvisor(e: Email) -> float | None:
    fontes = " ".join(e.alts) + " " + e.html + " " + e.texto
    padroes = (
        r"(\d(?:[.,]\d)?)\s*(?:de|of|/)\s*5\s*(?:bolhas|bolha|circulos|círculos|bubbles|bubble|estrelas|stars|pontos)",
        r"bubble[_-]?(\d)0\b",
        r"ratings/[^\s\"']*?(\d)(?:\.0|_0)?(?:-\w+)?\.(?:svg|gif|png)",
        r"(?:nota|rating|classifica[cç][aã]o|avaliou com)\s*[:=]?\s*(\d)(?:[.,]0)?\b",
    )
    for p in padroes:
        m = re.search(p, fontes, flags=re.I)
        if m:
            try:
                n = float(m.group(1).replace(",", "."))
            except ValueError:
                continue
            if 1 <= n <= 5:
                return n
    return None


_AUTOR_GENERICO = {"um viajante", "uma viajante", "a traveler", "a traveller", "alguem",
                   "someone", "um cliente", "um usuario", "a user", "a guest", "um hospede"}


def tripadvisor(e: Email, unidades: list[str]) -> dict | None:
    """None quando o e-mail é do Tripadvisor mas não é de avaliação nova
    (ranking, newsletter, dica de marketing)."""
    assunto_n = normalizar(e.assunto)
    links = " ".join(u for _, u in e.links)
    tem_link_de_review = bool(re.search(r"ShowUserReviews|OwnerResponse|reviewId|-r\d{5,}-", links, re.I))
    if not (any(x in assunto_n for x in _TA_AVALIACAO) or tem_link_de_review):
        return None

    externo = None
    for p in (r"-r(\d{5,})-", r"[?&](?:review|reviewId|review_id)=(\d{5,})", r"/review[s]?/(\d{5,})"):
        m = re.search(p, links + " " + e.html, flags=re.I)
        if m:
            externo = m.group(1)
            break
    m = re.search(r"-d(\d{4,})-|[?&](?:detail|locationId|location_id|d)=(\d{4,})|ManagementCenter-d(\d{4,})",
                  links + " " + e.html, flags=re.I)
    loja_id = next((g for g in (m.groups() if m else ()) if g), None)

    # Nome do local como o Tripadvisor escreve: no assunto ou na saudação.
    nome_local = None
    for p in (r"avalia[cç][aã]o (?:de|sobre|para|do|da) (.+?)(?:\s+no tripadvisor)?$",
              r"review (?:of|for) (.+?)(?:\s+on tripadvisor)?$",
              r"^(.+?) recebeu uma (?:nova )?avalia[cç][aã]o",
              r"^(.+?) has a new review"):
        m = re.search(p, e.assunto, flags=re.I)
        if m:
            nome_local = m.group(1).strip(" -:|\"“”")
            break
    if not nome_local:
        m = re.search(r"(?im)^\s*(?:ol[aá]|hello|hi|prezad[oa]s?)\s*,?\s+(.+?)[!,.]?\s*$", e.texto)
        nome_local = m.group(1).strip() if m else None
    unidade = casar_unidade(" ".join(filter(None, [nome_local, e.assunto, e.texto])), unidades)
    if not unidade and nome_local:
        unidade = sem_nome_do_cliente(nome_local)

    # Título: o primeiro trecho entre aspas.
    titulo = None
    m = re.search(r"[“\"]([^”\"\n]{3,200})[”\"]", e.texto)
    if m:
        titulo = m.group(1).strip()

    autor = None
    for p in (r"(?i:escrit[ao] por|written by|review by|postad[ao] por|posted by)\s+([A-ZÀ-Ú][\wÀ-ú.'\- ]{1,40}?)(?:\s+em\s|\s+on\s|\s*[,(\n]|\.?\s*$)",
              r"^([A-ZÀ-Ú][\wÀ-ú.'\- ]{1,40}?) (?:escreveu|wrote|avaliou)\b"):
        for m in re.finditer(p, e.texto, flags=re.M):
            candidato = m.group(1).strip()
            # "Um viajante escreveu…" é a frase padrão do aviso, não o autor.
            if normalizar(candidato) not in _AUTOR_GENERICO:
                autor = candidato
                break
        if autor:
            break

    paragrafos = _paragrafos_do_cliente(e, [e.assunto, titulo or "", nome_local or ""])
    texto = None
    if titulo:
        # O texto é o que vem logo depois do título.
        linhas = e.texto.splitlines()
        for i, l in enumerate(linhas):
            if titulo in l:
                seguinte = [x for x in linhas[i + 1:i + 6] if x.strip() in paragrafos]
                if seguinte:
                    texto = seguinte[0]
                break
    if not texto and paragrafos:
        texto = max(paragrafos, key=len)

    nota = _nota_tripadvisor(e)
    link = (_primeiro_link(e, "tripadvisor", "showuserreviews")
            or _primeiro_link(e, "tripadvisor", "review")
            or _primeiro_link(e, "tripadvisor"))
    return {
        "tipo": "avaliacao", "externo_id": externo, "loja_id": loja_id,
        "unidade": unidade, "nota": nota, "nota_maxima": 5,
        "titulo": titulo, "texto": _limpar_trecho(texto), "autor": autor,
        "cidade": None, "link": link,
    }


# ------------------------------- Reclame Aqui -------------------------------

def _tipo_reclameaqui(assunto: str, texto: str) -> str | None:
    a = normalizar(assunto)
    t = normalizar(texto[:600])
    if any(x in a for x in ("nova reclamacao", "recebeu uma reclamacao", "recebeu uma nova reclamacao",
                            "reclamacao nova", "new complaint")):
        return "reclamacao"
    if any(x in a for x in ("avaliou", "foi avaliada", "avaliacao do consumidor", "avaliacao da reclamacao",
                            "reclamacao avaliada", "nota do consumidor")):
        return "resultado"
    if any(x in a for x in ("replica", "respondeu", "nova mensagem", "nova interacao", "comentou",
                            "consumidor enviou", "mensagem do consumidor", "nova resposta")):
        return "interacao"
    # Assunto genérico ("Reclame AQUI - Cliente Exemplo"): decide pelo começo do texto.
    if "nova reclamacao" in t or "recebeu uma reclamacao" in t:
        return "reclamacao"
    if "avaliou" in t and "nota" in t:
        return "resultado"
    if "replica" in t or "respondeu a sua resposta" in t:
        return "interacao"
    return None


def reclameaqui(e: Email, unidades: list[str]) -> dict | None:
    """None para aviso que não é reclamação nem movimento dela (relatório,
    lembrete de prazo, newsletter)."""
    tipo = _tipo_reclameaqui(e.assunto, e.texto)
    if tipo is None:
        return None

    links = " ".join(u for _, u in e.links)
    externo = None
    for p in (r"reclameaqui\.com\.br/[^/\s]+/[^/\s?#]*_([A-Za-z0-9-]{8,24})/?",
              r"(?:ticket|tickets|reclamacao|reclamacoes|complaint)s?/(?:detalhe/)?(\d{5,})",
              r"(?i)(?:id da reclama[cç][aã]o|protocolo|c[oó]digo)\s*[:#]\s*([A-Za-z0-9-]{5,24})"):
        m = re.search(p, links + "\n" + e.texto)
        if m:
            externo = m.group(1)
            break

    titulo = _rotulo(e.texto, "T[ií]tulo", "Assunto da reclama[cç][aã]o", "Reclama[cç][aã]o sobre")
    if not titulo:
        m = re.search(r"(?i)(?:nova reclama[cç][aã]o|reclama[cç][aã]o)\s*[:\-–]\s*(.+?)(?:\s+[-–|]\s+.*)?$", e.assunto)
        if m:
            titulo = m.group(1).strip()
    if not titulo:
        m = re.search(r"[“\"]([^”\"\n]{3,200})[”\"]", e.texto)
        titulo = m.group(1).strip() if m else None

    autor = _rotulo(e.texto, "Consumidor", "Cliente", "Reclamante", "Nome", "Autor")
    cidade = _rotulo(e.texto, "Cidade", "Local", "Localiza[cç][aã]o")
    if not cidade:
        m = re.search(r"\b([A-ZÀ-Ú][A-Za-zÀ-ú' ]{2,30}\s*[-/]\s*[A-Z]{2})\b", e.texto)
        cidade = m.group(1).strip() if m else None

    texto = _rotulo(e.texto, "Reclama[cç][aã]o", "Descri[cç][aã]o", "Relato", "Mensagem",
                    "R[eé]plica", "Coment[aá]rio", "Texto")
    if not texto:
        par = _paragrafos_do_cliente(e, [e.assunto, titulo or "", autor or ""])
        texto = max(par, key=len) if par else None

    nota = None
    if tipo == "resultado":
        m = re.search(r"(?i)nota\s*(?:final|do consumidor|de atendimento)?\s*[:=]?\s*(\d{1,2}(?:[.,]\d)?)", e.texto)
        if m:
            n = float(m.group(1).replace(",", "."))
            nota = n if 0 <= n <= 10 else None
        resolvido = _rotulo(e.texto, "Resolvid[ao]", "Problema resolvido")
        voltaria = _rotulo(e.texto, "Voltaria a fazer neg[oó]cio", "Faria neg[oó]cio novamente")
        extra = " · ".join(x for x in (
            f"resolvida: {resolvido}" if resolvido else "",
            f"voltaria: {voltaria}" if voltaria else "") if x)
        if extra:
            titulo = f"{titulo} ({extra})" if titulo else extra

    unidade = casar_unidade(" ".join(filter(None, [titulo, texto, e.assunto])), unidades)
    link = (_primeiro_link(e, "reclameaqui.com.br", "_")
            or _primeiro_link(e, "hugme")
            or _primeiro_link(e, "reclameaqui"))
    return {
        "tipo": tipo, "externo_id": externo, "loja_id": None,
        "unidade": unidade, "nota": nota, "nota_maxima": 10 if tipo == "resultado" else None,
        "titulo": titulo, "texto": _limpar_trecho(texto), "autor": autor,
        "cidade": cidade, "link": link,
    }


LEITORES = {"tripadvisor": tripadvisor, "reclameaqui": reclameaqui}


# ------------------------------ classificação -------------------------------

def nivel(item: dict) -> str | None:
    """negativa | neutra | positiva — o que a tela e o aviso usam para cor e rota."""
    tipo, nota = item.get("tipo"), item.get("nota")
    if tipo == "reclamacao":
        return "negativa"
    if nota is None:
        return None
    nota = float(nota)
    if (item.get("nota_maxima") or 5) == 10:
        return "negativa" if nota <= 4 else "neutra" if nota <= 6 else "positiva"
    return "negativa" if nota <= 2 else "neutra" if nota < 4 else "positiva"


def faltando(item: dict) -> list[str]:
    """O que o leitor não achou e faz falta para o item ser útil."""
    falta = []
    if not item.get("texto"):
        falta.append("texto")
    if item.get("tipo") == "avaliacao" and item.get("nota") is None:
        falta.append("nota")
    if not item.get("unidade") and item.get("origem") == "tripadvisor":
        falta.append("unidade")
    return falta

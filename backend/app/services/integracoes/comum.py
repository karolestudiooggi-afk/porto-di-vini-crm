"""Pequenas leituras compartilhadas entre as integrações."""

from datetime import datetime, timezone

_FORMATOS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def momento(valor) -> datetime | None:
    """Lê datas em mais de um formato, devolvendo sempre com fuso.

    Sem isso, uma data fora do RFC3339 derrubaria a listagem inteira, e não só
    aquele campo. Data sem fuso é tratada como UTC, que é o que as duas APIs
    usam. Valor ilegível vira `None` em vez de erro.
    """
    if not valor or not isinstance(valor, str):
        return None
    texto = valor.strip().replace("Z", "+00:00")
    # As APIs às vezes mandam mais de 6 casas decimais (o Google manda 9); o
    # strptime só aceita 6.
    if "." in texto:
        cabeca, _, resto = texto.partition(".")
        n = 0
        while n < len(resto) and resto[n].isdigit():
            n += 1
        # resto[:n] são as casas decimais; resto[n:] é o fuso, se houver.
        texto = f"{cabeca}.{resto[:n][:6]}{resto[n:]}"
    for formato in _FORMATOS:
        try:
            lido = datetime.strptime(texto, formato)
        except ValueError:
            continue
        return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)
    return None

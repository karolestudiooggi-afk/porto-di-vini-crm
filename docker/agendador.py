"""Agendador do CRM no Docker — faz o papel dos timers do systemd.

* **Sync Domani -> banco** (`python -m sync.main`): nos horários de
  `SYNC_HORARIOS`, no fuso America/Sao_Paulo. Padrão "06:00", como o
  `crm-*-sync.timer` do template. Aceita mais de um: "06:00,13:00".
* **Continuação de campanhas** (`python -m app.services.agenda`): toda hora
  cheia, como o `crm-*-agenda.timer`. Continua campanhas maiores que a cota e
  dispara as agendadas.

Um trabalho de cada vez, nunca dois em paralelo. Se o container estava parado
na hora marcada, o trabalho roda assim que ele volta (o `Persistent=true` do
systemd): o último horário cumprido de cada um fica em
`/estado/agendador.json`, no volume `estado`.

Na primeira vez que sobe (sem esse arquivo), o sync do horário corrente é dado
como feito — o `scripts/instalar.sh` acabou de rodar o primeiro. A continuação
de campanhas roda logo; é segura a qualquer momento.

Falha não é repetida em loop: fica no log (`docker compose logs agendador`) e
o trabalho volta no próximo horário. Os dois são idempotentes.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
ESTADO = Path(os.getenv("AGENDADOR_ESTADO", "/estado/agendador.json"))
INTERVALO_SEG = 30

# nome -> (comando, tempo máximo em segundos)
TRABALHOS: dict[str, tuple[list[str], int]] = {
    "sync": (["python", "-m", "sync.main"], 2 * 3600),
    "campanhas": (["python", "-m", "app.services.agenda"], 3600),
}


def ler_horarios(texto: str) -> list[tuple[int, int]]:
    """'06:00, 13:30' -> [(6, 0), (13, 30)]. Erro de digitação para o container."""
    horarios = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        h, _, m = parte.partition(":")
        hora, minuto = int(h), int(m or 0)
        if not (0 <= hora < 24 and 0 <= minuto < 60):
            raise ValueError(f"horário inválido em SYNC_HORARIOS: {parte!r}")
        horarios.add((hora, minuto))
    if not horarios:
        raise ValueError("SYNC_HORARIOS vazio")
    return sorted(horarios)


def ultimo_sync_devido(agora: datetime, horarios: list[tuple[int, int]]) -> datetime:
    """O horário de sync mais recente que já passou (pode ser de ontem)."""
    for dias in (0, 1):
        dia = (agora - timedelta(days=dias)).date()
        candidatos = [
            datetime(dia.year, dia.month, dia.day, h, m, tzinfo=FUSO) for h, m in horarios
        ]
        passados = [c for c in candidatos if c <= agora]
        if passados:
            return max(passados)
    raise AssertionError("inalcançável: sempre há um horário nas últimas 24h")


def ultima_hora_cheia(agora: datetime) -> datetime:
    return agora.replace(minute=0, second=0, microsecond=0)


def horario_devido(nome: str, agora: datetime, horarios: list[tuple[int, int]]) -> datetime:
    return ultimo_sync_devido(agora, horarios) if nome == "sync" else ultima_hora_cheia(agora)


def pendentes(agora: datetime, estado: dict, horarios: list[tuple[int, int]]) -> list[str]:
    """Trabalhos cujo último horário devido ainda não foi cumprido."""
    fila = []
    for nome in TRABALHOS:
        feito = estado.get(nome)
        if feito is None or datetime.fromisoformat(feito) < horario_devido(nome, agora, horarios):
            fila.append(nome)
    return fila


def carregar() -> dict | None:
    try:
        return json.loads(ESTADO.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log(f"registro ilegível ({exc}); recomeçando do zero")
        return None


def salvar(estado: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, indent=2))
    tmp.replace(ESTADO)


def log(msg: str) -> None:
    print(f"{datetime.now(FUSO):%Y-%m-%d %H:%M:%S} agendador: {msg}", flush=True)


def rodar(nome: str) -> None:
    comando, limite = TRABALHOS[nome]
    log(f"{nome}: começou ({' '.join(comando)})")
    inicio = time.monotonic()
    try:
        codigo = subprocess.run(comando, cwd="/app", timeout=limite).returncode
    except subprocess.TimeoutExpired:
        log(f"{nome}: PASSOU DE {limite // 60} min e foi interrompido")
        return
    duracao = int(time.monotonic() - inicio)
    if codigo == 0:
        log(f"{nome}: ok em {duracao}s")
    else:
        log(f"{nome}: FALHOU (código {codigo}) em {duracao}s — volta no próximo horário")


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    horarios = ler_horarios(os.getenv("SYNC_HORARIOS", "06:00"))
    log("sync Domani às " + ", ".join(f"{h:02d}:{m:02d}" for h, m in horarios)
        + " e campanhas toda hora cheia (America/Sao_Paulo)")

    estado = carregar()
    if estado is None:
        agora = datetime.now(FUSO)
        estado = {"sync": ultimo_sync_devido(agora, horarios).isoformat()}
        salvar(estado)
        log("primeira vez: o sync de agora fica por conta do instalar.sh")

    while True:
        agora = datetime.now(FUSO)
        for nome in pendentes(agora, estado, horarios):
            rodar(nome)
            estado[nome] = horario_devido(nome, agora, horarios).isoformat()
            salvar(estado)
        time.sleep(INTERVALO_SEG)


if __name__ == "__main__":
    main()

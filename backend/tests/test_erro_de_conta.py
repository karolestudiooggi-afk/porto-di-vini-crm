"""Erro de CONTA não pode virar bounce.

Em outubro/2026 a conta do SendPulse venceu e ele respondeu
"554 5.9.1 Account expired" para cada destinatário. O CRM leu o 554 como
endereço inválido e bloqueou 900 clientes em três campanhas — que ainda
apareceram na tela como "Enviada", com 0 enviados.
"""

import asyncio
import smtplib
from types import SimpleNamespace

from app.services import campanhas
from app.services.sender import ErroPermanente, ErroTemporario, _classificar


# --------------------------------------------------------------- classificação

def test_conta_vencida_e_temporario():
    erro = _classificar(smtplib.SMTPResponseException(554, b"5.9.1 Account expired."))
    assert isinstance(erro, ErroTemporario)


def test_endereco_inexistente_continua_permanente():
    erro = _classificar(smtplib.SMTPResponseException(
        550, b"5.1.1 The email account that you tried to reach does not exist"))
    assert isinstance(erro, ErroPermanente)


# ------------------------------------------------------ banco simulado mínimo

class _Res:
    def __init__(self, rows):
        self.rows = rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class _Banco:
    def __init__(self, n):
        self.dest = {f"r{i}": {"id": f"r{i}", "email": f"cliente{i}@x.com", "nome": None,
                               "vars": {}, "status": "pendente", "erro": None}
                     for i in range(n)}
        self.supressoes: dict[str, str] = {}
        self.eventos: list[str] = []
        self.status_campanha = "agendada"

    async def commit(self):
        pass

    async def execute(self, sql, params=()):
        q = " ".join(sql.split())
        if "FROM email.campaigns c" in q:
            return _Res([{"status": self.status_campanha, "assunto": "x", "html": "<p>x</p>",
                          "remetente": None, "lista": "clientes"}])
        if "FOR UPDATE SKIP LOCKED" in q:
            fila = [d for d in self.dest.values() if d["status"] == "pendente"]
            for d in fila:
                d["status"] = "processando"
            return _Res([dict(d) for d in fila])
        if q.startswith("SELECT count(*)"):
            alvo = "enviado" if "'enviado'" in q else "pendente"
            return _Res([{"n": sum(d["status"] == alvo for d in self.dest.values())}])
        if q.startswith("UPDATE email.campaigns"):
            if params and params[0] in ("enviada", "enviando", "falhou"):
                self.status_campanha = params[0]
            return _Res([])
        if "SET status='enviado'" in q:
            self.dest[params[0]]["status"] = "enviado"
        elif "SET status='suprimido'" in q:
            self.dest[params[1]].update(status="suprimido", erro=params[0])
        elif "SET status='pendente', erro=" in q:
            self.dest[params[1]].update(status="pendente", erro=params[0])
        elif "SET status = 'pendente'" in q and "processando" in q:
            for d in self.dest.values():
                if d["status"] == "processando":
                    d["status"] = "pendente"
        elif q.startswith("UPDATE email.recipients SET erro="):
            self.dest[params[1]]["erro"] = params[0]
        elif "INSERT INTO email.suppressions" in q:
            self.supressoes.setdefault(params[0], params[3])
        elif "INSERT INTO email.events" in q:
            self.eventos.append(params[0])
        elif "DELETE FROM email.suppressions" in q:
            if self.supressoes.get(params[0]) == params[1]:
                del self.supressoes[params[0]]
        elif "DELETE FROM email.events" in q:
            self.eventos = [e for e in self.eventos if e != params[0]]
        return _Res([])


def _rodar(monkeypatch, banco, erro_para):
    class _SMTP:
        simulado = False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def enviar(self, *, para, **_):
            erro = erro_para(para)
            if erro:
                raise erro

    async def _nada(*a, **k):
        return None

    async def _cota(_conn):
        return SimpleNamespace(disponivel=1000)

    monkeypatch.setattr(campanhas, "Conexao", _SMTP)
    monkeypatch.setattr(campanhas, "materializar", _nada)
    monkeypatch.setattr(campanhas, "respirar", _nada)
    monkeypatch.setattr(campanhas, "remetente_da_campanha", lambda *a: None)
    monkeypatch.setattr(campanhas.cota_svc, "consultar", _cota)
    monkeypatch.setattr(campanhas.render, "montar", lambda *a, **k: ("x", "<p>x</p>"))
    monkeypatch.setattr(campanhas.render, "cabecalhos_unsubscribe", lambda *a, **k: {})
    return asyncio.run(campanhas.disparar(banco, "camp", "user"))


# ------------------------------------------------------------- o desastre

def test_mesma_recusa_em_todos_para_o_envio_sem_bloquear_ninguem(monkeypatch):
    banco = _Banco(10)
    resumo = _rodar(monkeypatch, banco,
                    lambda para: ErroPermanente(f"554 Transaction failed for <{para}>"))

    assert banco.supressoes == {}, "nenhum cliente pode ficar bloqueado"
    assert banco.eventos == [], "nenhum bounce falso no relatório"
    assert all(d["status"] == "pendente" for d in banco.dest.values())
    assert banco.status_campanha == "falhou"
    assert resumo["erro_conta"]


def test_bounce_real_continua_bloqueando(monkeypatch):
    """Erros diferentes, um por endereço, são bounce de verdade."""
    banco = _Banco(4)
    ruins = {"cliente0@x.com": "550 5.1.1 user unknown",
             "cliente1@x.com": "550 mailbox unavailable",
             "cliente2@x.com": "553 domain does not exist"}
    resumo = _rodar(monkeypatch, banco,
                    lambda para: ErroPermanente(ruins[para]) if para in ruins else None)

    assert set(banco.supressoes) == set(ruins)
    assert banco.dest["r3"]["status"] == "enviado"
    assert banco.status_campanha == "enviada"
    assert not resumo["erro_conta"]


def test_ninguem_enviado_nao_aparece_como_enviada(monkeypatch):
    """Fila esvaziada sem nenhum envio é falha, não "Enviada"."""
    banco = _Banco(2)
    msgs = iter(["550 5.1.1 user unknown", "553 domain does not exist"])
    _rodar(monkeypatch, banco, lambda para: ErroPermanente(next(msgs)))
    assert banco.status_campanha == "falhou"

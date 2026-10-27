"""Cria o primeiro admin do CRM (ou promove uma conta existente a admin).

Uso, na VPS:  ./scripts/criar-admin.sh   (padrão: ai@estudiooggi.com)

1. Cria a conta no Supabase Auth já confirmada (sem e-mail de confirmação),
   falando direto com o serviço `auth` pela rede interna do Docker — funciona
   antes mesmo do domínio e do HTTPS estarem prontos.
2. Liga a conta ao papel `admin` em app.usuarios (docs/API.md, "Primeiro
   usuário").

Se a conta já existe no Auth, a senha é trocada pela nova. Os demais acessos
entram pelo convite, na tela Usuários.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import httpx
import psycopg

AUTH = os.getenv("AUTH_INTERNO", "http://auth:9999")


def pedir_senha() -> str:
    senha = os.getenv("SENHA_ADMIN")
    if senha:
        return senha
    while True:
        senha = getpass.getpass("Senha (mínimo 8 caracteres): ")
        if len(senha) < 8:
            print("Curta demais.")
            continue
        if getpass.getpass("Repita a senha: ") != senha:
            print("As duas não batem.")
            continue
        return senha


def conta_no_auth(email: str, senha: str) -> str:
    chave = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {chave}", "apikey": chave}
    with httpx.Client(base_url=AUTH, headers=headers, timeout=20) as cli:
        r = cli.post("/admin/users", json={"email": email, "password": senha, "email_confirm": True})
        if r.status_code in (200, 201):
            print(f"Conta criada no Auth: {email}")
            return r.json()["id"]
        if r.status_code != 422:
            sys.exit(f"O Auth recusou ({r.status_code}): {r.text[:300]}")

        # 422 = já existe. Procura e troca a senha.
        pagina = 1
        while True:
            r = cli.get("/admin/users", params={"page": pagina, "per_page": 200})
            r.raise_for_status()
            usuarios = r.json().get("users", [])
            for u in usuarios:
                if (u.get("email") or "").lower() == email:
                    cli.put(f"/admin/users/{u['id']}",
                            json={"password": senha, "email_confirm": True}).raise_for_status()
                    print(f"Conta já existia no Auth; senha atualizada: {email}")
                    return u["id"]
            if len(usuarios) < 200:
                sys.exit("O Auth diz que o e-mail existe, mas ele não apareceu na lista.")
            pagina += 1


def ligar_admin(uid: str, email: str, nome: str | None) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        cur = conn.execute(
            """
            INSERT INTO app.usuarios (id, nome, email, papel_id)
            SELECT %s, %s, %s, id FROM app.papeis WHERE nome = 'admin'
            ON CONFLICT (id) DO UPDATE
               SET papel_id = EXCLUDED.papel_id,
                   nome = COALESCE(EXCLUDED.nome, app.usuarios.nome),
                   status = 'ativo',
                   updated_at = now()
            """,
            (uid, nome, email),
        )
        if cur.rowcount == 0:
            sys.exit("Papel 'admin' não encontrado: as migrations rodaram? (./scripts/instalar.sh)")
    print(f"{email} agora é admin do CRM.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("email")
    ap.add_argument("nome", nargs="?")
    args = ap.parse_args()
    email = args.email.strip().lower()
    uid = conta_no_auth(email, pedir_senha())
    ligar_admin(uid, email, args.nome)


if __name__ == "__main__":
    main()

"""Página pública de criação de senha (fluxo do convite).

É HTML servido pela própria API, não uma tela do front. Motivo: quem abre este
link ainda NÃO tem conta — não há sessão, não há token de API, e o front inteiro
exige autenticação. Uma página simples aqui evita ter que abrir uma exceção de
autenticação no app só para esse caso.
"""

import html as html_lib

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse
from psycopg import AsyncConnection

from app.audit import registrar
from app.config import settings
from app.db import get_conn
from app.services.supabase_admin import ErroSupabase, criar_usuario

router = APIRouter(tags=["acesso"])

_PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Criar senha · CRM</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; background:#0E0E10; margin:0;
         min-height:100vh; display:flex; align-items:center; justify-content:center;
         padding:24px; color:#18181b; }}
  .cartao {{ background:#fff; border-radius:16px; padding:32px; max-width:400px; width:100%; }}
  h1 {{ margin:0 0 8px; font-size:20px; }}
  p.sub {{ margin:0 0 20px; font-size:14px; color:#71717a; }}
  label {{ display:block; font-size:12px; font-weight:bold; margin:0 0 6px; }}
  input {{ width:100%; box-sizing:border-box; padding:12px; border:1px solid #e4e4e7;
           border-radius:8px; font-size:14px; margin-bottom:14px; }}
  button {{ width:100%; padding:12px; background:#E56D23; color:#fff; border:0;
            border-radius:8px; font-size:14px; font-weight:bold; cursor:pointer; }}
  .erro {{ background:#fef2f2; color:#b91c1c; padding:12px; border-radius:8px;
           font-size:13px; margin-bottom:14px; }}
  .ok {{ text-align:center; }}
</style></head>
<body><div class="cartao">{conteudo}</div></body></html>"""


def _pagina(conteudo: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGINA.format(conteudo=conteudo), status_code=status)


def _invalido() -> HTMLResponse:
    return _pagina(
        "<h1>Link inválido ou expirado</h1>"
        "<p class='sub'>Este convite já foi usado ou passou da validade. "
        "Peça um novo a quem administra o CRM.</p>",
        status=404,
    )


@router.get("/definir-senha", response_class=HTMLResponse)
async def formulario(token: str = "", conn: AsyncConnection = Depends(get_conn)):
    convite = await (
        await conn.execute(
            "SELECT email FROM app.convites "
            "WHERE token = %s AND status = 'pendente' AND expira_em > now()",
            (token,),
        )
    ).fetchone()
    if convite is None:
        return _invalido()

    # Escape obrigatório: o e-mail vem do convite e o token da query string.
    # Sem escapar, qualquer um dos dois injeta HTML nesta página.
    email = html_lib.escape(convite["email"])
    token_seguro = html_lib.escape(token, quote=True)

    return _pagina(f"""
      <h1>Criar sua senha</h1>
      <p class="sub">{email}</p>
      <form method="post" action="{settings.app_url.rstrip('/')}/api/definir-senha">
        <input type="hidden" name="token" value="{token_seguro}">
        <label for="senha">Senha (mínimo 8 caracteres)</label>
        <input id="senha" type="password" name="senha" minlength="8" required autofocus>
        <label for="confirmar">Repita a senha</label>
        <input id="confirmar" type="password" name="confirmar" minlength="8" required>
        <button type="submit">Criar senha e entrar</button>
      </form>""")


@router.post("/definir-senha", response_class=HTMLResponse)
async def salvar(
    token: str = Form(...),
    senha: str = Form(...),
    confirmar: str = Form(...),
    conn: AsyncConnection = Depends(get_conn),
):
    convite = await (
        await conn.execute(
            "SELECT id, email FROM app.convites "
            "WHERE token = %s AND status = 'pendente' AND expira_em > now()",
            (token,),
        )
    ).fetchone()
    if convite is None:
        return _invalido()

    token_seguro = html_lib.escape(token, quote=True)
    voltar = (f"<p><a href='{settings.app_url.rstrip('/')}/api/definir-senha"
              f"?token={token_seguro}'>Voltar</a></p>")

    if senha != confirmar:
        return _pagina(f"<h1>As senhas não conferem</h1>{voltar}", status=400)
    if len(senha) < 8:
        return _pagina(f"<h1>Senha muito curta</h1>"
                       f"<p class='sub'>Use ao menos 8 caracteres.</p>{voltar}", status=400)

    try:
        await criar_usuario(convite["email"], senha)
    except ErroSupabase as exc:
        return _pagina(f"<h1>Não foi possível criar a conta</h1>"
                       f"<p class='sub'>{html_lib.escape(str(exc))}</p>", status=502)

    # Só o token é zerado. O convite continua 'pendente' de propósito: quem o
    # consome é o primeiro login (ver app/auth.py::_aceitar_convite), e é lá que
    # o papel é atribuído. Assim, criar a conta não basta para ter acesso.
    await conn.execute("UPDATE app.convites SET token = NULL WHERE id = %s", (convite["id"],))
    await registrar(conn, None, "definir_senha", f"convite:{convite['id']}",
                    {"email": convite["email"]})

    return _pagina(f"""
      <div class="ok">
        <h1>Senha criada</h1>
        <p class="sub">Agora é só entrar no CRM com o seu e-mail.</p>
        <p><a href="{settings.app_url.rstrip('/')}/login">Ir para o login</a></p>
      </div>""")

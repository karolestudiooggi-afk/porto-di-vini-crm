"""Ambiente mínimo para a suíte rodar sem o `.env` da máquina.

O `.env` da raiz é gitignored (tem credencial), então um `git clone` limpo não o
tem — e sem ele o `Settings` do Pydantic falha na importação, derrubando a coleta
inteira dos testes. Definir as variáveis aqui, ANTES de qualquer import de `app`,
faz a suíte rodar em qualquer máquina e no CI.

Os valores são falsos de propósito: nenhum teste desta suíte toca banco ou SMTP.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://teste@localhost/teste")
os.environ.setdefault("SUPABASE_JWT_SECRET", "segredo-de-teste-nao-usar-em-producao")
os.environ.setdefault("APP_URL", "https://crm.teste.local")
# Garante que nenhum teste abra conexão SMTP de verdade, mesmo por engano.
os.environ.setdefault("EMAIL_DRY_RUN", "true")

"""
Motor de Segurança e Controle de Acessos.
Responsável por hashing de senhas, validação de login, bloqueio por tentativas,
gestão de usuários e trilha de auditoria.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import pandas as pd

DB_SEGURANCA = "seguranca_sistema.db"

PERFIS = ["Comum", "Administrador"]
MAX_TENTATIVAS = 5          # falhas seguidas antes de bloquear
BLOQUEIO_MINUTOS = 15       # tempo de bloqueio após exceder as tentativas
SENHA_MIN = 8
ITERACOES = 200_000
SENHA_PADRAO_ANTIGA = "admin123"
MSG_INVALIDO = "Usuário ou senha inválidos."


def _conn():
    return closing(sqlite3.connect(DB_SEGURANCA))


def _colunas(cur, tabela):
    return {r[1] for r in cur.execute(f"PRAGMA table_info({tabela})")}


def init_db_seguranca():
    """Cria/atualiza as tabelas de credenciais e logs e garante um administrador."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Comum',
                ativo INTEGER DEFAULT 1
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS logs_acesso (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_acesso TEXT DEFAULT 'Local',
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acao TEXT DEFAULT 'LOGIN'
            )"""
        )
        # Migrações de colunas novas (bancos já existentes continuam funcionando).
        cols = _colunas(cur, "usuarios")
        novas = {
            "trocar_senha": "INTEGER NOT NULL DEFAULT 0",
            "falhas": "INTEGER NOT NULL DEFAULT 0",
            "bloqueado_ate": "TEXT",
            "iteracoes": "INTEGER NOT NULL DEFAULT 100000",
            "ultimo_login": "TEXT",
        }
        for nome, tipo in novas.items():
            if nome not in cols:
                cur.execute(f"ALTER TABLE usuarios ADD COLUMN {nome} {tipo}")
        conn.commit()

        # Garante um administrador. A senha inicial vem de ADMIN_PASSWORD
        # (variável de ambiente ou secrets do Streamlit); sem ela, usa a antiga,
        # mas obriga a troca no primeiro acesso.
        if not cur.execute("SELECT 1 FROM usuarios WHERE role='Administrador' LIMIT 1").fetchone():
            senha_ini = _senha_inicial_admin()
            _inserir(cur, "admin", senha_ini or SENHA_PADRAO_ANTIGA, "Administrador", trocar=True)
            conn.commit()

        # Qualquer usuário que ainda use a senha padrão pública é obrigado a trocar.
        for uid, h, salt, it in cur.execute(
            "SELECT id, password_hash, salt, iteracoes FROM usuarios WHERE trocar_senha=0"
        ).fetchall():
            if hmac.compare_digest(_hash(SENHA_PADRAO_ANTIGA, salt, it)[0], h):
                cur.execute("UPDATE usuarios SET trocar_senha=1 WHERE id=?", (uid,))
        conn.commit()


def _senha_inicial_admin():
    senha = os.environ.get("ADMIN_PASSWORD")
    if senha:
        return senha
    try:
        import streamlit as st

        return st.secrets.get("ADMIN_PASSWORD")
    except Exception:
        return None


def _hash(senha, salt_hex=None, iteracoes=ITERACOES):
    """Hash PBKDF2-HMAC SHA-256 com salt aleatório."""
    salt = os.urandom(16) if salt_hex is None else bytes.fromhex(salt_hex)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, int(iteracoes))
    return h.hex(), salt.hex()


def validar_forca_senha(senha):
    """Retorna (ok, mensagem)."""
    if len(senha or "") < SENHA_MIN:
        return False, f"A senha precisa ter pelo menos {SENHA_MIN} caracteres."
    if not any(c.isalpha() for c in senha) or not any(c.isdigit() for c in senha):
        return False, "A senha precisa ter letras e números."
    if senha.lower() in {SENHA_PADRAO_ANTIGA, "12345678", "senha123", "password1"}:
        return False, "Essa senha é muito fácil de adivinhar."
    return True, ""


def _normalizar(username):
    return (username or "").lower().strip()


def _inserir(cur, username, senha, role, trocar):
    h, salt = _hash(senha)
    cur.execute(
        "INSERT INTO usuarios (username, password_hash, salt, role, trocar_senha, iteracoes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_normalizar(username), h, salt, role, int(trocar), ITERACOES),
    )


def _log(cur, username, acao):
    cur.execute(
        "INSERT INTO logs_acesso (username, acao, data_hora) VALUES (?, ?, ?)",
        (_normalizar(username)[:60], acao, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def criar_usuario(username, senha, role="Comum", trocar_senha=True, validar=True):
    """Cadastra um usuário. Por padrão ele troca a senha no primeiro acesso."""
    username = _normalizar(username)
    if not username or not username.replace(".", "").replace("_", "").replace("-", "").isalnum():
        return False, "Use só letras, números, ponto, hífen ou sublinhado no nome de usuário."
    if role not in PERFIS:
        return False, "Perfil inválido."
    if validar:
        ok, msg = validar_forca_senha(senha)
        if not ok:
            return False, msg
    with _conn() as conn:
        cur = conn.cursor()
        try:
            _inserir(cur, username, senha, role, trocar_senha)
            _log(cur, username, "USUARIO_CRIADO")
            conn.commit()
            return True, f"Usuário '{username}' criado."
        except sqlite3.IntegrityError:
            return False, "Esse nome de usuário já existe."


def autenticar_usuario(username, senha):
    """Valida as credenciais. Retorna (ok, perfil, mensagem)."""
    username = _normalizar(username)
    agora = datetime.now()
    with _conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, password_hash, salt, role, ativo, falhas, bloqueado_ate, iteracoes "
            "FROM usuarios WHERE username=?",
            (username,),
        ).fetchone()

        if not row:
            _hash(senha or "x")  # tempo de resposta parecido com usuário existente
            _log(cur, username, "FALHA_USUARIO")
            conn.commit()
            return False, None, MSG_INVALIDO

        uid, stored, salt, role, ativo, falhas, bloqueado_ate, it = row
        if bloqueado_ate and datetime.fromisoformat(bloqueado_ate) > agora:
            _log(cur, username, "BLOQUEADO")
            conn.commit()
            minutos = int((datetime.fromisoformat(bloqueado_ate) - agora).total_seconds() // 60) + 1
            return False, None, f"Muitas tentativas. Tente de novo em {minutos} minuto(s)."

        calculado, _ = _hash(senha or "", salt, it)
        if not hmac.compare_digest(calculado, stored):
            falhas = (falhas or 0) + 1
            bloqueio = None
            if falhas >= MAX_TENTATIVAS:
                bloqueio = (agora + timedelta(minutes=BLOQUEIO_MINUTOS)).isoformat()
                falhas = 0
            cur.execute("UPDATE usuarios SET falhas=?, bloqueado_ate=? WHERE id=?", (falhas, bloqueio, uid))
            _log(cur, username, "BLOQUEIO_ATIVADO" if bloqueio else "FALHA_SENHA")
            conn.commit()
            if bloqueio:
                return False, None, f"Muitas tentativas. Acesso bloqueado por {BLOQUEIO_MINUTOS} minutos."
            return False, None, MSG_INVALIDO

        if not ativo:
            _log(cur, username, "USUARIO_INATIVO")
            conn.commit()
            return False, None, "Usuário desativado. Fale com o administrador."

        # Sucesso: zera falhas e atualiza o hash para o padrão atual se necessário.
        if int(it) != ITERACOES:
            novo, novo_salt = _hash(senha)
            cur.execute(
                "UPDATE usuarios SET password_hash=?, salt=?, iteracoes=? WHERE id=?",
                (novo, novo_salt, ITERACOES, uid),
            )
        cur.execute(
            "UPDATE usuarios SET falhas=0, bloqueado_ate=NULL, ultimo_login=? WHERE id=?",
            (agora.strftime("%Y-%m-%d %H:%M:%S"), uid),
        )
        _log(cur, username, "LOGIN_SUCESSO")
        conn.commit()
        return True, role, "Autenticado com sucesso."


def precisa_trocar_senha(username):
    with _conn() as conn:
        r = conn.execute(
            "SELECT trocar_senha FROM usuarios WHERE username=?", (_normalizar(username),)
        ).fetchone()
    return bool(r and r[0])


def alterar_senha(username, senha_atual, nova_senha):
    """O próprio usuário troca a senha (exige a senha atual)."""
    username = _normalizar(username)
    ok, msg = validar_forca_senha(nova_senha)
    if not ok:
        return False, msg
    if senha_atual == nova_senha:
        return False, "A nova senha precisa ser diferente da atual."
    with _conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, password_hash, salt, iteracoes FROM usuarios WHERE username=?", (username,)
        ).fetchone()
        if not row or not hmac.compare_digest(_hash(senha_atual or "", row[2], row[3])[0], row[1]):
            return False, "Senha atual incorreta."
        h, salt = _hash(nova_senha)
        cur.execute(
            "UPDATE usuarios SET password_hash=?, salt=?, iteracoes=?, trocar_senha=0 WHERE id=?",
            (h, salt, ITERACOES, row[0]),
        )
        _log(cur, username, "SENHA_ALTERADA")
        conn.commit()
    return True, "Senha alterada com sucesso."


def redefinir_senha(username, por_admin):
    """Administrador gera uma senha temporária; o usuário troca no próximo acesso."""
    username = _normalizar(username)
    temporaria = "Tmp" + secrets.token_urlsafe(6).replace("-", "x").replace("_", "y") + "9"
    h, salt = _hash(temporaria)
    with _conn() as conn:
        cur = conn.cursor()
        n = cur.execute(
            "UPDATE usuarios SET password_hash=?, salt=?, iteracoes=?, trocar_senha=1, falhas=0, "
            "bloqueado_ate=NULL WHERE username=?",
            (h, salt, ITERACOES, username),
        ).rowcount
        if not n:
            return False, "Usuário não encontrado.", None
        _log(cur, por_admin, f"REDEFINIU_SENHA:{username}")
        conn.commit()
    return True, "Senha temporária gerada.", temporaria


def listar_usuarios():
    with _conn() as conn:
        return pd.read_sql_query(
            "SELECT username AS 'Usuário', role AS 'Perfil', "
            "CASE ativo WHEN 1 THEN 'Ativo' ELSE 'Desativado' END AS 'Situação', "
            "CASE trocar_senha WHEN 1 THEN 'Sim' ELSE 'Não' END AS 'Troca de senha pendente', "
            "COALESCE(ultimo_login, '—') AS 'Último acesso' FROM usuarios ORDER BY username",
            conn,
        )


def atualizar_usuario(username, role, ativo, por_admin):
    """Muda perfil/situação. Impede ficar sem nenhum administrador ativo."""
    username = _normalizar(username)
    if role not in PERFIS:
        return False, "Perfil inválido."
    with _conn() as conn:
        cur = conn.cursor()
        outros_admins = cur.execute(
            "SELECT COUNT(*) FROM usuarios WHERE role='Administrador' AND ativo=1 AND username<>?",
            (username,),
        ).fetchone()[0]
        if outros_admins == 0 and (role != "Administrador" or not ativo):
            return False, "O sistema precisa de pelo menos um administrador ativo."
        cur.execute("UPDATE usuarios SET role=?, ativo=? WHERE username=?", (role, int(ativo), username))
        _log(cur, por_admin, f"ALTEROU_USUARIO:{username}:{role}:{'ativo' if ativo else 'inativo'}")
        conn.commit()
    return True, "Usuário atualizado."


def obter_relatorio_acessos():
    """Retorna o histórico de logins e tentativas de acesso."""
    with _conn() as conn:
        return pd.read_sql_query(
            "SELECT username AS Usuário, acao AS Evento, data_hora AS 'Data/Hora' "
            "FROM logs_acesso ORDER BY id DESC LIMIT 500",
            conn,
        )

"""
Acesso ao banco de dados do sistema.

- Com DATABASE_URL configurado (Secrets do Streamlit ou variável de ambiente), usa PostgreSQL
  (ex.: Supabase) — os dados ficam guardados de forma permanente.
- Sem DATABASE_URL, usa arquivos SQLite ao lado do código (bom para rodar no computador;
  no Streamlit Cloud esses arquivos são apagados sempre que o app reinicia).

O restante do sistema escreve SQL no estilo do SQLite (parâmetros com "?", INSERT OR IGNORE,
INTEGER PRIMARY KEY AUTOINCREMENT); este módulo traduz para o PostgreSQL quando necessário.

Uso:
    with banco.conectar("valores_clinica.db") as conn:
        conn.execute("INSERT INTO t (a) VALUES (?)", (1,))
        conn.commit()
        df = banco.ler_df(conn, "SELECT * FROM t")
"""
import atexit
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Recife")
except Exception:  # sem base de fusos: usa o horário do servidor
    FUSO = None

PASTA = os.path.dirname(os.path.abspath(__file__))

IntegrityError = (sqlite3.IntegrityError,)
Error = (sqlite3.Error,)
try:
    import psycopg

    IntegrityError += (psycopg.IntegrityError,)
    Error += (psycopg.Error,)
except ImportError:
    psycopg = None

_pool = None


# ─────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────
def _url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url.strip()
    try:
        import streamlit as st

        url = st.secrets.get("DATABASE_URL")
        return url.strip() if url else None
    except Exception:
        return None


def usa_postgres():
    return bool(_url())


def descricao():
    """Texto curto para mostrar na tela qual banco está em uso."""
    return "PostgreSQL (permanente)" if usa_postgres() else "SQLite local (temporário no Streamlit Cloud)"


def agora():
    """Data/hora no fuso de Recife, no formato gravado no banco."""
    dt = datetime.now(FUSO).replace(tzinfo=None) if FUSO else datetime.now()
    return dt.replace(microsecond=0)


def agora_txt():
    return agora().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────
# Tradução de SQL (SQLite -> PostgreSQL)
# ─────────────────────────────────────────────────────────────
def _traduzir(sql):
    s = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    if re.search(r"INSERT\s+OR\s+IGNORE", s, re.I):
        s = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", s, flags=re.I).rstrip().rstrip(";")
        s += " ON CONFLICT DO NOTHING"
    s = s.replace("%", "%%").replace("?", "%s")
    return s


def _param(v):
    """Converte tipos do numpy/pandas para tipos simples do Python."""
    if v is None:
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    try:
        if not isinstance(v, (str, bytes)) and pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _params(p):
    return tuple(_param(v) for v in (p or ()))


class _Cursor:
    """Cursor com a mesma cara do sqlite3 (execute devolve o próprio cursor)."""

    def __init__(self, cur, pg):
        self._cur, self._pg = cur, pg

    def execute(self, sql, params=()):
        if self._pg:
            self._cur.execute(_traduzir(sql), _params(params))
        else:
            self._cur.execute(sql, _params(params))
        return self

    def executemany(self, sql, seq):
        seq = [_params(p) for p in seq]
        if not seq:
            return self
        self._cur.executemany(_traduzir(sql) if self._pg else sql, seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description


class Conexao:
    def __init__(self, conn, pg):
        self._conn, self.pg = conn, pg

    def cursor(self):
        return _Cursor(self._conn.cursor(), self.pg)

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq):
        return self.cursor().executemany(sql, seq)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def _obter_pool():
    global _pool
    if _pool is None:
        if psycopg is None:
            raise RuntimeError("DATABASE_URL configurado, mas o pacote 'psycopg' não está instalado "
                               "(confira o requirements.txt).")
        from psycopg_pool import ConnectionPool

        # prepare_threshold=None: compatível com o pooler do Supabase
        _pool = ConnectionPool(_url(), min_size=1, max_size=5, max_idle=300, open=True,
                               check=ConnectionPool.check_connection,
                               kwargs={"prepare_threshold": None, "connect_timeout": 15})
        atexit.register(_pool.close)
    return _pool


@contextmanager
def conectar(arquivo_sqlite):
    """Abre uma conexão. 'arquivo_sqlite' só é usado quando não há DATABASE_URL.
    O que não for confirmado com commit() é descartado ao sair do bloco."""
    if usa_postgres():
        pool = _obter_pool()
        raw = pool.getconn()
        try:
            yield Conexao(raw, True)
        finally:
            try:
                raw.rollback()
            finally:
                pool.putconn(raw)
    else:
        caminho = arquivo_sqlite if os.path.isabs(arquivo_sqlite) else os.path.join(PASTA, arquivo_sqlite)
        raw = sqlite3.connect(caminho, timeout=10)
        try:
            yield Conexao(raw, False)
        finally:
            raw.close()


# ─────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────
def ler_df(conn, sql, params=()):
    """Executa um SELECT e devolve um DataFrame."""
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def colunas(conn, tabela):
    """Nomes das colunas de uma tabela."""
    if conn.pg:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (tabela.lower(),),
        ).fetchall()
        return {r[0] for r in rows}
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}

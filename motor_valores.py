"""
Motor de Valores e Tabelas de Preços.
Gerencia a leitura multi-abas de especialidades, valores do plano e repasses da equipe.
"""
import io
import os
import sqlite3
import unicodedata
from contextlib import closing

import pandas as pd

# Caminho absoluto: o banco fica sempre ao lado deste arquivo, não importa de
# qual pasta o "streamlit run" for executado.
DB_VALORES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "valores_clinica.db")

COLUNAS_VALORES = ["especialidade", "plano", "tempo_atendimento", "valor_plano", "valor_profissional"]
COLUNAS_PLANO = ["plano", "codigo_tuss", "procedimento", "valor_plano"]
ESPECIALIDADES_PADRAO = ["PSICOLOGIA", "PSICOPEDAGOGIA", "PSICOMOTRICIDADE", "FONOAUDIOLOGIA", "NUTRIÇÃO", "FISIOTERAPIA"]


def _conectar():
    return closing(sqlite3.connect(DB_VALORES, timeout=10))


def init_db_valores():
    with _conectar() as conn, conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_especialidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_valores_plano (
                id INTEGER PRIMARY KEY AUTOINCREMENT, plano TEXT, codigo_tuss TEXT,
                procedimento TEXT, valor_plano REAL)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_repasse_profissional (
                id INTEGER PRIMARY KEY AUTOINCREMENT, especialidade TEXT, plano TEXT,
                tempo_atendimento TEXT, valor_profissional REAL)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_valores_completa (
                id INTEGER PRIMARY KEY AUTOINCREMENT, especialidade TEXT, plano TEXT,
                tempo_atendimento TEXT, valor_plano REAL, valor_profissional REAL)"""
        )


# ─────────────────────────── utilidades ───────────────────────────
def _sem_acento(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).upper()


def _limpa_texto(v):
    """Devolve texto limpo ou None para vazio/NaN."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return None if s.lower() in ("", "nan", "none", "nat") else s


def _para_float(v):
    """Converte número ou texto ('R$ 1.234,56', '80,5') em float; None se inválido."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = _sem_acento(v).replace("R$", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _achar_cabecalho(df_raw):
    """Linha de cabeçalho = a primeira com pelo menos 2 palavras-chave (evita confundir títulos)."""
    chaves = ("PLANO", "TEMPO", "VALOR", "PROFISSIONAL")
    for idx, row in df_raw.iterrows():
        texto = " ".join(_sem_acento(v) for v in row.values if pd.notnull(v))
        if sum(k in texto for k in chaves) >= 2:
            return idx
    return None


def _substituir_tabela(nome_tabela, df, colunas):
    """Troca o conteúdo da tabela mantendo o esquema (to_sql 'replace' apagaria a coluna id)."""
    base = df.copy()
    for c in colunas:
        if c not in base.columns:
            base[c] = None
    with _conectar() as conn, conn:
        conn.execute(f"DELETE FROM {nome_tabela}")
        base[colunas].to_sql(nome_tabela, conn, if_exists="append", index=False)


# ─────────────────────────── especialidades ───────────────────────────
def buscar_especialidades():
    try:
        with _conectar() as conn:
            rows = conn.execute(
                "SELECT nome FROM tabela_especialidades "
                "UNION SELECT DISTINCT especialidade FROM tabela_valores_completa ORDER BY 1"
            ).fetchall()
        lista = [r[0] for r in rows if r[0]]
    except sqlite3.Error:
        lista = []
    return lista or list(ESPECIALIDADES_PADRAO)


def adicionar_especialidade(nome):
    """Retorna (ok, mensagem)."""
    esp = (nome or "").strip().upper()
    if not esp:
        return False, "Informe o nome da especialidade."
    try:
        with _conectar() as conn, conn:
            cur = conn.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp,))
        if cur.rowcount == 0:
            return False, f"A especialidade {esp} já existe."
        return True, f"Especialidade {esp} cadastrada."
    except sqlite3.Error as e:
        return False, f"Erro ao cadastrar: {e}"


# ─────────────────────────── leitura / gravação ───────────────────────────
def buscar_tabela_plano():
    try:
        with _conectar() as conn:
            return pd.read_sql_query(f"SELECT {', '.join(COLUNAS_PLANO)} FROM tabela_valores_plano", conn)
    except Exception:
        return pd.DataFrame(columns=COLUNAS_PLANO)


def buscar_tabela_repasse():
    """Tabela completa (especialidade, plano, tempo, valor do plano, repasse)."""
    try:
        with _conectar() as conn:
            df = pd.read_sql_query(f"SELECT {', '.join(COLUNAS_VALORES)} FROM tabela_valores_completa", conn)
        if not df.empty:
            df["especialidade"] = df["especialidade"].astype(str).str.upper().str.strip()
        return df
    except Exception:
        return pd.DataFrame(columns=COLUNAS_VALORES)


def salvar_tabela_plano(df):
    _substituir_tabela("tabela_valores_plano", df, COLUNAS_PLANO)


def salvar_tabela_repasse(df):
    df = df.copy()  # não altera o DataFrame de quem chamou
    if not df.empty and "especialidade" in df.columns:
        df["especialidade"] = df["especialidade"].astype(str).str.upper().str.strip()
    _substituir_tabela("tabela_valores_completa", df, COLUNAS_VALORES)


def consultar_valor(especialidade, plano, tempo=None):
    """Devolve {'valor_plano', 'valor_profissional'} para a combinação, ou None se não houver."""
    df = buscar_tabela_repasse()
    if df.empty:
        return None
    m = (df["especialidade"].map(_sem_acento) == _sem_acento(especialidade).strip()) & (
        df["plano"].astype(str).map(_sem_acento).str.strip() == _sem_acento(plano).strip()
    )
    if tempo:
        com_tempo = m & (df["tempo_atendimento"].astype(str).str.strip() == str(tempo).strip())
        if com_tempo.any():
            m = com_tempo
    achados = df[m]
    if achados.empty:
        return None
    linha = achados.iloc[0]
    return {"valor_plano": float(linha["valor_plano"]), "valor_profissional": float(linha["valor_profissional"])}


# ─────────────────────────── importação do Excel ───────────────────────────
def processar_e_salvar_excel_multi_abas(arquivo_upload):
    """Lê todas as abas (cada aba = uma especialidade). Retorna (ok, mensagem)."""
    try:
        arquivo_upload.seek(0)
        xls = pd.ExcelFile(io.BytesIO(arquivo_upload.read()))
    except Exception as e:
        return False, (
            "O arquivo não é um Excel válido ou está corrompido. "
            f"Se for .xls, instale 'xlrd'; se for .xlsx, instale 'openpyxl'. Detalhe: {e}"
        )

    dfs, abas_ok, abas_erro = [], [], []
    for aba in xls.sheet_names:
        try:
            df_raw = pd.read_excel(xls, sheet_name=aba, header=None, dtype=object)
            if df_raw.empty:
                abas_erro.append(f"{aba} (vazia)")
                continue
            if df_raw.shape[1] < 4:
                abas_erro.append(f"{aba} (menos de 4 colunas)")
                continue

            cab = _achar_cabecalho(df_raw)
            corpo = df_raw.iloc[cab + 1:] if cab is not None else df_raw
            df_aba = corpo.iloc[:, :4].copy()
            df_aba.columns = ["plano", "tempo_atendimento", "valor_plano", "valor_profissional"]

            # Plano aparece só na 1ª linha de cada bloco -> preenche para baixo
            df_aba["plano"] = df_aba["plano"].map(_limpa_texto).ffill().fillna("Sem plano")
            df_aba["valor_plano"] = df_aba["valor_plano"].map(_para_float)
            df_aba["valor_profissional"] = df_aba["valor_profissional"].map(_para_float)
            df_aba = df_aba.dropna(subset=["valor_plano"])
            df_aba["valor_profissional"] = df_aba["valor_profissional"].fillna(0.0)
            df_aba = df_aba[~df_aba["plano"].map(_sem_acento).str.contains("PLANO DE SAUDE", na=False)]
            df_aba["tempo_atendimento"] = df_aba["tempo_atendimento"].map(_limpa_texto).fillna("")
            esp = aba.strip().upper()
            df_aba["especialidade"] = esp

            if df_aba.empty:
                abas_erro.append(f"{aba} (nenhuma linha com valor)")
                continue
            dfs.append(df_aba[COLUNAS_VALORES])
            abas_ok.append(esp)
        except Exception as ex:
            abas_erro.append(f"{aba} ({ex})")

    if not dfs:
        return False, "Nenhuma regra extraída. Abas com falha: " + ("; ".join(abas_erro) or "nenhuma aba legível")

    df_final = pd.concat(dfs, ignore_index=True)
    try:
        salvar_tabela_repasse(df_final)
        with _conectar() as conn, conn:
            conn.executemany("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", [(n,) for n in abas_ok])
    except Exception as e:
        return False, f"Erro ao gravar no banco: {e}"

    msg = f"Importação concluída: {len(df_final)} registros em {len(abas_ok)} abas ({', '.join(sorted(abas_ok))})."
    if abas_erro:
        msg += f" Abas ignoradas: {'; '.join(abas_erro)}."
    return True, msg

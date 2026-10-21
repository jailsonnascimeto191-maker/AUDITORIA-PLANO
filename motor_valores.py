"""
Motor de Valores e Tabelas de Preços.
Gerencia os valores pagos pelas operadoras, a margem da equipe e o cadastro de especialidades.
"""
import sqlite3
import pandas as pd

DB_VALORES = "valores_clinica.db"

def init_db_valores():
    """Inicializa as tabelas financeiras e de especialidades da clínica."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    
    # 1. Tabela de Especialidades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_especialidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
        )
    ''')
    
    # Pré-carregar as especialidades padrão da clínica se a tabela estiver vazia
    cursor.execute("SELECT COUNT(*) FROM tabela_especialidades")
    if cursor.fetchone()[0] == 0:
        especialidades_iniciais = [
            "Psicologia", "Psicopedagogia", "Psicomotricidade", 
            "Fisioterapia", "Terapia ocupacional", "Nutricionista", "Av neuro"
        ]
        for esp in especialidades_iniciais:
            cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp,))
    
    # 2. Tabela do Plano de Saúde (O que o convênio paga)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_valores_plano (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plano TEXT,
            codigo_tuss TEXT,
            procedimento TEXT,
            valor_plano REAL
        )
    ''')
    
    # 3. Tabela de Repasse (O que a clínica repassa ao profissional)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_repasse_profissional (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            especialidade TEXT,
            plano TEXT,
            tempo_atendimento TEXT,
            valor_profissional REAL
        )
    ''')
    
    conn.commit()
    conn.close()

def buscar_especialidades():
    """Retorna a lista de especialidades cadastradas."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM tabela_especialidades ORDER BY nome")
    lista = [row[0] for row in cursor.fetchall()]
    conn.close()
    return lista if lista else ["Geral"]

def adicionar_especialidade(nome):
    """Cadastra uma nova especialidade no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO tabela_especialidades (nome) VALUES (?)", (nome.strip().capitalize(),))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Ignora se já existir
    conn.close()

def buscar_tabela_plano():
    """Busca a tabela de recebimentos do plano salva no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_valores_plano", conn)
    conn.close()
    return df

def buscar_tabela_repasse():
    """Busca a tabela de repasses da equipe salva no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_repasse_profissional", conn)
    conn.close()
    return df

def salvar_tabela_plano(df):
    """Grava os dados da planilha do plano permanentemente no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    df.to_sql("tabela_valores_plano", conn, if_exists="replace", index=False)
    conn.close()

def salvar_tabela_repasse(df):
    """Grava os dados da planilha de repasse permanentemente no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    df.to_sql("tabela_repasse_profissional", conn, if_exists="replace", index=False)
    conn.close()

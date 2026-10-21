"""
Motor de Valores e Tabelas de Preços.
Gerencia os valores pagos pelas operadoras e a margem/repasse da equipe.
"""
import sqlite3
import pandas as pd

DB_VALORES = "valores_clinica.db"

def init_db_valores():
    """Inicializa as tabelas financeiras da clínica."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    
    # 1. Tabela do Plano de Saúde (O que o convênio paga)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_valores_plano (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plano TEXT,
            codigo_tuss TEXT,
            procedimento TEXT,
            valor_plano REAL
        )
    ''')
    
    # 2. Tabela de Repasse (O que a clínica repassa ao profissional)
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

def buscar_tabela_plano():
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_valores_plano", conn)
    conn.close()
    return df

def buscar_tabela_repasse():
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_repasse_profissional", conn)
    conn.close()
    return df

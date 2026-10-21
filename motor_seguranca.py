"""
Motor de Segurança e Controle de Acessos.
Responsável por hashing de senhas, validação de login, níveis de permissão e audit trail.
"""
import sqlite3
import hashlib
import os
import pandas as pd
from datetime import datetime

DB_SEGURANCA = "seguranca_sistema.db"

def init_db_seguranca():
    """Cria e protege as tabelas de credenciais e logs de auditoria."""
    conn = sqlite3.connect(DB_SEGURANCA)
    cursor = conn.cursor()
    
    # Tabela de Utilizadores com Salt para Criptografia Forte
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Comum',
            ativo INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de Rastreabilidade/Auditoria de Acessos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs_acesso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            ip_acesso TEXT DEFAULT 'Local',
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            acao TEXT DEFAULT 'LOGIN'
        )
    ''')

    # Garantir a criação do Utilizador Administrador Padrão
    cursor.execute("SELECT * FROM usuarios WHERE username='admin'")
    if not cursor.fetchone():
        criar_usuario('admin', 'admin123', role='Administrador')
        
    conn.commit()
    conn.close()

def _gerar_hash_senha(senha, salt_hex=None):
    """Gera um hash PBKDF2_HMAC SHA-256 (Padrão de alta segurança com Salt)."""
    if salt_hex is None:
        salt = os.urandom(16)
    else:
        salt = bytes.fromhex(salt_hex)
        
    pwd_hash = hashlib.pbkdf2_hmac('sha256', senha.encode('utf-8'), salt, 100000)
    return pwd_hash.hex(), salt.hex()

def criar_usuario(username, senha, role='Comum'):
    """Cadastra um novo utilizador no banco de segurança com senha criptografada."""
    conn = sqlite3.connect(DB_SEGURANCA)
    cursor = conn.cursor()
    
    pwd_hash, salt_hex = _gerar_hash_senha(senha)
    try:
        cursor.execute(
            "INSERT INTO usuarios (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            (username.lower().strip(), pwd_hash, salt_hex, role)
        )
        conn.commit()
        conn.close()
        return True, "Utilizador criado com sucesso!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Nome de utilizador já existe."

def autenticar_usuario(username, senha):
    """Valida as credenciais contra o hash criptografado."""
    conn = sqlite3.connect(DB_SEGURANCA)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT password_hash, salt, role, ativo FROM usuarios WHERE username=?", 
        (username.lower().strip(),)
    )
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return False, None, "Utilizador não encontrado."
        
    stored_hash, salt_hex, role, ativo = user
    
    if not ativo:
        conn.close()
        return False, None, "Utilizador desativado."
        
    calculated_hash, _ = _gerar_hash_senha(senha, salt_hex)
    
    if calculated_hash == stored_hash:
        # Registrar no Log de Auditoria
        cursor.execute("INSERT INTO logs_acesso (username, acao) VALUES (?, 'LOGIN_SUCESSO')", (username,))
        conn.commit()
        conn.close()
        return True, role, "Autenticado com sucesso."
    else:
        cursor.execute("INSERT INTO logs_acesso (username, acao) VALUES (?, 'FALHA_SENHA')", (username,))
        conn.commit()
        conn.close()
        return False, None, "Senha incorreta."

def obter_relatorio_acessos():
    """Retorna o histórico de logins e tentativas de acesso."""
    conn = sqlite3.connect(DB_SEGURANCA)
    df = pd.read_sql_query(
        "SELECT username AS Utilizador, acao AS Evento, data_hora AS 'Data/Hora' FROM logs_acesso ORDER BY id DESC LIMIT 200", 
        conn
    )
    conn.close()
    return df

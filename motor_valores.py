"""
Motor de Valores e Tabelas de Preços.
Gerencia a leitura multi-abas de especialidades, valores do plano e repasses da equipe.
"""
import sqlite3
import pandas as pd
import io

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
    
    # 2. Tabela Master de Valores e Repasses por Especialidade e Plano
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_valores_completa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            especialidade TEXT,
            plano TEXT,
            tempo_atendimento TEXT,
            valor_plano REAL,
            valor_profissional REAL
        )
    ''')
    
    conn.commit()
    conn.close()

def buscar_especialidades():
    """Retorna a lista de especialidades cadastradas no banco."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM tabela_especialidades ORDER BY nome")
    lista = [row[0] for row in cursor.fetchall()]
    conn.close()
    if not lista:
        lista = ["PSICOLOGIA", "PSICOPEDAGOGIA", "PSICOMOTRICIDADE", "FONOAUDIOLOGIA", "NUTRIÇÃO", "FISIOTERAPIA"]
    return lista

def adicionar_especialidade(nome):
    """Cadastra uma nova especialidade."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (nome.strip().upper(),))
        conn.commit()
    except Exception:
        pass
    conn.close()

def buscar_tabela_completa():
    """Busca todos os valores cadastrados no banco."""
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_valores_completa", conn)
    conn.close()
    return df

def processar_e_salvar_excel_multi_abas(arquivo_upload):
    """
    Lê o Excel multi-abas enviado, trata o layout específico das tabelas da clínica,
    preenche células mescladas (Forward Fill) e salva no banco de dados.
    Retorna (Sucesso: bool, Mensagem: str)
    """
    try:
        arquivo_upload.seek(0)
        dados = arquivo_upload.read()
        xls = pd.ExcelFile(io.BytesIO(dados))
        
        dfs_consolidados = []
        conexoes_especialidades = set()

        for sheet_name in xls.sheet_names:
            # Lê a aba sem cabeçalho fixo para inspecionar as linhas
            df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)
            if df_raw.empty:
                continue

            # Localiza a linha onde está o cabeçalho real (procura por 'PLANO DE SAÚDE')
            cab_idx = None
            for idx, row in df_raw.iterrows():
                linha_str = " ".join([str(val).upper() for val in row.values if pd.notnull(val)])
                if "PLANO" in linha_str or "VALOR PLANO" in linha_str:
                    cab_idx = idx
                    break

            if cab_idx is not None:
                # Extrai os dados a partir do cabeçalho encontrado
                df_aba = df_raw.iloc[cab_idx + 1:].copy()
                # Pega as 4 primeiras colunas úteis (Plano, Tempo, Valor Plano, Valor Profissional)
                df_aba = df_aba.iloc[:, :4]
                df_aba.columns = ["plano", "tempo_atendimento", "valor_plano", "valor_profissional"]
            else:
                # Fallback caso o layout seja diferente
                df_aba = df_raw.iloc[:, :4].copy()
                df_aba.columns = ["plano", "tempo_atendimento", "valor_plano", "valor_profissional"]

            # Limpeza e Tratamento de Dados
            df_aba["especialidade"] = sheet_name.strip().upper()
            conexoes_especialidades.add(sheet_name.strip().upper())

            # Preenchimento para baixo (Forward Fill) do plano (resolve células mescladas do Excel)
            df_aba["plano"] = df_aba["plano"].replace(["", "nan", "None"], pd.NA).ffill()

            # Remove linhas totalmente vazias ou cabeçalhos repetidos
            df_aba = df_aba.dropna(subset=["valor_plano"])
            df_aba = df_aba[~df_aba["plano"].astype(str).str.contains("PLANO DE SAÚDE", na=False, case=False)]

            # Conversão numérica segura
            df_aba["valor_plano"] = pd.to_numeric(df_aba["valor_plano"], errors="coerce").fillna(0.0)
            df_aba["valor_profissional"] = pd.to_numeric(df_aba["valor_profissional"], errors="coerce").fillna(0.0)
            df_aba["tempo_atendimento"] = df_aba["tempo_atendimento"].astype(str).str.strip()

            dfs_consolidados.append(df_aba)

        if not dfs_consolidados:
            return False, "⚠️ Erro de leitura: O ficheiro Excel não contém dados válidos nas abas."

        df_final = pd.concat(dfs_consolidados, ignore_index=True)

        # Salva na base de dados
        conn = sqlite3.connect(DB_VALORES)
        cursor = conn.cursor()
        
        # Insere as especialidades encontradas na tabela de especialidades
        for esp in conexoes_especialidades:
            cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp,))
        
        conn.commit()
        conn.close()

        # Substitui a tabela completa no banco
        conn = sqlite3.connect(DB_VALORES)
        df_final.to_sql("tabela_valores_completa", conn, if_exists="replace", index=False)
        conn.close()

        return True, f"✅ Ficheiro lido com sucesso! {len(df_final)} regras de valores importadas de {len(conexoes_especialidades)} abas ({', '.join(conexoes_especialidades)})."

    except Exception as e:
        return False, f"❌ Erro crítico ao processar o ficheiro Excel: {str(e)}. Verifique se o ficheiro está corrompido ou fechado."

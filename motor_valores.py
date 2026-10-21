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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_especialidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_valores_plano (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plano TEXT,
            codigo_tuss TEXT,
            procedimento TEXT,
            valor_plano REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_repasse_profissional (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            especialidade TEXT,
            plano TEXT,
            tempo_atendimento TEXT,
            valor_profissional REAL
        )
    ''')

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
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM tabela_especialidades ORDER BY nome")
    lista = [row[0] for row in cursor.fetchall()]
    conn.close()
    if not lista:
        lista = ["PSICOLOGIA", "PSICOPEDAGOGIA", "PSICOMOTRICIDADE", "FONOAUDIOLOGIA", "NUTRIÇÃO", "FISIOTERAPIA"]
    return lista

def adicionar_especialidade(nome):
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (nome.strip().upper(),))
        conn.commit()
    except Exception:
        pass
    conn.close()

def buscar_tabela_plano():
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_valores_plano", conn)
    conn.close()
    return df

def buscar_tabela_repasse():
    conn = sqlite3.connect(DB_VALORES)
    try:
        df = pd.read_sql_query("SELECT * FROM tabela_valores_completa", conn)
        if df.empty:
            df = pd.read_sql_query("SELECT * FROM tabela_repasse_profissional", conn)
    except Exception:
        df = pd.DataFrame(columns=["especialidade", "plano", "tempo_atendimento", "valor_profissional"])
    conn.close()
    return df

def salvar_tabela_plano(df):
    conn = sqlite3.connect(DB_VALORES)
    df.to_sql("tabela_valores_plano", conn, if_exists="replace", index=False)
    conn.close()

def salvar_tabela_repasse(df):
    conn = sqlite3.connect(DB_VALORES)
    df.to_sql("tabela_valores_completa", conn, if_exists="replace", index=False)
    df.to_sql("tabela_repasse_profissional", conn, if_exists="replace", index=False)
    conn.close()

def processar_e_salvar_excel_multi_abas(arquivo_upload):
    try:
        arquivo_upload.seek(0)
        dados = arquivo_upload.read()
        try:
            xls = pd.ExcelFile(io.BytesIO(dados))
        except Exception as e:
            return False, f"O ficheiro enviado não é um Excel válido ou está corrompido. Detalhe técnico: {str(e)}"
        
        dfs_consolidados = []
        conexoes_especialidades = set()
        abas_com_erro = []

        for sheet_name in xls.sheet_names:
            try:
                df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)
                if df_raw.empty:
                    continue

                cab_idx = None
                for idx, row in df_raw.iterrows():
                    linha_str = " ".join([str(val).upper() for val in row.values if pd.notnull(val)])
                    if "PLANO" in linha_str or "VALOR PLANO" in linha_str:
                        cab_idx = idx
                        break

                if cab_idx is not None:
                    df_aba = df_raw.iloc[cab_idx + 1:].copy()
                    df_aba = df_aba.iloc[:, :4]
                    df_aba.columns = ["plano", "tempo_atendimento", "valor_plano", "valor_profissional"]
                else:
                    df_aba = df_raw.iloc[:, :4].copy()
                    if df_aba.shape[1] >= 4:
                        df_aba.columns = ["plano", "tempo_atendimento", "valor_plano", "valor_profissional"]
                    else:
                        abas_com_erro.append(sheet_name)
                        continue

                esp_nome = sheet_name.strip().upper()
                df_aba["especialidade"] = esp_nome
                conexoes_especialidades.add(esp_nome)

                df_aba["plano"] = df_aba["plano"].replace(["", "nan", "None"], pd.NA).ffill()
                df_aba = df_aba.dropna(subset=["valor_plano"])
                df_aba = df_aba[~df_aba["plano"].astype(str).str.contains("PLANO DE SAÚDE", na=False, case=False)]

                df_aba["valor_plano"] = pd.to_numeric(df_aba["valor_plano"], errors="coerce").fillna(0.0)
                df_aba["valor_profissional"] = pd.to_numeric(df_aba["valor_profissional"], errors="coerce").fillna(0.0)
                df_aba["tempo_atendimento"] = df_aba["tempo_atendimento"].astype(str).str.strip()

                dfs_consolidados.append(df_aba)
            except Exception as ex:
                abas_com_erro.append(f"{sheet_name} ({str(ex)})")

        if not dfs_consolidados:
            return False, f"⚠️ Nenhuma regra de valor foi extraída. Abas com falha: {abas_com_erro}"

        df_final = pd.concat(dfs_consolidados, ignore_index=True)

        conn = sqlite3.connect(DB_VALORES)
        cursor = conn.cursor()
        for esp in conexoes_especialidades:
            cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp,))
        conn.commit()
        conn.close()

        salvar_tabela_repasse(df_final)

        msg_retorno = f"✅ Importação Master Concluída! {len(df_final)} registos processados de {len(conexoes_especialidades)} abas ({', '.join(conexoes_especialidades)})."
        if abas_com_erro:
            msg_retorno += f" ⚠️ Aviso: Abas com divergência: {abas_com_erro}."

        return True, msg_retorno

    except Exception as e:
        return False, f"❌ Erro crítico ao processar a planilha multi-abas: {str(e)}"

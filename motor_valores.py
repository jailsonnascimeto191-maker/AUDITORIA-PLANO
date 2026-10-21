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
    
    # 3. Tabela Master Completa para Multi-abas (Armazena separadamente por especialidade)
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
    """Retorna a lista completa de especialidades cadastradas no banco."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    
    # Garante que busca tanto da tabela de especialidades quanto das especialidades já importadas na tabela master
    cursor.execute("SELECT nome FROM tabela_especialidades UNION SELECT DISTINCT especialidade FROM tabela_valores_completa ORDER BY nome")
    lista = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    
    if not lista:
        lista = ["PSICOLOGIA", "PSICOPEDAGOGIA", "PSICOMOTRICIDADE", "FONOAUDIOLOGIA", "NUTRIÇÃO", "FISIOTERAPIA"]
    return lista

def adicionar_especialidade(nome):
    """Cadastra uma nova especialidade."""
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    try:
        esp_limpa = nome.strip().upper()
        cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp_limpa,))
        conn.commit()
    except Exception:
        pass
    conn.close()

def buscar_tabela_plano():
    """Busca a tabela de recebimentos do plano salva no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    df = pd.read_sql_query("SELECT * FROM tabela_valores_plano", conn)
    conn.close()
    return df

def buscar_tabela_repasse():
    """Busca a tabela completa de repasses e valores por especialidade."""
    conn = sqlite3.connect(DB_VALORES)
    try:
        df = pd.read_sql_query("SELECT * FROM tabela_valores_completa", conn)
        if not df.empty and 'especialidade' in df.columns:
            df['especialidade'] = df['especialidade'].astype(str).str.upper().str.strip()
    except Exception:
        df = pd.DataFrame(columns=["especialidade", "plano", "tempo_atendimento", "valor_plano", "valor_profissional"])
    conn.close()
    return df

def salvar_tabela_plano(df):
    """Grava os dados da planilha do plano no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    df.to_sql("tabela_valores_plano", conn, if_exists="replace", index=False)
    conn.close()

def salvar_tabela_repasse(df):
    """Grava os dados consolidados de repasse por especialidade no banco de dados."""
    conn = sqlite3.connect(DB_VALORES)
    if not df.empty and 'especialidade' in df.columns:
        df['especialidade'] = df['especialidade'].astype(str).str.upper().str.strip()
    df.to_sql("tabela_valores_completa", conn, if_exists="replace", index=False)
    conn.close()

def processar_e_salvar_excel_multi_abas(arquivo_upload):
    """
    Lê obrigatoriamente todas as abas do Excel, isola os valores por especialidade,
    trata células mescladas e notifica erros detalhados caso alguma aba falhe.
    """
    try:
        arquivo_upload.seek(0)
        dados = arquivo_upload.read()
        try:
            xls = pd.ExcelFile(io.BytesIO(dados))
        except Exception as e:
            return False, f"❌ Erro de Leitura: O ficheiro não é um Excel válido ou está corrompido. Detalhe: {str(e)}"
        
        dfs_consolidados = []
        conexoes_especialidades = set()
        abas_com_erro = []

        for sheet_name in xls.sheet_names:
            try:
                df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)
                if df_raw.empty:
                    abas_com_erro.append(f"{sheet_name} (Aba vazia)")
                    continue

                # Localiza a linha do cabeçalho real na aba
                cab_idx = None
                for idx, row in df_raw.iterrows():
                    linha_str = " ".join([str(val).upper() for val in row.values if pd.notnull(val)])
                    if "PLANO" in linha_str or "VALOR PLANO" in linha_str or "TEMPO" in linha_str:
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
                        abas_com_erro.append(f"{sheet_name} (Estrutura de colunas incompatível)")
                        continue

                # Define a especialidade exatamente com o nome da aba
                esp_nome = sheet_name.strip().upper()
                df_aba["especialidade"] = esp_nome
                conexoes_especialidades.add(esp_nome)

                # Preenchimento Forward Fill para células mescladas de planos
                df_aba["plano"] = df_aba["plano"].replace(["", "nan", "None"], pd.NA).ffill()
                df_aba = df_aba.dropna(subset=["valor_plano"])
                df_aba = df_aba[~df_aba["plano"].astype(str).str.contains("PLANO DE SAÚDE", na=False, case=False)]

                # Conversão numérica e limpeza
                df_aba["valor_plano"] = pd.to_numeric(df_aba["valor_plano"], errors="coerce").fillna(0.0)
                df_aba["valor_profissional"] = pd.to_numeric(df_aba["valor_profissional"], errors="coerce").fillna(0.0)
                df_aba["tempo_atendimento"] = df_aba["tempo_atendimento"].astype(str).str.strip()

                dfs_consolidados.append(df_aba)
            except Exception as ex:
                abas_com_erro.append(f"{sheet_name} (Erro de processamento: {str(ex)})")

        if not dfs_consolidados:
            return False, f"⚠️ Nenhuma regra de valor foi extraída de nenhuma aba. Abas com falha: {abas_com_erro}. Onde buscar a solução: Certifique-se de que cada aba possui colunas com 'Plano de Saúde', 'Tempo' e 'Valor'."

        df_final = pd.concat(dfs_consolidados, ignore_index=True)

        # Regista as especialidades na base de dados
        conn = sqlite3.connect(DB_VALORES)
        cursor = conn.cursor()
        for esp in conexoes_especialidades:
            cursor.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp,))
        conn.commit()
        conn.close()

        # Salva na tabela master consolidada
        salvar_tabela_repasse(df_final)

        msg_retorno = f"✅ Importação Master Concluída com Sucesso! {len(df_final)} regras de valores distribuídas por {len(conexoes_especialidades)} especialidades ({', '.join(sorted(conexoes_especialidades))})."
        if abas_com_erro:
            msg_retorno += f" ⚠️ Atenção, as seguintes abas não puderam ser lidas e precisam de ajuste: {abas_com_erro}."

        return True, msg_retorno

    except Exception as e:
        return False, f"❌ Erro crítico ao processar o arquivo Excel: {str(e)}. Onde buscar a solução: Verifique se o arquivo está aberto no Excel no seu computador durante o upload."

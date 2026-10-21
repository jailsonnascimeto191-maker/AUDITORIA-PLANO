import io
import streamlit as st
import pandas as pd
import sqlite3
import motor_seguranca
import motor_extracao

# Inicialização da Base de Dados Local
DB_VALORES = "valores_clinica.db"

def init_db_valores():
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tabela_especialidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
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

init_db_valores()

def buscar_especialidades():
    conn = sqlite3.connect(DB_VALORES)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT especialidade FROM tabela_valores_completa UNION SELECT nome FROM tabela_especialidades ORDER BY especialidade")
    lista = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    if not lista:
        lista = ["PSICOLOGIA", "PSICOPEDAGOGIA", "PSICOMOTRICIDADE", "FONOAUDIOLOGIA", "NUTRIÇÃO", "FISIOTERAPIA"]
    return lista

def processar_e_salvar_excel_multi_abas(arquivo_upload):
    try:
        arquivo_upload.seek(0)
        dados = arquivo_upload.read()
        xls = pd.ExcelFile(io.BytesIO(dados))
        
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
            return False, f"⚠️ Nenhuma regra extraída. Abas com erro: {abas_com_erro}"

        df_final = pd.concat(dfs_consolidados, ignore_index=True)

        conn = sqlite3.connect(DB_VALORES)
        df_final.to_sql("tabela_valores_completa", conn, if_exists="replace", index=False)
        conn.close()

        return True, f"✅ Importação Master Concluída! {len(df_final)} registos de {len(conexoes_especialidades)} abas ({', '.join(sorted(conexoes_especialidades))})."
    except Exception as e:
        return False, f"❌ Erro crítico ao processar o Excel: {str(e)}"

# Inicialização de Segurança
try:
    if hasattr(motor_seguranca, 'init_db_seguranca'):
        motor_seguranca.init_db_seguranca()
except Exception:
    pass

st.set_page_config(page_title="Espaço Saúde - Auditoria & Repasses", page_icon="🏥", layout="wide")

PLANOS_SAUDE = [
    "Identificar pelo arquivo", "Unimed Recife", "Bradesco Saúde",
    "SulAmérica", "Amil", "Cassi", "GEAP", "Postal Saúde", "Assefaz", "Outros"
]

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_atual = None
    st.session_state.nivel_permissao = None

if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style='text-align: center; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);'>
            <h2 style='color: #1e293b; margin-bottom: 0;'>🏥 Espaço Saúde</h2>
            <p style='color: #64748b; font-size: 14px;'>Sistema Integrado de Auditoria, Faturamento & Repasses</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            btn_entrar = st.form_submit_button("Acessar Painel", use_container_width=True)
            
            if btn_entrar:
                if hasattr(motor_seguranca, 'autenticar_usuario'):
                    sucesso, role, msg = motor_seguranca.autenticar_usuario(usuario, senha)
                    if sucesso:
                        st.session_state.autenticado = True
                        st.session_state.usuario_atual = usuario
                        st.session_state.nivel_permissao = role
                        st.rerun()
                    else:
                        st.error(f"⚠️ {msg}")
                else:
                    st.warning("⚠️ Módulo de segurança a sincronizar.")

else:
    menus_disponiveis = ["📊 Painel", "📥 Casa das Máquinas", "⚠️ Lupa de Glosas"]
    if st.session_state.nivel_permissao == "Administrador":
        menus_disponiveis.extend(["💰 Valores", "👥 Cadastros", "🛡️ Acessos"])

    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.usuario_atual.capitalize()}")
        st.caption(f"Perfil: **{st.session_state.nivel_permissao}**")
        
        if st.button("🚪 Sair do Sistema", use_container_width=True):
            st.session_state.autenticado = False
            st.rerun()
            
        st.markdown("---")
        menu = st.radio("Navegação", menus_disponiveis, label_visibility="collapsed")

    if menu == "📊 Painel":
        st.title("📊 Painel Geral de Faturamento & Repasses")
        df_proc = st.session_state.get("ultimo_processamento", pd.DataFrame())
        if not df_proc.empty:
            st.dataframe(df_proc, use_container_width=True)
        else:
            st.info("💡 Faça o upload de um extrato na **Casa das Máquinas**.")

    elif menu == "📥 Casa das Máquinas":
        st.title("📥 Casa das Máquinas")
        plano_selecionado = st.selectbox("Selecione a Operadora/Plano de Saúde", PLANOS_SAUDE)
        somente_glosas = st.checkbox("Filtrar e exibir APENAS itens com Glosa", value=True)
        
        arquivo_dem = st.file_uploader("Demonstrativo do Convênio", type=["xlsx", "xls", "csv", "pdf", "xml", "docx"])
        if st.button("⚡ Iniciar Processamento & Auditoria", type="primary", use_container_width=True):
            if arquivo_dem is not None:
                df_res, erro = motor_extracao.extrair_glosas_de_arquivo(arquivo_dem, plano=plano_selecionado, somente_glosas=somente_glosas)
                if not df_res.empty:
                    st.success(f"✅ Processamento concluído! {len(df_res)} registos validados.")
                    st.dataframe(df_res, use_container_width=True)
                    st.session_state["ultimo_processamento"] = df_res

    elif menu == "⚠️ Lupa de Glosas":
        st.title("⚠️ Lupa de Glosas")
        df = st.session_state.get("ultimo_processamento", pd.DataFrame())
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum arquivo auditado.")

    elif menu == "💰 Valores":
        st.title("💰 Gestão de Tabelas de Preços e Repasses")
        st.info("💡 Importe a sua planilha oficial da clínica abaixo. O sistema lerá todas as abas e distribuirá por especialidade.")
        
        file_repasse_multi = st.file_uploader("Subir Planilha Oficial (Excel Multi-abas)", type=["xlsx", "xls"])
        if file_repasse_multi:
            if st.button("🚀 Processar e Distribuir Todas as Abas", type="primary"):
                sucesso, msg = processar_e_salvar_excel_multi_abas(file_repasse_multi)
                if sucesso:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.markdown("---")
        especialidades_db = buscar_especialidades()
        esp_selecionada = st.selectbox("Visualizar Especialidade:", especialidades_db)

        conn = sqlite3.connect(DB_VALORES)
        df_master = pd.read_sql_query("SELECT * FROM tabela_valores_completa", conn)
        conn.close()

        if not df_master.empty and 'especialidade' in df_master.columns:
            df_esp = df_master[df_master['especialidade'].astype(str).str.upper() == str(esp_selecionada).upper()]
        else:
            df_esp = pd.DataFrame(columns=["especialidade", "plano", "tempo_atendimento", "valor_plano", "valor_profissional"])

        st.markdown(f"**Valores Atuais: {esp_selecionada}**")
        st.dataframe(df_esp, use_container_width=True)

    elif menu == "👥 Cadastros":
        st.title("👥 Cadastros")
        st.info("Gestão de profissionais e acessos.")

    elif menu == "🛡️ Acessos":
        st.title("🛡️ Auditoria de Segurança")
        if hasattr(motor_seguranca, 'obter_relatorio_acessos'):
            st.dataframe(motor_seguranca.obter_relatorio_acessos(), use_container_width=True)

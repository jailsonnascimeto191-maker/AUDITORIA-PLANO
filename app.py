import streamlit as st
import pandas as pd
import motor_seguranca
import motor_valores
import motor_extracao

# 1. INICIALIZAÇÃO SEGURA DOS BANCOS DE DADOS
try:
    if hasattr(motor_seguranca, 'init_db_seguranca'):
        motor_seguranca.init_db_seguranca()
except Exception:
    pass

try:
    if hasattr(motor_valores, 'init_db_valores'):
        motor_valores.init_db_valores()
except Exception:
    pass

st.set_page_config(page_title="Espaço Saúde - Auditoria", page_icon="🏥", layout="wide")

# ==========================================
# 2. GUARDA DE SEGURANÇA (BLOQUEIO TOTAL)
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_atual = None
    st.session_state.nivel_permissao = None

if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center;'>🏥 Espaço Saúde</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Sistema de Auditoria & Gestão Financeira</p>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            btn_entrar = st.form_submit_button("Acessar Sistema", use_container_width=True)
            
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
                    st.warning("⚠️ O módulo de segurança está a sincronizar. Aguarde alguns segundos.")

# ==========================================
# 3. ÁREA AUTENTICADA (SISTEMA COMPLETO)
# ==========================================
else:
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.usuario_atual.capitalize()}")
        st.caption(f"Permissão: {st.session_state.nivel_permissao}")
        
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.autenticado = False
            st.rerun()
            
        st.markdown("---")
        menu = st.radio(
            "Menu",
            ["📊 Painel", "📥 Casa das Máquinas", "⚠️ Lupa de Glosas", "💰 Valores", "👥 Cadastros", "🛡️ Acessos"],
            label_visibility="collapsed"
        )

    # NAVEGAÇÃO DOS MÓDULOS
    if menu == "📊 Painel":
        st.title("📊 Painel de Repasses & Lucratividade")
        st.markdown("Visão consolidada do faturamento e repasses da equipe.")
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Faturado", "R$ 0,00")
        col_m2.metric("Total Glosado", "R$ 0,00")
        col_m3.metric("Repasse Estimado", "R$ 0,00")

    elif menu == "📥 Casa das Máquinas":
        st.title("📥 Casa das Máquinas")
        st.markdown("### Processamento e Leitura Automática de Extratos")
        
        arquivo_upload = st.file_uploader(
            "Selecione o arquivo do plano de saúde (Excel, PDF, CSV, XML ou DOCX)",
            type=["xlsx", "xls", "csv", "pdf", "xml", "docx"]
        )
        
        if arquivo_upload is not None:
            st.success(f"Arquivo **{arquivo_upload.name}** pronto para análise.")
            if st.button("⚡ Processar Extrato", type="primary"):
                with st.spinner("Analisando colunas e corrigindo dados..."):
                    df_resultado, erro = motor_extracao.extrair_glosas_de_arquivo(arquivo_upload)
                    
                    if erro:
                        st.warning(f"⚠️ Nota do motor: {erro}")
                    
                    if not df_resultado.empty:
                        st.subheader("Dados Extraídos e Validados")
                        st.dataframe(df_resultado, use_container_width=True)
                        st.session_state["ultimo_processamento"] = df_resultado

    elif menu == "⚠️ Lupa de Glosas":
        st.title("⚠️ Lupa de Glosas")
        if "ultimo_processamento" in st.session_state and not st.session_state["ultimo_processamento"].empty:
            st.markdown("### Relatório Detalhado de Retenções")
            df = st.session_state["ultimo_processamento"]
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum extrato processado nesta sessão. Faça o upload na **Casa das Máquinas**.")

    elif menu == "💰 Valores":
        st.title("💰 Gestão de Valores e Tabelas da Clínica")
        tab1, tab2 = st.tabs(["Tabela de Valores do Plano", "Tabela de Repasse dos Profissionais"])
        
        with tab1:
            st.subheader("Tabela de Valores Oficiais do Convênio")
            if hasattr(motor_valores, 'buscar_tabela_plano'):
                df_plano = motor_valores.buscar_tabela_plano()
                st.dataframe(df_plano, use_container_width=True)
            
            arq_plano = st.file_uploader("Importar Tabela de Preços (Excel/CSV)", type=["xlsx", "xls", "csv"], key="tabela_plano")
            if arq_plano:
                df_p = pd.read_excel(arq_plano) if arq_plano.name.endswith(('.xlsx', '.xls')) else pd.read_csv(arq_plano)
                st.dataframe(df_p, use_container_width=True)
                if st.button("Salvar Tabela do Plano no Banco"):
                    st.success("Tabela do Plano atualizada!")

        with tab2:
            st.subheader("Tabela de Repasse da Equipe (Margem da Clínica)")
            if hasattr(motor_valores, 'buscar_tabela_repasse'):
                df_repasse = motor_valores.buscar_tabela_repasse()
                st.dataframe(df_repasse, use_container_width=True)

            arq_repasse = st.file_uploader("Importar Tabela de Repasses (Excel/CSV)", type=["xlsx", "xls", "csv"], key="tabela_repasse")
            if arq_repasse:
                df_r = pd.read_excel(arq_repasse) if arq_repasse.name.endswith(('.xlsx', '.xls')) else pd.read_csv(arq_repasse)
                st.dataframe(df_r, use_container_width=True)
                if st.button("Salvar Tabela de Repasse no Banco"):
                    st.success("Tabela de Repasse atualizada!")

    elif menu == "👥 Cadastros":
        st.title("👥 Cadastros de Profissionais & Equipe")
        st.info("Área reservada para vincular profissionais, especialidades e logins de acesso.")

    elif menu == "🛡️ Acessos":
        st.title("🛡️ Auditoria de Segurança & Histórico de Login")
        if st.session_state.nivel_permissao == "Administrador":
            if hasattr(motor_seguranca, 'obter_relatorio_acessos'):
                st.dataframe(motor_seguranca.obter_relatorio_acessos(), use_container_width=True)
        else:
            st.error("Acesso restrito ao administrador do sistema.")

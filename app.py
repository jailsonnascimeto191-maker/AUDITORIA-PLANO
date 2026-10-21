import streamlit as st
import pandas as pd
import motor_seguranca
import motor_valores
import motor_auditoria

# 1. INICIALIZAR BANCOS DE DADOS COM PROTEÇÃO CONTRA PROBLEMAS DE CACHE
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
                    st.warning("⚠️ O módulo de segurança está a sincronizar no GitHub. Por favor, aguarde alguns segundos e atualize a página.")

# ==========================================
# 3. ÁREA AUTENTICADA (SISTEMA LIBERADO)
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
        st.title("Painel de Repasses")
        st.info("Visão financeira consolidada e cruzamentos.")

    elif menu == "📥 Casa das Máquinas":
        st.title("Casa das Máquinas (Auditoria)")
        st.info("Upload de demonstrativos de planos e relatórios da equipe.")

    elif menu == "⚠️ Lupa de Glosas":
        st.title("Lupa de Glosas")
        st.info("Relatórios detalhados de retenções com exportação PDF/Excel.")

    elif menu == "💰 Valores":
        st.title("Gestão de Valores")
        tab1, tab2 = st.tabs(["Tabela de Valores do Plano", "Tabela de Repasse dos Profissionais"])
        with tab1:
            st.subheader("Valores Oficiais Pagos pelos Convênios")
            if hasattr(motor_valores, 'buscar_tabela_plano'):
                st.dataframe(motor_valores.buscar_tabela_plano(), use_container_width=True)
            else:
                st.info("Tabela em sincronização...")
        with tab2:
            st.subheader("Valores Repassados à Equipa (Margem da Clínica)")
            if hasattr(motor_valores, 'buscar_tabela_repasse'):
                st.dataframe(motor_valores.buscar_tabela_repasse(), use_container_width=True)
            else:
                st.info("Tabela em sincronização...")

    elif menu == "👥 Cadastros":
        st.title("Cadastros de Profissionais")
        st.info("Gestão de corpo clínico e permissões de usuários.")

    elif menu == "🛡️ Acessos":
        st.title("Auditoria de Segurança & Acessos")
        if st.session_state.nivel_permissao == "Administrador":
            if hasattr(motor_seguranca, 'obter_relatorio_acessos'):
                st.dataframe(motor_seguranca.obter_relatorio_acessos(), use_container_width=True)
            else:
                st.info("Logs em sincronização...")
        else:
            st.error("Acesso restrito ao administrador do sistema.")

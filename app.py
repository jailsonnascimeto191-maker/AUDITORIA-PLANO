import streamlit as st
import pandas as pd

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Espaço Saúde - Análise de Produção",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. ESTILIZAÇÃO CSS (VISUAL PREMIUM)
# ==========================================
st.markdown("""
<style>
    /* Fundo geral e tipografia */
    .stApp { background-color: #f4f6f5; font-family: 'Segoe UI', sans-serif; }
    
    /* Menu Lateral Verde Escuro */
    [data-testid="stSidebar"] { background-color: #0b2e1e !important; color: #ffffff !important; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    
    /* Estilo dos Cartões (KPIs) */
    .metric-card {
        background-color: #ffffff; border: 1px solid #e1e6e3; border-radius: 8px;
        padding: 18px 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); height: 100%;
    }
    .metric-title { font-size: 11px; font-weight: 700; color: #556b60; text-transform: uppercase; margin-bottom: 6px; }
    .metric-value { font-size: 26px; font-weight: 800; color: #0d2818; }
    .metric-value-green { font-size: 26px; font-weight: 800; color: #1e7e48; }
    .metric-value-red { font-size: 26px; font-weight: 800; color: #b32d2d; }
    .metric-subtext { font-size: 12px; color: #708579; margin-top: 4px; }
    
    /* Botões Padrão Verde */
    .stButton>button {
        background-color: #1b6b3e !important; color: white !important;
        border-radius: 6px !important; font-weight: 600 !important; border: none !important;
    }
    .stButton>button:hover { background-color: #14522f !important; }
    
    /* Aviso amarelo suave para área de administração */
    .admin-warning {
        background-color: #fdf5e6; color: #855a1f; padding: 12px 16px; 
        border-radius: 6px; border: 1px solid #f5e1c8; font-size: 14px; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. BANCOS DE DADOS EM MEMÓRIA (INICIAM VAZIOS/MOCK)
# ==========================================
# Histórico de Auditoria
if 'db_auditoria' not in st.session_state:
    st.session_state.db_auditoria = pd.DataFrame(columns=[
        'MES_COMPETENCIA', 'PROFISSIONAL', 'DATA_ATENDIMENTO',
        'PACIENTE', 'OPERADORA', 'VALOR_PRODUCAO',
        'VALOR_PAGO', 'VALOR_GLOSA', 'MOTIVO_GLOSA', 'REPASSE_FINAL'
    ])

# Cadastros de Valores (Mock para visualização inicial)
if 'db_valores_fisio' not in st.session_state:
    st.session_state.db_valores_fisio = pd.DataFrame({
        "PLANO DE SAÚDE": ["BRADESCO", "UNIMED", "CASSI"],
        "TEMPO": ["30 MIN", "60 MIN", "30 MIN"],
        "VALOR PLANO (R$)": [11.86, 23.72, 16.74],
        "VALOR PROF (R$)": [5.93, 11.86, 8.37]
    })

# ==========================================
# 4. BARRA LATERAL (MENU E NAVEGAÇÃO)
# ==========================================
with st.sidebar:
    st.markdown("## 🏥 Espaço Saúde")
    st.markdown("<p style='font-size: 12px; color: #a3b8ac; margin-top: -15px;'>Sistema de Análise</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    menu = st.radio(
        "Navegação",
        ["📊 Painel", "📤 Enviar arquivos", "⚠️ Glosas", "⚙️ Cadastros"],
        label_visibility="collapsed"
    )

df_db = st.session_state.db_auditoria

# ==========================================
# TELA 1: PAINEL PRINCIPAL
# ==========================================
if menu == "📊 Painel":
    col_titulo, col_usuario = st.columns([3, 1])
    with col_titulo:
        st.title("Painel de Repasses")
        st.caption("Visão financeira consolidada e geração de relatórios")
    with col_usuario:
        st.markdown("<br><p style='text-align: right; font-weight: 600;'>Olá, <b>Jailson</b></p>", unsafe_allow_html=True)

    st.markdown("### Filtros de Pesquisa")
    f_col1, f_col2, f_col3 = st.columns([1, 2, 1])
    
    meses_disponiveis = df_db['MES_COMPETENCIA'].unique().tolist() if not df_db.empty else ['Sem dados']
    profissionais_disponiveis = ['Todos'] + df_db['PROFISSIONAL'].unique().tolist() if not df_db.empty else ['Todos']
    
    with f_col1:
        mes_selecionado = st.selectbox("Competência", meses_disponiveis)
    with f_col2:
        prof_selecionado = st.selectbox("Profissional", profissionais_disponiveis)
    with f_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("☁️ Salvar na Nuvem", use_container_width=True)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown('<div class="metric-card"><div class="metric-title">Produção</div><div class="metric-value">R$ 0,00</div><div class="metric-subtext">0 atendimentos</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown('<div class="metric-card"><div class="metric-title">Pago pelos Planos</div><div class="metric-value">R$ 0,00</div><div class="metric-subtext">Valor faturado</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown('<div class="metric-card"><div class="metric-title">Total Glosado</div><div class="metric-value-red">R$ 0,00</div><div class="metric-subtext">Valores retidos</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown('<div class="metric-card"><div class="metric-title">Repasse Definitivo</div><div class="metric-value-green">R$ 0,00</div><div class="metric-subtext">A transferir</div></div>', unsafe_allow_html=True)

    st.markdown("<br>### Detalhamento para o Relatório", unsafe_allow_html=True)
    st.info("Nenhum arquivo processado. Vá a 'Enviar arquivos' para iniciar.")

# ==========================================
# TELA 2: ENVIO DE ARQUIVOS
# ==========================================
elif menu == "📤 Enviar arquivos":
    st.title("Casa das Máquinas (Auditoria)")
    st.caption("Faça o upload dos arquivos para cruzamento. Eles serão descartados após o processamento.")
    
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        st.markdown("#### 1. Extratos (Operadoras)")
        st.file_uploader("CASSI (.xlsx)", type=["xlsx"])
        st.file_uploader("Unimed (.xlsx)", type=["xlsx"])
        st.file_uploader("Bradesco (.xlsx)", type=["xlsx"])
    with col_e2:
        st.markdown("#### 2. Planilhas (Equipe)")
        st.file_uploader("Arraste os espelhamentos (.xlsx)", type=["xlsx"], accept_multiple_files=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    st.button("🚀 Processar Auditoria", type="primary")

# ==========================================
# TELA 3: CONTROLE DE GLOSAS
# ==========================================
elif menu == "⚠️ Glosas":
    st.title("Lupa de Glosas")
    st.caption("Investigue retenções e organize recursos por competência.")

    f_col1, f_col2 = st.columns(2)
    with f_col1:
        st.selectbox("Mês da Glosa", ['Sem dados'])
    with f_col2:
        st.selectbox("Profissional", ['Todos'])

    st.markdown('<div class="metric-card" style="width: 300px; margin-top: 15px; margin-bottom: 25px;"><div class="metric-title">Dinheiro Retido</div><div class="metric-value-red">R$ 0,00</div><div class="metric-subtext">0 atendimentos glosados</div></div>', unsafe_allow_html=True)
    st.info("Nenhuma glosa detectada no momento.")

# ==========================================
# TELA 4: CADASTROS (CONFIGURAÇÕES GERAIS)
# ==========================================
elif menu == "⚙️ Cadastros":
    st.title("Cadastros")
    st.markdown('<div class="admin-warning">Somente administradores alteram cadastros, valores e regras. As suas mudanças aqui refletem-se em toda a auditoria.</div>', unsafe_allow_html=True)

    # Criação das Abas
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Tabela de valores", "Planos", "Profissionais", "Feriados", "Códigos de glosa", "Regras do repasse"
    ])

    # ABA 1: TABELA DE VALORES
    with tab1:
        st.markdown("Tabela no mesmo formato da planilha da clínica. O repasse usa o **valor do profissional** desta tabela.")
        
        # Botões de Importar/Exportar
        col_btn1, col_btn2, _ = st.columns([2, 2, 8])
        with col_btn1:
            st.button("📥 Importar planilha")
        with col_btn2:
            st.button("📤 Exportar planilha")
            
        st.markdown("<hr style='margin-top: 5px; margin-bottom: 15px;'>", unsafe_allow_html=True)
        
        # Pílulas/Seleção de Especialidade
        especialidade = st.radio(
            "Selecione a Especialidade:",
            ["Fisioterapia", "Fonoaudiologia", "Nutrição", "Psicologia", "Psicomotricidade", "Psicopedagogia"],
            horizontal=True
        )
        
        st.markdown(f"**TABELA DE VALORES - {especialidade.upper()} | CLÍNICA ESPAÇO SAÚDE**")
        
        # Editor Interativo de Dados (Data Grid)
        # O st.data_editor permite adicionar, remover e editar linhas como no Excel
        novo_df = st.data_editor(
            st.session_state.db_valores_fisio,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "PLANO DE SAÚDE": st.column_config.SelectboxColumn("PLANO DE SAÚDE", options=["BRADESCO", "UNIMED", "CASSI", "FOX", "MEDSERVICE"], required=True),
                "TEMPO": st.column_config.SelectboxColumn("TEMPO", options=["30 MIN", "45 MIN", "60 MIN"], required=True),
                "VALOR PLANO (R$)": st.column_config.NumberColumn("VALOR PLANO (R$)", format="%.2f"),
                "VALOR PROF (R$)": st.column_config.NumberColumn("VALOR PROF (R$)", format="%.2f")
            }
        )

    # ABA 2: PLANOS
    with tab2:
        st.subheader("Gestão de Convênios")
        st.info("Aqui você poderá adicionar novos planos de saúde ou remover operadoras desativadas.")

    # ABA 3: PROFISSIONAIS
    with tab3:
        st.subheader("Equipe Clínica")
        st.info("Aqui você associará o nome do profissional à sua respectiva especialidade e conselho.")

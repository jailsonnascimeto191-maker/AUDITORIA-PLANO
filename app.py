import streamlit as st
import pandas as pd
import datetime

# Configuração da Página
st.set_page_config(
    page_title="Espaço Saúde - Análise de Produção",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# ESTILIZAÇÃO CSS (VISUAL ESPAÇO SAÚDE)
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #f4f6f5; font-family: 'Segoe UI', sans-serif; }
    [data-testid="stSidebar"] { background-color: #0b2e1e !important; color: #ffffff !important; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    
    .metric-card {
        background-color: #ffffff; border: 1px solid #e1e6e3; border-radius: 8px;
        padding: 18px 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); height: 100%;
    }
    .metric-title { font-size: 11px; font-weight: 700; color: #556b60; text-transform: uppercase; margin-bottom: 6px; }
    .metric-value { font-size: 26px; font-weight: 800; color: #0d2818; }
    .metric-value-green { font-size: 26px; font-weight: 800; color: #1e7e48; }
    .metric-value-red { font-size: 26px; font-weight: 800; color: #b32d2d; }
    .metric-subtext { font-size: 12px; color: #708579; margin-top: 4px; }
    
    .stButton>button {
        background-color: #1b6b3e !important; color: white !important;
        border-radius: 6px !important; font-weight: 600 !important; border: none !important;
    }
    .stButton>button:hover { background-color: #14522f !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# BANCO DE DADOS SIMULADO (NUVEM)
# ==========================================
if 'db_auditoria' not in st.session_state:
    # Gerar dados de teste para visualização imediata do layout
    dados_teste = {
        'MES_COMPETENCIA': ['Outubro 2026', 'Outubro 2026', 'Outubro 2026', 'Setembro 2026', 'Outubro 2026'],
        'PROFISSIONAL': ['Dra. Ana (Fono)', 'Dr. Carlos (Psico)', 'Dra. Ana (Fono)', 'Dra. Ana (Fono)', 'Dra. Beatriz (TO)'],
        'DATA_ATENDIMENTO': ['10/10/2026', '12/10/2026', '15/10/2026', '05/09/2026', '20/10/2026'],
        'PACIENTE': ['João Silva', 'Maria Souza', 'Pedro Alves', 'Lucas Costa', 'Fernanda Lima'],
        'OPERADORA': ['UNIMED', 'CASSI', 'BRADESCO', 'UNIMED', 'FOX SAÚDE'],
        'VALOR_PRODUCAO': [100.0, 120.0, 100.0, 100.0, 150.0],
        'VALOR_PAGO': [100.0, 0.0, 80.0, 100.0, 150.0],
        'VALOR_GLOSA': [0.0, 120.0, 20.0, 0.0, 0.0],
        'MOTIVO_GLOSA': ['Sem Glosa', 'Falta de Autorização', 'Código Incorreto', 'Sem Glosa', 'Sem Glosa'],
        'REPASSE_FINAL': [100.0, 0.0, 80.0, 100.0, 150.0]
    }
    st.session_state.db_auditoria = pd.DataFrame(dados_teste)

df_db = st.session_state.db_auditoria

# ==========================================
# BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.markdown("## 🏥 Espaço Saúde")
    st.markdown("<p style='font-size: 12px; color: #a3b8ac; margin-top: -15px;'>Sistema de Análise</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    menu = st.radio(
        "Navegação",
        ["📊 Painel", "📁 Enviar arquivos", "⚠️ Glosas"],
        label_visibility="collapsed"
    )

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

    # Filtros
    st.markdown("### Filtros de Pesquisa")
    f_col1, f_col2, f_col3 = st.columns([1, 2, 1])
    
    meses_disponiveis = df_db['MES_COMPETENCIA'].unique().tolist()
    profissionais_disponiveis = ['Todos'] + df_db['PROFISSIONAL'].unique().tolist()
    
    with f_col1:
        mes_selecionado = st.selectbox("Competência (Mês/Ano)", meses_disponiveis)
    with f_col2:
        prof_selecionado = st.selectbox("Profissional", profissionais_disponiveis)
    with f_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("☁️ Salvar Competência na Nuvem", use_container_width=True):
            st.success(f"Competência de {mes_selecionado} gravada com sucesso!")

    # Lógica de Filtragem
    df_filtrado = df_db[df_db['MES_COMPETENCIA'] == mes_selecionado]
    if prof_selecionado != 'Todos':
        df_filtrado = df_filtrado[df_filtrado['PROFISSIONAL'] == prof_selecionado]

    # Cálculos
    tot_prod = df_filtrado['VALOR_PRODUCAO'].sum()
    tot_pago = df_filtrado['VALOR_PAGO'].sum()
    tot_glosa = df_filtrado['VALOR_GLOSA'].sum()
    tot_repasse = df_filtrado['REPASSE_FINAL'].sum()
    qtd_atendimentos = len(df_filtrado)

    # Cartões (KPIs)
    st.markdown("<br>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    
    with k1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Produção Informada</div>
            <div class="metric-value">R$ {tot_prod:,.2f}</div>
            <div class="metric-subtext">{qtd_atendimentos} atendimentos validados</div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Pago pelos Planos</div>
            <div class="metric-value">R$ {tot_pago:,.2f}</div>
            <div class="metric-subtext">Valor faturado com sucesso</div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Total Glosado</div>
            <div class="metric-value-red">R$ {tot_glosa:,.2f}</div>
            <div class="metric-subtext">Valores retidos / negados</div>
        </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Repasse Definitivo</div>
            <div class="metric-value-green">R$ {tot_repasse:,.2f}</div>
            <div class="metric-subtext">Valor final a transferir</div>
        </div>
        """, unsafe_allow_html=True)

    # Tabela e Geração de PDF
    st.markdown("<br>### Detalhamento para o Relatório", unsafe_allow_html=True)
    
    df_exibicao = df_filtrado[['DATA_ATENDIMENTO', 'PACIENTE', 'OPERADORA', 'VALOR_PAGO', 'MOTIVO_GLOSA']].copy()
    df_exibicao.columns = ['Data', 'Paciente', 'Plano', 'Valor Pago (R$)', 'Situação / Glosa']
    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
    
    col_pdf1, col_pdf2 = st.columns([1, 4])
    with col_pdf1:
        # Placeholder para o download do PDF
        relatorio_csv = df_exibicao.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Gerar Relatório (PDF/Excel)",
            data=relatorio_csv,
            file_name=f"Repasse_{prof_selecionado}_{mes_selecionado}.csv",
            mime="text/csv",
            type="primary"
        )

# ==========================================
# TELA 2: ENVIO DE ARQUIVOS
# ==========================================
elif menu == "📁 Enviar arquivos":
    st.title("Envio de Arquivos (Auditoria)")
    st.caption("Apenas cruze e processe planilhas nesta área.")
    
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        st.markdown("#### 1. Extratos das Operadoras")
        st.file_uploader("CASSI (.xlsx)", type=["xlsx"])
        st.file_uploader("Unimed (.xlsx)", type=["xlsx"])
        st.file_uploader("Bradesco (.xlsx)", type=["xlsx"])
    with col_e2:
        st.markdown("#### 2. Planilhas dos Profissionais")
        st.file_uploader("Arraste os espelhamentos (.xlsx)", type=["xlsx"], accept_multiple_files=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Processar Auditoria (Simulação)", type="primary"):
        st.success("Arquivos cruzados com sucesso! Os dados foram enviados para o Painel e Glosas.")

# ==========================================
# TELA 3: CONTROLE DE GLOSAS
# ==========================================
elif menu == "⚠️ Glosas":
    st.title("Controle Cirúrgico de Glosas")
    st.caption("Investigue retenções e organize recursos por competência.")

    # Filtros
    f_col1, f_col2 = st.columns(2)
    meses_disponiveis = df_db['MES_COMPETENCIA'].unique().tolist()
    profissionais_disponiveis = ['Todos'] + df_db['PROFISSIONAL'].unique().tolist()
    
    with f_col1:
        mes_selecionado = st.selectbox("Mês da Glosa", meses_disponiveis)
    with f_col2:
        prof_selecionado = st.selectbox("Profissional", profissionais_disponiveis)

    # Filtrar apenas o que tem glosa
    df_glosas = df_db[(df_db['MES_COMPETENCIA'] == mes_selecionado) & (df_db['VALOR_GLOSA'] > 0)]
    if prof_selecionado != 'Todos':
        df_glosas = df_glosas[df_glosas['PROFISSIONAL'] == prof_selecionado]

    # Resumo
    tot_glosa_tela = df_glosas['VALOR_GLOSA'].sum()
    st.markdown(f"""
    <div class="metric-card" style="width: 300px; margin-top: 15px; margin-bottom: 25px;">
        <div class="metric-title">Dinheiro Retido</div>
        <div class="metric-value-red">R$ {tot_glosa_tela:,.2f}</div>
        <div class="metric-subtext">{len(df_glosas)} atendimentos glosados</div>
    </div>
    """, unsafe_allow_html=True)

    # Tabela de Glosas
    st.markdown("### Detalhamento das Retenções")
    if not df_glosas.empty:
        df_exib_glosas = df_glosas[['DATA_ATENDIMENTO', 'PACIENTE', 'OPERADORA', 'VALOR_PRODUCAO', 'VALOR_GLOSA', 'MOTIVO_GLOSA']].copy()
        df_exib_glosas.columns = ['Data', 'Paciente', 'Operadora', 'Valor Original', 'Valor Retido', 'Motivo da Glosa']
        st.dataframe(df_exib_glosas, use_container_width=True, hide_index=True)
    else:
        st.success(f"Nenhuma glosa encontrada para {prof_selecionado} no mês de {mes_selecionado}!")

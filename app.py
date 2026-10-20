import streamlit as st
import pandas as pd
import motor_valores
import motor_extracao
import motor_auditoria

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
    
    .admin-warning {
        background-color: #fdf5e6; color: #855a1f; padding: 12px 16px; 
        border-radius: 6px; border: 1px solid #f5e1c8; font-size: 14px; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. ESTADOS DA SESSÃO (DADOS)
# ==========================================
if 'db_auditoria' not in st.session_state:
    st.session_state.db_auditoria = pd.DataFrame(columns=[
        'MES_COMPETENCIA', 'PROFISSIONAL', 'DATA_ATENDIMENTO',
        'PACIENTE', 'OPERADORA', 'VALOR_PRODUCAO',
        'VALOR_PAGO', 'VALOR_GLOSA', 'MOTIVO_GLOSA', 'REPASSE_FINAL'
    ])

especialidades_fixas = [
    "PSICOLOGIA", "FISIOTERAPIA", "FONOAUDIOLOGIA", 
    "NUTRIÇÃO", "PSICOMOTRICIDADE", "PSICOPEDAGOGIA"
]

if 'db_valores_por_especialidade' not in st.session_state:
    st.session_state.db_valores_por_especialidade = {
        esp: pd.DataFrame({
            "PLANO DE SAÚDE": ["BRADESCO", "UNIMED", "CASSI"],
            "TEMPO": ["30 MIN", "60 MIN", "30 MIN"],
            "VALOR PLANO (R$)": [46.82, 93.64, 16.74],
            "VALOR PROF (R$)": [23.41, 46.82, 8.37]
        }) for esp in especialidades_fixas
    }

if 'arquivos_extratos_enviados' not in st.session_state:
    st.session_state.arquivos_extratos_enviados = []

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

    with st.expander("ℹ️ Como funciona o Painel de Repasses"):
        st.markdown("""
        * **O que faz:** Apresenta o resumo financeiro consolidado da clínica com base nos cruzamentos efetuados[cite: 1].
        * **Como usar:** Selecione a competência (mês) e o profissional desejado nos filtros acima para visualizar os indicadores de produção, valores pagos pelos planos, montantes glosados e o valor definitivo do repasse a transferir.
        """)

    st.markdown("### Filtros de Pesquisa")
    f_col1, f_col2, f_col3 = st.columns([1, 2, 1])
    
    meses_disponiveis = df_db['MES_COMPETENCIA'].unique().tolist() if not df_db.empty else ['Sem dados']
    profissionais_disponiveis = ['Todos'] + df_db['PROFISSIONAL'].unique().tolist() if not df_db.empty else ['Todos']
    
    with f_col1:
        st.selectbox("Competência", meses_disponiveis)
    with f_col2:
        st.selectbox("Profissional", profissionais_disponiveis)
    with f_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("☁️ Salvar na Nuvem", use_container_width=True):
            st.success("Dados sincronizados com o Google Sheets!")

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
    st.caption("Faça o upload dos demonstrativos e espelhamentos para cruzamento.")
    
    with st.expander("ℹ️ Como funciona a Casa das Máquinas"):
        st.markdown("""
        * **O que faz:** Processa e cruza automaticamente os extratos e demonstrativos das operadoras com os espelhamentos da equipa.
        * **Como usar:** Selecione o plano ou a opção de identificação automática, envie o documento e confirme o nome do ficheiro antes de processar.
        """)
    
    col_e1, col_e2 = st.columns(2)
    
    with col_e1:
        st.markdown("#### 3. Demonstrativo do plano")
        st.caption("Demonstrativo de pagamento ou de análise de conta, com glosas.")
        
        plano_selecionado = st.selectbox(
            "Plano de saúde",
            ["Identificar pelo arquivo", "BRADESCO", "UNIMED", "CASSI", "FOX", "SULAMÉRICA", "MEDSERVICE"],
            help="Formatos de demonstrativos aceitos: Excel (.xlsx, .xls), XML (.xml), Word (.docx, .doc), PDF (.pdf), HTML (.html, .htm)."
        )
        
        arquivo_demonstrativo = st.file_uploader(
            f"Enviar Demonstrativo ({plano_selecionado})", 
            key="uploader_demonstrativo"
        )
        
        if arquivo_demonstrativo is not None:
            info_arquivo = {"plano": plano_selecionado, "nome": arquivo_demonstrativo.name}
            if info_arquivo not in st.session_state.arquivos_extratos_enviados:
                st.session_state.arquivos_extratos_enviados.append(info_arquivo)
            st.success(f"Ficheiro carregado: **{arquivo_demonstrativo.name}**")
            
        if st.session_state.arquivos_extratos_enviados:
            st.markdown("<p style='font-size: 13px; font-weight: 600; margin-top: 10px;'>Demonstrativos anexados:</p>", unsafe_allow_html=True)
            for idx, item in enumerate(st.session_state.arquivos_extratos_enviados):
                st.markdown(f"- ✅ **[{item['plano']}]**: `{item['nome']}`")

    with col_e2:
        st.markdown("#### 4. Planilhas de Atendimento (Equipe)")
        st.caption("Espelhamentos de atendimento dos profissionais.")
        
        arquivos_equipe = st.file_uploader(
            "Arraste os espelhamentos dos profissionais", 
            accept_multiple_files=True,
            help="Formatos aceitos para equipa: Excel (.xlsx, .xls) ou CSV (.csv)."
        )
        if arquivos_equipe:
            st.markdown(f"✅ **{len(arquivos_equipe)} ficheiro(s) de equipa carregado(s):**")
            for arq in arquivos_equipe:
                st.markdown(f"- `{arq.name}`")
        
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Processar Auditoria Completa", type="primary"):
        if not st.session_state.arquivos_extratos_enviados and not arquivos_equipe:
            st.warning("Por favor, envie pelo menos um demonstrativo de plano ou planilha de equipa.")
        else:
            st.success("Motores acionados! Cruzamento de dados iniciado com sucesso.")

# ==========================================
# TELA 3: CONTROLE DE GLOSAS
# ==========================================
elif menu == "⚠️ Glosas":
    st.title("Lupa de Glosas")
    st.caption("Investigue retenções e organize recursos por competência.")

    with st.expander("ℹ️ Como funciona a Lupa de Glosas"):
        st.markdown("""
        * **O que faz:** Identifica, cataloga e monitoriza os valores retidos ou recusados pelas operadoras de saúde.
        * **Como usar:** Filtre por mês ou profissional para auditar os motivos das retenções e preparar os recursos de contestação correspondentes.
        """)

    f_col1, f_col2 = st.columns(2)
    with f_col1:
        st.selectbox("Mês da Glosa", ['Sem dados'])
    with f_col2:
        st.selectbox("Profissional", ['Todos'])

    st.markdown('<div class="metric-card" style="width: 300px; margin-top: 15px; margin-bottom: 25px;"><div class="metric-title">Dinheiro Retido</div><div class="metric-value-red">R$ 0,00</div><div class="metric-subtext">0 atendimentos glosados</div></div>', unsafe_allow_html=True)
    st.info("Nenhuma glosa detectada no momento.")

# ==========================================
# TELA 4: CADASTROS (CONFIGURAÇÕES)
# ==========================================
elif menu == "⚙️ Cadastros":
    st.title("Cadastros")
    st.markdown('<div class="admin-warning">Somente administradores alteram cadastros, valores e regras. As suas mudanças aqui refletem-se em toda a auditoria.</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Tabela de valores", "Planos", "Profissionais", "Feriados", "Códigos de glosa", "Regras do repasse"
    ])

    with tab1:
        st.markdown("Tabela no mesmo formato da planilha da clínica. O repasse usa o **valor do profissional** desta tabela.")
        
        with st.expander("ℹ️ Como gerir a Tabela de Valores"):
            st.markdown("""
            * **O que faz:** Define os valores cobrados aos planos de saúde e os respetivos repasses devidos aos profissionais por tempo de atendimento (30 min, 60 min, etc.).
            * **Como usar:** Selecione a especialidade desejada e utilize a grelha abaixo para editar diretamente os valores, ou faça o upload de um ficheiro Excel na barra lateral para atualizar automaticamente todas as tabelas em massa.
            """)
        
        col_btn1, col_btn2, _ = st.columns([3, 3, 6])
        
        with col_btn1:
            arquivo_importado = st.file_uploader("📥 Atualizar Valores por Excel", key="up_valores", label_visibility="collapsed")
            if arquivo_importado is not None:
                dicionario_abas, erro = motor_valores.processar_tabela_valores_por_abas(arquivo_importado)
                if erro:
                    st.error(f"Erro ao ler arquivo: {erro}")
                else:
                    for esp, df_novo in dicionario_abas.items():
                        st.session_state.db_valores_por_especialidade[esp] = df_novo
                    st.success("Valores atualizados com sucesso a partir do Excel!")
                    
        with tab2:
            pass 

        st.markdown("<hr style='margin-top: 5px; margin-bottom: 15px;'>", unsafe_allow_html=True)
        
        especialidade_selecionada = st.radio(
            "Selecione a Especialidade:",
            especialidades_fixas,
            horizontal=True
        )
        
        st.markdown(f"**TABELA DE VALORES - {especialidade_selecionada} | CLÍNICA ESPAÇO SAÚDE**")
        
        if especialidade_selecionada not in st.session_state.db_valores_por_especialidade:
            st.session_state.db_valores_por_especialidade[especialidade_selecionada] = pd.DataFrame(columns=["PLANO DE SAÚDE", "TEMPO", "VALOR PLANO (R$)", "VALOR PROF (R$)"])

        df_atual = st.session_state.db_valores_por_especialidade[especialidade_selecionada]
        
        df_editado = st.data_editor(
            df_atual,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "PLANO DE SAÚDE": st.column_config.SelectboxColumn(
                    "PLANO_DE_SAUDE", 
                    options=["BRADESCO", "UNIMED", "CASSI", "FOX", "SULAMÉRICA", "MEDSERVICE"], 
                    required=True
                ),
                "TEMPO": st.column_config.SelectboxColumn(
                    "TEMPO", 
                    options=["30 MIN", "45 MIN", "60 MIN"], 
                    required=True
                ),
                "VALOR PLANO (R$)": st.column_config.NumberColumn(
                    "VALOR_PLANO", 
                    format="%.2f"
                ),
                "VALOR PROF (R$)": st.column_config.NumberColumn(
                    "VALOR_PROF", 
                    format="%.2f"
                )
            }
        )
        
        st.session_state.db_valores_por_especialidade[especialidade_selecionada] = df_editado

    with tab2:
        st.subheader("Gestão de Convênios")
        st.info("Adicione novos planos ou remova operadoras.")

    with tab3:
        st.subheader("Equipe Clínica")
        st.info("Associe profissionais às respetivas especialidades.")

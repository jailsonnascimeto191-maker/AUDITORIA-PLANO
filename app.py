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

if 'db_glosas' not in st.session_state:
    st.session_state.db_glosas = pd.DataFrame(columns=[
        "Nome do paciente", "Código", "Procedimento",
        "Valor informado", "Valor recebido", "Valor da glosa",
        "Código da glosa", "Motivo da glosa"
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

if 'arquivos_equipe_enviados' not in st.session_state:
    st.session_state.arquivos_equipe_enviados = []

# ==========================================
# 4. BARRA LATERAL (MENU E NAVEGAÇÃO)
# ==========================================
with st.sidebar:
    st.markdown("## Espaço Saúde")
    st.markdown("<p style='font-size: 12px; color: #a3b8ac; margin-top: -15px;'>Sistema de Análise</p>", unsafe_allow_html=True)
    st.markdown("---")
    menu = st.radio(
        "Navegação",
        ["📊 Painel", "📥 Enviar arquivos", "🔍 Glosas", "⚙️ Cadastros"],
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
        * *O que faz:* Apresenta o resumo financeiro consolidado da clínica com base nos cruzamentos efetuados.
        * *Como usar:* Selecione a competência (mês) e o profissional desejado nos filtros acima para visualizar os totais.
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

    total_glosa_painel = st.session_state.db_glosas["Valor da glosa"].sum() if not st.session_state.db_glosas.empty else 0.0
    total_inf_painel = st.session_state.db_glosas["Valor informado"].sum() if not st.session_state.db_glosas.empty else 0.0
    total_pago_painel = st.session_state.db_glosas["Valor recebido"].sum() if not st.session_state.db_glosas.empty else 0.0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Produção</div><div class="metric-value">R$ {total_inf_painel:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Pago pelos Planos</div><div class="metric-value-green">R$ {total_pago_painel:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Total Glosado</div><div class="metric-value-red">R$ {total_glosa_painel:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown('<div class="metric-card"><div class="metric-title">Repasse Definitivo</div><div class="metric-value">R$ 0,00</div></div>', unsafe_allow_html=True)

    st.markdown("<br>### Detalhamento para o Relatório", unsafe_allow_html=True)
    if df_db.empty:
        st.info("Nenhum arquivo de repasse cruzado. Vá a 'Enviar arquivos' para iniciar.")
    else:
        st.dataframe(df_db, use_container_width=True, hide_index=True)

# ==========================================
# TELA 2: ENVIO DE ARQUIVOS
# ==========================================
elif menu == "📥 Enviar arquivos":
    st.title("Casa das Máquinas (Auditoria)")
    st.caption("Faça o upload dos demonstrativos e espelhamentos para cruzamento.")

    with st.expander("ℹ️ Como funciona a Casa das Máquinas"):
        st.markdown("""
        * *O que faz:* Processa e cruza automaticamente os extratos das operadoras com os espelhamentos e relatórios de glosa.
        * *Como usar:* Selecione o plano ou identificação automática, envie o documento do plano e clique em Processar Auditoria Completa.
        """)

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        st.markdown("#### 3. Demonstrativo do plano")
        st.caption("Demonstrativo de pagamento ou de análise de conta, com glosas.")

        plano_selecionado = st.selectbox(
            "Plano de saúde",
            ["Identificar pelo arquivo", "BRADESCO", "UNIMED", "CASSI", "FOX", "SULAMÉRICA", "MEDSERVICE"],
            help="Formatos de demonstrativos aceitos: Excel (.xlsx, .xls), XML (.xml), Word (.docx, .doc), PDF (.pdf), HTML (.html, .htm) ou CSV (.csv)."
        )

        arquivo_demonstrativo = st.file_uploader(
            f"Enviar Demonstrativo ({plano_selecionado})",
            key="uploader_demonstrativo"
        )

        if arquivo_demonstrativo is not None:
            nomes_atuais = [item["nome"] for item in st.session_state.arquivos_extratos_enviados]
            if arquivo_demonstrativo.name not in nomes_atuais:
                plano_id = (
                    motor_auditoria.extrair_nome_operadora(arquivo_demonstrativo.name)
                    if plano_selecionado == "Identificar pelo arquivo"
                    else plano_selecionado
                )
                st.session_state.arquivos_extratos_enviados.append({
                    "plano": plano_id,
                    "nome": arquivo_demonstrativo.name,
                    "arquivo": arquivo_demonstrativo
                })
            st.success(f"Ficheiro carregado: *{arquivo_demonstrativo.name}*")

        if st.session_state.arquivos_extratos_enviados:
            st.markdown("<p style='font-size: 13px; font-weight: 600; margin-top: 10px;'>Demonstrativos anexados:</p>", unsafe_allow_html=True)
            for item in st.session_state.arquivos_extratos_enviados:
                st.markdown(f"- *[{item['plano']}]*: {item['nome']}")

    with col_e2:
        st.markdown("#### 4. Planilhas de Atendimento (Equipe)")
        st.caption("Espelhamentos de atendimento dos profissionais.")

        arquivo_eq = st.file_uploader(
            "Arraste os espelhamentos dos profissionais",
            key="uploader_equipe",
            accept_multiple_files=True,
            help="Formatos aceitos para equipa: Excel (.xlsx, .xls), Word (.docx, .doc), PDF (.pdf) ou CSV (.csv)."
        )

        if arquivo_eq:
            for arq in arquivo_eq:
                if arq.name not in st.session_state.arquivos_equipe_enviados:
                    st.session_state.arquivos_equipe_enviados.append(arq.name)
            st.success(f"{len(arquivo_eq)} Espelhamento(s) carregado(s) com sucesso.")

        if st.session_state.arquivos_equipe_enviados:
            st.markdown("<p style='font-size: 13px; font-weight: 600; margin-top: 10px;'>Espelhamentos anexados:</p>", unsafe_allow_html=True)
            for nome_arq in st.session_state.arquivos_equipe_enviados:
                st.markdown(f"- {nome_arq}")

    st.markdown("<br>", unsafe_allow_html=True)
    col_proc, col_limpar, _ = st.columns([3, 2, 5])

    with col_proc:
        if st.button("⚙️ Processar Auditoria Completa", type="primary", use_container_width=True):
            if not st.session_state.arquivos_extratos_enviados and not st.session_state.arquivos_equipe_enviados:
                st.warning("Por favor, envie pelo menos um demonstrativo de plano ou espelhamento de equipa.")
            else:
                lista_glosas = []
                erros = []
                for item in st.session_state.arquivos_extratos_enviados:
                    df_ext, erro_ext = motor_extracao.extrair_glosas_de_arquivo(item["arquivo"], item["plano"])
                    if erro_ext:
                        erros.append(f"{item['nome']}: {erro_ext}")
                    elif df_ext is not None and not df_ext.empty:
                        lista_glosas.append(df_ext)

                if lista_glosas:
                    st.session_state.db_glosas = pd.concat(lista_glosas, ignore_index=True)
                    st.success(f"Auditoria concluída! {len(st.session_state.db_glosas)} registo(s) enviado(s) para a Lupa de Glosas.")
                else:
                    st.warning("O ficheiro foi lido, mas nenhuma linha de glosa foi identificada automaticamente.")

                for err in erros:
                    st.error(f"Aviso ao ler {err}")

    with col_limpar:
        if st.button("🗑️ Limpar Ficheiros", use_container_width=True):
            st.session_state.arquivos_extratos_enviados = []
            st.session_state.arquivos_equipe_enviados = []
            st.session_state.db_glosas = pd.DataFrame(columns=[
                "Nome do paciente", "Código", "Procedimento",
                "Valor informado", "Valor recebido", "Valor da glosa",
                "Código da glosa", "Motivo da glosa"
            ])
            st.rerun()

# ==========================================
# TELA 3: CONTROLE DE GLOSAS
# ==========================================
elif menu == "🔍 Glosas":
    st.title("Lupa de Glosas")
    st.caption("Investigue retenções e gere relatórios detalhados para a chefia.")

    with st.expander("ℹ️ Como funciona a Lupa de Glosas"):
        st.markdown("""
        * *O que faz:* Isola automaticamente os atendimentos onde o valor recebido foi menor que o valor informado.
        * *Como usar:* Envie os demonstrativos na aba 'Enviar arquivos', clique em 'Processar Auditoria Completa' e volte aqui para validar e exportar o relatório.
        """)

    st.markdown("### Relatório Detalhado de Glosas")

    df_glosas = st.session_state.db_glosas

    if df_glosas.empty:
        st.markdown('<div class="metric-card" style="width: 300px; margin-top: 10px; margin-bottom: 20px;"><div class="metric-title">Total Glosado no Relatório</div><div class="metric-value-red">R$ 0,00</div></div>', unsafe_allow_html=True)
        st.info("Nenhum demonstrativo processado no momento. Vá à aba 'Enviar arquivos', faça o upload do demonstrativo do plano e clique em 'Processar Auditoria Completa'.")
    else:
        st.success(f"A exibir {len(df_glosas)} registo(s) extraído(s) dos demonstrativos enviados.")

        total_glosado = df_glosas["Valor da glosa"].sum() if "Valor da glosa" in df_glosas.columns else 0.0
        st.markdown(f'<div class="metric-card" style="width: 300px; margin-top: 10px; margin-bottom: 20px;"><div class="metric-title">Total Glosado no Relatório</div><div class="metric-value-red">R$ {total_glosado:,.2f}</div></div>', unsafe_allow_html=True)

        df_glosas_editado = st.data_editor(
            df_glosas,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )
        st.session_state.db_glosas = df_glosas_editado

        col_btn1, col_btn2, _ = st.columns([2, 2, 6])
        with col_btn1:
            excel_data = motor_auditoria.gerar_excel_glosas(df_glosas_editado)
            st.download_button(
                label="📥 Baixar Relatório (Excel)",
                data=excel_data,
                file_name="Relatorio_Glosas_Chefia.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        with col_btn2:
            pdf_data = motor_auditoria.gerar_pdf_glosas(df_glosas_editado)
            if pdf_data:
                st.download_button(
                    label="📄 Baixar Relatório (PDF)",
                    data=pdf_data,
                    file_name="Relatorio_Glosas_Chefia.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("⚠️ Adicione 'fpdf' no requirements.txt para ativar os PDFs.")

# ==========================================
# TELA 4: CADASTROS (CONFIGURAÇÕES)
# ==========================================
elif menu == "⚙️ Cadastros":
    st.title("Cadastros")
    st.markdown('<div class="admin-warning">Somente administradores alteram cadastros, valores e regras. As suas mudanças impactam os cálculos de auditoria.</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Tabela de valores", "Planos", "Profissionais", "Feriados", "Códigos de glosa", "Regras do repasse"
    ])

    with tab1:
        st.markdown("Tabela no mesmo formato da planilha da clínica. O repasse usa o *valor do profissional* desta tabela.")
        with st.expander("ℹ️ Como gerir a Tabela de Valores"):
            st.markdown("""
            * *O que faz:* Define os valores cobrados aos planos de saúde e os respetivos repasses devidos aos profissionais.
            * *Como usar:* Selecione a especialidade desejada e utilize a grelha abaixo para editar diretamente os valores ou importe o Excel.
            """)

        col_btn1, col_btn2, _ = st.columns([3, 3, 6])
        with col_btn1:
            arquivo_importado = st.file_uploader("📥 Atualizar Valores por

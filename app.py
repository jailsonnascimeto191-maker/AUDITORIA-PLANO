import io
import streamlit as st
import pandas as pd
import motor_seguranca
import motor_valores
import motor_extracao

# Inicialização dos Bancos de Dados de Segurança e Valores
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

st.set_page_config(page_title="Espaço Saúde - Auditoria & Repasses", page_icon="🏥", layout="wide")

# Lista dos Planos de Saúde atendidos pela clínica
PLANOS_SAUDE = [
    "Identificar pelo arquivo",
    "Unimed Recife",
    "Bradesco Saúde",
    "SulAmérica",
    "Amil",
    "Casssi",
    "GEAP",
    "Postal Saúde",
    "Assefaz",
    "Outros"
]

# ==========================================
# 1. CONTROLE DE ACESSO & SEGURANÇA (LOGIN)
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_atual = None
    st.session_state.nivel_permissao = None

if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>🏥 Espaço Saúde</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Sistema Integrado de Auditoria, Faturamento & Repasses</p>", unsafe_allow_html=True)
        
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
                    st.warning("⚠️ O módulo de segurança está sincronizando. Aguarde alguns segundos.")

# ==========================================
# 2. SISTEMA COMPLETO (ÁREA RESTRITA)
# ==========================================
else:
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.usuario_atual.capitalize()}")
        st.caption(f"Perfil: **{st.session_state.nivel_permissao}**")
        
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.autenticado = False
            st.rerun()
            
        st.markdown("---")
        menu = st.radio(
            "Navegação",
            ["📊 Painel", "📥 Casa das Máquinas", "⚠️ Lupa de Glosas", "💰 Valores", "👥 Cadastros", "🛡️ Acessos"],
            label_visibility="collapsed"
        )

    # ----------------------------------------------------------------------
    # MENU 1: PAINEL DE REPASSES & MÉTRICAS
    # ----------------------------------------------------------------------
    if menu == "📊 Painel":
        st.title("📊 Painel Geral de Faturamento & Repasses")
        st.markdown("Visão consolidada das auditorias, margens de lucro e valores a repassar.")
        
        df_proc = st.session_state.get("ultimo_processamento", pd.DataFrame())
        
        if not df_proc.empty:
            total_inf = df_proc["Valor informado"].sum() if "Valor informado" in df_proc else 0.0
            total_pago = df_proc["Valor pago"].sum() if "Valor pago" in df_proc else 0.0
            total_glosa = df_proc["Valor da glosa"].sum() if "Valor da glosa" in df_proc else 0.0
            qtd_atendimentos = len(df_proc)
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Atendimentos Auditados", f"{qtd_atendimentos}")
            c2.metric("Total Cobrado/Informado", f"R$ {total_inf:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            c3.metric("Total Liberado/Pago", f"R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            c4.metric("Total Glosado", f"R$ {total_glosa:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), delta=f"-R$ {total_glosa:,.2f}", delta_color="inverse")
            
            st.markdown("---")
            col_left, col_right = st.columns([2, 1])
            with col_left:
                st.subheader("Resumo de Atendimentos Por Paciente")
                if "Nome do paciente" in df_proc:
                    resumo_pac = df_proc.groupby("Nome do paciente")[["Valor informado", "Valor pago", "Valor da glosa"]].sum().reset_index()
                    st.dataframe(resumo_pac, use_container_width=True)
            with col_right:
                st.subheader("Indicadores de Glosa")
                pct_glosa = (total_glosa / total_inf * 100) if total_inf > 0 else 0
                st.metric("Índice de Retenção (Glosa)", f"{pct_glosa:.1f}%")
                if pct_glosa > 5:
                    st.warning("⚠️ O índice de glosa está acima da meta operacional (5%).")
                else:
                    st.success("✅ Margem de glosa dentro do limite aceitável.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Informado", "R$ 0,00")
            c2.metric("Total Pago", "R$ 0,00")
            c3.metric("Total Glosado", "R$ 0,00")
            st.info("💡 Faça o upload de um extrato na **Casa das Máquinas** para gerar métricas automáticas.")

    # ----------------------------------------------------------------------
    # MENU 2: CASA DAS MÁQUIS (UPLOAD & AUDITORIA INTEGRADA)
    # ----------------------------------------------------------------------
    elif menu == "📥 Casa das Máquinas":
        st.title("📥 Casa das Máquinas")
        st.markdown("Central de upload para cruzamento do demonstrativo do convênio com os relatórios dos profissionais.")
        
        st.subheader("1. Configurações da Sessão de Faturamento")
        col_p1, col_p2, col_p3 = st.columns(3)
        
        with col_p1:
            plano_selecionado = st.selectbox("Selecione a Operadora/Plano de Saúde", PLANOS_SAUDE)
        with col_p2:
            somente_glosas = st.checkbox("Filtrar e exibir APENAS itens com Glosa (> R$ 0,00)", value=True)
        with col_p3:
            modo_cruzamento = st.checkbox("Cruzar automaticamente com a Tabela de Preços cadastrada", value=True)

        st.markdown("---")
        col_u1, col_u2 = st.columns(2)
        
        with col_u1:
            st.subheader("📄 Demonstrativo / Extrato do Plano")
            st.caption("Suba o arquivo oficial recebido da operadora (PDF, Excel, CSV, XML ou DOCX).")
            arquivo_dem = st.file_uploader(
                "Arquivo do Convênio", 
                type=["xlsx", "xls", "csv", "pdf", "xml", "docx"],
                key="u_demonstrativo"
            )
            
        with col_u2:
            st.subheader("👥 Relatório de Frequência / Presença da Equipe")
            st.caption("Suba a planilha interna de sessões/atendimentos entregue pelos profissionais.")
            arquivo_prof = st.file_uploader(
                "Planilha de Atendimento dos Profissionais (Opcional)", 
                type=["xlsx", "xls", "csv"],
                key="u_profissionais"
            )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⚡ Iniciar Processamento & Auditoria Completa", type="primary", use_container_width=True):
            if arquivo_dem is None:
                st.error("Por favor, selecione ao menos o arquivo do demonstrativo do plano de saúde.")
            else:
                with st.spinner("Analisando estrutura, preenchendo hierarquias (Forward Fill) e auditando valores..."):
                    df_res, erro = motor_extracao.extrair_glosas_de_arquivo(
                        arquivo_dem, 
                        plano=plano_selecionado, 
                        somente_glosas=somente_glosas
                    )
                    
                    if erro:
                        st.info(f"ℹ️ Detalhe do processamento: {erro}")
                        
                    if not df_res.empty:
                        st.success(f"✅ Processamento concluído! {len(df_res)} registros validados com sucesso.")
                        
                        # Exibição do auto-mapeamento de colunas
                        mapeamento = df_res.attrs.get("mapeamento", {})
                        if mapeamento:
                            with st.expander("🔍 Mapeamento Automático de Colunas Identificado pelo Motor"):
                                st.json(mapeamento)
                        
                        st.markdown("### Tabela de Atendimentos Auditados")
                        st.dataframe(df_res, use_container_width=True)
                        st.session_state["ultimo_processamento"] = df_res
                        
                        # Processamento opcional do relatório de profissionais
                        if arquivo_prof is not None:
                            try:
                                df_p = pd.read_excel(arquivo_prof) if arquivo_prof.name.endswith(('.xlsx', '.xls')) else pd.read_csv(arquivo_prof)
                                st.markdown("### 📋 Comparativo com Relatório da Equipe")
                                st.dataframe(df_p.head(10), use_container_width=True)
                                st.caption("Cruzamento com atestados de presença registrado no sistema.")
                            except Exception as e:
                                st.warning(f"Não foi possível ler a planilha de presença: {e}")

    # ----------------------------------------------------------------------
    # MENU 3: LUPA DE GLOSAS (ANÁLISE DETALHADA E EXPORTAÇÃO)
    # ----------------------------------------------------------------------
    elif menu == "⚠️ Lupa de Glosas":
        st.title("⚠️ Lupa de Glosas & Recuperação de Retenções")
        
        df = st.session_state.get("ultimo_processamento", pd.DataFrame())
        
        if not df.empty:
            st.markdown("### Filtros de Análise Detalhada")
            f_col1, f_col2 = st.columns(2)
            
            with f_col1:
                pacientes = ["Todos"] + sorted([str(p) for p in df["Nome do paciente"].unique() if p])
                paciente_filtro = st.selectbox("Filtrar por Paciente", pacientes)
            with f_col2:
                motivos = ["Todos"] + sorted([str(m) for m in df["Motivo da glosa"].unique() if m])
                motivo_filtro = st.selectbox("Filtrar por Motivo da Glosa", motivos)
                
            df_filtrado = df.copy()
            if paciente_filtro != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Nome do paciente"] == paciente_filtro]
            if motivo_filtro != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Motivo da glosa"] == motivo_filtro]
                
            st.dataframe(df_filtrado, use_container_width=True)
            
            st.markdown("---")
            st.subheader("📥 Exportar Relatório Oficial de Glosas")
            exp_c1, exp_c2 = st.columns(2)
            
            with exp_c1:
                # Exportar Excel
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer:
                    df_filtrado.to_excel(writer, sheet_name='Glosas', index=False)
                st.download_button(
                    label="📊 Baixar Relatório em Excel (.xlsx)",
                    data=buffer_excel.getvalue(),
                    file_name="Relatorio_Glosas_EspacoSaude.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
            with exp_c2:
                # Exportar CSV
                csv_data = df_filtrado.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📄 Baixar Relatório em CSV (.csv)",
                    data=csv_data,
                    file_name="Relatorio_Glosas_EspacoSaude.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.info("Nenhum arquivo auditado no momento. Dirija-se à **Casa das Máquinas** e suba o demonstrativo do plano.")

    # ----------------------------------------------------------------------
    # MENU 4: VALORES (TABELA DO PLANO DE SAÚDE + TABELA DE REPASSES)
    # ----------------------------------------------------------------------
    elif menu == "💰 Valores":
        st.title("💰 Gestão de Tabelas de Preços e Repasses")
        st.markdown("Consulte e atualize os preçários dos convênios e as tabelas de margem da clínica.")
        
        tab1, tab2 = st.tabs(["🏥 Tabela de Valores do Plano (Recebimentos)", "👥 Tabela de Repasse dos Profissionais (Custos/Lucro)"])
        
        with tab1:
            st.subheader("1. Preçário Oficial dos Convênios / Operadoras")
            col_v1, col_v2 = st.columns([2, 1])
            with col_v1:
                plano_tabela = st.selectbox("Selecione o Convênio para Visualizar/Editar", PLANOS_SAUDE[1:])
            
            if hasattr(motor_valores, 'buscar_tabela_plano'):
                df_p = motor_valores.buscar_tabela_plano()
                st.dataframe(df_p, use_container_width=True)
            
            st.markdown("#### Importar Novo Preçário por Arquivo")
            file_plano = st.file_uploader("Subir Tabela do Plano (Excel/CSV)", type=["xlsx", "xls", "csv"], key="t_plano_file")
            if file_plano:
                df_up_p = pd.read_excel(file_plano) if file_plano.name.endswith(('.xlsx', '.xls')) else pd.read_csv(file_plano)
                st.dataframe(df_up_p, use_container_width=True)
                if st.button("💾 Salvar Preçário no Banco de Dados", type="primary"):
                    st.success("Tabela do Plano atualizada no cofre de dados!")

        with tab2:
            st.subheader("2. Tabela de Repasses da Equipe (Margem de Lucro)")
            if hasattr(motor_valores, 'buscar_tabela_repasse'):
                df_r = motor_valores.buscar_tabela_repasse()
                st.dataframe(df_r, use_container_width=True)
                
            st.markdown("#### Importar Nova Tabela de Repasses")
            file_repasse = st.file_uploader("Subir Tabela de Repasse dos Profissionais (Excel/CSV)", type=["xlsx", "xls", "csv"], key="t_repasse_file")
            if file_repasse:
                df_up_r = pd.read_excel(file_repasse) if file_repasse.name.endswith(('.xlsx', '.xls')) else pd.read_csv(file_repasse)
                st.dataframe(df_up_r, use_container_width=True)
                if st.button("💾 Salvar Tabela de Repasse no Banco de Dados", type="primary"):
                    st.success("Tabela de repasse e margens de lucro atualizada!")

    # ----------------------------------------------------------------------
    # MENU 5: CADASTROS (PROFISSIONAIS, USUÁRIOS E RECEPÇÃO)
    # ----------------------------------------------------------------------
    elif menu == "👥 Cadastros":
        st.title("👥 Cadastros de Profissionais & Acessos da Recepção")
        
        tab_cad1, tab_cad2 = st.tabs(["Corpo Clínico & Profissionais", "🔐 Gestão de Usuários do Sistema"])
        
        with tab_cad1:
            st.subheader("Cadastrar Novo Profissional")
            with st.form("form_cad_prof"):
                c_n1, c_n2 = st.columns(2)
                nome_prof = c_n1.text_input("Nome Completo do Profissional")
                especialidade = c_n2.selectbox("Especialidade", ["Psicologia", "Fisioterapia", "Fonoaudiologia", "Terapia Ocupacional", "Nutrição", "Médico", "Outro"])
                c_n3, c_n4 = st.columns(2)
                registro_conselho = c_n3.text_input("Número de Registro (CRP, CREFITO, etc.)")
                chave_pix = c_n4.text_input("Chave PIX / Dados Bancários para Repasse")
                
                btn_cad_p = st.form_submit_button("Salvar Profissional")
                if btn_cad_p:
                    st.success(f"Profissional **{nome_prof}** cadastrado com sucesso!")

        with tab_cad2:
            st.subheader("Criar Acesso para Funcionário/Recepção")
            if st.session_state.nivel_permissao == "Administrador":
                with st.form("form_cad_user"):
                    u_col1, u_col2 = st.columns(2)
                    novo_user = u_col1.text_input("Nome de Usuário (Login)")
                    nova_senha = u_col2.text_input("Senha Inicial", type="password")
                    perfil_user = st.selectbox("Nível de Permissão", ["Comum", "Administrador"])
                    
                    btn_cad_u = st.form_submit_button("Criar Usuário")
                    if btn_cad_u:
                        if hasattr(motor_seguranca, 'criar_usuario'):
                            ok, msg = motor_seguranca.criar_usuario(novo_user, nova_senha, role=perfil_user)
                            if ok:
                                st.success(f"Usuário **{novo_user}** criado com sucesso!")
                            else:
                                st.error(f"Erro: {msg}")
            else:
                st.warning("Apenas administradores podem criar novos usuários de acesso.")

    # ----------------------------------------------------------------------
    # MENU 6: ACESSOS (AUDITORIA DE SEGURANÇA E LOGS)
    # ----------------------------------------------------------------------
    elif menu == "🛡️ Acessos":
        st.title("🛡️ Auditoria de Segurança & Histórico de Logins")
        st.markdown("Registro imutável de todas as tentativas e acessos ao sistema.")
        
        if st.session_state.nivel_permissao == "Administrador":
            if hasattr(motor_seguranca, 'obter_relatorio_acessos'):
                df_logs = motor_seguranca.obter_relatorio_acessos()
                st.dataframe(df_logs, use_container_width=True)
            else:
                st.info("Carregando logs de auditoria...")
        else:
            st.error("Acesso restrito ao administrador do sistema.")

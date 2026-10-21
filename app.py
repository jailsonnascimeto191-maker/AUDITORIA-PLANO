import io
import inspect
import sqlite3
from contextlib import closing

import pandas as pd
import streamlit as st

# set_page_config PRECISA ser o primeiro comando do Streamlit no script.
st.set_page_config(
    page_title="Espaço Saúde | Auditoria & Repasses",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

import motor_seguranca  # noqa: E402
import motor_extracao  # noqa: E402

# ─────────────────────────────────────────────────────────────
# Compatibilidade: use_container_width foi substituído por width="stretch"
# nas versões novas do Streamlit. Detectamos qual a versão suporta.
# ─────────────────────────────────────────────────────────────
def _largura(fn):
    try:
        if "width" in inspect.signature(fn).parameters:
            return {"width": "stretch"}
    except (TypeError, ValueError):
        pass
    return {"use_container_width": True}


FULL_DF = _largura(st.dataframe)
FULL_BTN = _largura(st.button)
FULL_DL = _largura(st.download_button)
FULL_FORM_BTN = _largura(st.form_submit_button)

# ─────────────────────────────────────────────────────────────
# Banco de dados local
# ─────────────────────────────────────────────────────────────
DB_VALORES = "valores_clinica.db"
COLUNAS_VALORES = ["especialidade", "plano", "tempo_atendimento", "valor_plano", "valor_profissional"]


def conectar():
    return closing(sqlite3.connect(DB_VALORES))


def init_db_valores():
    with conectar() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_especialidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_valores_completa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especialidade TEXT,
                plano TEXT,
                tempo_atendimento TEXT,
                valor_plano REAL,
                valor_profissional REAL)"""
        )
        conn.commit()


def buscar_especialidades():
    try:
        with conectar() as conn:
            rows = conn.execute(
                """SELECT especialidade AS nome FROM tabela_valores_completa
                   UNION SELECT nome FROM tabela_especialidades ORDER BY nome"""
            ).fetchall()
        lista = [r[0] for r in rows if r[0]]
    except sqlite3.Error:
        lista = []
    return lista or ["PSICOLOGIA", "PSICOPEDAGOGIA", "PSICOMOTRICIDADE", "FONOAUDIOLOGIA", "NUTRIÇÃO", "FISIOTERAPIA"]


def carregar_valores():
    with conectar() as conn:
        return pd.read_sql_query(
            "SELECT especialidade, plano, tempo_atendimento, valor_plano, valor_profissional "
            "FROM tabela_valores_completa",
            conn,
        )


def _para_float(v):
    """Converte número ou texto ('R$ 1.234,56', '80,5') em float. Retorna None se inválido."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).upper().replace("R$", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _achar_cabecalho(df_raw):
    """Acha a linha de cabeçalho exigindo pelo menos 2 palavras-chave (evita confundir títulos)."""
    chaves = ("PLANO", "TEMPO", "VALOR", "PROFISSIONAL")
    for idx, row in df_raw.iterrows():
        texto = " ".join(str(v).upper() for v in row.values if pd.notnull(v))
        if sum(k in texto for k in chaves) >= 2:
            return idx
    return None


def processar_e_salvar_excel_multi_abas(arquivo_upload):
    try:
        arquivo_upload.seek(0)
        xls = pd.ExcelFile(io.BytesIO(arquivo_upload.read()))
    except Exception as e:
        return False, f"Não foi possível abrir o Excel: {e}. Verifique se 'openpyxl' (xlsx) ou 'xlrd' (xls) está instalado."

    dfs, abas_ok, abas_erro = [], [], []
    for aba in xls.sheet_names:
        try:
            df_raw = pd.read_excel(xls, sheet_name=aba, header=None, dtype=object)
            if df_raw.empty:
                continue
            if df_raw.shape[1] < 4:
                abas_erro.append(f"{aba} (menos de 4 colunas)")
                continue

            cab = _achar_cabecalho(df_raw)
            df_aba = (df_raw.iloc[cab + 1:] if cab is not None else df_raw).iloc[:, :4].copy()
            df_aba.columns = ["plano", "tempo_atendimento", "valor_plano", "valor_profissional"]

            df_aba["plano"] = (
                df_aba["plano"].astype(object)
                .where(df_aba["plano"].notna(), None)
                .map(lambda x: str(x).strip() if x is not None else None)
                .replace(["", "nan", "None"], None)
            )
            df_aba["plano"] = df_aba["plano"].ffill().fillna("Sem plano")

            df_aba["valor_plano"] = df_aba["valor_plano"].map(_para_float)
            df_aba["valor_profissional"] = df_aba["valor_profissional"].map(_para_float)
            df_aba = df_aba.dropna(subset=["valor_plano"])
            df_aba["valor_profissional"] = df_aba["valor_profissional"].fillna(0.0)
            df_aba = df_aba[~df_aba["plano"].str.contains("PLANO DE SAÚDE", case=False, na=False)]
            df_aba["tempo_atendimento"] = df_aba["tempo_atendimento"].fillna("").astype(str).str.strip()
            df_aba["especialidade"] = aba.strip().upper()

            if df_aba.empty:
                abas_erro.append(f"{aba} (nenhuma linha com valor)")
                continue
            dfs.append(df_aba[COLUNAS_VALORES])
            abas_ok.append(aba.strip().upper())
        except Exception as ex:
            abas_erro.append(f"{aba} ({ex})")

    if not dfs:
        return False, "Nenhuma regra foi extraída. Abas com problema: " + ("; ".join(abas_erro) or "nenhuma aba legível")

    df_final = pd.concat(dfs, ignore_index=True)
    try:
        with conectar() as conn:
            # Mantém o esquema da tabela (não usa if_exists="replace", que apaga a coluna id)
            conn.execute("DELETE FROM tabela_valores_completa")
            df_final.to_sql("tabela_valores_completa", conn, if_exists="append", index=False)
            conn.executemany(
                "INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", [(n,) for n in abas_ok]
            )
            conn.commit()
    except Exception as e:
        return False, f"Erro ao gravar no banco: {e}"

    msg = f"Importação concluída: {len(df_final)} registros em {len(abas_ok)} abas ({', '.join(sorted(abas_ok))})."
    if abas_erro:
        msg += f" Abas ignoradas: {'; '.join(abas_erro)}."
    return True, msg


init_db_valores()

try:
    if hasattr(motor_seguranca, "init_db_seguranca"):
        motor_seguranca.init_db_seguranca()
except Exception as e:  # não esconde mais o erro
    st.warning(f"Módulo de segurança não inicializou: {e}")

# ─────────────────────────────────────────────────────────────
# Tema / CSS
# ─────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');

:root {
  --navy: #0F2A43;
  --navy-2: #173a5a;
  --teal: #0E7C86;
  --teal-dark: #0A5F67;
  --bg: #F3F5F8;
  --card: #FFFFFF;
  --line: #E1E6EC;
  --ink: #1B2733;
  --muted: #637083;
}

html, body, .stApp, [class*="css"] { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.stApp { background: var(--bg); color: var(--ink); }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }

/* Sidebar */
[data-testid="stSidebar"] { background: var(--navy); border-right: 0; }
[data-testid="stSidebar"] * { color: #DCE6F0; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: 10px 14px; border-radius: 8px; width: 100%; cursor: pointer;
  border-left: 3px solid transparent; transition: background .15s;
}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.07); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background: rgba(255,255,255,.12); border-left-color: #4FD1C5; font-weight: 600;
}
[data-testid="stSidebar"] .stButton button {
  background: transparent; border: 1px solid rgba(255,255,255,.25); color: #fff;
}
[data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,.1); border-color: #fff; }

.marca { display:flex; align-items:center; gap:10px; padding: 4px 4px 14px; }
.marca .logo { width:36px; height:36px; border-radius:9px; background:var(--teal);
  display:flex; align-items:center; justify-content:center; font-size:19px; }
.marca .nome { font-weight:600; font-size:16px; line-height:1.1; color:#fff; }
.marca .sub { font-size:11.5px; color:#9FB3C8; }
.usuario { background: rgba(255,255,255,.07); border-radius: 10px; padding: 10px 12px; margin-bottom: 10px; }
.usuario b { color:#fff; }
.usuario span { font-size:12px; color:#9FB3C8; }

/* Cabeçalho de página */
.pagina-titulo { font-size: 26px; font-weight: 600; color: var(--ink); margin: 0; }
.pagina-sub { color: var(--muted); font-size: 14px; margin: 4px 0 22px; }

/* Cartões e métricas */
[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px 18px; border-top: 3px solid var(--teal);
}
[data-testid="stMetricLabel"] { color: var(--muted); }
[data-testid="stMetricValue"] { font-weight: 600; color: var(--ink); }
[data-testid="stForm"], [data-testid="stFileUploader"] section {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
}
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: var(--card); }

/* Botões */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
  border-radius: 8px; font-weight: 500; padding: .55rem 1rem;
}
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button {
  background: var(--teal); border: 1px solid var(--teal); color: #fff;
}
.stButton button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover {
  background: var(--teal-dark); border-color: var(--teal-dark); color: #fff;
}

/* Login */
.login-marca { text-align:center; margin: 6vh 0 18px; }
.login-marca .logo { width:56px; height:56px; border-radius:14px; background:var(--navy);
  display:inline-flex; align-items:center; justify-content:center; font-size:28px; margin-bottom:12px; }
.login-marca h1 { font-size:24px; font-weight:600; margin:0; color:var(--ink); }
.login-marca p { color:var(--muted); font-size:14px; margin:6px 0 0; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def cabecalho(titulo, subtitulo=""):
    st.markdown(
        f"<h1 class='pagina-titulo'>{titulo}</h1><p class='pagina-sub'>{subtitulo}</p>",
        unsafe_allow_html=True,
    )


def tabela(df, **kw):
    st.dataframe(df, hide_index=True, **FULL_DF, **kw)


def baixar(df, nome, rotulo="Baixar CSV"):
    st.download_button(
        rotulo, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        file_name=f"{nome}.csv", mime="text/csv", **FULL_DL,
    )


def kpis_do_processamento(df):
    colunas = st.columns(4)
    colunas[0].metric("Registros auditados", f"{len(df):,}".replace(",", "."))
    achados = 1
    for col in df.columns:
        if achados >= 4:
            break
        if "valor" in str(col).lower() or "glosa" in str(col).lower():
            num = pd.to_numeric(df[col], errors="coerce")
            if num.notna().any():
                total = f"R$ {num.sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                colunas[achados].metric(str(col).replace("_", " ").capitalize(), total)
                achados += 1


# ─────────────────────────────────────────────────────────────
# Sessão
# ─────────────────────────────────────────────────────────────
for chave, padrao in (("autenticado", False), ("usuario_atual", None), ("nivel_permissao", None)):
    st.session_state.setdefault(chave, padrao)

PLANOS_SAUDE = [
    "Identificar pelo arquivo", "Unimed Recife", "Bradesco Saúde", "SulAmérica",
    "Amil", "Cassi", "GEAP", "Postal Saúde", "Assefaz", "Outros",
]

# ─────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────
if not st.session_state.autenticado:
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        st.markdown(
            """<div class='login-marca'><div class='logo'>🏥</div>
            <h1>Espaço Saúde</h1>
            <p>Auditoria, faturamento e repasses</p></div>""",
            unsafe_allow_html=True,
        )
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", **FULL_FORM_BTN)

        if entrar:
            if not usuario or not senha:
                st.error("Informe usuário e senha.")
            elif not hasattr(motor_seguranca, "autenticar_usuario"):
                st.warning("O módulo de segurança não tem a função 'autenticar_usuario'.")
            else:
                try:
                    sucesso, role, msg = motor_seguranca.autenticar_usuario(usuario, senha)
                except Exception as e:
                    sucesso, role, msg = False, None, f"Falha no módulo de segurança: {e}"
                if sucesso:
                    st.session_state.update(autenticado=True, usuario_atual=usuario, nivel_permissao=role)
                    st.rerun()
                else:
                    st.error(msg)
    st.stop()

# ─────────────────────────────────────────────────────────────
# Navegação
# ─────────────────────────────────────────────────────────────
MENUS_BASE = ["Painel", "Casa das Máquinas", "Lupa de Glosas"]
MENUS_ADMIN = ["Valores", "Cadastros", "Acessos"]
eh_admin = st.session_state.nivel_permissao == "Administrador"
menus = MENUS_BASE + (MENUS_ADMIN if eh_admin else [])

with st.sidebar:
    st.markdown(
        """<div class='marca'><div class='logo'>🏥</div>
        <div><div class='nome'>Espaço Saúde</div><div class='sub'>Auditoria & Repasses</div></div></div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='usuario'><b>{str(st.session_state.usuario_atual).capitalize()}</b><br>"
        f"<span>Perfil: {st.session_state.nivel_permissao}</span></div>",
        unsafe_allow_html=True,
    )
    menu = st.radio("Navegação", menus, label_visibility="collapsed")
    st.markdown("---")
    if st.button("Sair do sistema", **FULL_BTN):
        for k in ("autenticado", "usuario_atual", "nivel_permissao", "ultimo_processamento"):
            st.session_state.pop(k, None)
        st.rerun()

if menu in MENUS_ADMIN and not eh_admin:
    st.error("Você não tem permissão para acessar esta área.")
    st.stop()

df_proc = st.session_state.get("ultimo_processamento", pd.DataFrame())

# ─────────────────────────────────────────────────────────────
# Páginas
# ─────────────────────────────────────────────────────────────
if menu == "Painel":
    cabecalho("Painel geral", "Resumo do último demonstrativo auditado.")
    if df_proc.empty:
        st.info("Nenhum demonstrativo processado ainda. Envie um arquivo em **Casa das Máquinas**.")
    else:
        kpis_do_processamento(df_proc)
        st.markdown("&nbsp;", unsafe_allow_html=True)
        tabela(df_proc)

elif menu == "Casa das Máquinas":
    cabecalho("Casa das Máquinas", "Envie o demonstrativo do convênio para extrair e auditar os itens.")
    c1, c2 = st.columns([2, 1])
    plano = c1.selectbox("Operadora / plano de saúde", PLANOS_SAUDE)
    c2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    somente_glosas = c2.checkbox("Exibir apenas itens com glosa", value=True)

    arquivo = st.file_uploader(
        "Demonstrativo do convênio", type=["xlsx", "xls", "csv", "pdf", "xml", "docx"]
    )
    if st.button("Processar e auditar", type="primary", **FULL_BTN):
        if arquivo is None:
            st.warning("Selecione um arquivo antes de processar.")
        else:
            with st.spinner("Lendo e auditando o demonstrativo..."):
                try:
                    resultado = motor_extracao.extrair_glosas_de_arquivo(
                        arquivo, plano=plano, somente_glosas=somente_glosas
                    )
                    df_res, erro = resultado if isinstance(resultado, tuple) else (resultado, None)
                except Exception as e:
                    df_res, erro = pd.DataFrame(), f"{type(e).__name__}: {e}"

            if erro:
                st.error(f"Problema na extração: {erro}")
            if df_res is not None and not df_res.empty:
                st.session_state["ultimo_processamento"] = df_res
                st.success(f"Processamento concluído: {len(df_res)} registros validados.")
                kpis_do_processamento(df_res)
                st.markdown("&nbsp;", unsafe_allow_html=True)
                tabela(df_res)
                baixar(df_res, "auditoria_glosas")
            elif not erro:
                st.warning("Nenhum registro encontrado. Desmarque o filtro de glosas ou confira o arquivo e a operadora.")

elif menu == "Lupa de Glosas":
    cabecalho("Lupa de glosas", "Pesquise e filtre os itens do último demonstrativo.")
    if df_proc.empty:
        st.info("Nenhum arquivo auditado. Processe um demonstrativo em **Casa das Máquinas**.")
    else:
        busca = st.text_input("Buscar em todas as colunas", placeholder="Paciente, procedimento, motivo da glosa...")
        df_view = df_proc
        if busca.strip():
            mask = df_proc.astype(str).apply(lambda c: c.str.contains(busca.strip(), case=False, na=False)).any(axis=1)
            df_view = df_proc[mask]
        st.caption(f"{len(df_view)} de {len(df_proc)} registros")
        tabela(df_view)
        baixar(df_view, "lupa_glosas")

elif menu == "Valores":
    cabecalho("Tabelas de preços e repasses", "Importe a planilha oficial da clínica. Cada aba vira uma especialidade.")
    arquivo_valores = st.file_uploader("Planilha oficial (Excel com várias abas)", type=["xlsx", "xls"])
    if arquivo_valores and st.button("Importar todas as abas", type="primary"):
        with st.spinner("Importando..."):
            ok, msg = processar_e_salvar_excel_multi_abas(arquivo_valores)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.markdown("---")
    df_master = carregar_valores()
    m1, m2, m3 = st.columns(3)
    m1.metric("Registros de preço", len(df_master))
    m2.metric("Especialidades", df_master["especialidade"].nunique() if not df_master.empty else 0)
    m3.metric("Planos", df_master["plano"].nunique() if not df_master.empty else 0)
    st.markdown("&nbsp;", unsafe_allow_html=True)

    esp = st.selectbox("Especialidade", buscar_especialidades())
    df_esp = (
        df_master[df_master["especialidade"].astype(str).str.upper() == str(esp).upper()]
        if not df_master.empty else pd.DataFrame(columns=COLUNAS_VALORES)
    )
    if df_esp.empty:
        st.info("Nenhum valor cadastrado para esta especialidade.")
    else:
        tabela(
            df_esp,
            column_config={
                "valor_plano": st.column_config.NumberColumn("Valor do plano", format="R$ %.2f"),
                "valor_profissional": st.column_config.NumberColumn("Repasse profissional", format="R$ %.2f"),
            },
        )
        baixar(df_esp, f"valores_{esp.lower()}")

elif menu == "Cadastros":
    cabecalho("Cadastros", "Gestão de profissionais e acessos.")
    st.info("Esta área ainda não foi implementada.")

elif menu == "Acessos":
    cabecalho("Auditoria de segurança", "Registro de acessos ao sistema.")
    if hasattr(motor_seguranca, "obter_relatorio_acessos"):
        try:
            tabela(motor_seguranca.obter_relatorio_acessos())
        except Exception as e:
            st.error(f"Não foi possível carregar o relatório: {e}")
    else:
        st.info("O módulo de segurança não possui 'obter_relatorio_acessos'.")

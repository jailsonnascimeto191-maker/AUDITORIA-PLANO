import html
import io
import inspect
import os
import time
from types import SimpleNamespace

import pandas as pd
import streamlit as st

# set_page_config PRECISA ser o primeiro comando do Streamlit no script.
st.set_page_config(
    page_title="Espaço Saúde | Auditoria & Repasses",
    page_icon=(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icone.png")
               if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icone.png"))
               else "🏥"),
    layout="wide",
    initial_sidebar_state="expanded",
)

import banco  # noqa: E402
import motor_seguranca  # noqa: E402
import motor_extracao  # noqa: E402
import motor_conhecimento  # noqa: E402
import motor_historico  # noqa: E402
import paginas_relatorios  # noqa: E402


# ─────────────────────────────────────────────────────────────
# Compatibilidade: use_container_width -> width="stretch"
# ─────────────────────────────────────────────────────────────
def _largura(fn):
    try:
        if "width" in inspect.signature(fn).parameters:
            return {"width": "stretch"}
    except (TypeError, ValueError):
        pass
    return {"use_container_width": True}


FULL_DF = _largura(st.dataframe)
FULL_ED = _largura(st.data_editor)
FULL_BTN = _largura(st.button)
FULL_DL = _largura(st.download_button)
FULL_FORM_BTN = _largura(st.form_submit_button)

# ─────────────────────────────────────────────────────────────
# Constantes de negócio
# ─────────────────────────────────────────────────────────────
DB_VALORES = "valores_clinica.db"

ESPECIALIDADES = [
    "PSICOLOGIA",
    "PSICOPEDAGOGIA",
    "PSICOMOTRICIDADE",
    "FISIOTERAPIA",
    "NUTRIÇÃO",
    "TERAPIA OCUPACIONAL",
]

PLANOS_SAUDE = [
    "Identificar pelo arquivo", "Unimed Recife", "Bradesco Saúde", "SulAmérica",
    "Amil", "Cassi", "GEAP", "Postal Saúde", "Assefaz", "Outros",
]

# Dois tipos de tabela de valores: o que o plano paga à clínica (faturamento)
# e o que a clínica repassa ao profissional (repasse).
TIPOS = {
    "faturamento": {
        "tabela": "tabela_valores_faturamento",
        "col": "valor_plano",
        "rotulo_valor": "Valor pago pelo plano",
        "titulo": "Faturamento (valores do plano)",
        "modelo_col": "Valor do plano",
    },
    "repasse": {
        "tabela": "tabela_valores_repasse",
        "col": "valor_profissional",
        "rotulo_valor": "Valor de repasse ao profissional",
        "titulo": "Repasse ao profissional",
        "modelo_col": "Valor do repasse (profissional)",
    },
}


# ─────────────────────────────────────────────────────────────
# Banco de dados local
# ─────────────────────────────────────────────────────────────
def conectar():
    return banco.conectar(DB_VALORES)


def consultar(sql, params=()):
    with conectar() as conn:
        return banco.ler_df(conn, sql, params)


def init_db():
    with conectar() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_especialidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE)"""
        )
        # Tabela antiga (versões anteriores do sistema): só é lida uma vez, na migração abaixo.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_valores_completa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especialidade TEXT,
                plano TEXT,
                tempo_atendimento TEXT,
                valor_plano REAL,
                valor_profissional REAL)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_valores_faturamento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especialidade TEXT NOT NULL,
                plano TEXT NOT NULL,
                tempo_atendimento TEXT,
                valor_plano REAL NOT NULL)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_valores_repasse (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                especialidade TEXT NOT NULL,
                plano TEXT NOT NULL,
                tempo_atendimento TEXT,
                valor_profissional REAL NOT NULL)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tabela_profissionais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                registro TEXT NOT NULL,
                especialidade TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT,
                criado_por TEXT,
                UNIQUE (registro, especialidade))"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS log_alteracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora TEXT,
                usuario TEXT,
                acao TEXT,
                detalhe TEXT)"""
        )
        for tb in ("tabela_valores_faturamento", "tabela_valores_repasse"):
            if "codigo_tuss" not in banco.colunas(conn, tb):
                conn.execute(f"ALTER TABLE {tb} ADD COLUMN codigo_tuss TEXT")
        conn.commit()

        # Migração única: se as tabelas novas estão vazias, copia da tabela antiga.
        n_f = conn.execute("SELECT COUNT(*) FROM tabela_valores_faturamento").fetchone()[0]
        n_r = conn.execute("SELECT COUNT(*) FROM tabela_valores_repasse").fetchone()[0]
        if n_f == 0 and n_r == 0:
            conn.execute(
                """INSERT INTO tabela_valores_faturamento
                   (especialidade, plano, tempo_atendimento, valor_plano)
                   SELECT especialidade, COALESCE(plano, 'Sem plano'), tempo_atendimento, valor_plano
                   FROM tabela_valores_completa WHERE valor_plano IS NOT NULL"""
            )
            conn.execute(
                """INSERT INTO tabela_valores_repasse
                   (especialidade, plano, tempo_atendimento, valor_profissional)
                   SELECT especialidade, COALESCE(plano, 'Sem plano'), tempo_atendimento, valor_profissional
                   FROM tabela_valores_completa
                   WHERE valor_profissional IS NOT NULL AND valor_profissional > 0"""
            )
            conn.commit()


def registrar_log(acao, detalhe):
    try:
        with conectar() as conn:
            conn.execute(
                "INSERT INTO log_alteracoes (data_hora, usuario, acao, detalhe) "
                "VALUES (?, ?, ?, ?)",
                (banco.agora_txt(), str(st.session_state.get("usuario_atual")), acao, detalhe),
            )
            conn.commit()
    except banco.Error:
        pass


def especialidades_disponiveis():
    extras = []
    try:
        with conectar() as conn:
            for tb in ("tabela_valores_faturamento", "tabela_valores_repasse"):
                extras += [r[0] for r in conn.execute(f"SELECT DISTINCT especialidade FROM {tb}") if r[0]]
    except banco.Error:
        pass
    return ESPECIALIDADES + sorted({e for e in extras if e not in ESPECIALIDADES})


# ── Profissionais ────────────────────────────────────────────
def listar_profissionais():
    return consultar(
        "SELECT id, nome, registro, especialidade, ativo, criado_em "
        "FROM tabela_profissionais ORDER BY nome"
    )


def cadastrar_profissional(nome, registro, especialidade):
    nome = " ".join(nome.split())
    registro = registro.strip().upper()
    if len(nome.split()) < 2:
        return False, "Informe o nome completo (nome e sobrenome)."
    if not registro:
        return False, "Informe o número do CRM / registro profissional."
    try:
        with conectar() as conn:
            conn.execute(
                "INSERT INTO tabela_profissionais (nome, registro, especialidade, ativo, criado_em, criado_por) "
                "VALUES (?, ?, ?, 1, ?, ?)",
                (nome, registro, especialidade, banco.agora_txt(), str(st.session_state.get("usuario_atual"))),
            )
            conn.commit()
    except banco.IntegrityError:
        return False, f"Já existe um profissional com o registro {registro} em {especialidade.title()}."
    registrar_log("Cadastro de profissional", f"{nome} | {registro} | {especialidade}")
    return True, f"Profissional {nome} cadastrado com sucesso."


def atualizar_profissional(pid, nome, registro, especialidade, ativo):
    nome = " ".join(nome.split())
    registro = registro.strip().upper()
    if len(nome.split()) < 2 or not registro:
        return False, "Preencha o nome completo e o registro profissional."
    try:
        with conectar() as conn:
            conn.execute(
                "UPDATE tabela_profissionais SET nome=?, registro=?, especialidade=?, ativo=? WHERE id=?",
                (nome, registro, especialidade, int(ativo), int(pid)),
            )
            conn.commit()
    except banco.IntegrityError:
        return False, "Já existe outro profissional com esse registro nessa especialidade."
    registrar_log("Edição de profissional", f"id {pid} | {nome} | {registro} | {especialidade} | ativo={int(ativo)}")
    return True, "Cadastro atualizado."


def excluir_profissional(pid, nome):
    with conectar() as conn:
        conn.execute("DELETE FROM tabela_profissionais WHERE id=?", (int(pid),))
        conn.commit()
    registrar_log("Exclusão de profissional", f"id {pid} | {nome}")


# ── Valores (faturamento / repasse) ──────────────────────────
def valores_df(tipo, esp):
    cfg = TIPOS[tipo]
    return consultar(
        f"SELECT id, plano, codigo_tuss, tempo_atendimento, {cfg['col']} FROM {cfg['tabela']} "
        "WHERE UPPER(especialidade) = UPPER(?) ORDER BY plano, tempo_atendimento",
        (esp,),
    )


def inserir_valor(tipo, esp, plano, tempo, valor, codigo=""):
    cfg = TIPOS[tipo]
    plano = plano.strip()
    if not plano:
        return False, "Informe o plano de saúde."
    with conectar() as conn:
        conn.execute(
            f"INSERT INTO {cfg['tabela']} (especialidade, plano, tempo_atendimento, {cfg['col']}, codigo_tuss) "
            "VALUES (?,?,?,?,?)",
            (esp, plano, tempo.strip(), float(valor), (codigo or "").strip() or None),
        )
        conn.commit()
    registrar_log(f"Valor cadastrado ({tipo})", f"{esp} | {plano} | {tempo.strip()} | R$ {valor:.2f}")
    return True, "Valor cadastrado."


def salvar_edicao(tipo, esp, original, editado):
    cfg = TIPOS[tipo]
    col, tb = cfg["col"], cfg["tabela"]
    ed = editado.copy()
    ed["plano"] = ed["plano"].map(_limpa_plano)
    ed["tempo_atendimento"] = ed["tempo_atendimento"].fillna("").astype(str).str.strip()
    ed["codigo_tuss"] = (ed["codigo_tuss"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
                         if "codigo_tuss" in ed.columns else "")
    ed[col] = pd.to_numeric(ed[col], errors="coerce")

    invalidas = ed[ed["plano"].isna() | ed[col].isna()]
    if not invalidas.empty:
        return False, f"{len(invalidas)} linha(s) sem plano ou sem valor. Complete ou remova antes de salvar."

    mantidos = ed[ed["id"].notna()]
    novos = ed[ed["id"].isna()]
    removidos = set(original["id"].astype(int)) - set(mantidos["id"].astype(int))

    with conectar() as conn:
        conn.executemany(f"DELETE FROM {tb} WHERE id=?", [(i,) for i in removidos])
        conn.executemany(
            f"UPDATE {tb} SET plano=?, tempo_atendimento=?, {col}=?, codigo_tuss=? WHERE id=?",
            [(r["plano"], r["tempo_atendimento"], float(r[col]), r["codigo_tuss"] or None, int(r["id"]))
             for _, r in mantidos.iterrows()],
        )
        conn.executemany(
            f"INSERT INTO {tb} (especialidade, plano, tempo_atendimento, {col}, codigo_tuss) VALUES (?,?,?,?,?)",
            [(esp, r["plano"], r["tempo_atendimento"], float(r[col]), r["codigo_tuss"] or None)
             for _, r in novos.iterrows()],
        )
        conn.commit()
    registrar_log(
        f"Tabela editada ({tipo})",
        f"{esp} | {len(novos)} nova(s), {len(removidos)} removida(s), {len(mantidos)} mantida(s)",
    )
    return True, f"Alterações salvas: {len(novos)} nova(s), {len(removidos)} removida(s)."


# ── Importação de planilhas ──────────────────────────────────
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


def _limpa_plano(x):
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return None
    s = str(x).strip()
    return None if s.lower() in ("", "nan", "none") else s


def _achar_cabecalho(df_raw):
    """Acha a linha de cabeçalho exigindo pelo menos 2 palavras-chave."""
    chaves = ("PLANO", "TEMPO", "VALOR", "PROFISSIONAL")
    for idx, row in df_raw.iterrows():
        texto = " ".join(str(v).upper() for v in row.values if pd.notnull(v))
        if sum(k in texto for k in chaves) >= 2:
            return idx
    return None


def ler_planilha(arquivo, tipo):
    """Lê um Excel com uma aba por especialidade. Retorna ({especialidade: df}, [erros])."""
    try:
        arquivo.seek(0)
        xls = pd.ExcelFile(io.BytesIO(arquivo.read()))
    except Exception as e:
        return {}, [f"Não foi possível abrir o Excel: {e}. Verifique se 'openpyxl' (xlsx) ou 'xlrd' (xls) está instalado."]

    dados, erros = {}, []
    for aba in xls.sheet_names:
        try:
            df_raw = pd.read_excel(xls, sheet_name=aba, header=None, dtype=object)
            if df_raw.empty:
                continue
            n = df_raw.shape[1]
            if n < 3:
                erros.append(f"{aba} (menos de 3 colunas)")
                continue
            # Formato antigo (4 colunas): plano, tempo, valor do plano, valor do profissional.
            idx_valor = 3 if (tipo == "repasse" and n >= 4) else 2
            cab = _achar_cabecalho(df_raw)
            corpo = df_raw.iloc[cab + 1:] if cab is not None else df_raw
            df = corpo.iloc[:, [0, 1, idx_valor]].copy()
            df.columns = ["plano", "tempo_atendimento", "valor"]

            df["plano"] = df["plano"].map(_limpa_plano).ffill().fillna("Sem plano")
            df["valor"] = df["valor"].map(_para_float)
            df = df.dropna(subset=["valor"])
            df = df[~df["plano"].str.contains("PLANO DE SAÚDE", case=False, na=False)]
            df["tempo_atendimento"] = df["tempo_atendimento"].fillna("").astype(str).str.strip()
            if df.empty:
                erros.append(f"{aba} (nenhuma linha com valor)")
                continue
            dados[aba.strip().upper()] = df.reset_index(drop=True)
        except Exception as ex:
            erros.append(f"{aba} ({ex})")
    return dados, erros


def gravar_importacao(tipo, dados, modo_substituir):
    cfg = TIPOS[tipo]
    tb, col = cfg["tabela"], cfg["col"]
    total = 0
    with conectar() as conn:
        for esp, df in dados.items():
            if modo_substituir:
                conn.execute(f"DELETE FROM {tb} WHERE UPPER(especialidade) = UPPER(?)", (esp,))
            conn.executemany(
                f"INSERT INTO {tb} (especialidade, plano, tempo_atendimento, {col}) VALUES (?,?,?,?)",
                [(esp, r.plano, r.tempo_atendimento, float(r.valor)) for r in df.itertuples()],
            )
            conn.execute("INSERT OR IGNORE INTO tabela_especialidades (nome) VALUES (?)", (esp,))
            total += len(df)
        conn.commit()
    modo = "substituição" if modo_substituir else "adição"
    registrar_log(f"Importação de planilha ({tipo})", f"{total} registros | {', '.join(sorted(dados))} | modo: {modo}")
    return total


def gerar_modelo(tipo):
    cfg = TIPOS[tipo]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for esp in ESPECIALIDADES:
            pd.DataFrame(columns=["Plano", "Tempo de atendimento", cfg["modelo_col"]]).to_excel(
                writer, sheet_name=esp[:31], index=False
            )
    return buf.getvalue()


def indicadores_cadastro():
    ind = {"prof_ativos": 0, "prof_total": 0, "regras_fat": 0, "regras_rep": 0}
    try:
        with conectar() as conn:
            ind["prof_total"] = conn.execute("SELECT COUNT(*) FROM tabela_profissionais").fetchone()[0]
            ind["prof_ativos"] = conn.execute("SELECT COUNT(*) FROM tabela_profissionais WHERE ativo=1").fetchone()[0]
            ind["regras_fat"] = conn.execute("SELECT COUNT(*) FROM tabela_valores_faturamento").fetchone()[0]
            ind["regras_rep"] = conn.execute("SELECT COUNT(*) FROM tabela_valores_repasse").fetchone()[0]
    except banco.Error:
        pass
    return ind


@st.cache_resource(show_spinner=False)
def _inicializar_bancos(chave_banco):
    """Cria/migra os bancos uma única vez por servidor e por banco configurado (antes rodava
    a cada clique). Se o DATABASE_URL mudar nos Secrets, roda de novo para o banco novo.
    Retorna a mensagem de erro, se houver."""
    try:
        init_db()
        motor_historico.init_historico()
        motor_conhecimento.init_conhecimento()
        motor_seguranca.init_db_seguranca()
    except Exception as e:
        return str(e)
    return None


_erro_init = _inicializar_bancos(banco.chave_configuracao())
if _erro_init:
    _inicializar_bancos.clear()  # tenta de novo na próxima interação
    st.error(_erro_init)
    st.stop()

# ─────────────────────────────────────────────────────────────
# Tema / CSS
# ─────────────────────────────────────────────────────────────
# Logotipo (desenhado em SVG: fica igual em qualquer computador ou celular, ao contrário de um emoji)
LOGO_SVG = (
    "<svg viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Espaço Saúde'>"
    "<rect width='40' height='40' rx='10' fill='#0E7C86'/>"
    "<rect x='16.5' y='9' width='7' height='22' rx='2' fill='#FFFFFF'/>"
    "<rect x='9' y='16.5' width='22' height='7' rx='2' fill='#FFFFFF'/>"
    "<circle cx='30' cy='30' r='5.2' fill='#0F2A43'/>"
    "<path d='M27.6 30.1l1.6 1.6 3.2-3.3' stroke='#4FD1C5' stroke-width='1.6' fill='none' "
    "stroke-linecap='round' stroke-linejoin='round'/>"
    "</svg>"
)

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
[data-testid="stSidebar"] .stButton button {
  background: transparent; border: 1px solid rgba(255,255,255,.25); color: #fff;
}
[data-testid="stSidebar"] .stButton button:hover { background: rgba(255,255,255,.1); border-color: #fff; }

/* Menu lateral (botões agrupados por seção) */
.nav-secao { font-size: 10.5px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
  color: #7F96AD; margin: 14px 4px 4px; }
[data-testid="stSidebar"] [class*="st-key-nav_"] { margin-bottom: -10px; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button {
  justify-content: flex-start; text-align: left; background: transparent; border: 0;
  border-left: 3px solid transparent; border-radius: 8px; padding: .45rem .8rem; color: #DCE6F0;
  min-height: 0; font-weight: 400; box-shadow: none;
}
[data-testid="stSidebar"] [class*="st-key-nav_"] button p { font-size: 14px; text-align: left; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button:hover { background: rgba(255,255,255,.07); color: #fff; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button[kind="primary"],
[data-testid="stSidebar"] [class*="st-key-nav_"] button[kind="primary"]:hover {
  background: rgba(255,255,255,.12); border-left-color: #4FD1C5; color: #fff; font-weight: 600;
}

.marca { display:flex; align-items:center; gap:10px; padding: 4px 4px 14px; }
.marca .logo { width:36px; height:36px; flex: 0 0 36px; }
.marca .logo svg, .login-marca .logo svg { width:100%; height:100%; display:block; }
.marca .nome { font-weight:600; font-size:16px; line-height:1.1; color:#fff; }
.marca .sub { font-size:11.5px; color:#9FB3C8; }
.usuario { background: rgba(255,255,255,.07); border-radius: 10px; padding: 10px 12px; margin-bottom: 10px; }
.usuario b { color:#fff; }
.usuario span { font-size:12px; color:#9FB3C8; }

/* Cabeçalho de página */
.pagina-titulo { font-size: 26px; font-weight: 600; color: var(--ink); margin: 0; }
.pagina-sub { color: var(--muted); font-size: 14px; margin: 4px 0 22px; }
.secao-titulo { font-size: 13px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); margin: 22px 0 8px; }

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

/* Abas */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { padding: 10px 16px; font-weight: 500; color: var(--muted); }
.stTabs [aria-selected="true"] { color: var(--teal-dark); font-weight: 600; }

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
.login-marca .logo { width:56px; height:56px; display:inline-block; margin-bottom:12px; }
.login-marca h1 { font-size:24px; font-weight:600; margin:0; color:var(--ink); }
.login-marca p { color:var(--muted); font-size:14px; margin:6px 0 0; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# Componentes de interface
# ─────────────────────────────────────────────────────────────
def cabecalho(titulo, subtitulo=""):
    st.markdown(
        f"<h1 class='pagina-titulo'>{titulo}</h1><p class='pagina-sub'>{subtitulo}</p>",
        unsafe_allow_html=True,
    )


def secao(titulo):
    st.markdown(f"<div class='secao-titulo'>{titulo}</div>", unsafe_allow_html=True)


def tabela(df, **kw):
    """Mostra um DataFrame; colunas de valor em dinheiro saem formatadas em R$ automaticamente."""
    cfg = {}
    for c in df.columns:
        nome = str(c)
        if nome.lower().startswith(("valor", "repasse")) and pd.api.types.is_numeric_dtype(df[c]):
            cfg[nome] = st.column_config.NumberColumn(nome, format="R$ %.2f")
        elif nome in ("Linhas", "Itens") and pd.api.types.is_numeric_dtype(df[c]):
            cfg[nome] = st.column_config.NumberColumn(nome, format="%d")
    cfg.update(kw.pop("column_config", None) or {})
    st.dataframe(df, hide_index=True, column_config=cfg, **FULL_DF, **kw)


def baixar(df, nome, rotulo="Baixar CSV", key=None):
    st.download_button(
        rotulo, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        file_name=f"{nome}.csv", mime="text/csv", key=key, **FULL_DL,
    )


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def avisar(tipo, msg):
    """Guarda uma mensagem para ser exibida após o st.rerun()."""
    st.session_state["flash"] = (tipo, msg)


def mostrar_flash():
    flash = st.session_state.pop("flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])


def kpis_do_processamento(df):
    """Sempre exibe os 4 indicadores, mesmo sem dados (valores zerados)."""
    total = glosado = 0.0
    itens_glosa = 0
    n = 0 if df is None else len(df)

    if n:
        cols = [str(c) for c in df.columns]
        col_valor = next((c for c in cols if "valor" in c.lower() and "glosa" not in c.lower()), None)
        cols_glosa = [c for c in cols if "glosa" in c.lower()]
        num = lambda c: pd.to_numeric(df[c].map(_para_float), errors="coerce")
        if col_valor:
            total = float(num(col_valor).sum())
        col_num = next((c for c in cols_glosa if num(c).notna().any()), None)
        if col_num:
            s = num(col_num)
            glosado = float(s.sum())
            itens_glosa = int((s > 0).sum())
        elif cols_glosa:
            itens_glosa = int(df[cols_glosa[0]].astype(str).str.strip().replace({"nan": "", "None": ""}).ne("").sum())

    perc = (glosado / total * 100) if total else 0.0
    c = st.columns(4)
    c[0].metric("Registros auditados", f"{n:,}".replace(",", "."))
    c[1].metric("Valor apresentado", brl(total))
    c[2].metric("Valor glosado", brl(glosado), help=f"{perc:.1f}% do valor apresentado".replace(".", ","))
    c[3].metric("Itens com glosa", f"{itens_glosa:,}".replace(",", "."))


def kpis_cadastro():
    ind = indicadores_cadastro()
    c = st.columns(4)
    c[0].metric("Profissionais ativos", ind["prof_ativos"])
    c[1].metric("Profissionais cadastrados", ind["prof_total"])
    c[2].metric("Regras de faturamento", ind["regras_fat"])
    c[3].metric("Regras de repasse", ind["regras_rep"])


# ─────────────────────────────────────────────────────────────
# Seção reutilizável de Valores (faturamento / repasse)
# ─────────────────────────────────────────────────────────────
def secao_valores(tipo):
    cfg = TIPOS[tipo]
    col = cfg["col"]
    especs = especialidades_disponiveis()

    sub = st.tabs(["Tabelas por especialidade", "Cadastrar valor", "Importar planilha"])

    # 1) Uma tabela editável por especialidade
    with sub[0]:
        abas = st.tabs([e.title() for e in especs])
        for aba, esp in zip(abas, especs):
            with aba:
                ver_key = f"ver_{tipo}_{esp}"
                ver = st.session_state.setdefault(ver_key, 0)
                original = valores_df(tipo, esp)
                st.caption(
                    f"{len(original)} registro(s) em {esp.title()}. "
                    "Edite direto na tabela, adicione linhas no final ou apague selecionando a linha e pressionando Delete."
                )
                editado = st.data_editor(
                    original,
                    key=f"ed_{tipo}_{esp}_{ver}",
                    num_rows="dynamic",
                    hide_index=True,
                    disabled=["id"],
                    column_config={
                        "id": None,
                        "plano": st.column_config.TextColumn("Plano de saúde", required=True),
                        "codigo_tuss": st.column_config.TextColumn(
                            "Código TUSS (opcional)",
                            help="Ligue o valor ao código do procedimento no demonstrativo. Sem código, o "
                                 "sistema usa a especialidade (quando houver um único valor para o plano)."),
                        "tempo_atendimento": st.column_config.TextColumn("Tempo de atendimento"),
                        col: st.column_config.NumberColumn(
                            cfg["rotulo_valor"], format="R$ %.2f", min_value=0.0, required=True
                        ),
                    },
                    **FULL_ED,
                )
                b1, b2 = st.columns([1, 1])
                if b1.button("Salvar alterações", type="primary", key=f"salvar_{tipo}_{esp}", **FULL_BTN):
                    ok, msg = salvar_edicao(tipo, esp, original, editado)
                    if ok:
                        st.session_state[ver_key] = ver + 1
                        avisar("success", msg)
                        st.rerun()
                    else:
                        st.error(msg)
                with b2:
                    baixar(original.drop(columns=["id"]), f"{tipo}_{esp.lower().replace(' ', '_')}",
                           key=f"dl_{tipo}_{esp}")

    # 2) Cadastro manual
    with sub[1]:
        with st.form(f"form_valor_{tipo}", clear_on_submit=True):
            f1, f2 = st.columns(2)
            esp_sel = f1.selectbox("Especialidade", especs, format_func=str.title)
            plano = f2.text_input("Plano de saúde", placeholder="Ex.: Unimed Recife")
            f3, f4, f5 = st.columns(3)
            tempo = f3.text_input("Tempo de atendimento", placeholder="Ex.: 50 min")
            codigo = f4.text_input("Código TUSS (opcional)", placeholder="Ex.: 50000470")
            valor = f5.number_input(cfg["rotulo_valor"] + " (R$)", min_value=0.0, step=1.0, format="%.2f")
            enviar = st.form_submit_button("Cadastrar valor", **FULL_FORM_BTN)
        if enviar:
            if valor <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                ok, msg = inserir_valor(tipo, esp_sel, plano, tempo, valor, codigo)
                if ok:
                    avisar("success", f"{msg} ({esp_sel.title()} · {plano.strip()} · {brl(valor)})")
                    st.rerun()
                else:
                    st.error(msg)

    # 3) Importação por planilha
    with sub[2]:
        st.markdown(
            "Envie um Excel com **uma aba por especialidade** (o nome da aba deve ser o da especialidade). "
            "Colunas: plano, tempo de atendimento e valor."
        )
        st.download_button(
            "Baixar modelo de planilha",
            gerar_modelo(tipo),
            file_name=f"modelo_{tipo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"modelo_{tipo}",
        )
        arquivo = st.file_uploader("Planilha (xlsx ou xls)", type=["xlsx", "xls"], key=f"up_{tipo}")
        modo = st.radio(
            "Como aplicar",
            ["Substituir a tabela das especialidades presentes no arquivo", "Adicionar aos valores existentes"],
            key=f"modo_{tipo}",
        )
        if arquivo:
            dados, erros = ler_planilha(arquivo, tipo)
            if dados:
                resumo = pd.DataFrame(
                    [{"Aba / especialidade": k.title(), "Registros": len(v)} for k, v in dados.items()]
                )
                tabela(resumo)
                desconhecidas = [k for k in dados if k not in especs]
                if desconhecidas:
                    st.warning("Abas fora da lista de especialidades (serão importadas mesmo assim): "
                               + ", ".join(desconhecidas))
            for e in erros:
                st.warning(f"Aba ignorada: {e}")
            if dados and st.button("Confirmar importação", type="primary", key=f"conf_{tipo}"):
                total = gravar_importacao(tipo, dados, modo.startswith("Substituir"))
                for k in list(st.session_state.keys()):
                    if k.startswith(f"ver_{tipo}_"):
                        st.session_state[k] += 1
                avisar("success", f"Importação concluída: {total} registros em {len(dados)} especialidade(s).")
                st.rerun()


# ─────────────────────────────────────────────────────────────
# Helpers entregues às páginas de relatórios (paginas_relatorios.py)
# ─────────────────────────────────────────────────────────────
H = SimpleNamespace(
    cabecalho=cabecalho, secao=secao, tabela=tabela, brl=brl,
    FULL_BTN=FULL_BTN, FULL_DL=FULL_DL, valores_df=valores_df,
    listar_profissionais=listar_profissionais, PLANOS_SAUDE=PLANOS_SAUDE,
    registrar_log=registrar_log,
)

# ─────────────────────────────────────────────────────────────
# Sessão
# ─────────────────────────────────────────────────────────────
for chave, padrao in (("autenticado", False), ("usuario_atual", None), ("nivel_permissao", None),
                      ("trocar_senha", False), ("ultima_atividade", 0.0)):
    st.session_state.setdefault(chave, padrao)

INATIVIDADE_MIN = 30  # encerra a sessão após 30 minutos sem uso


def sair(motivo=None):
    for k in ("autenticado", "usuario_atual", "nivel_permissao", "ultimo_processamento", "trocar_senha"):
        st.session_state.pop(k, None)
    if motivo:
        st.session_state["flash"] = ("info", motivo)
    st.rerun()


if st.session_state.get("autenticado"):
    agora = time.time()
    ultima = st.session_state.get("ultima_atividade") or agora
    if agora - ultima > INATIVIDADE_MIN * 60:
        sair(f"Sua sessão foi encerrada após {INATIVIDADE_MIN} minutos sem uso. Entre novamente.")
    st.session_state["ultima_atividade"] = agora

# ─────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────
if not st.session_state.autenticado:
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        st.markdown(
            f"""<div class='login-marca'><div class='logo'>{LOGO_SVG}</div>
            <h1>Espaço Saúde</h1>
            <p>Auditoria, faturamento e repasses</p></div>""",
            unsafe_allow_html=True,
        )
        mostrar_flash()
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
                    nome = usuario.lower().strip()
                    trocar = bool(getattr(motor_seguranca, "precisa_trocar_senha", lambda u: False)(nome))
                    st.session_state.update(
                        autenticado=True, usuario_atual=nome, nivel_permissao=role,
                        trocar_senha=trocar, ultima_atividade=time.time(),
                    )
                    st.rerun()
                else:
                    st.error(msg)
    st.stop()

# ─────────────────────────────────────────────────────────────
# Troca de senha obrigatória (primeiro acesso ou senha temporária)
# ─────────────────────────────────────────────────────────────
if st.session_state.get("trocar_senha"):
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        st.markdown(
            f"""<div class='login-marca'><div class='logo'>{LOGO_SVG}</div>
            <h1>Crie uma nova senha</h1>
            <p>Por segurança, troque a senha antes de continuar.</p></div>""",
            unsafe_allow_html=True,
        )
        with st.form("form_troca_obrigatoria"):
            atual = st.text_input("Senha atual", type="password")
            nova = st.text_input("Nova senha", type="password",
                                 help="Mínimo de 8 caracteres, com letras e números.")
            conf = st.text_input("Repita a nova senha", type="password")
            ok_btn = st.form_submit_button("Salvar nova senha", **FULL_FORM_BTN)
        if ok_btn:
            if nova != conf:
                st.error("As duas senhas novas não são iguais.")
            else:
                ok, msg = motor_seguranca.alterar_senha(st.session_state.usuario_atual, atual, nova)
                if ok:
                    st.session_state.trocar_senha = False
                    avisar("success", msg)
                    st.rerun()
                else:
                    st.error(msg)
        if st.button("Sair", **FULL_BTN):
            sair()
    st.stop()

# ─────────────────────────────────────────────────────────────
# Navegação
# ─────────────────────────────────────────────────────────────
# Seções do menu: (seção, [(página, descrição mostrada ao passar o mouse), ...])
SECOES_MENU = [
    ("Visão geral", [
        ("Painel", "Indicadores e gráficos de todo o histórico de glosas"),
    ]),
    ("Operação", [
        ("Casa das Máquinas", "Importar e auditar o demonstrativo do convênio"),
        ("Lupa de Glosas", "Pesquisar glosas no último demonstrativo ou no histórico"),
    ]),
    ("Relatórios", [
        ("Produção do Profissional", "Espelho da produção e do repasse de um profissional no mês"),
        ("Relatório de Glosas", "Relação de glosas em Excel e PDF"),
        ("Faturamento x Recebimento", "Conferir se o que foi faturado nos lotes foi pago"),
    ]),
]
SECAO_ADMIN = ("Administração", [
    ("Valores", "Tabelas de faturamento e de repasse por especialidade"),
    ("Cadastros", "Profissionais da clínica"),
    ("Acessos", "Usuários, registro de acessos e histórico de alterações"),
])
MENUS_ADMIN = [p for p, _ in SECAO_ADMIN[1]]
eh_admin = st.session_state.nivel_permissao == "Administrador"
secoes = SECOES_MENU + ([SECAO_ADMIN] if eh_admin else [])
paginas = [p for _, itens in secoes for p, _ in itens]
if st.session_state.get("menu") not in paginas:
    st.session_state["menu"] = "Painel"
menu = st.session_state["menu"]

with st.sidebar:
    st.markdown(
        f"<div class='marca'><div class='logo'>{LOGO_SVG}</div>"
        "<div><div class='nome'>Espaço Saúde</div><div class='sub'>Auditoria & Repasses</div></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='usuario'><b>{html.escape(str(st.session_state.usuario_atual).capitalize())}</b><br>"
        f"<span>Perfil: {html.escape(str(st.session_state.nivel_permissao))}</span></div>",
        unsafe_allow_html=True,
    )
    n = 0
    for titulo_secao, itens in secoes:
        st.markdown(f"<div class='nav-secao'>{titulo_secao}</div>", unsafe_allow_html=True)
        for pagina, descricao in itens:
            n += 1
            if st.button(pagina, key=f"nav_{n}", help=descricao,
                         type="primary" if pagina == menu else "secondary", **FULL_BTN):
                st.session_state["menu"] = pagina
                st.rerun()
    st.markdown("---")
    with st.expander("Alterar minha senha"):
        with st.form("form_minha_senha", clear_on_submit=True):
            atual = st.text_input("Senha atual", type="password")
            nova = st.text_input("Nova senha", type="password")
            conf = st.text_input("Repita a nova senha", type="password")
            trocar = st.form_submit_button("Salvar", **FULL_FORM_BTN)
        if trocar:
            if nova != conf:
                st.error("As senhas novas não são iguais.")
            else:
                ok, msg = motor_seguranca.alterar_senha(st.session_state.usuario_atual, atual, nova)
                (st.success if ok else st.error)(msg)
    if st.button("Sair do sistema", key="sair_sistema", **FULL_BTN):
        sair()

if menu in MENUS_ADMIN and not eh_admin:
    st.error("Você não tem permissão para acessar esta área.")
    st.stop()

df_proc = st.session_state.get("ultimo_processamento", pd.DataFrame())
mostrar_flash()

PERIODOS = {"Últimos 3 meses": 3, "Últimos 6 meses": 6, "Últimos 12 meses": 12, "Todo o histórico": None}


def _desde(periodo):
    meses = PERIODOS.get(periodo)
    if not meses:
        return None
    inicio = (pd.Timestamp.today().normalize().replace(day=1) - pd.DateOffset(months=meses - 1))
    return inicio.strftime("%Y-%m-%d")


def _filtrar_texto(df, busca):
    if not busca.strip():
        return df
    mask = df.astype(str).apply(lambda c: c.str.contains(busca.strip(), case=False, na=False, regex=False)).any(axis=1)
    return df[mask]


# ─────────────────────────────────────────────────────────────
# Páginas
# ─────────────────────────────────────────────────────────────
if menu == "Painel":
    cabecalho("Painel geral", "Indicadores de todos os demonstrativos já processados na Casa das Máquinas.")
    ops_disp = motor_historico.operadoras()
    if not ops_disp:
        secao("Base cadastral")
        kpis_cadastro()
        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.info("Ainda não há demonstrativos no histórico. Processe um arquivo em **Casa das Máquinas** "
                "e os gráficos aparecem aqui.")
    else:
        f1, f2 = st.columns([1, 2])
        periodo = f1.selectbox("Período (data do atendimento)", list(PERIODOS), index=2, key="painel_periodo")
        ops_sel = f2.multiselect("Operadoras", ops_disp, default=ops_disp, key="painel_ops")
        itens = motor_historico.carregar_itens(_desde(periodo), ops_sel or None)
        r = motor_historico.resumo_painel(itens)

        secao("Glosas no período")
        c = st.columns(4)
        c[0].metric("Valor apresentado", brl(r["apresentado"]))
        c[1].metric("Valor glosado", brl(r["glosado"]))
        c[2].metric("% glosado", f"{r['pct'] * 100:.1f}%".replace(".", ","))
        c[3].metric("Itens glosados", f"{r['itens_glosados']:,}".replace(",", "."))
        if r.get("itens_diferenca"):
            st.caption(f"Fora das glosas: {r['itens_diferenca']} atendimento(s) pagos abaixo do valor de referência "
                       f"sem justificativa do plano, somando {brl(r['diferencas'])}. Pesquise na **Lupa de Glosas** "
                       "desmarcando \"Só itens com glosa\".")

        if r["itens_glosados"] == 0:
            st.success("Nenhuma glosa no período e nas operadoras escolhidas.")
        else:
            g1, g2 = st.columns(2)
            with g1:
                secao("Valor glosado por mês")
                st.bar_chart(r["por_mes"], x="Mês", y="Valor glosado", color="#0E7C86", height=280)
            with g2:
                secao("Valor glosado por operadora")
                st.bar_chart(r["por_operadora"], x="Operadora", y="Valor glosado", color="#0F2A43",
                             horizontal=True, height=280)
            secao("Principais motivos de glosa")
            mot = r["motivos"].copy()
            mot["% do glosado"] = mot["% do glosado"] * 100
            tabela(mot, column_config={"% do glosado": st.column_config.NumberColumn(format="%.1f%%")})

        secao("Base cadastral")
        kpis_cadastro()

        with st.expander("Demonstrativos processados"):
            lista = motor_historico.listar_demonstrativos()
            tabela(lista.drop(columns=["id"]))
            if eh_admin and not lista.empty:
                rot = {int(x["id"]): f"{x['Arquivo']} — {x['Processado em']} ({x['Operadora']})"
                       for _, x in lista.iterrows()}
                d1, d2 = st.columns([3, 1])
                alvo = d1.selectbox("Remover do histórico", list(rot), format_func=rot.get, key="hist_alvo")
                conf_del = d2.checkbox("Confirmo", key=f"hist_conf_{alvo}")
                if d2.button("Remover", disabled=not conf_del, key=f"hist_del_{alvo}", **FULL_BTN):
                    motor_historico.excluir_demonstrativo(alvo)
                    registrar_log("Demonstrativo removido do histórico", rot[alvo])
                    avisar("success", "Demonstrativo removido do histórico.")
                    st.rerun()

elif menu == "Casa das Máquinas":
    cabecalho("Casa das Máquinas",
              "Envie o demonstrativo do convênio: o sistema entende a estrutura do arquivo, aponta as glosas "
              "e guarda no histórico.")
    c1, c2 = st.columns([2, 1])
    plano = c1.selectbox("Operadora / plano de saúde", PLANOS_SAUDE)
    exibir = c2.selectbox("Exibir", ["Itens com glosa", "Diferenças a conferir", "Todos os itens"])

    arquivo = st.file_uploader(
        "Demonstrativo do convênio", type=paginas_relatorios.TIPOS_DEMONSTRATIVO
    )

    def _processar(nome_arq, dados, plano_sel, reprocessando=False):
        class _Arq(io.BytesIO):
            name = nome_arq
        with st.spinner("Lendo a estrutura do arquivo e auditando os atendimentos..."):
            try:
                df_res, erro = motor_conhecimento.extrair(_Arq(dados), plano=plano_sel, somente_glosas=False)
            except Exception as e:
                df_res, erro = pd.DataFrame(), f"{type(e).__name__}: {e}"
        if df_res is None or df_res.empty:
            st.error(f"Problema na extração: {erro or 'nenhum registro encontrado.'}")
            return
        operadora = df_res.attrs.get("operadora") or plano_sel
        if operadora == "INDEFINIDO" and plano_sel != motor_extracao.PLANO_AUTOMATICO:
            operadora = plano_sel
        df_res["Operadora"] = operadora
        try:
            _, substituiu, ignorados = motor_historico.salvar_demonstrativo(
                df_res, nome_arq, motor_historico.hash_arquivo(dados), str(st.session_state.usuario_atual), operadora)
            aviso = " A versão anterior deste arquivo foi substituída no histórico." if substituiu else " Guardado no histórico."
            if ignorados:
                aviso += (f" {ignorados} atendimento(s) já estavam no histórico por outro arquivo e não foram "
                          "contados de novo.")
        except Exception as e:
            aviso = f" Não foi possível guardar no histórico: {e}"
        registrar_log("Demonstrativo reprocessado" if reprocessando else "Demonstrativo processado",
                      f"{nome_arq} | {operadora} | {len(df_res)} atendimentos")
        st.session_state["ultimo_processamento"] = df_res
        st.session_state["ultimo_arquivo"] = nome_arq
        st.session_state["ultimo_arquivo_dados"] = (nome_arq, dados, plano_sel)
        st.session_state["ultima_leitura"] = dict(leituras=df_res.attrs.get("leituras", []),
                                                  resumo=df_res.attrs.get("resumo", {}), operadora=operadora)
        avisar("success", f"Processamento concluído: {len(df_res)} atendimentos.{aviso}")
        st.rerun()

    if st.button("Processar e auditar", type="primary", **FULL_BTN):
        if arquivo is None:
            st.warning("Selecione um arquivo antes de processar.")
        else:
            _processar(arquivo.name, arquivo.getvalue(), plano)

    if not df_proc.empty:
        secao(f"Resultado: {st.session_state.get('ultimo_arquivo', 'último demonstrativo')}")
        kpis_do_processamento(df_proc)
        dif_total = float(pd.to_numeric(df_proc.get("Diferença sem justificativa", pd.Series(dtype=float)),
                                        errors="coerce").fillna(0).sum())
        n_dif = int((pd.to_numeric(df_proc.get("Diferença sem justificativa", pd.Series(dtype=float)),
                                   errors="coerce").fillna(0) > 0.005).sum())
        if n_dif:
            st.caption(f"Além das glosas, {n_dif} atendimento(s) foram pagos abaixo do valor de referência sem "
                       f"justificativa do plano (total {brl(dif_total)}). Veja em **Exibir → Diferenças a conferir**.")

        leitura = st.session_state.get("ultima_leitura") or {}
        res = leitura.get("resumo") or {}
        with st.expander("Conferência da leitura (como o sistema entendeu o arquivo)"):
            m = st.columns(4)
            m[0].metric("Linhas lidas", f"{res.get('linhas_lidas', 0):,}".replace(",", "."))
            m[1].metric("Cópias ignoradas", f"{res.get('copias_removidas', 0):,}".replace(",", "."),
                        help="O mesmo pagamento repetido em outra aba/tabela do arquivo conta uma vez só.")
            m[2].metric("Linhas agrupadas", f"{res.get('linhas_agrupadas', 0):,}".replace(",", "."),
                        help="Várias sessões da mesma guia ou o mesmo atendimento pago em mais de um crédito.")
            m[3].metric("Atendimentos", f"{res.get('atendimentos', 0):,}".replace(",", "."))
            fontes = df_proc["Fonte do valor informado"].value_counts() if "Fonte do valor informado" in df_proc else pd.Series(dtype=int)
            if len(fontes):
                st.caption("Origem do valor apresentado: " + " · ".join(f"{k}: {v}" for k, v in fontes.items()))
            if fontes.get(motor_extracao.FONTE_APRENDIDO, 0):
                st.info("Este arquivo não traz o valor apresentado. Para os procedimentos sem valor cadastrado, o "
                        "sistema usou o valor que o plano costuma pagar. Cadastre em **Valores** (com o código "
                        "TUSS) para que a glosa seja calculada pelo valor da clínica.")

            # um editor por layout de tabela (abas iguais compartilham o mesmo layout)
            layouts = {}
            for lt in leitura.get("leituras", []):
                if lt.get("assinatura") and lt["assinatura"] not in layouts:
                    layouts[lt["assinatura"]] = lt
            for n_lay, (assin, lt) in enumerate(layouts.items()):
                st.markdown(f"**Layout {n_lay + 1}** — exemplo: {html.escape(str(lt.get('tabela', '')))} · "
                            f"leitura: {lt.get('origem_mapa', 'automático')}")
                for obs in lt.get("observacoes", []):
                    st.caption(obs)
                opcoes = [""] + list(lt.get("colunas", []))
                tab = motor_conhecimento.mapa_para_tabela(lt)
                ed = st.data_editor(
                    tab, key=f"mapa_{assin}", hide_index=True, disabled=["Campo do sistema"],
                    column_config={"Coluna do arquivo": st.column_config.SelectboxColumn(
                        "Coluna do arquivo", options=opcoes, help="Deixe vazio se o arquivo não tem esse dado.")},
                    **FULL_ED,
                )
                if st.button("Salvar este padrão e reprocessar", key=f"salvar_mapa_{assin}",
                             help="O sistema passa a ler todo arquivo com este mesmo layout desta forma."):
                    novo = {r["Campo do sistema"]: r["Coluna do arquivo"] for _, r in ed.iterrows()
                            if r["Coluna do arquivo"]}
                    motor_conhecimento.salvar_perfil(assin, novo, lt.get("colunas", []), leitura.get("operadora"),
                                                     str(st.session_state.usuario_atual))
                    registrar_log("Padrão de leitura salvo", f"{leitura.get('operadora')} | {len(novo)} campos")
                    dados_arq = st.session_state.get("ultimo_arquivo_dados")
                    if dados_arq:
                        _processar(*dados_arq, reprocessando=True)
                    else:
                        avisar("success", "Padrão salvo. Ele será usado nos próximos arquivos com este layout.")
                        st.rerun()

        st.markdown("&nbsp;", unsafe_allow_html=True)
        if exibir == "Itens com glosa":
            vis = df_proc[df_proc["Valor da glosa"] > 0.005]
        elif exibir == "Diferenças a conferir":
            vis = df_proc[pd.to_numeric(df_proc.get("Diferença sem justificativa", 0), errors="coerce").fillna(0) > 0.005]
        else:
            vis = df_proc
        if vis.empty:
            st.success("Nenhum item nesta visão.")
        else:
            st.caption(f"{len(vis)} de {len(df_proc)} atendimentos")
            tabela(vis)
            baixar(vis, "auditoria_glosas")

elif menu == "Lupa de Glosas":
    cabecalho("Lupa de glosas", "Pesquise glosas no último demonstrativo processado ou em todo o histórico.")
    opcoes = ["Todo o histórico"] + (["Último demonstrativo processado"] if not df_proc.empty else [])
    l1, l2 = st.columns([1, 2])
    origem = l1.radio("Onde pesquisar", opcoes, key="lupa_origem")
    if origem == "Todo o histórico":
        ops_disp = motor_historico.operadoras()
        ops_sel = l2.multiselect("Operadoras", ops_disp, default=ops_disp, key="lupa_ops")
        periodo = l2.selectbox("Período (data do atendimento)", list(PERIODOS), index=3, key="lupa_periodo")
        base = motor_historico.carregar_itens(_desde(periodo), ops_sel or None) if ops_disp else pd.DataFrame()
        base = base.drop(columns=["_iso"], errors="ignore")
    else:
        base = df_proc
    if base.empty:
        st.info("Nenhum demonstrativo processado ainda. Envie um arquivo em **Casa das Máquinas**.")
    else:
        b1, b2 = st.columns([3, 1])
        busca = b1.text_input("Buscar em todas as colunas", placeholder="Paciente, guia, procedimento, motivo...")
        b2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        so_glosas = b2.checkbox("Só itens com glosa", value=True, key="lupa_so_glosas")
        df_view = base[base["Valor da glosa"] > 0.005] if so_glosas else base
        df_view = _filtrar_texto(df_view, busca)
        st.caption(f"{len(df_view)} registro(s) · valor glosado: {brl(float(df_view['Valor da glosa'].sum()))}")
        tabela(df_view)
        baixar(df_view, "lupa_glosas")

elif menu == "Produção do Profissional":
    paginas_relatorios.render_producao(H)

elif menu == "Relatório de Glosas":
    paginas_relatorios.render_glosas(H)

elif menu == "Faturamento x Recebimento":
    paginas_relatorios.render_faturamento(H)

elif menu == "Valores":
    cabecalho(
        "Tabelas de valores",
        "Faturamento (o que o plano paga à clínica) e repasse (o que o profissional recebe), uma tabela por especialidade.",
    )
    aba_fat, aba_rep = st.tabs([TIPOS["faturamento"]["titulo"], TIPOS["repasse"]["titulo"]])
    with aba_fat:
        secao_valores("faturamento")
    with aba_rep:
        secao_valores("repasse")

elif menu == "Cadastros":
    cabecalho("Cadastros", "Cadastro e gestão dos profissionais da clínica.")
    kpis_cadastro()
    st.markdown("&nbsp;", unsafe_allow_html=True)

    aba_novo, aba_lista = st.tabs(["Novo profissional", "Profissionais cadastrados"])

    with aba_novo:
        with st.form("form_profissional", clear_on_submit=True):
            nome = st.text_input("Nome completo", placeholder="Ex.: Maria Souza Lima")
            f1, f2 = st.columns(2)
            registro = f1.text_input("CRM / registro no conselho", placeholder="Ex.: CRP 02/12345")
            especialidade = f2.selectbox("Especialidade", ESPECIALIDADES, format_func=str.title)
            salvar = st.form_submit_button("Cadastrar profissional", **FULL_FORM_BTN)
        if salvar:
            ok, msg = cadastrar_profissional(nome, registro, especialidade)
            if ok:
                avisar("success", msg)
                st.rerun()
            else:
                st.error(msg)

    with aba_lista:
        df_prof = listar_profissionais()
        if df_prof.empty:
            st.info("Nenhum profissional cadastrado ainda. Use a aba **Novo profissional**.")
        else:
            f1, f2, f3 = st.columns([2, 1, 1])
            busca_p = f1.text_input("Buscar por nome ou registro", key="busca_prof")
            filtro_esp = f2.selectbox("Especialidade", ["Todas"] + ESPECIALIDADES, format_func=str.title, key="filtro_esp")
            filtro_st = f3.selectbox("Situação", ["Todos", "Ativos", "Inativos"], key="filtro_st")

            vis = df_prof.copy()
            if busca_p.strip():
                b = busca_p.strip()
                vis = vis[vis["nome"].str.contains(b, case=False, na=False) | vis["registro"].str.contains(b, case=False, na=False)]
            if filtro_esp != "Todas":
                vis = vis[vis["especialidade"] == filtro_esp]
            if filtro_st != "Todos":
                vis = vis[vis["ativo"] == (1 if filtro_st == "Ativos" else 0)]

            exibir = vis.assign(
                situacao=vis["ativo"].map({1: "Ativo", 0: "Inativo"}),
                especialidade=vis["especialidade"].str.title(),
            )[["nome", "registro", "especialidade", "situacao", "criado_em"]]
            exibir.columns = ["Nome completo", "CRM / registro", "Especialidade", "Situação", "Cadastrado em"]
            st.caption(f"{len(vis)} de {len(df_prof)} profissionais")
            tabela(exibir)
            baixar(exibir, "profissionais", key="dl_prof")

            secao("Editar ou excluir")
            rotulos = {int(r.id): f"{r.nome} — {r.registro} ({r.especialidade.title()})" for r in df_prof.itertuples()}
            pid = st.selectbox("Profissional", list(rotulos), format_func=rotulos.get, key="sel_prof")
            atual = df_prof[df_prof["id"] == pid].iloc[0]
            with st.form(f"form_edit_prof_{pid}"):
                e_nome = st.text_input("Nome completo", value=atual["nome"])
                e1, e2, e3 = st.columns([2, 2, 1])
                e_reg = e1.text_input("CRM / registro", value=atual["registro"])
                idx = ESPECIALIDADES.index(atual["especialidade"]) if atual["especialidade"] in ESPECIALIDADES else 0
                e_esp = e2.selectbox("Especialidade", ESPECIALIDADES, index=idx, format_func=str.title)
                e_ativo = e3.checkbox("Ativo", value=bool(atual["ativo"]))
                atualizar = st.form_submit_button("Salvar alterações", **FULL_FORM_BTN)
            if atualizar:
                ok, msg = atualizar_profissional(pid, e_nome, e_reg, e_esp, e_ativo)
                if ok:
                    avisar("success", msg)
                    st.rerun()
                else:
                    st.error(msg)

            with st.expander("Excluir este profissional"):
                st.caption("Prefira marcar como inativo para manter o histórico. A exclusão é definitiva.")
                confirma = st.checkbox("Confirmo a exclusão", key=f"conf_del_{pid}")
                if st.button("Excluir profissional", disabled=not confirma, key=f"del_{pid}"):
                    excluir_profissional(pid, atual["nome"])
                    avisar("success", "Profissional excluído.")
                    st.rerun()

elif menu == "Acessos":
    cabecalho("Segurança e acessos", "Usuários do sistema, registro de acessos e histórico de alterações.")
    if banco.usa_postgres():
        st.success(f"Banco de dados: {banco.descricao()}. Os cadastros ficam guardados mesmo quando o app reinicia.")
    else:
        st.warning(f"Banco de dados: {banco.descricao()}. No Streamlit Cloud, usuários, valores e profissionais "
                   "são apagados quando o app reinicia. Configure DATABASE_URL nos Secrets para guardar de vez.")
    aba_us, aba_ac, aba_log, aba_apr = st.tabs(["Usuários", "Acessos", "Histórico de alterações",
                                                "Aprendizado da leitura"])
    with aba_us:
        secao("Usuários cadastrados")
        df_us = motor_seguranca.listar_usuarios()
        tabela(df_us)

        c_novo, c_edit = st.columns(2)
        with c_novo:
            secao("Novo usuário")
            with st.form("form_novo_usuario", clear_on_submit=True):
                novo_nome = st.text_input("Nome de usuário", placeholder="ex.: maria.silva")
                novo_perfil = st.selectbox("Perfil", motor_seguranca.PERFIS)
                nova_senha = st.text_input("Senha inicial", type="password",
                                           help="Mínimo de 8 caracteres, com letras e números. "
                                                "A pessoa troca no primeiro acesso.")
                criar = st.form_submit_button("Criar usuário", **FULL_FORM_BTN)
            if criar:
                ok, msg = motor_seguranca.criar_usuario(novo_nome, nova_senha, novo_perfil)
                if ok:
                    registrar_log("Usuário criado", f"{novo_nome} | {novo_perfil}")
                    avisar("success", msg)
                    st.rerun()
                else:
                    st.error(msg)
        with c_edit:
            secao("Editar usuário")
            nomes = df_us["Usuário"].tolist()
            if nomes:
                alvo = st.selectbox("Usuário", nomes, key="sel_usuario")
                linha = df_us[df_us["Usuário"] == alvo].iloc[0]
                perfil = st.selectbox("Perfil", motor_seguranca.PERFIS,
                                      index=motor_seguranca.PERFIS.index(linha["Perfil"])
                                      if linha["Perfil"] in motor_seguranca.PERFIS else 0,
                                      key=f"perfil_{alvo}")
                ativo = st.checkbox("Ativo", value=linha["Situação"] == "Ativo", key=f"ativo_{alvo}")
                b1, b2 = st.columns(2)
                if b1.button("Salvar", type="primary", key="salvar_usuario", **FULL_BTN):
                    if alvo == st.session_state.usuario_atual and not ativo:
                        st.error("Você não pode desativar o seu próprio usuário.")
                    else:
                        ok, msg = motor_seguranca.atualizar_usuario(alvo, perfil, ativo,
                                                                    st.session_state.usuario_atual)
                        if ok:
                            registrar_log("Usuário alterado", f"{alvo} | {perfil} | ativo={int(ativo)}")
                            avisar("success", msg)
                            st.rerun()
                        else:
                            st.error(msg)
                if b2.button("Gerar senha temporária", key="reset_usuario", **FULL_BTN):
                    ok, msg, temp = motor_seguranca.redefinir_senha(alvo, st.session_state.usuario_atual)
                    if ok:
                        registrar_log("Senha redefinida", alvo)
                        st.success(f"{msg} Passe para {alvo} com segurança: **{temp}** "
                                   "(ela será pedida para trocar no próximo acesso).")
                    else:
                        st.error(msg)
    with aba_ac:
        if hasattr(motor_seguranca, "obter_relatorio_acessos"):
            try:
                tabela(motor_seguranca.obter_relatorio_acessos())
            except Exception as e:
                st.error(f"Não foi possível carregar o relatório: {e}")
        else:
            st.info("O módulo de segurança não possui 'obter_relatorio_acessos'.")
    with aba_log:
        df_log = consultar(
            'SELECT data_hora AS "Data/hora", usuario AS "Usuário", acao AS "Ação", detalhe AS "Detalhe" '
            "FROM log_alteracoes ORDER BY id DESC LIMIT 500"
        )
        if df_log.empty:
            st.info("Nenhuma alteração registrada ainda.")
        else:
            tabela(df_log)
            baixar(df_log, "historico_alteracoes", key="dl_log")
    with aba_apr:
        st.caption("O que o sistema aprendeu lendo os demonstrativos. Isso é usado automaticamente nos próximos arquivos.")
        apr = motor_conhecimento.resumo_aprendizado()
        a1, a2, a3 = st.columns(3)
        a1.metric("Padrões de leitura salvos", apr["perfis"],
                  help="Layouts de arquivo cujas colunas foram confirmadas na Casa das Máquinas.")
        a2.metric("Valores de referência", apr["referencias"],
                  help="Quanto cada operadora costuma pagar por código, por mês.")
        a3.metric("Códigos de glosa conhecidos", apr["codigos"],
                  help="Significado dos códigos de glosa (tabela TUSS 38) aprendido das justificativas.")
        perfis = motor_conhecimento.listar_perfis()
        if perfis.empty:
            st.info("Nenhum padrão de leitura salvo ainda. Ao conferir a leitura de um arquivo na Casa das Máquinas, "
                    "use **Salvar este padrão** para o sistema lembrar.")
        else:
            secao("Padrões de leitura salvos")
            tabela(perfis.drop(columns=["assinatura", "mapeamento"]))
            rot = {r["assinatura"]: f"{r['Operadora'] or 'sem operadora'} — salvo em {r['Salvo em']}"
                   for _, r in perfis.iterrows()}
            p1, p2 = st.columns([3, 1])
            alvo_p = p1.selectbox("Apagar padrão", list(rot), format_func=rot.get, key="perfil_alvo")
            if p2.button("Apagar", key="perfil_apagar", **FULL_BTN):
                motor_conhecimento.excluir_perfil(alvo_p)
                registrar_log("Padrão de leitura apagado", rot[alvo_p])
                avisar("success", "Padrão apagado. Os próximos arquivos com esse layout serão lidos automaticamente.")
                st.rerun()

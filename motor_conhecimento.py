"""
O que o sistema aprende para ler melhor os próximos arquivos, guardado no banco:

- Perfis de leitura: quando o usuário confirma ou corrige quais colunas do arquivo correspondem a
  cada campo, o sistema guarda esse mapeamento pelo "jeitão" do arquivo (conjunto de nomes de colunas).
  Na próxima vez que chegar um arquivo com o mesmo layout, usa o mapeamento salvo.
- Valores de referência: quanto cada operadora paga normalmente por código de procedimento (por mês),
  aprendido dos itens pagos por inteiro. Usado quando o demonstrativo não traz o valor apresentado e
  não há valor cadastrado na tabela de faturamento.
- Códigos de glosa: o significado de cada código (tabela TUSS 38), aprendido das justificativas que
  as operadoras escrevem ("1705 VALOR APRESENTADO A MAIOR"). Usado quando um arquivo traz só o código.
"""
import json

import pandas as pd

import banco
import motor_extracao as me

DB = "valores_clinica.db"


def _conectar():
    return banco.conectar(DB)


def init_conhecimento():
    with _conectar() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS perfis_leitura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assinatura TEXT UNIQUE NOT NULL,
                operadora TEXT,
                mapeamento TEXT,
                colunas TEXT,
                atualizado_em TEXT,
                usuario TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS referencias_valor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operadora TEXT NOT NULL,
                codigo TEXT NOT NULL,
                mes TEXT NOT NULL,
                valor REAL NOT NULL,
                atualizado_em TEXT,
                UNIQUE (operadora, codigo, mes))"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS codigos_glosa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                descricao TEXT,
                atualizado_em TEXT)"""
        )
        conn.commit()


def carregar():
    """Tudo o que já foi aprendido + a tabela de valores cadastrada, no formato do motor_extracao."""
    con = dict(perfis={}, referencias={}, codigos_glosa={}, tabela_valores=None)
    try:
        with _conectar() as conn:
            for assin, mapa in conn.execute("SELECT assinatura, mapeamento FROM perfis_leitura").fetchall():
                try:
                    con["perfis"][assin] = json.loads(mapa or "{}")
                except ValueError:
                    pass
            for op, cod, mes, v in conn.execute(
                    "SELECT operadora, codigo, mes, valor FROM referencias_valor").fetchall():
                con["referencias"][(op, cod, mes)] = float(v)
            for cod, desc in conn.execute("SELECT codigo, descricao FROM codigos_glosa").fetchall():
                con["codigos_glosa"][cod] = desc
            cols = banco.colunas(conn, "tabela_valores_faturamento")
            if cols:
                extra = "".join(f", {c}" for c in ("codigo_tuss", "vigencia_inicio", "vigencia_fim") if c in cols)
                con["tabela_valores"] = banco.ler_df(
                    conn, f"SELECT especialidade, plano, tempo_atendimento, valor_plano{extra} "
                          "FROM tabela_valores_faturamento")
    except banco.Error:
        pass
    return con


def aprender(df):
    """Guarda os valores de referência e códigos de glosa descobertos num arquivo lido."""
    refs = (df.attrs or {}).get("referencias_aprendidas") or {}
    codigos = (df.attrs or {}).get("codigos_glosa_aprendidos") or {}
    if not refs and not codigos:
        return 0, 0
    agora = banco.agora_txt()
    with _conectar() as conn:
        conn.executemany(
            "INSERT INTO referencias_valor (operadora, codigo, mes, valor, atualizado_em) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (operadora, codigo, mes) DO UPDATE SET valor = excluded.valor, "
            "atualizado_em = excluded.atualizado_em",
            [(op, cod, mes, float(v), agora) for (op, cod, mes), v in refs.items()],
        )
        conn.executemany(
            "INSERT INTO codigos_glosa (codigo, descricao, atualizado_em) VALUES (?, ?, ?) "
            "ON CONFLICT (codigo) DO NOTHING",
            [(c, d, agora) for c, d in codigos.items()],
        )
        conn.commit()
    return len(refs), len(codigos)


def salvar_perfil(assinatura, mapa, colunas, operadora, usuario):
    if not assinatura:
        return False
    with _conectar() as conn:
        conn.execute(
            "INSERT INTO perfis_leitura (assinatura, operadora, mapeamento, colunas, atualizado_em, usuario) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (assinatura) DO UPDATE SET operadora = excluded.operadora, "
            "mapeamento = excluded.mapeamento, colunas = excluded.colunas, "
            "atualizado_em = excluded.atualizado_em, usuario = excluded.usuario",
            (assinatura, operadora, json.dumps(mapa, ensure_ascii=False),
             json.dumps(list(colunas), ensure_ascii=False), banco.agora_txt(), usuario),
        )
        conn.commit()
    return True


def excluir_perfil(assinatura):
    with _conectar() as conn:
        conn.execute("DELETE FROM perfis_leitura WHERE assinatura = ?", (assinatura,))
        conn.commit()


def listar_perfis():
    with _conectar() as conn:
        df = banco.ler_df(conn, 'SELECT assinatura, operadora AS "Operadora", mapeamento, '
                                'atualizado_em AS "Salvo em", usuario AS "Usuário" FROM perfis_leitura '
                                'ORDER BY atualizado_em DESC')
    if not df.empty:
        df["Campos"] = df["mapeamento"].map(lambda m: len(json.loads(m or "{}")))
    return df


def resumo_aprendizado():
    with _conectar() as conn:
        n = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return dict(perfis=n("perfis_leitura"), referencias=n("referencias_valor"), codigos=n("codigos_glosa"))


def extrair(arquivo, plano=me.PLANO_AUTOMATICO, somente_glosas=True, data_pagamento_padrao=None,
            aprender_com_arquivo=True):
    """Lê um demonstrativo usando tudo o que o sistema já aprendeu e aprende com ele."""
    df, erro = me.extrair_glosas_de_arquivo(arquivo, plano=plano, somente_glosas=somente_glosas,
                                            data_pagamento_padrao=data_pagamento_padrao,
                                            conhecimento=carregar())
    if aprender_com_arquivo and df is not None and df.attrs.get("referencias_aprendidas") is not None:
        try:
            aprender(df)
        except banco.Error:
            pass
    return df, erro


CAMPOS_EDITAVEIS = [c for c in me.CAMPOS if c not in ("Valor unitário", "Status da glosa")]


def mapa_para_tabela(leitura):
    """Mapeamento de uma tabela lida, no formato campo -> coluna (para a tela de conferência)."""
    mapa = leitura.get("mapa") or {}
    return pd.DataFrame([{"Campo do sistema": c, "Coluna do arquivo": mapa.get(c, "")} for c in CAMPOS_EDITAVEIS])


# --------------------------------------------------------------------------
# Sugestão da tabela de valores a partir dos demonstrativos (com reajustes)
# --------------------------------------------------------------------------
def sugerir_valores(itens, minimo_mes=5):
    """A partir dos itens do histórico de UMA operadora, sugere o valor de cada código de procedimento e
    os períodos de vigência (reajustes), pela data do atendimento.

    Usa só itens pagos por inteiro (sem glosa, sem justificativa, quantidade toda liberada). Para cada
    código e mês do atendimento, pega o valor unitário mais frequente; meses seguidos com o mesmo valor
    formam um período. Retorna DataFrame com: Código, Procedimento, Especialidade, Valor, Início, Fim,
    Atendimentos."""
    cols = ["Código", "Procedimento", "Especialidade", "Valor", "Início", "Fim", "Atendimentos", "Conferir"]
    if itens is None or itens.empty:
        return pd.DataFrame(columns=cols)
    d = itens.copy()
    num = lambda c: pd.to_numeric(d.get(c), errors="coerce")
    qs, ql, pago, glosa = num("Quantidade"), num("Quantidade liberada"), num("Valor pago"), num("Valor da glosa")
    texto = lambda c: d.get(c, pd.Series("", index=d.index)).fillna("").astype(str).str.strip()
    cheio = (texto("Motivo da glosa").eq("") & texto("Código da glosa").eq("") & (glosa.fillna(0) <= 0.005)
             & (ql.isna() | qs.isna() | (ql >= qs)) & (pago > 0) & texto("Código").ne("") & texto("Código").ne("-"))
    d = d[cheio].copy()
    if d.empty:
        return pd.DataFrame(columns=cols)
    unid = qs[d.index].where(qs[d.index] > 0, 1.0).fillna(1.0)
    d["_unit"] = (pago[d.index] / unid).round(2)
    iso = d["_iso"] if "_iso" in d.columns else d["Data do evento"].map(me.data_iso)
    d["_mes"] = iso.fillna("").astype(str).str[:7]
    d = d[d["_mes"].str.len() == 7]

    linhas = []
    for cod, g in d.groupby("Código"):
        proc = g["Procedimento"].fillna("").astype(str).value_counts().index[0]
        meses = []
        for mes, gm in g.groupby("_mes", sort=True):
            cont = gm["_unit"].value_counts()
            if cont.iloc[0] < minimo_mes or cont.iloc[0] < 0.5 * len(gm):
                continue  # mês com poucos atendimentos ou valores misturados: não decide nada
            meses.append((mes, float(cont.index[0]), len(gm)))
        if not meses:
            continue
        # junta meses seguidos com o mesmo valor (diferença de 1 centavo conta como igual). Um mês que
        # volta a um valor já substituído é faturamento atrasado, não reajuste: não abre período novo.
        periodos, superados = [], []
        igual = lambda a, b: abs(a - b) <= 0.011
        for mes, val, n in meses:
            if periodos and igual(periodos[-1]["valor"], val):
                periodos[-1]["ate"] = mes
                periodos[-1]["n"] += n
            elif any(igual(v, val) for v in superados):
                continue
            else:
                if periodos:
                    superados.append(periodos[-1]["valor"])
                periodos.append(dict(valor=val, de=mes, ate=mes, n=n))
        for i, p in enumerate(periodos):
            alertas = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(periodos):
                    var = periodos[j]["valor"] / p["valor"] - 1 if p["valor"] else 0
                    if abs(var) > 0.15:
                        alertas.append(f"variação de {var * 100:+.0f}% em relação ao período "
                                       f"{'anterior' if j < i else 'seguinte'}".replace(".", ","))
            if p["n"] < 10:
                alertas.append("poucos atendimentos")
            if alertas:
                alertas.insert(0, "Pode ser pagamento em partes ou valor incompleto")
            p["conferir"] = "; ".join(alertas)
            inicio = None if i == 0 else pd.Timestamp(p["de"] + "-01").date()
            fim = (pd.Timestamp(periodos[i + 1]["de"] + "-01") - pd.Timedelta(days=1)).date() \
                if i + 1 < len(periodos) else None
            linhas.append({"Código": str(cod), "Procedimento": proc,
                           "Especialidade": me.especialidade_do_procedimento(proc) or "",
                           "Valor": round(p["valor"], 2), "Início": inicio, "Fim": fim, "Atendimentos": int(p["n"]),
                           "Conferir": p["conferir"]})
    out = pd.DataFrame(linhas, columns=cols)
    return out.sort_values(["Atendimentos"], ascending=False, kind="stable").sort_values(
        ["Código", "Início"], na_position="first", kind="stable").reset_index(drop=True)

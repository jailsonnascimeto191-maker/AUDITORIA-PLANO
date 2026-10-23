"""
Histórico dos demonstrativos processados na Casa das Máquinas.

Cada arquivo processado é guardado no banco (todas as linhas, com e sem glosa). Isso alimenta o
Painel (gráficos por mês, operadora e motivo) e a pesquisa da Lupa de Glosas.
Se o mesmo arquivo (mesmo conteúdo) for processado de novo, a versão anterior é substituída.
Atendimentos que já estão no histórico vindos de OUTRO arquivo (mesma guia, código, data, paciente e
data de crédito) não são gravados de novo, para não contar em dobro.
"""
import hashlib
import re

import pandas as pd

import banco
import motor_extracao as me

DB = "valores_clinica.db"  # mesmo banco das tabelas de valores (no PostgreSQL, tudo fica junto)

# coluna do DataFrame do motor_extracao -> coluna no banco
COLUNAS = {
    "Data do evento": "data_evento",
    "Protocolo": "protocolo",
    "Doc Original": "guia",
    "Nome do paciente": "paciente",
    "Código": "codigo",
    "Procedimento": "procedimento",
    "Valor informado": "valor_informado",
    "Valor pago": "valor_pago",
    "Valor da glosa": "valor_glosa",
    "Motivo da glosa": "motivo",
    "Quantidade": "quantidade",
    "Valor unitário": "valor_unitario",
    "Lote": "lote",
    "Status da glosa": "status",
    "Data de pagamento": "data_pagamento",
    "Quantidade liberada": "quantidade_liberada",
    "Código da glosa": "codigo_glosa",
    "Valor de referência": "valor_referencia",
    "Fonte do valor informado": "fonte_valor",
    "Diferença sem justificativa": "diferenca",
    "Alertas": "alertas",
    "Rede": "rede",
}
NUMERICAS = {"valor_informado", "valor_pago", "valor_glosa", "quantidade", "valor_unitario",
             "quantidade_liberada", "valor_referencia", "diferenca"}


def _conectar():
    return banco.conectar(DB)


def init_historico():
    with _conectar() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS demonstrativos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora TEXT,
                usuario TEXT,
                arquivo TEXT,
                hash TEXT,
                operadora TEXT,
                linhas INTEGER,
                valor_informado REAL,
                valor_pago REAL,
                valor_glosa REAL)"""
        )
        cols = ",\n".join(f"{c} {'REAL' if c in NUMERICAS else 'TEXT'}" for c in COLUNAS.values())
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS demonstrativo_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demonstrativo_id INTEGER NOT NULL,
                operadora TEXT,
                data_evento_iso TEXT,
                {cols})"""
        )
        # bancos criados por versões anteriores: acrescenta as colunas novas
        existentes = banco.colunas(conn, "demonstrativo_itens")
        for c in list(COLUNAS.values()) + ["chave"]:
            if c not in existentes:
                conn.execute(f"ALTER TABLE demonstrativo_itens ADD COLUMN {c} {'REAL' if c in NUMERICAS else 'TEXT'}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_itens_demo ON demonstrativo_itens (demonstrativo_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_itens_chave ON demonstrativo_itens (chave)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_itens_data ON demonstrativo_itens (data_evento_iso)")
        conn.commit()


def hash_arquivo(dados):
    return hashlib.sha256(dados).hexdigest()


def _iso(data_br):
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", str(data_br or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def chave_atendimento(reg):
    """Identifica um pagamento de um atendimento (para não gravar o mesmo duas vezes)."""
    partes = [str(reg.get(c) or "").strip().upper() for c in
              ("Doc Original", "Código", "Data do evento", "Nome do paciente", "Data de pagamento")]
    if not partes[0] or partes[0] == "-" or not partes[1] or partes[1] == "-":
        return None
    return hashlib.sha1("|".join(partes).encode()).hexdigest()[:20]


def salvar_demonstrativo(df, arquivo, hash_, usuario, operadora):
    """Guarda o demonstrativo (todas as linhas). Retorna (id, substituiu_anterior, ignorados), onde
    'ignorados' é o número de atendimentos que já estavam no histórico por outro arquivo."""
    if df is None or df.empty:
        return None, False, 0
    with _conectar() as conn:
        antigos = [r[0] for r in conn.execute("SELECT id FROM demonstrativos WHERE hash = ?", (hash_,)).fetchall()]
        for i in antigos:
            conn.execute("DELETE FROM demonstrativo_itens WHERE demonstrativo_id = ?", (i,))
            conn.execute("DELETE FROM demonstrativos WHERE id = ?", (i,))
        registros = [dict(zip(df.columns, r)) for r in df.itertuples(index=False)]
        chaves = [chave_atendimento(r) for r in registros]
        existentes = set()
        lista = [c for c in set(chaves) if c]
        for i in range(0, len(lista), 500):
            parte = lista[i:i + 500]
            existentes.update(r[0] for r in conn.execute(
                f"SELECT chave FROM demonstrativo_itens WHERE chave IN ({', '.join(['?'] * len(parte))})",
                parte).fetchall())
        novos = [(r, c) for r, c in zip(registros, chaves) if not c or c not in existentes]
        ignorados = len(registros) - len(novos)
        num = lambda col: round(float(pd.to_numeric(pd.Series([r.get(col) for r, _ in novos]), errors="coerce").sum()), 2)
        did = banco.inserir(
            conn,
            "INSERT INTO demonstrativos (data_hora, usuario, arquivo, hash, operadora, linhas, "
            "valor_informado, valor_pago, valor_glosa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (banco.agora_txt(), usuario, arquivo, hash_, operadora, len(novos),
             num("Valor informado"), num("Valor pago"), num("Valor da glosa")),
        )
        nomes = list(COLUNAS.values())
        sql = (f"INSERT INTO demonstrativo_itens (demonstrativo_id, operadora, data_evento_iso, chave, "
               f"{', '.join(nomes)}) VALUES ({', '.join(['?'] * (len(nomes) + 4))})")
        linhas = []
        for reg, chave in novos:
            valores = []
            for col_df, col_db in COLUNAS.items():
                v = reg.get(col_df)
                if col_db in NUMERICAS:
                    try:
                        v = float(v)
                        v = None if pd.isna(v) else v
                    except (TypeError, ValueError):
                        v = None
                else:
                    v = "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)
                valores.append(v)
            linhas.append((did, operadora, _iso(reg.get("Data do evento")), chave, *valores))
        conn.executemany(sql, linhas)
        conn.commit()
    return did, bool(antigos), ignorados


def listar_demonstrativos():
    with _conectar() as conn:
        return banco.ler_df(
            conn,
            'SELECT id, data_hora AS "Processado em", usuario AS "Usuário", arquivo AS "Arquivo", '
            'operadora AS "Operadora", linhas AS "Linhas", valor_informado AS "Valor apresentado", '
            'valor_glosa AS "Valor glosado" FROM demonstrativos ORDER BY id DESC',
        )


def excluir_demonstrativo(did):
    with _conectar() as conn:
        conn.execute("DELETE FROM demonstrativo_itens WHERE demonstrativo_id = ?", (int(did),))
        conn.execute("DELETE FROM demonstrativos WHERE id = ?", (int(did),))
        conn.commit()


def operadoras():
    with _conectar() as conn:
        rows = conn.execute("SELECT DISTINCT operadora FROM demonstrativos ORDER BY operadora").fetchall()
    return [r[0] for r in rows if r[0]]


def carregar_itens(desde_iso=None, operadoras_sel=None, somente_glosas=False):
    """Itens do histórico como DataFrame, com as mesmas colunas do motor_extracao
    (+ Operadora, Arquivo e Processado em)."""
    filtros, params = [], []
    if desde_iso:
        filtros.append("i.data_evento_iso >= ?")
        params.append(desde_iso)
    if operadoras_sel:
        filtros.append(f"i.operadora IN ({', '.join(['?'] * len(operadoras_sel))})")
        params += list(operadoras_sel)
    if somente_glosas:
        filtros.append("i.valor_glosa > 0.005")
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    sel = ", ".join(f'i.{db} AS "{df}"' for df, db in COLUNAS.items())
    with _conectar() as conn:
        df = banco.ler_df(
            conn,
            f'SELECT {sel}, i.operadora AS "Operadora", i.data_evento_iso AS "_iso", '
            f'd.arquivo AS "Arquivo", d.data_hora AS "Processado em" '
            f"FROM demonstrativo_itens i JOIN demonstrativos d ON d.id = i.demonstrativo_id {where} "
            f"ORDER BY i.data_evento_iso DESC, i.id",
            params,
        )
    for c in ("Valor informado", "Valor pago", "Valor da glosa", "Diferença sem justificativa"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for c in ("Quantidade", "Quantidade liberada", "Valor unitário", "Valor de referência"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def resumo_painel(itens):
    """Agregações para o Painel. 'itens' vem de carregar_itens()."""
    vazio = dict(apresentado=0.0, glosado=0.0, itens_glosados=0, pct=0.0, diferencas=0.0, itens_diferenca=0,
                 por_mes=pd.DataFrame(columns=["Mês", "Valor glosado"]),
                 por_operadora=pd.DataFrame(columns=["Operadora", "Valor glosado"]),
                 motivos=pd.DataFrame(columns=["Motivo da glosa", "Itens", "Valor glosado", "% do glosado"]))
    if itens is None or itens.empty:
        return vazio
    g = itens[itens["Valor da glosa"] > 0.005].copy()
    apresentado = float(itens["Valor informado"].sum())
    glosado = float(g["Valor da glosa"].sum())
    dif = pd.to_numeric(itens.get("Diferença sem justificativa", pd.Series(dtype=float)), errors="coerce").fillna(0)
    res = dict(apresentado=apresentado, glosado=glosado, itens_glosados=int(len(g)),
               pct=(glosado / apresentado) if apresentado else 0.0,
               diferencas=float(dif.sum()), itens_diferenca=int((dif > 0.005).sum()))
    if g.empty:
        return {**vazio, **res}
    g["Mês"] = g["_iso"].fillna("").str[:7].replace("", "Sem data")
    pm = g.groupby("Mês", sort=True)["Valor da glosa"].sum().reset_index()
    pm = pm.rename(columns={"Valor da glosa": "Valor glosado"})
    pm["Mês"] = pm["Mês"].map(lambda m: f"{m[5:7]}/{m[:4]}" if m != "Sem data" else m)
    po = (g.groupby("Operadora")["Valor da glosa"].sum().reset_index()
          .rename(columns={"Valor da glosa": "Valor glosado"}).sort_values("Valor glosado", ascending=False))
    g["Motivo da glosa"] = me.agrupar_motivos(g["Motivo da glosa"]).replace("", "Sem motivo informado")
    mo = (g.groupby("Motivo da glosa").agg(Itens=("Valor da glosa", "count"),
                                            **{"Valor glosado": ("Valor da glosa", "sum")})
          .reset_index().sort_values("Valor glosado", ascending=False).head(10))
    mo["% do glosado"] = (mo["Valor glosado"] / glosado) if glosado else 0.0
    return {**res, "por_mes": pm, "por_operadora": po, "motivos": mo}

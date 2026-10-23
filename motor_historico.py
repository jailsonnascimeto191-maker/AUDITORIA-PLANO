"""
Histórico dos demonstrativos processados na Casa das Máquinas.

Cada arquivo processado é guardado no banco (todas as linhas, com e sem glosa). Isso alimenta o
Painel (gráficos por mês, operadora e motivo) e a pesquisa da Lupa de Glosas.
Se o mesmo arquivo (mesmo conteúdo) for processado de novo, a versão anterior é substituída.
Atendimentos que já estão no histórico vindos de OUTRO arquivo (mesma guia, código, data, paciente e
data de crédito) não são gravados de novo, para não contar em dobro.

Pagamento em duas partes entre arquivos diferentes: ao guardar um demonstrativo, o sistema procura no
histórico da mesma operadora a outra parte do pagamento (ver motor_extracao.encontrar_pares) e LIGA as duas
linhas, guardando os valores originais. Remover ou substituir um dos arquivos desfaz o vínculo.
"""
import hashlib
import json
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
    "Complemento recebido": "complemento",
    "Vínculo": "vinculo",
}
NUMERICAS = {"valor_informado", "valor_pago", "valor_glosa", "quantidade", "valor_unitario",
             "quantidade_liberada", "valor_referencia", "diferenca", "complemento"}
# campos alterados por um vínculo entre arquivos (guardados em orig_json para poder desfazer)
CAMPOS_VINCULO = ["Valor informado", "Valor da glosa", "Diferença sem justificativa", "Status da glosa",
                  "Motivo da glosa", "Alertas", "Complemento recebido", "Vínculo"]


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
        for c in list(COLUNAS.values()) + ["chave", "orig_json"]:
            if c not in existentes:
                conn.execute(f"ALTER TABLE demonstrativo_itens ADD COLUMN {c} {'REAL' if c in NUMERICAS else 'TEXT'}")
        if "vinculo_item" not in existentes:
            conn.execute("ALTER TABLE demonstrativo_itens ADD COLUMN vinculo_item INTEGER")
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
        religar = set()
        for i in antigos:
            op_antiga = _desvincular(conn, i)
            if op_antiga:
                religar.add(op_antiga)
            conn.execute("DELETE FROM demonstrativo_itens WHERE demonstrativo_id = ?", (i,))
            conn.execute("DELETE FROM demonstrativos WHERE id = ?", (i,))
        for op_antiga in religar:
            _vincular(conn, op_antiga)
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
        operadora = _desvincular(conn, int(did))
        conn.execute("DELETE FROM demonstrativo_itens WHERE demonstrativo_id = ?", (int(did),))
        conn.execute("DELETE FROM demonstrativos WHERE id = ?", (int(did),))
        if operadora:
            _vincular(conn, operadora)  # refaz os vínculos entre os arquivos que ficaram
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
    for c in ("Valor informado", "Valor pago", "Valor da glosa", "Diferença sem justificativa",
              "Complemento recebido"):
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


# --------------------------------------------------------------------------
# Pagamento em duas partes entre arquivos diferentes
# --------------------------------------------------------------------------
def _py(v):
    if v is None:
        return None
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    try:
        if not isinstance(v, str) and pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _itens_operadora(conn, operadora):
    sel = ", ".join(f'i.{db} AS "{df}"' for df, db in COLUNAS.items())
    df = banco.ler_df(
        conn,
        f'SELECT i.id AS "_id", i.demonstrativo_id AS "_demo", i.vinculo_item AS "_vinc", i.orig_json AS "_orig", '
        f'{sel}, i.operadora AS "Operadora", d.arquivo AS "Arquivo" '
        f"FROM demonstrativo_itens i JOIN demonstrativos d ON d.id = i.demonstrativo_id WHERE i.operadora = ?",
        (operadora,),
    )
    for c in ("Valor informado", "Valor pago", "Valor da glosa", "Diferença sem justificativa", "Complemento recebido"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Vínculo"] = df["Vínculo"].fillna("")
    df.index = df["_id"].astype(int)
    return df


def _atualizar_totais(conn, demos):
    for did in {int(d) for d in demos if d is not None}:
        r = conn.execute("SELECT COUNT(*), SUM(valor_informado), SUM(valor_pago), SUM(valor_glosa) "
                         "FROM demonstrativo_itens WHERE demonstrativo_id = ?", (did,)).fetchone()
        conn.execute("UPDATE demonstrativos SET linhas=?, valor_informado=?, valor_pago=?, valor_glosa=? WHERE id=?",
                     (r[0], round(r[1] or 0, 2), round(r[2] or 0, 2), round(r[3] or 0, 2), did))


def _gravar_campos(conn, df, item_id, extra_sql="", extra_params=()):
    sets = ", ".join(f"{COLUNAS[c]} = ?" for c in CAMPOS_VINCULO)
    conn.execute(f"UPDATE demonstrativo_itens SET {sets}{extra_sql} WHERE id = ?",
                 tuple(_py(df.at[item_id, c]) for c in CAMPOS_VINCULO) + tuple(extra_params) + (int(item_id),))


def vincular_historico(operadora, demonstrativo_id=None):
    """Liga, entre arquivos diferentes da mesma operadora, as aparições da mesma guia (recurso, restante,
    pagamento repetido, glosa mantida) e os complementos pagos em outra guia. Com demonstrativo_id, só os
    vínculos que envolvem esse arquivo; sem ele, todo o histórico da operadora.
    Retorna (vínculos criados, casos para conferir)."""
    if not operadora:
        return 0, 0
    with _conectar() as conn:
        n = _vincular(conn, operadora, demonstrativo_id)
        conn.commit()
    return n


def _vincular(conn, operadora, demonstrativo_id=None):
    df = _itens_operadora(conn, operadora)
    if df.empty or df["_demo"].nunique() < 2:
        return 0, 0
    exigir = {int(demonstrativo_id)} if demonstrativo_id is not None else None
    if True:
        afetados = set()
        origem = lambda k: f"arquivo {df.at[k, 'Arquivo']}"
        # 1) a mesma guia em outro arquivo (recurso, restante, pagamento repetido, glosa mantida)
        mesma, conferir = me.encontrar_mesma_guia(df, df["_demo"], exigir_em=exigir)
        for a, seguintes, tipo, ref in mesma:
            orig = me.aplicar_vinculo_guia(df, a, seguintes, tipo, origem, ref)
            for item in [a] + list(seguintes):
                parceiro = seguintes[-1] if item == a else a
                original = {c: _py(v) for c, v in orig[item].items()}
                _gravar_campos(conn, df, item, ", vinculo_item = ?, orig_json = ?",
                               (int(parceiro), json.dumps(original, ensure_ascii=False)))
                afetados.add(df.at[item, "_demo"])
        # 2) complemento pago em outra guia (pagamento em duas partes)
        pares, ambiguos = me.encontrar_pares(df, grupo=df["_demo"], exigir_em=exigir)
        ambiguos = set(ambiguos) | set(conferir)
        for a, b in pares:
            orig = me.aplicar_vinculo(df, a, b, origem_a=f"arquivo {df.at[a, 'Arquivo']}",
                                      origem_b=f"arquivo {df.at[b, 'Arquivo']}")
            for item, parceiro in ((a, b), (b, a)):
                original = {c: _py(v) for c, v in orig[item].items()}
                _gravar_campos(conn, df, item, ", vinculo_item = ?, orig_json = ?",
                               (int(parceiro), json.dumps(original, ensure_ascii=False)))
                afetados.add(df.at[item, "_demo"])
        for k in ambiguos:
            if me.ALERTA_POSSIVEL_PARTES not in str(df.at[k, "Alertas"] or ""):
                novo = "; ".join([x for x in [str(df.at[k, "Alertas"] or "")] if x] + [me.ALERTA_POSSIVEL_PARTES])
                conn.execute("UPDATE demonstrativo_itens SET alertas = ? WHERE id = ?", (novo, int(k)))
        _atualizar_totais(conn, afetados)
    return len(pares) + len(mesma), len(ambiguos)


def _desvincular(conn, demonstrativo_id):
    """Antes de remover um demonstrativo: restaura (pelos valores originais guardados) todos os itens de outros
    arquivos que estavam ligados a ele, direta ou indiretamente, e limpa os avisos de conferência. Depois que o
    arquivo sai, _religar() refaz os vínculos entre os arquivos que ficaram."""
    did = int(demonstrativo_id)
    op = conn.execute("SELECT operadora FROM demonstrativos WHERE id = ?", (did,)).fetchone()
    if not op:
        return 0
    rows = conn.execute("SELECT id, demonstrativo_id, vinculo_item, orig_json FROM demonstrativo_itens "
                        "WHERE operadora = ? AND vinculo_item IS NOT NULL", (op[0],)).fetchall()
    info = {int(r[0]): (int(r[1]), r[2], r[3]) for r in rows}
    # grupos ligados (vínculo em qualquer direção)
    viz = {}
    for iid, (_, parc, _) in info.items():
        if parc is not None:
            viz.setdefault(iid, set()).add(int(parc))
            viz.setdefault(int(parc), set()).add(iid)
    inicio = [i for i, (d, _, _) in info.items() if d == did]
    marcados, pilha = set(), list(inicio)
    while pilha:
        k = pilha.pop()
        if k in marcados:
            continue
        marcados.add(k)
        pilha.extend(viz.get(k, ()))
    afetados = set()
    for iid in marcados:
        if iid not in info or info[iid][0] == did:
            continue
        try:
            orig = json.loads(info[iid][2] or "{}")
        except ValueError:
            orig = {}
        if orig:
            sets = ", ".join(f"{COLUNAS[c]} = ?" for c in CAMPOS_VINCULO if c in orig)
            conn.execute(f"UPDATE demonstrativo_itens SET {sets}, vinculo_item = NULL, orig_json = NULL WHERE id = ?",
                         tuple(orig[c] for c in CAMPOS_VINCULO if c in orig) + (iid,))
        else:
            conn.execute("UPDATE demonstrativo_itens SET vinculo_item = NULL, orig_json = NULL WHERE id = ?", (iid,))
        afetados.add(info[iid][0])
    for iid, alertas in conn.execute(
            "SELECT id, alertas FROM demonstrativo_itens WHERE operadora = ? AND alertas LIKE ?",
            (op[0], f"%{me.ALERTA_POSSIVEL_PARTES}%")).fetchall():
        novo = "; ".join(x for x in str(alertas).split("; ") if x and x != me.ALERTA_POSSIVEL_PARTES)
        conn.execute("UPDATE demonstrativo_itens SET alertas = ? WHERE id = ?", (novo, int(iid)))
    _atualizar_totais(conn, afetados)
    return op[0]


def pagamentos_em_partes(operadoras_sel=None):
    """Três listas para conferência: vínculos feitos, pagos a menor aguardando complemento/cobrança e
    possíveis vínculos com mais de um candidato."""
    itens = carregar_itens(operadoras_sel=operadoras_sel)
    cols = ["Operadora", "Data do evento", "Nome do paciente", "Código", "Procedimento", "Doc Original",
            "Valor informado", "Valor pago", "Complemento recebido", "Data de pagamento", "Vínculo", "Arquivo"]
    if itens.empty:
        vazio = pd.DataFrame(columns=cols)
        return vazio, vazio, vazio
    itens["Complemento recebido"] = pd.to_numeric(itens.get("Complemento recebido"), errors="coerce").fillna(0.0)
    cols = [c for c in cols if c in itens.columns]
    vinculados = itens[itens["Status da glosa"] == me.STATUS_PAGO_EM_PARTES][cols]
    pend = itens[itens["Status da glosa"] == "Pago a menor sem justificativa"].copy()
    pend["Falta receber"] = (pend["Diferença sem justificativa"]).round(2)
    pendentes = pend[[c for c in cols if c not in ("Complemento recebido", "Vínculo")] + ["Falta receber"]]
    possiveis = itens[itens["Alertas"].fillna("").str.contains(me.ALERTA_POSSIVEL_PARTES, regex=False)][cols]
    return vinculados.reset_index(drop=True), pendentes.reset_index(drop=True), possiveis.reset_index(drop=True)


def possiveis_duplicidades(operadoras_sel=None):
    """Atendimentos que o plano parece ter pago mais de uma vez (mesma guia em créditos diferentes)."""
    itens = carregar_itens(operadoras_sel=operadoras_sel)
    if itens.empty:
        return itens
    d = itens[itens["Status da glosa"] == me.STATUS_DUPLICIDADE].copy()
    d["Pago a mais"] = (d["Valor pago"] - d["Valor informado"]).clip(lower=0).round(2)
    # quando as duas aparições estão em arquivos diferentes, a segunda tem informado zero: pago a mais = pago
    cols = ["Operadora", "Data do evento", "Nome do paciente", "Código", "Procedimento", "Doc Original", "Protocolo",
            "Valor informado", "Valor pago", "Pago a mais", "Data de pagamento", "Vínculo", "Arquivo"]
    return d[[c for c in cols if c in d.columns]].reset_index(drop=True)

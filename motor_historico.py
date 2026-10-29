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
import logging
import hashlib
import json
import re

import pandas as pd

import banco
import motor_extracao as me

log = logging.getLogger("azus")

DB = "valores_clinica.db"  # mesmo banco das tabelas de valores (no PostgreSQL, tudo fica junto)
# mude sempre que init_historico() passar a criar uma coluna/índice novo: o app roda a migração de novo
VERSAO_ESQUEMA = "2026-10-28 duplicado_de"

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
    "Glosa original": "glosa_original",
    "Data da glosa": "data_glosa",
    "Situação do recurso": "recurso_situacao",
    "Protocolo do recurso": "recurso_protocolo",
    "Data do recurso": "recurso_data",
    "Recebido no recurso": "recurso_recebido",
    "Vínculo": "vinculo",
}
NUMERICAS = {"valor_informado", "valor_pago", "valor_glosa", "quantidade", "valor_unitario",
             "quantidade_liberada", "valor_referencia", "diferenca", "complemento", "glosa_original",
             "recurso_recebido"}
# campos alterados por um vínculo entre arquivos (guardados em orig_json para poder desfazer)
CAMPOS_VINCULO = me.CAMPOS_LIGACAO


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
        if "duplicado_de" not in existentes:
            # atendimento que já estava no histórico por outro arquivo: fica guardado, mas não conta, e assume
            # o lugar do outro se aquele arquivo for removido
            conn.execute("ALTER TABLE demonstrativo_itens ADD COLUMN duplicado_de INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_itens_demo ON demonstrativo_itens (demonstrativo_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_itens_chave ON demonstrativo_itens (chave)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_itens_data ON demonstrativo_itens (data_evento_iso)")
        conn.commit()


def hash_arquivo(dados):
    return hashlib.sha256(dados).hexdigest()


def _iso(data_br):
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", str(data_br or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def chave_atendimento(reg, ocorrencia=0):
    """Identifica um pagamento de um atendimento, para não contar o mesmo duas vezes quando ele aparece em
    mais de um arquivo. Sem número de guia, usa paciente, procedimento, datas, valor pago e protocolo.
    'ocorrencia' separa linhas iguais dentro do mesmo arquivo (ex.: duas sessões no mesmo dia, sem guia)."""
    txt = lambda c: str(reg.get(c) or "").strip().upper()
    guia, codigo = txt("Doc Original"), txt("Código")
    if guia and guia != "-" and codigo and codigo != "-":
        partes = [guia, codigo, txt("Data do evento"), txt("Nome do paciente"), txt("Data de pagamento")]
    else:
        paciente, data = txt("Nome do paciente"), txt("Data do evento")
        if not paciente or paciente in ("-", "NÃO IDENTIFICADO") or not data or data == "-":
            return None
        try:
            pago = f"{float(reg.get('Valor pago')):.2f}"
        except (TypeError, ValueError):
            pago = ""
        partes = ["SEM GUIA", codigo, data, paciente, txt("Data de pagamento"), pago, txt("Protocolo"),
                  txt("Procedimento")]
    base = "|".join(partes) + (f"#{ocorrencia}" if ocorrencia else "")
    return hashlib.sha1(base.encode()).hexdigest()[:20]


def salvar_demonstrativo(df, arquivo, hash_, usuario, operadora):
    """Guarda o demonstrativo (todas as linhas) e refaz as ligações da operadora.
    Depois de salvar, chame vincular_historico(operadora) para refazer as ligações.
    Retorna (id, substituiu_anterior, repetidos). 'repetidos' são atendimentos que já estavam no histórico por
    outro arquivo: ficam guardados sem contar de novo. Se TODOS já estavam, nada é gravado e o id é None."""
    if df is None or df.empty:
        return None, False, 0
    with _conectar() as conn:
        antigos = [r[0] for r in conn.execute("SELECT id FROM demonstrativos WHERE hash = ?", (hash_,)).fetchall()]
        ops = {r[0] for r in conn.execute(
            f"SELECT operadora FROM demonstrativos WHERE id IN ({', '.join(['?'] * len(antigos))})",
            antigos).fetchall()} if antigos else set()
        for i in antigos:
            _remover(conn, i)
        registros = [dict(zip(df.columns, r)) for r in df.itertuples(index=False)]
        chaves = _chaves(df)
        existentes = {}
        lista = [c for c in set(chaves) if c]
        for i in range(0, len(lista), 500):
            parte = lista[i:i + 500]
            for chave, iid in conn.execute(
                    f"SELECT chave, id FROM demonstrativo_itens WHERE duplicado_de IS NULL AND "
                    f"chave IN ({', '.join(['?'] * len(parte))})", parte).fetchall():
                existentes.setdefault(chave, iid)
        repetidos = sum(1 for c in chaves if c and c in existentes)
        # a operadora deste arquivo é religada por vincular_historico(), chamado logo depois de salvar
        if repetidos == len(registros):  # o arquivo inteiro já está no histórico (ex.: cópia salva de novo)
            for op in ops - {operadora}:
                _religar(conn, op)
            conn.commit()
            return None, bool(antigos), repetidos
        did = banco.inserir(
            conn,
            "INSERT INTO demonstrativos (data_hora, usuario, arquivo, hash, operadora, linhas, "
            "valor_informado, valor_pago, valor_glosa) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0)",
            (banco.agora_txt(), usuario, arquivo, hash_, operadora),
        )
        nomes = list(COLUNAS.values())
        sql = (f"INSERT INTO demonstrativo_itens (demonstrativo_id, operadora, data_evento_iso, chave, duplicado_de, "
               f"{', '.join(nomes)}) VALUES ({', '.join(['?'] * (len(nomes) + 5))})")
        linhas = []
        for reg, chave in zip(registros, chaves):
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
            linhas.append((did, operadora, _iso(reg.get("Data do evento")), chave,
                           existentes.get(chave) if chave else None, *valores))
        conn.executemany(sql, linhas)
        for op in ops - {operadora}:
            _religar(conn, op)
        _atualizar_totais(conn, [did])
        conn.commit()
    return did, bool(antigos), repetidos


def _chaves(df):
    vistas, chaves = {}, []
    for r in (dict(zip(df.columns, x)) for x in df.itertuples(index=False)):
        base = chave_atendimento(r)
        n = vistas.get(base, 0) if base else 0
        if base:
            vistas[base] = n + 1
        chaves.append(chave_atendimento(r, n) if base else None)
    return chaves


def arquivos_com_os_mesmos_atendimentos(df):
    """Nomes dos arquivos do histórico que já têm os atendimentos deste DataFrame."""
    lista = [c for c in set(_chaves(df)) if c][:500]
    if not lista:
        return []
    with _conectar() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT d.arquivo FROM demonstrativo_itens i JOIN demonstrativos d ON d.id = i.demonstrativo_id "
            f"WHERE i.duplicado_de IS NULL AND i.chave IN ({', '.join(['?'] * len(lista))})", lista).fetchall()
    return [r[0] for r in rows]


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
        r = conn.execute("SELECT operadora FROM demonstrativos WHERE id = ?", (int(did),)).fetchone()
        _remover(conn, int(did))
        if r and r[0]:
            _religar(conn, r[0])  # refaz as ligações entre os arquivos que ficaram
        conn.commit()


def _remover(conn, did):
    """Apaga um demonstrativo. Atendimentos de outros arquivos que estavam guardados como repetidos deste
    passam a contar no lugar dele (nada some do histórico)."""
    copias = {}
    for cid, original in conn.execute(
            "SELECT c.id, c.duplicado_de FROM demonstrativo_itens c JOIN demonstrativo_itens o ON o.id = c.duplicado_de "
            "WHERE o.demonstrativo_id = ? AND c.demonstrativo_id <> ? ORDER BY c.id", (did, did)).fetchall():
        copias.setdefault(original, []).append(cid)
    promover, repontar = [], []
    for ids in copias.values():
        promover.append((ids[0],))
        repontar += [(ids[0], outro) for outro in ids[1:]]
    if promover:
        conn.executemany("UPDATE demonstrativo_itens SET duplicado_de = NULL WHERE id = ?", promover)
    if repontar:
        conn.executemany("UPDATE demonstrativo_itens SET duplicado_de = ? WHERE id = ?", repontar)
    conn.execute("DELETE FROM demonstrativo_itens WHERE demonstrativo_id = ?", (did,))
    conn.execute("DELETE FROM demonstrativos WHERE id = ?", (did,))


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
        filtros.append("(i.valor_glosa > 0.005 OR i.status = ?)")
        params.append(me.STATUS_GLOSA_SEM_VALOR)
    filtros.append("i.duplicado_de IS NULL")
    where = "WHERE " + " AND ".join(filtros)
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
              "Complemento recebido", "Glosa original", "Recebido no recurso"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for c in ("Data da glosa", "Situação do recurso", "Protocolo do recurso", "Data do recurso", "Vínculo", "Alertas"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    for c in ("Quantidade", "Quantidade liberada", "Valor unitário", "Valor de referência"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def resumo_painel(itens):
    """Agregações para o Painel. 'itens' vem de carregar_itens()."""
    vazio = dict(apresentado=0.0, glosado=0.0, itens_glosados=0, pct=0.0, diferencas=0.0, itens_diferenca=0,
                 itens_sem_valor=0,
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
               diferencas=float(dif.sum()), itens_diferenca=int((dif > 0.005).sum()),
               itens_sem_valor=int((itens["Status da glosa"] == me.STATUS_GLOSA_SEM_VALOR).sum()))
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
        f"FROM demonstrativo_itens i JOIN demonstrativos d ON d.id = i.demonstrativo_id "
        f"WHERE i.operadora = ? AND i.duplicado_de IS NULL",
        (operadora,),
    )
    for c in ("Valor informado", "Valor pago", "Valor da glosa", "Diferença sem justificativa", "Complemento recebido",
              "Glosa original", "Recebido no recurso"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("Data da glosa", "Situação do recurso", "Protocolo do recurso", "Data do recurso"):
        df[c] = df[c].fillna("")
    df["Vínculo"] = df["Vínculo"].fillna("")
    df.index = df["_id"].astype(int)
    return df


def _atualizar_totais(conn, demos):
    for did in {int(d) for d in demos if d is not None}:
        r = conn.execute("SELECT COUNT(*), SUM(valor_informado), SUM(valor_pago), SUM(valor_glosa) "
                         "FROM demonstrativo_itens WHERE demonstrativo_id = ? AND duplicado_de IS NULL", (did,)).fetchone()
        conn.execute("UPDATE demonstrativos SET linhas=?, valor_informado=?, valor_pago=?, valor_glosa=? WHERE id=?",
                     (r[0], round(r[1] or 0, 2), round(r[2] or 0, 2), round(r[3] or 0, 2), did))


def _gravar_campos(conn, df, item_id, extra_sql="", extra_params=()):
    sets = ", ".join(f"{COLUNAS[c]} = ?" for c in CAMPOS_VINCULO)
    conn.execute(f"UPDATE demonstrativo_itens SET {sets}{extra_sql} WHERE id = ?",
                 tuple(_py(df.at[item_id, c]) for c in CAMPOS_VINCULO) + tuple(extra_params) + (int(item_id),))


def vincular_historico(operadora, demonstrativo_id=None):
    """Refaz, a partir dos valores originais de cada arquivo, todas as ligações entre arquivos da operadora
    (mesma guia, reapresentações, pagamentos em duas partes). O resultado não depende da ordem em que os
    arquivos foram enviados. demonstrativo_id é aceito por compatibilidade e não muda o resultado.
    Retorna (vínculos criados, casos para conferir)."""
    if not operadora:
        return 0, 0
    with _conectar() as conn:
        n = _religar(conn, operadora)
        conn.commit()
    return n


def _restaurar(conn, operadora):
    """Volta todos os itens da operadora aos valores com que cada arquivo foi lido (desfaz as ligações)."""
    afetados = set()
    for iid, did, orig_json in conn.execute(
            "SELECT id, demonstrativo_id, orig_json FROM demonstrativo_itens WHERE operadora = ? AND "
            "orig_json IS NOT NULL", (operadora,)).fetchall():
        try:
            orig = json.loads(orig_json or "{}")
        except ValueError:
            orig = {}
        campos = [c for c in CAMPOS_VINCULO if c in orig]
        if campos:
            sets = ", ".join(f"{COLUNAS[c]} = ?" for c in campos)
            conn.execute(f"UPDATE demonstrativo_itens SET {sets}, vinculo_item = NULL, orig_json = NULL WHERE id = ?",
                         tuple(orig[c] for c in campos) + (iid,))
        else:
            conn.execute("UPDATE demonstrativo_itens SET vinculo_item = NULL, orig_json = NULL WHERE id = ?", (iid,))
        afetados.add(did)
    return afetados


def _religar(conn, operadora):
    afetados = _restaurar(conn, operadora)
    n = _vincular(conn, operadora)
    demos = [r[0] for r in conn.execute("SELECT id FROM demonstrativos WHERE operadora = ?", (operadora,)).fetchall()]
    _atualizar_totais(conn, set(demos) | afetados)
    return n


def _guardar_original(df, item):
    """JSON dos campos de ligação como estão agora (antes de mudar). Gravado com COALESCE: vale o primeiro."""
    return json.dumps({c: _py(df.at[item, c]) for c in CAMPOS_VINCULO}, ensure_ascii=False)


def _vincular(conn, operadora, demonstrativo_id=None):
    df = _itens_operadora(conn, operadora)
    if df.empty:
        return 0, 0
    if df["_demo"].nunique() < 2:  # um arquivo só: nada para ligar entre arquivos, mas o padrão é aprendido
        _ligar_reapresentacoes(conn, df, operadora, None, lambda k: "", set(), so_aprender=True)
        return 0, 0
    exigir = {int(demonstrativo_id)} if demonstrativo_id is not None else None
    afetados = set()
    origem = lambda k: f"arquivo {df.at[k, 'Arquivo']}"
    # 1) a mesma guia em outro arquivo (recurso, restante, pagamento repetido, glosa mantida)
    mesma, conferir = me.encontrar_mesma_guia(df, df["_demo"], exigir_em=exigir)
    for a, seguintes, tipo, ref in mesma:
        orig = me.aplicar_vinculo_guia(df, a, seguintes, tipo, origem, ref)
        for item in [a] + list(seguintes):
            parceiro = seguintes[-1] if item == a else a
            original = {c: _py(v) for c, v in orig[item].items()}
            _gravar_campos(conn, df, item, ", vinculo_item = ?, orig_json = COALESCE(orig_json, ?)",
                           (int(parceiro), json.dumps(original, ensure_ascii=False)))
            afetados.add(df.at[item, "_demo"])
    # 2) lotes de reapresentação (recurso/complemento) com outro número de guia: padrão aprendido
    n_reap, conferir_reap = _ligar_reapresentacoes(conn, df, operadora, exigir, origem, afetados)
    # 3) complemento pago em outra guia (pagamento em duas partes)
    pares, ambiguos = me.encontrar_pares(df, grupo=df["_demo"], exigir_em=exigir)
    ambiguos = set(ambiguos) | set(conferir)
    for a, b in pares:
        orig = me.aplicar_vinculo(df, a, b, origem_a=f"arquivo {df.at[a, 'Arquivo']}",
                                  origem_b=f"arquivo {df.at[b, 'Arquivo']}")
        for item, parceiro in ((a, b), (b, a)):
            original = {c: _py(v) for c, v in orig[item].items()}
            _gravar_campos(conn, df, item, ", vinculo_item = ?, orig_json = COALESCE(orig_json, ?)",
                           (int(parceiro), json.dumps(original, ensure_ascii=False)))
            afetados.add(df.at[item, "_demo"])
    for k in ambiguos:
        if me.ALERTA_POSSIVEL_PARTES not in str(df.at[k, "Alertas"] or ""):
            original = _guardar_original(df, k)
            novo = "; ".join([x for x in [str(df.at[k, "Alertas"] or "")] if x] + [me.ALERTA_POSSIVEL_PARTES])
            conn.execute("UPDATE demonstrativo_itens SET alertas = ?, orig_json = COALESCE(orig_json, ?) "
                         "WHERE id = ?", (novo, original, int(k)))
    _atualizar_totais(conn, afetados)
    return len(pares) + len(mesma) + n_reap, len(ambiguos) + conferir_reap


def _ligar_reapresentacoes(conn, df, operadora, exigir, origem, afetados, so_aprender=False):
    """Aprende as famílias de protocolo com TODO o histórico da operadora (mais evidência que um arquivo só),
    guarda o que aprendeu e liga as reapresentações aos atendimentos originais de outros arquivos."""
    import motor_conhecimento as mk
    import motor_padroes as mp
    try:
        definidos = mk.padroes_definidos(conn).get(me._norm(operadora), {})
        familias, analise, tipos = mp.preparar(df, definidos)
    except Exception:  # padrões são um extra: nunca impedem o restante (mas o erro fica registrado)
        log.exception("Falha ao analisar as famílias de protocolo no histórico (%s)", operadora)
        return 0, 0
    if familias:
        try:
            mk.salvar_padroes(operadora, analise, conn)
        except banco.Error:
            pass
    if not familias or so_aprender:
        return 0, 0
    ligacoes, sem, varios = mp.encontrar_reapresentacoes(df, familias, tipos, grupo=df["_demo"], exigir_em=exigir)
    fam = mp.familias_da_linha(df, familias)
    for a, k in ligacoes:
        orig = mp.aplicar_reapresentacao(df, a, k, origem, familia_k=", ".join(fam[k]))
        for item, parceiro in ((a, k), (k, a)):
            original = {c: _py(v) for c, v in orig[item].items()}
            _gravar_campos(conn, df, item, ", vinculo_item = ?, orig_json = COALESCE(orig_json, ?)",
                           (int(parceiro), json.dumps(original, ensure_ascii=False)))
            afetados.add(df.at[item, "_demo"])
    # avisos só nas linhas do arquivo novo (as antigas já receberam o aviso quando foram lidas)
    novos = {k for k in (sem | varios) if exigir is None or df.at[k, "_demo"] in exigir}
    antes = {k: (str(df.at[k, "Alertas"] or ""), _guardar_original(df, k)) for k in novos}
    mp.marcar_avisos(df, sem & novos, varios & novos)
    for k in novos:
        if str(df.at[k, "Alertas"] or "") != antes[k][0]:
            conn.execute("UPDATE demonstrativo_itens SET alertas = ?, orig_json = COALESCE(orig_json, ?) WHERE id = ?",
                         (df.at[k, "Alertas"], antes[k][1], int(k)))
    return len(ligacoes), len(varios & novos)


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
    vinculados = itens[itens["Status da glosa"].isin([me.STATUS_PAGO_EM_PARTES, me.STATUS_RECURSO_PAGO,
                                                      me.STATUS_RECURSO_PARCIAL])][cols]
    pend = itens[itens["Status da glosa"] == me.STATUS_PAGO_A_MENOR].copy()
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

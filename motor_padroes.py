"""
Padrões aprendidos dos demonstrativos: famílias de protocolo e lotes de reapresentação (recurso de glosa,
complemento de pagamento).

Nada aqui é regra fixa de operadora. O sistema observa os próprios demonstrativos:

1) Famílias de protocolo. Os números de protocolo costumam ter um começo que indica o tipo de lote, seguido de
   um contador. O sistema descobre até onde vai esse começo olhando as datas: se, ao separar por mais um dígito,
   os grupos convivem no mesmo período (são usados lado a lado), o dígito indica TIPO e a separação continua;
   se cada grupo ocupa uma época diferente, o dígito é só CONTADOR e a família termina ali.

2) Lotes de reapresentação. Numa família em que quase todos os atendimentos (mesmo paciente, procedimento e data)
   JÁ tinham sido pagos ou glosados antes em outra família, os lotes dessa família são reapresentações: recurso de
   glosa ou complemento. Isso só é concluído com evidência suficiente (MIN_LINHAS e MIN_PROPORCAO); nos demais
   casos a família fica como "sem evidência", e o usuário pode definir o tipo em Acessos → Aprendizado da leitura.

3) Ligação. Cada linha de um lote de reapresentação é ligada ao atendimento original (o único com o mesmo
   paciente, procedimento e data, pago antes, numa família comum). Se houver mais de um candidato ou nenhum,
   nada é ligado e a linha recebe um aviso para conferir. Os valores vêm sempre do demonstrativo.
"""
import re

import pandas as pd

import motor_extracao as me

TIPO_NORMAL = "Lote normal"
TIPO_REAPRESENTACAO = "Reapresentação (recurso ou complemento)"
TIPO_INDEFINIDO = "Sem evidência suficiente"
TIPOS = [TIPO_NORMAL, TIPO_REAPRESENTACAO, TIPO_INDEFINIDO]

MIN_LINHAS = 10          # linhas de uma família para concluir alguma coisa
MIN_PROPORCAO = 0.9      # atendimentos já vistos antes, para ser reapresentação
MAX_PROPORCAO_NORMAL = 0.1
MIN_TOKEN = 6            # protocolos com menos dígitos não entram (não dá para separar tipo de contador)
MAX_PROFUNDIDADE = 8

STATUS_RECURSO_PAGO = "Glosa revertida em recurso"
STATUS_RECURSO_PARCIAL = "Recurso pago em parte"
ALERTA_SEM_ORIGINAL = "Lote de reapresentação: atendimento original não encontrado (pode estar em outro demonstrativo)"
ALERTA_VARIOS_ORIGINAIS = "Lote de reapresentação com mais de um atendimento original possível: conferir"
ALERTA_ACIMA = "Recebeu mais que o valor informado somando a reapresentação: conferir (pode ser diferença de tabela)"
TOL = me.TOL


# --------------------------------------------------------------------------
# Famílias de protocolo
# --------------------------------------------------------------------------
def tokens(protocolo):
    """Números de protocolo de uma linha (uma linha consolidada pode ter mais de um)."""
    if protocolo is None or (isinstance(protocolo, float) and pd.isna(protocolo)):
        return []
    partes = re.split(r"[;,/|\s]+", str(protocolo))
    return [t for t in (re.sub(r"\D", "", p) for p in partes) if len(t) >= MIN_TOKEN]


def _data_linha(df):
    d = pd.to_datetime(df.get("Data de pagamento"), format="%d/%m/%Y", errors="coerce")
    e = pd.to_datetime(df.get("Data do evento"), format="%d/%m/%Y", errors="coerce")
    return d.fillna(e)


def _convivem(sub, L):
    """Os filhos (prefixo com L+1 dígitos) são usados lado a lado no tempo? None se não há 2 filhos relevantes."""
    filho = sub["p"].str[:L + 1]
    vc = filho.value_counts()
    grandes = list(vc[vc >= max(MIN_LINHAS // 2, 0.02 * len(sub))].index)
    if len(grandes) < 2:
        return None
    faixa = {}
    for f in grandes:
        d = sub.loc[filho == f, "d"].dropna()
        if len(d) < 3:
            return None
        faixa[f] = (d.quantile(.1), d.quantile(.9))
    pares = sobrepostos = 0
    for i, a in enumerate(grandes):
        for b in grandes[i + 1:]:
            pares += 1
            sobrepostos += max(faixa[a][0], faixa[b][0]) < min(faixa[a][1], faixa[b][1])
    return sobrepostos / pares


def descobrir_familias(df):
    """Lista de prefixos (famílias) descobertos nos protocolos. Vazia se não houver protocolo suficiente."""
    if df is None or df.empty or "Protocolo" not in df.columns:
        return []
    datas = _data_linha(df)
    linhas = [(t, datas.iat[i]) for i, p in enumerate(df["Protocolo"].tolist()) for t in tokens(p)]
    if len(linhas) < MIN_LINHAS:
        return []
    t = pd.DataFrame(linhas, columns=["p", "d"])
    familias = sorted({f for f in _separar("", 0, t) if f}, key=lambda f: (-len(f), f))
    if not familias:
        return []
    # o contador começa no mesmo ponto em todos os protocolos: as famílias com muita evidência mostram onde,
    # e as pequenas (poucas linhas, separação incerta) não passam desse ponto
    contagem = t["p"].map(lambda p: familia_de(p, familias)).value_counts()
    confiaveis = [f for f, n in contagem.items() if f and n >= 5 * MIN_LINHAS]
    if confiaveis:
        limite = max(len(f) for f in confiaveis)
        familias = sorted({f[:limite] for f in familias}, key=lambda f: (-len(f), f))
    return familias


def _separar(nome, L, sub):
    """Famílias dentro de `sub`, cujos protocolos começam todos com `nome` (examinando o dígito L+1).
    Ramos pequenos ficam na família de cima (nome)."""
    if L >= MAX_PROFUNDIDADE or len(sub) < 2 * MIN_LINHAS or sub["p"].str.len().min() <= L + 4:
        return [nome]
    filho = sub["p"].str[:L + 1]
    vc = filho.value_counts()
    conv = _convivem(sub, L)
    if conv is None:  # um só caminho relevante: olha mais fundo mantendo o nome
        return [nome] + _separar(nome, L + 1, sub[filho == vc.index[0]])
    if conv >= 0.5:  # os ramos convivem no tempo: o dígito indica tipo de lote
        res = [nome]
        for f in vc[vc >= max(MIN_LINHAS // 2, 0.02 * len(sub))].index:
            res += _separar(f, L + 1, sub[filho == f])
        return res
    return [nome]  # cada ramo numa época: o dígito é contador


def familia_de(token, familias):
    for f in familias:  # já ordenadas da mais longa para a mais curta
        if token.startswith(f):
            return f
    return ""


def familias_da_linha(df, familias):
    return df["Protocolo"].map(lambda p: sorted({familia_de(t, familias) for t in tokens(p)} - {""}))


# --------------------------------------------------------------------------
# Evidência: atendimentos que reaparecem
# --------------------------------------------------------------------------
def chave_atendimento(df):
    partes = [df["Nome do paciente"].map(me._norm), df["Código"].fillna("").astype(str).str.strip(),
              df["Data do evento"].astype(str)]
    if "Operadora" in df.columns:
        partes.append(df["Operadora"].map(me._norm))
    return partes[0].str.cat(partes[1:], sep="|")


def analisar_familias(df, familias=None):
    """Para cada família: linhas, quantas são atendimentos já vistos antes em outra família, prazo típico entre
    atendimento e pagamento, procedimentos principais e o tipo concluído pela evidência."""
    familias = familias if familias is not None else descobrir_familias(df)
    if not familias:
        return pd.DataFrame(columns=["Família", "Linhas", "Já vistos antes", "% já vistos", "Prazo típico (dias)",
                                     "Procedimentos principais", "Período", "Tipo pela evidência"])
    fam = familias_da_linha(df, familias)
    chave = chave_atendimento(df)
    pag = pd.to_datetime(df["Data de pagamento"], format="%d/%m/%Y", errors="coerce")
    evento = pd.to_datetime(df["Data do evento"], format="%d/%m/%Y", errors="coerce")
    # primeira data de pagamento de cada atendimento em cada família
    reg = pd.DataFrame({"k": chave, "fam": fam, "pag": pag}).explode("fam").dropna(subset=["fam"])
    primeiro = reg.groupby(["k", "fam"])["pag"].min()
    por_chave = {}
    for (k, f), d in primeiro.items():
        por_chave.setdefault(k, []).append((f, d))
    linhas = []
    for f in familias:
        idx = [i for i, fs in zip(df.index, fam) if f in fs]
        if not idx:
            continue
        vistos = 0
        for i in idx:
            d = pag[i]
            if len(fam[i]) > 1:  # o próprio demonstrativo mostra a mesma guia em outra família de lote
                vistos += 1
            elif any(g != f and pd.notna(dg) and pd.notna(d) and dg < d for g, dg in por_chave.get(chave[i], [])):
                vistos += 1
        n = len(idx)
        prop = vistos / n
        if n >= MIN_LINHAS and prop >= MIN_PROPORCAO:
            tipo = TIPO_REAPRESENTACAO
        elif n >= MIN_LINHAS and prop <= MAX_PROPORCAO_NORMAL:
            tipo = TIPO_NORMAL
        else:
            tipo = TIPO_INDEFINIDO
        prazo = (pag[idx] - evento[idx]).dt.days.dropna()
        proc = df.loc[idx, "Procedimento"].fillna("").astype(str).str.strip()
        proc = proc[proc.ne("") & proc.ne("-")].value_counts().head(3)
        ev = evento[idx].dropna()
        linhas.append({
            "Família": f, "Linhas": n, "Já vistos antes": vistos, "% já vistos": round(100 * prop, 1),
            "Prazo típico (dias)": int(prazo.median()) if len(prazo) else None,
            "Procedimentos principais": "; ".join(f"{p} ({q})" for p, q in proc.items()),
            "Período": f"{ev.min():%m/%Y} a {ev.max():%m/%Y}" if len(ev) else "",
            "Tipo pela evidência": tipo,
        })
    return pd.DataFrame(linhas)


def tipos_efetivos(analise, definidos=None):
    """Tipo usado para cada família: o definido pelo usuário vale mais que o concluído pela evidência."""
    definidos = definidos or {}
    tipos = {r["Família"]: r["Tipo pela evidência"] for _, r in analise.iterrows()} if not analise.empty else {}
    for f, t in definidos.items():
        if t in (TIPO_NORMAL, TIPO_REAPRESENTACAO):
            tipos[f] = t
    return tipos


# --------------------------------------------------------------------------
# Ligação das reapresentações aos atendimentos originais
# --------------------------------------------------------------------------
def encontrar_reapresentacoes(df, familias, tipos, grupo=None, exigir_em=None):
    """Retorna (ligações [(original, reapresentação)], sem_original, varios_originais)."""
    reap = {f for f, t in tipos.items() if t == TIPO_REAPRESENTACAO}
    if df is None or df.empty or not reap:
        return [], set(), set()
    fam = familias_da_linha(df, familias)
    livre = df["Vínculo"].fillna("").astype(str).str.strip().eq("") if "Vínculo" in df.columns else \
        pd.Series(True, index=df.index)
    eh_reap = fam.map(lambda fs: bool(fs) and set(fs) <= reap)
    eh_orig = fam.map(lambda fs: bool(set(fs) - reap)) & livre
    chave = chave_atendimento(df)
    pag = pd.to_datetime(df["Data de pagamento"], format="%d/%m/%Y", errors="coerce")
    inf = pd.to_numeric(df["Valor informado"], errors="coerce").fillna(0)
    pago = pd.to_numeric(df["Valor pago"], errors="coerce").fillna(0)
    originais = {}
    for i in df.index[eh_orig]:
        originais.setdefault(chave[i], []).append(i)
    ligacoes, sem, varios = [], set(), set()
    usados = {}
    for k in df.index[eh_reap & livre]:
        if exigir_em is not None and grupo is not None:
            cand_all = originais.get(chave[k], [])
            if grupo[k] not in exigir_em and not any(grupo[c] in exigir_em for c in cand_all):
                continue
        cand = [c for c in originais.get(chave[k], [])
                if c != k and (pd.isna(pag[k]) or pd.isna(pag[c]) or pag[c] < pag[k])]
        if len(cand) > 1:  # desempate: o único que ficou devendo exatamente o que veio agora
            exatos = [c for c in cand if abs((inf[c] - pago[c]) - pago[k]) <= TOL and pago[k] > TOL]
            cand = exatos if len(exatos) == 1 else cand
        if not cand:
            sem.add(k)
        elif len(cand) > 1:
            varios.add(k)
        else:
            usados.setdefault(cand[0], []).append(k)
    for c, ks in usados.items():
        if len(ks) == 1:
            ligacoes.append((c, ks[0]))
        else:  # o mesmo original reapresentado mais de uma vez: liga em ordem de pagamento
            for k in sorted(ks, key=lambda x: (pag[x] if pd.notna(pag[x]) else pd.Timestamp.max, x)):
                ligacoes.append((c, k))
    return ligacoes, sem, varios


def aplicar_reapresentacao(df, a, k, origem=None, familia_k=""):
    """Liga o atendimento original (a) e a reapresentação (k), sem apagar nenhuma linha.
    A reapresentação deixa de contar como atendimento novo; o original passa a mostrar o que foi recuperado.
    Devolve os valores originais das duas linhas (para poder desfazer)."""
    campos = ["Valor informado", "Valor da glosa", "Diferença sem justificativa", "Status da glosa",
              "Motivo da glosa", "Alertas", "Complemento recebido", "Vínculo"]
    orig = {x: {c: df.at[x, c] if c in df.columns else None for c in campos} for x in (a, k)}
    origem = origem or (lambda x: "")
    onde = lambda x: f", {origem(x)}" if origem(x) else ""
    inf_a = me._num(df.at[a, "Valor informado"])
    pa, pk = me._num(df.at[a, "Valor pago"]), me._num(df.at[k, "Valor pago"])
    ja = me._num(df.at[a, "Complemento recebido"])
    glosa_a = me._num(df.at[a, "Valor da glosa"])
    dif_a = me._num(df.at[a, "Diferença sem justificativa"])
    motivo_a = str(df.at[a, "Motivo da glosa"] or "")
    justificada = bool(motivo_a.strip()) and not motivo_a.startswith(me._MOTIVOS_GERADOS)
    dt_a, dt_k = df.at[a, "Data de pagamento"], df.at[k, "Data de pagamento"]
    guia_a, guia_k = str(df.at[a, "Doc Original"]), str(df.at[k, "Doc Original"])
    lote_k = f"protocolo {df.at[k, 'Protocolo']}" if str(df.at[k, "Protocolo"] or "").strip() else "outro lote"
    alertas_a = [x for x in str(df.at[a, "Alertas"] or "").split("; ")
                 if x and not x.startswith(("Pago ", "Sem valor", "Possível pagamento em partes"))]
    total = pa + ja + pk
    falta_antes = glosa_a + dif_a

    if pk <= TOL:
        nota = f"Reapresentado no {lote_k} em {dt_k} (guia {guia_k}{onde(k)}) e não pago"
        df.at[a, "Vínculo"] = nota
        df.at[k, "Status da glosa"] = me.STATUS_GLOSA_MANTIDA
    else:
        recuperado = min(pk, falta_antes) if falta_antes > TOL else 0.0
        resto = max(falta_antes - pk, 0.0)
        # tira do que faltava primeiro a glosa justificada, depois a diferença sem justificativa
        tira_glosa = min(glosa_a, recuperado)
        df.at[a, "Valor da glosa"] = round(glosa_a - tira_glosa, 2)
        df.at[a, "Diferença sem justificativa"] = round(max(dif_a - (recuperado - tira_glosa), 0.0), 2)
        df.at[a, "Complemento recebido"] = round(ja + pk, 2)
        if falta_antes > TOL and resto <= TOL:
            status = STATUS_RECURSO_PAGO if (justificada and glosa_a > TOL) else me.STATUS_PAGO_EM_PARTES
        elif falta_antes > TOL:
            status = STATUS_RECURSO_PARCIAL
        else:
            status = df.at[a, "Status da glosa"]
        df.at[a, "Status da glosa"] = status
        if status in (me.STATUS_PAGO_EM_PARTES,) and not justificada:
            df.at[a, "Motivo da glosa"] = ""
        nota = f"Recebido {me._br_valor(pk)} no {lote_k} em {dt_k} (guia {guia_k}{onde(k)})"
        df.at[a, "Vínculo"] = nota
        extra = [f"{status}: {me._br_valor(pa)} em {dt_a} + {me._br_valor(pk)} em {dt_k}"] \
            if status in (STATUS_RECURSO_PAGO, STATUS_RECURSO_PARCIAL, me.STATUS_PAGO_EM_PARTES) else []
        if inf_a > TOL and total > inf_a + TOL:
            extra.append(ALERTA_ACIMA)
        df.at[a, "Alertas"] = "; ".join(alertas_a + extra)
        df.at[k, "Status da glosa"] = me.STATUS_COMPLEMENTO
    # a reapresentação nunca conta como atendimento novo
    df.at[k, "Valor informado"] = 0.0
    df.at[k, "Valor da glosa"] = 0.0
    df.at[k, "Diferença sem justificativa"] = 0.0
    df.at[k, "Complemento recebido"] = 0.0
    df.at[k, "Alertas"] = ""
    if str(df.at[k, "Motivo da glosa"] or "").startswith(me._MOTIVOS_GERADOS):
        df.at[k, "Motivo da glosa"] = ""
    fam = f" (família {familia_k})" if familia_k else ""
    df.at[k, "Vínculo"] = f"Reapresentação{fam} do atendimento pago em {dt_a} (guia {guia_a}{onde(a)})"
    return orig


def marcar_avisos(df, sem, varios):
    for conj, aviso in ((sem, ALERTA_SEM_ORIGINAL), (varios, ALERTA_VARIOS_ORIGINAIS)):
        for k in conj:
            atual = [x for x in str(df.at[k, "Alertas"] or "").split("; ")
                     if x and x not in (ALERTA_SEM_ORIGINAL, ALERTA_VARIOS_ORIGINAIS)]
            df.at[k, "Alertas"] = "; ".join(atual + [aviso])


def preparar(df, definidos=None):
    """Famílias, análise e tipo usado para cada família.
    definidos: {família: {"tipo": ..., "usuario": bool}} já aprendidos para a operadora. O que o usuário definiu
    sempre vale; o aprendido antes (com mais arquivos) completa quando este arquivo sozinho não basta."""
    familias = descobrir_familias(df)
    if not familias:
        return [], analisar_familias(df, []), {}
    analise = analisar_familias(df, familias)
    tipos = tipos_efetivos(analise)
    for f, t in (definidos or {}).items():
        if f in familias and t.get("tipo") in (TIPO_NORMAL, TIPO_REAPRESENTACAO) and (
                t.get("usuario") or tipos.get(f, TIPO_INDEFINIDO) == TIPO_INDEFINIDO):
            tipos[f] = t["tipo"]
    if not analise.empty:
        analise = analise.assign(**{"Tipo usado": analise["Família"].map(lambda f: tipos.get(f, TIPO_INDEFINIDO))})
    return familias, analise, tipos


def linhas_reapresentacao(df, familias, tipos):
    reap = {f for f, t in tipos.items() if t == TIPO_REAPRESENTACAO}
    if not reap or df is None or df.empty:
        return pd.Series(False, index=getattr(df, "index", None))
    return familias_da_linha(df, familias).map(lambda fs: bool(fs) and set(fs) <= reap)


def ligar_no_arquivo(out, familias, tipos, analise=None):
    """Liga, dentro do arquivo, as reapresentações aos atendimentos originais. Retorna (df, resumo)."""
    resumo = dict(familias=list(familias), ligadas=0, sem_original=0, varios=0,
                  analise=None if analise is None or analise.empty else analise.to_dict("records"))
    if not familias or not tipos:
        return out, resumo
    out = out.copy()
    for c, v in (("Complemento recebido", 0.0), ("Vínculo", ""), ("Alertas", "")):
        if c not in out.columns:
            out[c] = v
    ligacoes, sem, varios = encontrar_reapresentacoes(out, familias, tipos)
    fam = familias_da_linha(out, familias)
    for a, k in ligacoes:
        aplicar_reapresentacao(out, a, k, familia_k=", ".join(fam[k]))
    marcar_avisos(out, sem, varios)
    resumo.update(ligadas=len(ligacoes), sem_original=len(sem), varios=len(varios))
    return out, resumo

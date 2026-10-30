"""
Ligação dos demonstrativos TISS no histórico de uma operadora (chamado por motor_historico a cada arquivo
guardado ou removido, sempre a partir dos valores originais, então a ordem de envio não muda o resultado).

1. Cópias da mesma análise/pagamento (o PDF e o XML do mesmo lote, ou o mesmo arquivo baixado de novo) já
   ficam guardadas sem contar (motor_historico.chave_atendimento). Aqui a cópia completa o que falta na outra
   (o nome do paciente que só o PDF traz) e, se os valores ou os códigos de glosa não baterem, a guia vai para
   conferir: o sistema não escolhe sozinho qual versão vale.
2. Pagamento de uma guia que está na análise de conta (mesmo protocolo + guia): é a confirmação do pagamento.
   A análise ganha a data do pagamento e a linha do pagamento deixa de contar (senão o atendimento contaria
   duas vezes). Valor pago diferente do liberado na análise vai para conferir.
3. Pagamento de recurso de glosa (tipo de pagamento 2 / 'Ajuste Ant. X - Orig. Y'): o valor volta para a
   glosa original da mesma guia (Recurso de glosa: recebido, recebido em parte ou não pago).
4. Guias da análise sem pagamento: aguardando (dentro do prazo que a própria operadora costuma levar) ou
   atrasado (já saíram pagamentos depois do prazo e esta guia não estava em nenhum).
"""
import numpy as np
import pandas as pd

import leitor_tiss as lt
import motor_extracao as me

TOL = me.TOL
STATUS_PAGAMENTO_CONFERIDO = "Pagamento conferido com a análise de conta"
ALERTA_DIVERGENCIA = "Arquivos da mesma análise com valores ou códigos de glosa diferentes: conferir qual vale"
ALERTA_PAGO_DIFERENTE = "Valor pago diferente do liberado na análise de conta: conferir"
ALERTA_ATRASADO = "Pagamento atrasado"
ALERTA_AGUARDANDO = "Aguardando pagamento"
ALERTA_RECURSO_SEM_ORIGINAL = "Pagamento de recurso: a glosa original não está no histórico"
ALERTA_RECURSO_VARIOS = "Pagamento de recurso com mais de uma glosa original possível: conferir"
MARGEM_DIAS_UTEIS = 5          # folga sobre o maior prazo já visto antes de chamar de atrasado
MIN_PAGAMENTOS_PARA_PRAZO = 3  # só calcula prazo com pagamentos suficientes


def _t(v):
    v = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
    return "" if v in ("-", "nan", "None") else v


def _n(v):
    return me._num(v)


def _dt(v):
    d = pd.to_datetime(_t(v), format="%d/%m/%Y", errors="coerce")
    return None if pd.isna(d) else d


def _sem_nome(v):
    return me._norm(_t(v)) in ("", "NAO IDENTIFICADO")


def _add_alerta(df, k, texto, prefixo=None):
    atual = [x for x in str(df.at[k, "Alertas"] or "").split("; ")
             if x and x != lt.AVISO_SEM_ANALISE and not (prefixo and x.startswith(prefixo))]
    if texto not in atual:
        atual.append(texto)
    df.at[k, "Alertas"] = "; ".join(atual)


def _codigos(v):
    return ";".join(sorted({x.strip() for x in _t(v).split(";") if x.strip()}))


def ligar(df, copias=None):
    """df: itens da operadora (índice = id do item; colunas do motor_extracao + 'Arquivo'), modificado no lugar.
    copias: itens guardados como cópia (colunas iguais + '_original' = id do item que conta).
    Devolve (ids alterados, valores originais {id: {campo: valor}}, resumo)."""
    resumo = dict(confirmados=0, recursos=0, atrasados=0, divergencias=0)
    if df is None or df.empty or "Documento" not in df.columns:
        return set(), {}, resumo
    doc = df["Documento"].fillna("").astype(str)
    tiss = df.index[doc.isin([lt.DOC_ANALISE, lt.DOC_PAGAMENTO])]
    if not len(tiss):
        return set(), {}, resumo
    orig = {k: {c: df.at[k, c] if c in df.columns else None for c in me.CAMPOS_LIGACAO} for k in tiss}
    mudou = set()
    prot = df["Protocolo"].map(_t)
    guia = df["Doc Original"].map(_t)
    A = df.index[doc.eq(lt.DOC_ANALISE)]
    P = df.index[doc.eq(lt.DOC_PAGAMENTO)]

    # 1) cópias (PDF + XML do mesmo lote, ou baixado de novo)
    if copias is not None and not copias.empty:
        for _, c in copias.iterrows():
            k = c.get("_original")
            if k is None or pd.isna(k):
                continue
            k = int(k)
            if k not in df.index or k not in orig:
                continue
            if _sem_nome(df.at[k, "Nome do paciente"]) and not _sem_nome(c.get("Nome do paciente")):
                df.at[k, "Nome do paciente"] = c.get("Nome do paciente")
                mudou.add(k)
            if not _t(df.at[k, "Carteira"]) and _t(c.get("Carteira")):
                df.at[k, "Carteira"] = c.get("Carteira")
                mudou.add(k)
            dif = (abs(_n(df.at[k, "Valor pago"]) - _n(c.get("Valor pago"))) > TOL
                   or abs(_n(df.at[k, "Valor da glosa"]) - _n(c.get("Valor da glosa"))) > TOL
                   or _codigos(df.at[k, "Código da glosa"]) != _codigos(c.get("Código da glosa")))
            if dif:
                desc = lambda pg, gl, cg, arq: (f"{arq}: pago {me._br_valor(_n(pg))}, glosa {me._br_valor(_n(gl))}"
                                                + (f" ({_t(cg)})" if _t(cg) else ""))
                _add_alerta(df, k, f"{ALERTA_DIVERGENCIA} [{desc(df.at[k, 'Valor pago'], df.at[k, 'Valor da glosa'], df.at[k, 'Código da glosa'], df.at[k, 'Arquivo'])} × "
                                   f"{desc(c.get('Valor pago'), c.get('Valor da glosa'), c.get('Código da glosa'), c.get('Arquivo'))}]",
                            prefixo=ALERTA_DIVERGENCIA)
                mudou.add(k)
                resumo["divergencias"] += 1

    analise_por = {}
    for k in A:
        analise_por.setdefault((prot[k], guia[k]), []).append(k)
    pag_por = {}
    for k in P:
        pag_por.setdefault((prot[k], guia[k]), []).append(k)

    def zerar(k, status, vinculo, manter_pago):
        df.at[k, "Valor informado"] = 0.0
        df.at[k, "Valor da glosa"] = 0.0
        df.at[k, "Diferença sem justificativa"] = 0.0
        if not manter_pago:
            df.at[k, "Valor pago"] = 0.0
        df.at[k, "Status da glosa"] = status
        df.at[k, "Motivo da glosa"] = ""
        df.at[k, "Alertas"] = ""
        df.at[k, "Vínculo"] = vinculo
        mudou.add(k)

    # 2) pagamento confirma a análise do mesmo protocolo + guia
    prazos, ultimo_pag = [], None
    for k in P:
        dp = _dt(df.at[k, "Data de pagamento"])
        if dp is not None and (ultimo_pag is None or dp > ultimo_pag):
            ultimo_pag = dp
    for chave, pags in pag_por.items():
        itens = analise_por.get(chave)
        if not itens:
            continue
        for p in pags:
            data_pag = _t(df.at[p, "Data de pagamento"])
            liberado = round(sum(_n(df.at[i, "Valor pago"]) for i in itens), 2)
            for i in itens:
                if not _t(df.at[i, "Data de pagamento"]):
                    df.at[i, "Data de pagamento"] = data_pag
                    mudou.add(i)
            if abs(liberado - _n(df.at[p, "Valor pago"])) > TOL:
                for i in itens:
                    _add_alerta(df, i, f"{ALERTA_PAGO_DIFERENTE} (liberado {me._br_valor(liberado)}, pago "
                                       f"{me._br_valor(_n(df.at[p, 'Valor pago']))} em {data_pag})",
                                prefixo=ALERTA_PAGO_DIFERENTE)
            dprot, dpag = _dt(df.at[itens[0], "Data do protocolo"]), _dt(data_pag)
            if dprot is not None and dpag is not None and dpag >= dprot:
                prazos.append(int(np.busday_count(dprot.date(), dpag.date())))
            zerar(p, STATUS_PAGAMENTO_CONFERIDO,
                  f"Pagamento da guia em {data_pag} conferido com a análise de conta ({df.at[itens[0], 'Arquivo']})",
                  manter_pago=False)
            resumo["confirmados"] += 1

    # 3) recursos: o pagamento (ou a análise) do protocolo do recurso devolve a glosa original da mesma guia
    def originais(g, rec_prot, origem):
        """Linhas da glosa original: análise do protocolo original; sem ela, o pagamento original."""
        if origem and origem != "recurso":
            linhas = analise_por.get((origem, g)) or pag_por.get((origem, g)) or []
            return [k for k in linhas if (_n(df.at[k, "Valor da glosa"]) > TOL or _n(df.at[k, "Glosa original"]) > TOL)], [origem]
        cand = {}
        for (pr, gg), linhas in list(analise_por.items()) + list(pag_por.items()):
            if gg == g and pr != rec_prot:
                for k in linhas:
                    if _n(df.at[k, "Valor da glosa"]) > TOL or _n(df.at[k, "Glosa original"]) > TOL:
                        cand.setdefault(pr, []).append(k)
        if len(cand) == 1:
            pr = next(iter(cand))
            return list(dict.fromkeys(cand[pr])), [pr]
        return [], sorted(cand)

    recursos = []  # (data do recurso, protocolo do recurso, guia, protocolo original informado, linhas que pagam)
    vistos = set()
    for k in P:
        origem = _t(df.at[k, "Protocolo original"])
        if not origem:
            continue
        chave = (prot[k], guia[k])
        if chave in vistos:
            continue
        vistos.add(chave)
        fontes = analise_por.get(chave) or pag_por.get(chave)
        recursos.append((_dt(df.at[k, "Data de pagamento"]) or pd.Timestamp.max, prot[k], guia[k], origem, fontes))
    for _, rec_prot, g, origem, fontes in sorted(recursos, key=lambda r: (r[0], r[1])):
        alvo, prots = originais(g, rec_prot, origem)
        data_rec = _t(df.at[fontes[0], "Data de pagamento"])
        if not alvo:
            for f in fontes:
                _add_alerta(df, f, ALERTA_RECURSO_VARIOS if len(prots) > 1 else ALERTA_RECURSO_SEM_ORIGINAL)
                mudou.add(f)
            continue
        prot_orig = prots[0]
        recebido = {k: 0.0 for k in alvo}
        sobra = 0.0
        usados = set()
        for f in fontes:
            pago_f = _n(df.at[f, "Valor pago"])
            par = None
            if _t(df.at[f, "Código"]):  # análise do recurso: volta para o mesmo procedimento e data
                par = next((k for k in alvo if k not in usados and _t(df.at[k, "Código"]) == _t(df.at[f, "Código"])
                            and _t(df.at[k, "Data do evento"]) == _t(df.at[f, "Data do evento"])), None)
            if par is not None:
                usados.add(par)
                recebido[par] += pago_f
            else:
                sobra += pago_f
            zerar(f, me.STATUS_COMPLEMENTO if pago_f > TOL else me.STATUS_GLOSA_MANTIDA,
                  f"Recurso da glosa do protocolo {prot_orig} (guia {g}), pago em {data_rec}", manter_pago=True)
        for k in alvo:  # pagamento por guia: completa as glosas da guia em ordem
            glosa_k = _n(df.at[k, "Glosa original"]) or _n(df.at[k, "Valor da glosa"])
            ja = _n(df.at[k, "Recebido no recurso"])
            r = round(min(max(glosa_k - ja - recebido[k], 0.0), sobra), 2)
            recebido[k] += r
            sobra = round(sobra - r, 2)
        if sobra > TOL and alvo:  # devolveu mais do que tinha sido glosado
            recebido[alvo[-1]] += sobra
        for k in alvo:
            glosado = _n(df.at[k, "Glosa original"]) or _n(df.at[k, "Valor da glosa"])
            total = round(_n(df.at[k, "Recebido no recurso"]) + recebido[k], 2)
            sit = me.situacao_recurso(glosado, total)
            protocolos = "; ".join(dict.fromkeys(x for x in [_t(df.at[k, "Protocolo do recurso"]), rec_prot] if x))
            df.at[k, "Glosa original"] = glosado
            df.at[k, "Data da glosa"] = _t(df.at[k, "Data da glosa"]) or _t(df.at[k, "Data de pagamento"])
            df.at[k, "Situação do recurso"] = sit
            df.at[k, "Protocolo do recurso"] = protocolos
            df.at[k, "Data do recurso"] = data_rec
            df.at[k, "Recebido no recurso"] = total
            df.at[k, "Valor da glosa"] = round(max(glosado - total, 0.0), 2)
            if sit == me.RECURSO_RECEBIDO:
                df.at[k, "Status da glosa"] = me.STATUS_RECURSO_PAGO
            elif sit == me.RECURSO_PARCIAL:
                df.at[k, "Status da glosa"] = me.STATUS_RECURSO_PARCIAL
            motivo = _t(df.at[k, "Motivo da glosa"])
            motivo = "" if motivo.startswith(me._MOTIVOS_GERADOS) else motivo
            volta = f"recebido {me._br_valor(total)} em {data_rec}" if total > TOL else f"não pago em {data_rec}"
            df.at[k, "Vínculo"] = (f"Glosado no protocolo {prot_orig}" + (f" ({motivo})" if motivo else "")
                                   + f": {me._br_valor(glosado)}. Recurso no protocolo {protocolos}: {volta}")
            if total > glosado + TOL:
                me._marcar_excesso(df, k, total - glosado)
            mudou.add(k)
        resumo["recursos"] += 1

    # 4) análise sem pagamento: aguardando ou atrasado (pelo prazo que a própria operadora costuma levar)
    if len(P) and ultimo_pag is not None and len(prazos) >= MIN_PAGAMENTOS_PARA_PRAZO:
        prazo = max(prazos) + MARGEM_DIAS_UTEIS
        for k in A:
            if _t(df.at[k, "Data de pagamento"]) or _t(df.at[k, "Vínculo"]):
                continue
            dprot = _dt(df.at[k, "Data do protocolo"])
            if dprot is None:
                continue
            limite = pd.Timestamp(np.busday_offset(dprot.date(), prazo, roll="forward"))
            if ultimo_pag > limite:
                _add_alerta(df, k, f"{ALERTA_ATRASADO}: protocolado em {dprot:%d/%m/%Y}; a operadora costuma pagar "
                                   f"em até {max(prazos)} dias úteis e nenhum pagamento até {ultimo_pag:%d/%m/%Y} "
                                   f"traz esta guia", prefixo=ALERTA_ATRASADO)
                resumo["atrasados"] += 1
            else:
                _add_alerta(df, k, f"{ALERTA_AGUARDANDO} (previsto até {limite:%d/%m/%Y})", prefixo=ALERTA_AGUARDANDO)
            mudou.add(k)
    mudou = {k for k in mudou if any(not _igual(orig[k][c], df.at[k, c]) for c in me.CAMPOS_LIGACAO if c in df.columns)}
    return mudou, {k: orig[k] for k in mudou}, resumo


def _igual(a, b):
    na = a is None or (isinstance(a, float) and pd.isna(a))
    nb = b is None or (isinstance(b, float) and pd.isna(b))
    if na or nb:
        return na and nb
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.005
    return str(a) == str(b)

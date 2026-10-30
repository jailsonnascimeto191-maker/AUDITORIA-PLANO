"""
Recursos de glosa e anomalias para a equipe verificar.

recursos(df): guias glosadas que voltaram em outro crédito/protocolo (recurso) e quanto foi recebido.
anomalias(df): situações fora do padrão que o sistema não tem como decidir sozinho. Nada é corrigido
automaticamente: cada caso vem com o que verificar e as guias envolvidas.
"""
import pandas as pd

import motor_extracao as me
import motor_padroes as mp

# textos fixos aqui (e não lidos de motor_extracao): se o servidor ainda tiver uma versão antiga daquele módulo
# na memória durante uma atualização, esta parte continua funcionando
RECURSO_RECEBIDO = getattr(me, "RECURSO_RECEBIDO", "Recebido")
RECURSO_PARCIAL = getattr(me, "RECURSO_PARCIAL", "Recebido em parte")
STATUS_COMPLEMENTO = getattr(me, "STATUS_COMPLEMENTO", "Complemento de pagamento")
STATUS_GLOSA_MANTIDA = getattr(me, "STATUS_GLOSA_MANTIDA", "Glosa mantida em novo crédito")
STATUS_DUPLICIDADE = getattr(me, "STATUS_DUPLICIDADE", "Possível pagamento em duplicidade")
TOL = getattr(me, "TOL", 0.02)

TIPO_COBRANCA_DOBRO = "Possível cobrança em dobro"
TIPO_PAGO_REPETIDO = "Pagamento repetido"
TIPO_ACIMA = "Recebeu mais que o informado"
TIPO_SEM_ORIGINAL_DEFINIDO = "Recurso com mais de um original possível"
TIPO_ATRASADO = "Pagamento atrasado"
TIPO_VERSOES = "Versões diferentes do mesmo demonstrativo"
TIPO_PAGO_DIFERENTE = "Pago diferente do liberado"
TIPO_GLOSA_MAIOR = "Glosa maior que o valor"
TIPO_GUIA_FORA_PADRAO = "Número de guia fora do padrão"

# demonstrativos TISS (análise de conta + pagamento): alerta -> (tipo, o que verificar)
try:
    import leitor_tiss as _lt
    import motor_tiss as _mt
    _ALERTAS_TISS = [
        (_mt.ALERTA_ATRASADO, TIPO_ATRASADO,
         "A guia está na análise de conta, mas não apareceu em nenhum demonstrativo de pagamento dentro do prazo que "
         "a operadora costuma levar. Confira se o pagamento caiu; se não, cobre a operadora."),
        (_mt.ALERTA_DIVERGENCIA, TIPO_VERSOES,
         "Dois arquivos da mesma análise (PDF e XML, ou baixados em datas diferentes) trazem valores ou motivos de "
         "glosa diferentes. A operadora pode ter refeito a análise: confira no portal qual é a versão atual."),
        (_mt.ALERTA_PAGO_DIFERENTE, TIPO_PAGO_DIFERENTE,
         "O demonstrativo de pagamento pagou um valor diferente do liberado na análise de conta desta guia."),
        (_mt.ALERTA_RECURSO_VARIOS, TIPO_SEM_ORIGINAL_DEFINIDO,
         "Pagamento de recurso, mas a mesma guia tem glosa em mais de um protocolo. Confira a qual glosa ele se refere."),
        (_lt.ALERTA_GLOSA_MAIOR, TIPO_GLOSA_MAIOR,
         "A operadora glosou mais do que o valor processado da guia. Pode ser erro de cálculo: peça a correção."),
        (_lt.ALERTA_GUIA_FORA_PADRAO, TIPO_GUIA_FORA_PADRAO,
         "O número da guia tem dígitos a mais que as outras. Confira se foi digitado errado no faturamento: isso "
         "atrapalha a conferência e o recurso."),
    ]
except Exception:  # durante uma atualização, um módulo novo pode ainda não estar carregado
    _ALERTAS_TISS = []

COLUNAS_ANOMALIA = ["Tipo", "O que verificar", "Data do atendimento", "Paciente", "Guia", "Código", "Procedimento",
                    "Valor pago", "Protocolo", "Data de pagamento", "Operadora", "Arquivo"]
COLUNAS_RECURSO = ["Data do atendimento", "Paciente", "Guia", "Código", "Procedimento", "Protocolo da glosa",
                   "Data da glosa", "Motivo da glosa", "Valor glosado", "Protocolo do recurso", "Data do recurso",
                   "Valor recebido", "Falta receber", "Situação", "Operadora", "Arquivo"]


def _col(df, c, padrao=""):
    return df[c] if c in df.columns else pd.Series(padrao, index=df.index)


def _num(df, c):
    return pd.to_numeric(_col(df, c, 0.0), errors="coerce").fillna(0.0)


def _texto(df, c):
    return _col(df, c).fillna("").astype(str).str.strip()


def recursos(df):
    """Uma linha por guia glosada que foi reapresentada (recurso), com o resultado."""
    if df is None or df.empty or "Situação do recurso" not in df.columns:
        return pd.DataFrame(columns=COLUNAS_RECURSO)
    d = df[_texto(df, "Situação do recurso").ne("")]
    if d.empty:
        return pd.DataFrame(columns=COLUNAS_RECURSO)
    prot_rec = _texto(d, "Protocolo do recurso")

    def protocolo_glosa(p, pr):
        rec = {x.strip() for x in pr.split(";") if x.strip()}
        resto = [x.strip() for x in str(p).split(";") if x.strip() and x.strip() not in rec and x.strip() != "-"]
        return "; ".join(resto)

    glosado = _num(d, "Glosa original")
    recebido = _num(d, "Recebido no recurso")
    out = pd.DataFrame({
        "Data do atendimento": _texto(d, "Data do evento"),
        "Paciente": _texto(d, "Nome do paciente"),
        "Guia": _texto(d, "Doc Original"),
        "Código": _texto(d, "Código"),
        "Procedimento": _texto(d, "Procedimento"),
        "Protocolo da glosa": [protocolo_glosa(p, pr) for p, pr in zip(_texto(d, "Protocolo"), prot_rec)],
        "Data da glosa": _texto(d, "Data da glosa"),
        "Motivo da glosa": _texto(d, "Motivo da glosa"),
        "Valor glosado": glosado.round(2),
        "Protocolo do recurso": prot_rec,
        "Data do recurso": _texto(d, "Data do recurso"),
        "Valor recebido": recebido.round(2),
        "Falta receber": (glosado - recebido).clip(lower=0).round(2),
        "Situação": _texto(d, "Situação do recurso"),
        "Operadora": _texto(d, "Operadora"),
        "Arquivo": _texto(d, "Arquivo"),
    })
    if not out["Operadora"].ne("").any():
        out = out.drop(columns=["Operadora"])
    if not out["Arquivo"].ne("").any():
        out = out.drop(columns=["Arquivo"])
    return out.reset_index(drop=True)


_COLUNAS_USADAS = ["Data do evento", "Nome do paciente", "Doc Original", "Código", "Procedimento", "Valor pago",
                   "Protocolo", "Data de pagamento", "Status da glosa", "Alertas", "Motivo da glosa", "Vínculo",
                   "Valor informado", "Complemento recebido"]


def _com_colunas(d):
    """Cópia com as colunas que esta análise usa (vazias quando o arquivo não as trouxe)."""
    faltam = [c for c in _COLUNAS_USADAS if c not in d.columns]
    if faltam:
        d = d.copy()
        for c in faltam:
            d[c] = ""
    return d


def _linha(df, i, tipo, oque):
    return {"Tipo": tipo, "O que verificar": oque,
            "Data do atendimento": df.at[i, "Data do evento"], "Paciente": df.at[i, "Nome do paciente"],
            "Guia": df.at[i, "Doc Original"], "Código": df.at[i, "Código"], "Procedimento": df.at[i, "Procedimento"],
            "Valor pago": me._num(df.at[i, "Valor pago"]), "Protocolo": df.at[i, "Protocolo"],
            "Data de pagamento": df.at[i, "Data de pagamento"],
            "Operadora": df.at[i, "Operadora"] if "Operadora" in df.columns else "",
            "Arquivo": df.at[i, "Arquivo"] if "Arquivo" in df.columns else ""}


def anomalias(df):
    """Casos que pedem verificação humana. Retorna DataFrame (vazio se não houver nada)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUNAS_ANOMALIA)
    d = _com_colunas(df.reset_index(drop=True))
    linhas = []
    status = _texto(d, "Status da glosa")
    alertas = _texto(d, "Alertas")
    pago = _num(d, "Valor pago")
    guia = _texto(d, "Doc Original")
    chave = mp.chave_atendimento(d)
    # sem o nome do paciente (ex.: XML TISS) não dá para saber se é o mesmo atendimento: cada linha fica sozinha
    sem_nome = d["Nome do paciente"].map(me._norm).isin(["", "NAO IDENTIFICADO"])
    chave = chave.where(~sem_nome, pd.Series([f"#linha{i}" for i in d.index], index=d.index))
    # linhas que representam um atendimento pago (não a segunda parte de um pagamento já ligado)
    atendimento_pago = (pago > TOL) & ~status.isin([STATUS_COMPLEMENTO, STATUS_GLOSA_MANTIDA,
                                                       STATUS_DUPLICIDADE])
    por_chave = {}
    for i in d.index[atendimento_pago]:
        por_chave.setdefault(chave[i], []).append(i)

    # 1) glosa revertida em recurso, mas o mesmo atendimento já foi pago em outra guia
    situ = _texto(d, "Situação do recurso")
    for i in d.index[situ.isin([RECURSO_RECEBIDO, RECURSO_PARCIAL])]:
        outras = [j for j in por_chave.get(chave[i], []) if j != i and guia[j] not in ("", "-") and guia[j] != guia[i]]
        if not outras:
            continue
        j = outras[0]
        motivo = str(d.at[i, "Motivo da glosa"] or "").strip()
        dup = "DUPLICIDADE" in me._norm(motivo)
        oque = ((f"O plano glosou alegando duplicidade ({motivo}) e depois pagou no recurso. " if dup else
                 f"Glosa revertida em recurso{' (' + motivo + ')' if motivo else ''}. ")
                + f"Existe outra guia paga do mesmo paciente, procedimento e data: guia {guia[j]}, "
                  f"{me._br_valor(pago[j])} em {d.at[j, 'Data de pagamento']}"
                + (f" (mais {len(outras) - 1} outra(s))" if len(outras) > 1 else "")
                + ". Confira se foram duas sessões no mesmo dia; se não, foi cobrado em dobro e o plano pode "
                  "pedir a devolução.")
        linhas.append(_linha(d, i, TIPO_COBRANCA_DOBRO, oque))

    # 2) mesma guia paga por inteiro mais de uma vez
    for i in d.index[status.eq(STATUS_DUPLICIDADE)]:
        linhas.append(_linha(d, i, TIPO_PAGO_REPETIDO,
                             "A mesma guia foi paga por inteiro mais de uma vez. Confira no extrato se o valor "
                             "entrou duas vezes; se sim, o plano deve pedir a devolução."
                             + (f" {d.at[i, 'Vínculo']}" if str(d.at[i, 'Vínculo'] or '').strip() else "")))

    # 3) somando o que veio depois, recebeu mais do que o valor informado
    for i in d.index[alertas.str.contains(mp.ALERTA_ACIMA, regex=False)]:
        linhas.append(_linha(d, i, TIPO_ACIMA,
                             f"Recebeu {me._br_valor(pago[i] + me._num(d.at[i, 'Complemento recebido']))} para um "
                             f"valor informado de {me._br_valor(me._num(d.at[i, 'Valor informado']))}. Pode ser "
                             "diferença de tabela paga depois (reajuste) ou valor cadastrado desatualizado."))

    # 4) lote de reapresentação com mais de um atendimento original possível
    for i in d.index[alertas.str.contains(mp.ALERTA_VARIOS_ORIGINAIS, regex=False)]:
        linhas.append(_linha(d, i, TIPO_SEM_ORIGINAL_DEFINIDO,
                             "Pagamento num lote de recurso/complemento, mas há mais de um atendimento original do "
                             "mesmo paciente, procedimento e data. Confira a qual guia ele se refere."))

    # 5) demonstrativos TISS: atraso, versões diferentes, valores incoerentes
    for alerta, tipo, oque in _ALERTAS_TISS:
        for i in d.index[alertas.str.contains(alerta, regex=False)]:
            detalhe = next((x for x in alertas[i].split("; ") if x.startswith(alerta)), "")
            extra = detalhe[len(alerta):].strip(" :[]()") if detalhe else ""
            linhas.append(_linha(d, i, tipo, oque + (f" ({extra})" if extra else "")))

    out = pd.DataFrame(linhas, columns=COLUNAS_ANOMALIA)
    for c in ("Operadora", "Arquivo"):
        if not out[c].astype(str).str.strip().ne("").any():
            out = out.drop(columns=[c])
    return out

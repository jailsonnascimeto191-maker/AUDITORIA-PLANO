"""
Páginas do app para os três novos relatórios:

    render_producao(H)      -> "Produção do Profissional"
    render_glosas(H)        -> "Relatório de Glosas"
    render_faturamento(H)   -> "Faturamento x Recebimento"

H é um SimpleNamespace criado no APP.py com os helpers que já existem lá (cabecalho, secao, tabela,
brl, FULL_BTN, FULL_DL, valores_df, listar_profissionais, PLANOS_SAUDE, registrar_log).
"""
from datetime import date

import pandas as pd
import streamlit as st

import motor_cruzamento as mc
import motor_conhecimento
import motor_extracao
import motor_historico
import motor_relatorios as mr

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro"]
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Formatos que o motor_extracao sabe ler (usado também na Casa das Máquinas)
TIPOS_DEMONSTRATIVO = ["xlsx", "xlsm", "xls", "csv", "txt", "pdf", "xml", "docx", "html", "htm"]
TIPOS_PLANILHA = ["xlsx", "xls", "csv"]


# ─────────────────────────────────────────────────────────────
# Helpers de interface
# ─────────────────────────────────────────────────────────────
def _slug(txt):
    return motor_extracao._norm(txt).lower().replace(" ", "_") or "relatorio"


def _int_br(v):
    return f"{int(round(v)):,}".replace(",", ".")


def _metricas(itens):
    cols = st.columns(len(itens))
    for c, (rotulo, valor) in zip(cols, itens):
        c.metric(rotulo, valor)


def _date_input(rotulo, key):
    try:
        return st.date_input(rotulo, value=date.today(), format="DD/MM/YYYY", key=key)
    except TypeError:  # versões antigas do Streamlit
        return st.date_input(rotulo, value=date.today(), key=key)


def _exibir(H, df, moeda=(), pct=(), **kw):
    """Mostra um DataFrame com colunas de dinheiro formatadas em R$ e percentuais em %."""
    if df is None or df.empty:
        st.info("Nenhum registro.")
        return
    v = df.copy()
    for c in pct:
        if c in v.columns:
            v[c] = v[c].map(lambda x: "-" if pd.isna(x) else f"{x * 100:.1f}%".replace(".", ","))
    cfg = {c: st.column_config.NumberColumn(c, format="R$ %.2f") for c in moeda if c in v.columns}
    H.tabela(v, column_config=cfg, **kw)


def _ui_datas_pagamento(arquivos, chave):
    """Permite informar a data de pagamento de um demonstrativo que não a traz (nem na tabela nem no topo)."""
    datas = {}
    if not arquivos:
        return datas
    with st.expander("Data de pagamento dos demonstrativos (só preencha se o arquivo não informar)"):
        st.caption("O sistema procura a data de pagamento dentro do arquivo. Se não achar, "
                   "marque o arquivo abaixo e informe a data.")
        for i, a in enumerate(arquivos):
            c1, c2 = st.columns(2)
            if c1.checkbox(f"Informar para: {a.name}", key=f"{chave}_pagto_usar_{i}"):
                with c2:
                    datas[a.name] = _date_input("Data de pagamento", f"{chave}_pagto_{i}")
    return datas


def _ler_demonstrativos(arquivos, plano, datas):
    """Lê TODAS as linhas (e abas) de cada demonstrativo. Retorna (consolidado, erros, resumo_por_arquivo)."""
    itens, erros, resumo = [], [], []
    for a in arquivos:
        df, erro = motor_conhecimento.extrair(
            a, plano=plano, somente_glosas=False, data_pagamento_padrao=datas.get(a.name))
        if df.empty:
            erros.append(f"{a.name}: {erro or 'nada encontrado'}")
            continue
        itens.append((a.name, df))
        resumo.append({
            "Arquivo": a.name, "Operadora": df.attrs.get("operadora", ""),
            "Abas/tabelas com dados": f"{df.attrs.get('abas_com_dados', 1)} de {df.attrs.get('abas_total', 1)}",
            "Linhas lidas": len(df),
            "Colunas reconhecidas": ", ".join(df.attrs.get("mapeamento", {}).keys()),
        })
    return mc.consolidar_demonstrativos(itens), erros, pd.DataFrame(resumo)


def _downloads(H, res, base, chave):
    c1, c2 = st.columns(2)
    c1.download_button("Baixar Excel", res["xlsx"], file_name=f"{base}.xlsx", mime=MIME_XLSX,
                       key=f"dl_x_{chave}", **H.FULL_DL)
    c2.download_button("Baixar PDF", res["pdf"], file_name=f"{base}.pdf", mime="application/pdf",
                       key=f"dl_p_{chave}", **H.FULL_DL)


def _vazio(H, titulo, texto, expressao="normal", item=None):
    fn = getattr(H, "vazio", None)
    if fn:
        fn(titulo, texto, expressao, item)
    else:
        st.info(f"{titulo}. {texto}")


def _log(H, acao, detalhe):
    fn = getattr(H, "registrar_log", None)
    if fn:
        fn(acao, detalhe)


# ─────────────────────────────────────────────────────────────
# 1) Produção do profissional
# ─────────────────────────────────────────────────────────────
def render_producao(H):
    H.cabecalho(
        "Produção do profissional",
        "Cruze o controle de atendimento com o demonstrativo do plano e gere o espelho da produção do mês.",
    )
    profs = H.listar_profissionais()
    if not profs.empty:
        profs = profs[profs["ativo"] == 1]
    if profs.empty:
        _vazio(H, "Cadastre a equipe primeiro", "Cadastre ao menos um profissional ativo em Cadastros para montar o "
                  "relatório de produção.", "normal", "prancheta")
        return

    rotulos = {int(r.id): f"{r.nome} — {r.registro} ({r.especialidade.title()})" for r in profs.itertuples()}
    H.secao("1. Profissional e mês")
    c1, c2, c3 = st.columns([3, 1.3, 1])
    pid = c1.selectbox("Profissional analisado", list(rotulos), format_func=rotulos.get, key="prod_prof")
    hoje = date.today()
    mes = c2.selectbox("Mês de produção", list(range(1, 13)), index=hoje.month - 1,
                       format_func=lambda m: MESES[m - 1], key="prod_mes")
    ano = int(c3.number_input("Ano", min_value=2020, max_value=2100, value=hoje.year, step=1, key="prod_ano"))
    prof = profs[profs["id"] == pid].iloc[0]

    H.secao("2. Arquivos")
    u1, u2 = st.columns(2)
    arq_ctrl = u1.file_uploader("Controle de atendimento (Excel ou CSV)", type=TIPOS_PLANILHA, key="prod_ctrl")
    arqs_demo = u2.file_uploader("Demonstrativo(s) de pagamento (opcional)", type=TIPOS_DEMONSTRATIVO,
                                 accept_multiple_files=True, key="prod_demo")

    H.secao("3. Opções")
    planos = [p for p in H.PLANOS_SAUDE if p != "Identificar pelo arquivo"]
    o1, o2 = st.columns(2)
    plano_padrao = o1.selectbox("Plano padrão (se o controle não tiver coluna de plano)", planos, key="prod_plano_padrao")
    plano_op = o2.selectbox("Operadora do demonstrativo", H.PLANOS_SAUDE, key="prod_plano_op")
    descontar = st.checkbox(
        "Descontar a glosa do repasse (reduz o repasse na mesma proporção da glosa do atendimento)",
        value=False, key="prod_descontar")
    datas = _ui_datas_pagamento(arqs_demo, "prod")

    if st.button("Gerar relatório de produção", type="primary", **H.FULL_BTN):
        if arq_ctrl is None:
            st.warning("Envie o controle de atendimento do profissional.")
        else:
            with H.carregando("Lendo o controle, cruzando com o demonstrativo e montando o relatório..."):
                ctrl, erro = mc.ler_controle_atendimento(arq_ctrl, plano_padrao=plano_padrao)
                if erro:
                    st.error(f"Controle de atendimento: {erro}")
                    return
                sem_data = int((ctrl["Data"] == "-").sum())
                ctrl_mes = mc.filtrar_competencia(ctrl, "Data", ano, mes)
                if ctrl_mes.empty:
                    st.warning(f"O controle não tem atendimentos em {MESES[mes - 1]}/{ano}. "
                               "Confira o mês e o ano escolhidos.")
                    return

                demo, erros_demo, resumo_arqs = pd.DataFrame(), [], pd.DataFrame()
                if arqs_demo:
                    demo, erros_demo, resumo_arqs = _ler_demonstrativos(arqs_demo, plano_op, datas)

                cruz, so_demo = mc.cruzar_controle_demonstrativo(ctrl_mes, demo if not demo.empty else None)
                esp_nome = prof["especialidade"]
                tab_f = H.valores_df("faturamento", esp_nome)
                tab_r = H.valores_df("repasse", esp_nome)
                espelho = mc.montar_espelho_producao(cruz, tab_f, tab_r, descontar_glosa=descontar)
                resumo = mc.resumo_producao(espelho)
                por_plano = mc.producao_por_plano(espelho)
                competencia = f"{MESES[mes - 1]}/{ano}"
                spec = mr.spec_producao(prof["nome"], prof["registro"], esp_nome.title(), competencia,
                                        espelho, resumo, por_plano, so_demo, descontou_glosa=descontar)
                st.session_state["rel_producao"] = dict(
                    espelho=espelho, resumo=resumo, por_plano=por_plano, so_demo=so_demo,
                    xlsx=mr.gerar_excel(spec), pdf=mr.gerar_pdf(spec),
                    base=f"producao_{_slug(prof['nome'])}_{ano}-{mes:02d}",
                    avisos=erros_demo
                    + ([f"{sem_data} linha(s) do controle sem data válida ficaram fora da competência."]
                       if sem_data else [])
                    + ([f"Não há valores de faturamento cadastrados para {esp_nome.title()}; "
                        "usei o valor informado no demonstrativo quando existia."] if tab_f.empty else [])
                    + ([f"Não há valores de repasse cadastrados para {esp_nome.title()}; o repasse ficou zerado."]
                       if tab_r.empty else []),
                    resumo_arqs=resumo_arqs, tem_demo=not demo.empty,
                    titulo=f"{prof['nome']} - {competencia}")
            _log(H, "Relatório de produção", f"{prof['nome']} | {competencia}")

    res = st.session_state.get("rel_producao")
    if not res:
        st.info("Escolha o profissional e o mês, envie o controle de atendimento e clique em **Gerar relatório**.")
        return

    st.caption(f"Relatório gerado para: {res['titulo']}")
    for a in res["avisos"]:
        st.warning(a)
    r = res["resumo"]
    H.secao("Resumo da produção")
    _metricas([("Atendimentos", _int_br(r["atendimentos"])), ("Pacientes", _int_br(r["pacientes"])),
               ("Total a receber (tabela)", H.brl(r["receber"])), ("Pago pelo plano", H.brl(r["pago"]))])
    _metricas([("Glosado", H.brl(r["glosa"])), ("Repasse ao profissional", H.brl(r["repasse"])),
               ("Não localizados", _int_br(r["nao_localizados"])),
               ("Informados só pelo plano", _int_br(len(res["so_demo"])))])
    _downloads(H, res, res["base"], "prod")

    moeda = ["Valor unitário (plano)", "Valor total a receber", "Valor pago pelo plano", "Valor da glosa",
             "Repasse unitário", "Repasse ao profissional"]
    abas = st.tabs(["Espelho da produção", "Resumo por plano", "Não localizados", "Só no demonstrativo",
                    "Arquivos lidos"])
    with abas[0]:
        _exibir(H, res["espelho"], moeda)
    with abas[1]:
        _exibir(H, res["por_plano"], ["Valor total a receber", "Valor pago pelo plano", "Valor da glosa",
                                       "Repasse ao profissional"])
    with abas[2]:
        nl = res["espelho"][res["espelho"]["Situação"].str.startswith("Não localizado")]
        st.caption("Atendimentos do controle que não aparecem no demonstrativo: confira se foram faturados.")
        _exibir(H, nl[["Data", "Paciente", "Plano", "Tempo", "Quantidade", "Guia", "Lote"]])
    with abas[3]:
        st.caption("Itens que o plano informou para estes pacientes, mas que não estão no controle do mês.")
        _exibir(H, res["so_demo"], ["Valor informado", "Valor pago", "Valor da glosa"])
    with abas[4]:
        _exibir(H, res["resumo_arqs"])


# ─────────────────────────────────────────────────────────────
# 2) Relatório de glosas
# ─────────────────────────────────────────────────────────────
def render_glosas(H):
    H.cabecalho(
        "Relatório de glosas",
        "Tudo o que foi glosado: data, paciente, guia do prestador, lote e motivo. Exporta para Excel e PDF.",
    )
    ultimo = st.session_state.get("ultimo_processamento", pd.DataFrame())
    HIST = "Histórico (todos os demonstrativos já processados)"
    opcoes = ["Enviar demonstrativo(s)"]
    if motor_historico.operadoras():
        opcoes.insert(0, HIST)
    if ultimo is not None and not ultimo.empty:
        opcoes.insert(0, "Usar o último demonstrativo processado (Casa das Máquinas)")
    H.secao("1. Origem dos dados")
    origem = st.radio("Origem dos dados", opcoes, key="glo_origem", horizontal=True)

    arqs, plano_op, datas = [], motor_extracao.PLANO_AUTOMATICO, {}
    if origem.startswith("Enviar"):
        arqs = st.file_uploader("Demonstrativo(s) de pagamento (todas as abas serão lidas)",
                                type=TIPOS_DEMONSTRATIVO, accept_multiple_files=True, key="glo_arqs")
        plano_op = st.selectbox("Operadora / plano de saúde", H.PLANOS_SAUDE, key="glo_plano")

    if st.button("Gerar relatório de glosas", type="primary", **H.FULL_BTN):
        with H.carregando("Lendo o(s) demonstrativo(s) e montando o relatório..."):
            erros, resumo_arqs = [], pd.DataFrame()
            if origem.startswith("Enviar"):
                if not arqs:
                    st.warning("Envie ao menos um demonstrativo.")
                    return
                demo, erros, resumo_arqs = _ler_demonstrativos(arqs, plano_op, datas)
                nomes = [a.name for a in arqs]
            elif origem == HIST:
                demo = motor_historico.carregar_itens().drop(columns=["_iso"], errors="ignore")
                nomes = ["Histórico de demonstrativos"]
            else:
                demo = ultimo.copy()
                demo.attrs.update(ultimo.attrs)
                if "Operadora" not in demo.columns:
                    demo["Operadora"] = ultimo.attrs.get("operadora", "")
                nomes = ["Último demonstrativo processado"]
            if demo.empty:
                st.error("Não consegui extrair dados. " + " | ".join(erros))
                return
            glosas = demo[demo["Valor da glosa"] > 0.005].reset_index(drop=True)
            st.session_state["rel_glosas_base"] = dict(demo=demo, glosas=glosas, nomes=nomes, erros=erros,
                                                       resumo_arqs=resumo_arqs)
            st.session_state.pop("rel_glosas", None)

    base = st.session_state.get("rel_glosas_base")
    if not base:
        st.info("Escolha a origem dos dados e clique em **Gerar relatório de glosas**.")
        return
    for e in base["erros"]:
        st.warning(e)
    glosas = base["glosas"]
    if glosas.empty:
        _vazio(H, "Nenhuma glosa encontrada", "Os demonstrativos analisados não têm itens glosados.", "feliz", "moeda")
        _exibir(H, base["resumo_arqs"])
        return

    # filtros opcionais (valem para a tela e para os arquivos exportados)
    f1, f2 = st.columns(2)
    ops = sorted({str(x) for x in glosas.get("Operadora", pd.Series(dtype=str)) if str(x)})
    sel_ops = f1.multiselect("Filtrar por operadora", ops, default=ops, key="glo_f_ops") if len(ops) > 1 else ops
    busca = f2.text_input("Buscar (paciente, guia, motivo...)", key="glo_busca")
    vis = glosas
    if ops and sel_ops:
        vis = vis[vis["Operadora"].astype(str).isin(sel_ops)]
    if busca.strip():
        m = vis.astype(str).apply(lambda c: c.str.contains(busca.strip(), case=False, na=False, regex=False)).any(axis=1)
        vis = vis[m]
    vis = vis.reset_index(drop=True)
    if vis.empty:
        st.warning("Nenhuma glosa com esses filtros.")
        return

    spec = mr.spec_glosas(vis, base["demo"], base["nomes"])
    chave = (len(vis), round(float(vis["Valor da glosa"].sum()), 2), tuple(sel_ops), busca.strip())
    cache = st.session_state.get("rel_glosas")
    if not cache or cache["chave"] != chave:
        with H.carregando("Montando Excel e PDF..."):
            cache = dict(chave=chave, xlsx=mr.gerar_excel(spec), pdf=mr.gerar_pdf(spec))
        st.session_state["rel_glosas"] = cache
        _log(H, "Relatório de glosas", f"{len(vis)} itens | {', '.join(base['nomes'])}")

    total = float(vis["Valor da glosa"].sum())
    apres = float(base["demo"]["Valor informado"].sum())
    H.secao("Resumo das glosas")
    _metricas([("Itens glosados", _int_br(len(vis))),
               ("Guias com glosa", _int_br(vis["Doc Original"].replace("-", pd.NA).nunique())),
               ("Valor glosado", H.brl(total)),
               ("% do apresentado", f"{(total / apres * 100) if apres else 0:.1f}%".replace(".", ","))])
    _downloads(H, cache, f"relatorio_glosas_{date.today():%Y-%m-%d}", "glo")

    nomes_abas = ["Relação de glosas", "Por motivo", "Por operadora", "Por lote / protocolo", "Arquivos lidos"]
    abas = st.tabs(nomes_abas)
    d = spec["detalhes"][0]
    with abas[0]:
        _exibir(H, d["df"], d["moeda"])
    for aba, res in zip(abas[1:4], spec["resumos"]):
        with aba:
            _exibir(H, res["df"], res.get("moeda", ()), res.get("pct", ()))
    with abas[4]:
        _exibir(H, base["resumo_arqs"])


# ─────────────────────────────────────────────────────────────
# 3) Faturamento x recebimento
# ─────────────────────────────────────────────────────────────
def render_faturamento(H):
    H.cabecalho(
        "Faturamento x recebimento",
        "Confira se tudo o que foi faturado nos lotes foi pago, em que mês e com quantos dias de demora.",
    )
    H.secao("1. Arquivos")
    u1, u2 = st.columns(2)
    arqs_fat = u1.file_uploader("Faturamento (lote com as guias)", type=TIPOS_PLANILHA,
                                accept_multiple_files=True, key="fat_arqs")
    arqs_demo = u2.file_uploader("Demonstrativo(s) de pagamento", type=TIPOS_DEMONSTRATIVO,
                                 accept_multiple_files=True, key="fat_demo")
    H.secao("2. Opções")
    planos = [p for p in H.PLANOS_SAUDE if p != "Identificar pelo arquivo"]
    o1, o2 = st.columns(2)
    plano_fat = o1.selectbox("Plano do faturamento (se o arquivo não tiver coluna de plano)", planos, key="fat_plano")
    plano_op = o2.selectbox("Operadora do demonstrativo", H.PLANOS_SAUDE, key="fat_plano_op")
    usar_envio = st.checkbox("O arquivo de faturamento não traz a data de envio: informar a data de envio do lote",
                             key="fat_usar_envio")
    data_envio = _date_input("Data de envio do lote", "fat_envio") if usar_envio else None
    datas = _ui_datas_pagamento(arqs_demo, "fat")

    if st.button("Analisar faturamento x recebimento", type="primary", **H.FULL_BTN):
        if not arqs_fat or not arqs_demo:
            st.warning("Envie o faturamento e o demonstrativo de pagamento.")
        else:
            with H.carregando("Lendo os arquivos e conferindo guia por guia..."):
                partes, erros = [], []
                for a in arqs_fat:
                    f, erro = mc.ler_faturamento(a, plano_padrao=plano_fat)
                    if erro:
                        erros.append(f"{a.name}: {erro}")
                    else:
                        partes.append(f)
                if not partes:
                    st.error("Não consegui ler o faturamento. " + " | ".join(erros))
                    return
                fat = pd.concat(partes, ignore_index=True)
                demo, erros_demo, resumo_arqs = _ler_demonstrativos(arqs_demo, plano_op, datas)
                if demo.empty:
                    st.error("Não consegui ler o demonstrativo. " + " | ".join(erros_demo))
                    return
                res = mc.cruzar_faturamento_recebimento(fat, demo, data_envio_padrao=data_envio)
                spec = mr.spec_faturamento(res, [a.name for a in arqs_fat], [a.name for a in arqs_demo])
                st.session_state["rel_faturamento"] = dict(
                    res=res, spec=spec, xlsx=mr.gerar_excel(spec), pdf=mr.gerar_pdf(spec),
                    avisos=erros + erros_demo, resumo_arqs=resumo_arqs,
                    base=f"faturamento_x_recebimento_{date.today():%Y-%m-%d}")
            _log(H, "Faturamento x recebimento", f"{len(res)} guias | {len(arqs_fat)} faturamento(s)")

    out = st.session_state.get("rel_faturamento")
    if not out:
        st.info("Envie o faturamento (lote) e o demonstrativo e clique em **Analisar**.")
        return

    for a in out["avisos"]:
        st.warning(a)
    res, spec = out["res"], out["spec"]
    sem_envio = (res["Base do prazo"] == "Data do atendimento").any() if len(res) else False
    if sem_envio:
        st.info("O faturamento não trouxe data de envio do lote. O prazo de pagamento foi contado a partir da "
                "data do atendimento. Para contar do envio, informe a data de envio acima.")

    k = {rot: val for rot, val, _ in spec["kpis"]}
    H.secao("Resumo")
    _metricas([("Guias faturadas", _int_br(k["Guias faturadas"])), ("Faturado", H.brl(k["Valor faturado"])),
               ("Pago", H.brl(k["Valor pago"])), ("Glosado", H.brl(k["Valor glosado"]))])
    _metricas([("Em aberto (cobrar)", H.brl(k["Valor em aberto (cobrar)"])),
               ("% já pago", f"{k['% do faturado já pago'] * 100:.1f}%".replace(".", ",")),
               ("Prazo médio (dias)", _int_br(k["Prazo médio de pagamento (dias)"])),
               ("Sem retorno no demonstrativo", _int_br(k["Guias sem retorno no demonstrativo"]))])
    _downloads(H, out, out["base"], "fat")

    fm = ["Valor faturado", "Valor pago", "Valor da glosa", "Valor em aberto"]
    abas = st.tabs(["A cobrar", "Conferência por guia", "Por plano", "Por lote", "Por mês de pagamento",
                    "Por situação", "Arquivos lidos"])
    with abas[0]:
        st.caption("Guias não pagas, glosadas ou pagas a menor: base para a cobrança ao plano.")
        _exibir(H, spec["detalhes"][0]["df"], fm)
    with abas[1]:
        _exibir(H, spec["detalhes"][1]["df"], fm)
    titulos = {"Por plano de saúde": 2, "Por lote": 3, "Por mês de pagamento": 4, "Por situação do pagamento": 5}
    for r in spec["resumos"]:
        i = titulos.get(r["titulo"])
        if i is not None:
            with abas[i]:
                _exibir(H, r["df"], fm, ["% pago"])
    with abas[6]:
        _exibir(H, out["resumo_arqs"])

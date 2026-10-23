"""
Motor de cruzamento de dados do sistema Espaço Saúde.

Três usos principais:

1) Produção do profissional
   ler_controle_atendimento()  ->  cruzar_controle_demonstrativo()  ->  montar_espelho_producao()

2) Relatório de glosas (usa direto o DataFrame do motor_extracao; ver relatorio de glosas em motor_relatorios)

3) Faturamento x recebimento
   ler_faturamento()  ->  cruzar_faturamento_recebimento()  ->  resumir_recebimento()

Os demonstrativos devem ser lidos com motor_extracao.extrair_glosas_de_arquivo(..., somente_glosas=False)
(para ter TODAS as linhas, não só as glosadas) e reunidos com consolidar_demonstrativos().
"""
import csv
import io
import re
from difflib import SequenceMatcher

import pandas as pd

import motor_extracao as me

_norm = me._norm
_txt = me._txt

TOL = 0.02  # tolerância (R$) nas comparações de valores

# --------------------------------------------------------------------------
# Configuração dos campos dos arquivos de entrada
# --------------------------------------------------------------------------
CAMPOS_CONTROLE = {
    "Data": dict(
        tipo="data",
        sin=["DATA ATENDIMENTO", "DATA DO ATENDIMENTO", "DATA SESSAO", "DATA REALIZACAO", "DATA", "DT"],
        excl=["NASC", "PAGAMENTO", "VENC", "ENVIO", "EMISSAO"],
        exige_nome=True,
    ),
    "Paciente": dict(
        tipo="nome",
        sin=["NOME PACIENTE", "NOME DO PACIENTE", "PACIENTE", "NOME BENEFICIARIO", "BENEFICIARIO",
             "CLIENTE", "NOME"],
        excl=["MEDICO", "PROFISSIONAL", "PLANO", "OPERADORA", "CONVENIO", "MAE", "RESPONSAVEL",
              "TERAPEUTA", "PRESTADOR"],
    ),
    "Plano": dict(
        tipo="livre",
        sin=["PLANO DE SAUDE", "PLANO", "CONVENIO", "OPERADORA"],
        excl=["DATA", "VALOR", "NUMERO", "CARTEIRA", "CODIGO"],
    ),
    "Quantidade": dict(
        tipo="livre",
        sin=["QUANTIDADE", "QTD", "QTDE", "SESSOES", "SESSAO", "ATENDIMENTOS", "QUANT"],
        excl=["VALOR", "VL", "VLR"],
    ),
    "Tempo": dict(
        tipo="livre",
        sin=["TEMPO ATENDIMENTO", "TEMPO DE ATENDIMENTO", "TEMPO", "DURACAO", "MINUTOS"],
        excl=[],
    ),
    "Guia": dict(
        tipo="id",
        sin=["GUIA PRESTADOR", "NUMERO GUIA", "NRO GUIA", "GUIA", "SENHA"],
        excl=["DATA", "VALOR"],
    ),
    "Lote": dict(
        tipo="id",
        sin=["NUMERO LOTE", "NRO LOTE", "LOTE"],
        excl=["DATA", "VALOR"],
    ),
    "Código": dict(
        tipo="codigo",
        sin=["CODIGO TUSS", "TUSS", "CODIGO", "COD"],
        excl=["GUIA", "LOTE", "CARTEIRA", "CPF"],
    ),
    "Procedimento": dict(
        tipo="livre",
        sin=["PROCEDIMENTO", "DESCRICAO", "SERVICO"],
        excl=["CODIGO", "VALOR", "DATA"],
    ),
}

CAMPOS_FATURAMENTO = {
    "Lote": dict(tipo="id", sin=["NUMERO LOTE", "NRO LOTE", "NR LOTE", "LOTE"], excl=["DATA", "VALOR"]),
    "Guia": dict(
        tipo="id",
        sin=["GUIA PRESTADOR", "NUMERO GUIA PRESTADOR", "NUMERO GUIA", "NRO GUIA", "NR GUIA", "GUIA",
             "DOC ORIGINAL", "DOCUMENTO", "SENHA"],
        excl=["DATA", "VALOR", "OPERADORA", "CARTEIRA", "CPF"],
    ),
    "Paciente": dict(
        tipo="nome",
        sin=["NOME PACIENTE", "NOME DO PACIENTE", "PACIENTE", "NOME BENEFICIARIO", "BENEFICIARIO",
             "CLIENTE", "NOME"],
        excl=["MEDICO", "PROFISSIONAL", "PLANO", "OPERADORA", "CONVENIO", "MAE", "RESPONSAVEL",
              "TERAPEUTA", "PRESTADOR"],
    ),
    "Plano": dict(
        tipo="livre",
        sin=["PLANO DE SAUDE", "PLANO", "CONVENIO", "OPERADORA"],
        excl=["DATA", "VALOR", "NUMERO", "CARTEIRA", "CODIGO"],
    ),
    "Data atendimento": dict(
        tipo="data",
        sin=["DATA ATENDIMENTO", "DATA DO ATENDIMENTO", "DATA REALIZACAO", "DATA EXECUCAO", "DATA SESSAO",
             "DATA EVENTO", "DATA", "DT"],
        excl=["NASC", "PAGAMENTO", "VENC", "ENVIO", "FATURAMENTO", "REMESSA", "PROTOCOLO", "ENTREGA", "EMISSAO"],
        exige_nome=True,
    ),
    "Data envio": dict(
        tipo="data",
        sin=["DATA ENVIO", "DATA DE ENVIO", "DT ENVIO", "DATA FATURAMENTO", "DATA REMESSA",
             "DATA ENTREGA", "DATA PROTOCOLO"],
        excl=["ATENDIMENTO", "NASC"],
        exige_nome=True,
    ),
    "Valor faturado": dict(
        tipo="dinheiro",
        sin=["VALOR FATURADO", "VALOR APRESENTADO", "VALOR INFORMADO", "VALOR COBRADO", "VALOR TOTAL",
             "FATURADO", "APRESENTADO", "TOTAL", "VALOR", "VLR"],
        excl=["GLOSA", "PAGO", "UNIT", "UNITARIO", "QTD", "QTDE", "QUANTIDADE"],
    ),
    "Quantidade": dict(
        tipo="livre",
        sin=["QUANTIDADE", "QTD", "QTDE", "SESSOES", "SESSAO", "QUANT"],
        excl=["VALOR", "VL", "VLR"],
    ),
}

COLUNAS_CONTROLE = ["Data", "Paciente", "Plano", "Tempo", "Quantidade", "Guia", "Lote", "Código",
                    "Procedimento", "Aba"]
COLUNAS_FATURAMENTO = ["Lote", "Guia", "Paciente", "Plano", "Data atendimento", "Valor faturado",
                       "Quantidade", "Data envio", "Aba"]


# --------------------------------------------------------------------------
# Leitura genérica
# --------------------------------------------------------------------------
def _abas_brutas(arquivo):
    """Devolve [(nome_da_aba, DataFrame bruto)] — lê TODAS as abas de um Excel."""
    nome = (getattr(arquivo, "name", "") or "").lower()
    arquivo.seek(0)
    dados = arquivo.read()
    if not dados:
        raise ValueError("O arquivo está vazio.")
    if nome.endswith((".xlsx", ".xlsm", ".xls")):
        abas = pd.read_excel(io.BytesIO(dados), sheet_name=None, header=None, dtype=object)
        return list(abas.items())
    if nome.endswith((".csv", ".txt", ".tsv")):
        texto = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                texto = dados.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if texto is None:
            raise ValueError("Erro de encoding no CSV.")
        sep = me._detectar_separador(texto)
        linhas = [l for l in csv.reader(io.StringIO(texto), delimiter=sep) if any(c.strip() for c in l)]
        if not linhas:
            raise ValueError("O arquivo não tem linhas com conteúdo.")
        largura = max(len(l) for l in linhas)
        bruto = pd.DataFrame([l + [None] * (largura - len(l)) for l in linhas], dtype=object)
        return [("arquivo", bruto)]
    raise ValueError(f"Formato não suportado: {getattr(arquivo, 'name', '')}. Use Excel (.xlsx/.xls) ou CSV.")


def _mapear(tabela, campos):
    """Atribui a cada campo a melhor coluna (pelo nome do cabeçalho + conteúdo)."""
    cols = list(tabela.columns)
    perfis = {c: me._perfil(tabela[c]) for c in cols}
    hn = {c: _norm(c) for c in cols}
    cand = []
    for campo in campos:
        for c in cols:
            s = me._score_campo(campo, hn[c], perfis[c], campos)
            if s >= me.LIMIAR_ATRIBUICAO:
                outro = max((me._score_nome(hn[c], o, campos) for o in campos if o != campo), default=0.0)
                if outro >= 70 and me._score_nome(hn[c], campo, campos) < me.LIMIAR_ATRIBUICAO:
                    continue
                cand.append((s, campo, c))
    cand.sort(key=lambda x: -x[0])
    mapa, usadas = {}, set()
    for s, campo, c in cand:
        if campo not in mapa and c not in usadas:
            mapa[campo] = c
            usadas.add(c)
    return mapa


def _serie(tabela, mapa, campo, fn=_txt, padrao=""):
    if campo in mapa:
        return tabela[mapa[campo]].apply(fn)
    return pd.Series([padrao] * len(tabela), index=tabela.index)


def _qtd(v):
    q = me.limpar_valor_monetario(v)
    return q if q > 0 else 1.0


def _ffill(serie, invalidos=("", "-")):
    return serie.replace(list(invalidos), pd.NA).ffill()


def _eh_nome_plausivel(v):
    n = _norm(v)
    return len(n) >= 5 and any(ch.isalpha() for ch in n)


# --------------------------------------------------------------------------
# 1) Controle de atendimento do profissional
# --------------------------------------------------------------------------
def ler_controle_atendimento(arquivo, plano_padrao=None):
    """Lê o controle de atendimento (todas as abas). Retorna (DataFrame, erro_ou_None).

    Colunas: Data, Paciente, Plano, Tempo, Quantidade, Guia, Lote, Código, Procedimento, Aba.
    O plano vem da coluna de plano do controle; se não existir, usa plano_padrao."""
    vazio = pd.DataFrame(columns=COLUNAS_CONTROLE)
    try:
        abas = _abas_brutas(arquivo)
    except Exception as e:
        return vazio, str(e)

    partes, mapa_ref, cabecalhos = [], {}, []
    for nome_aba, raw in abas:
        try:
            tabela = me._preparar_tabela(raw, CAMPOS_CONTROLE)
        except Exception:
            continue
        if tabela.empty or tabela.shape[1] < 2:
            continue
        cabecalhos.append([str(c) for c in tabela.columns][:12])
        mapa = _mapear(tabela, CAMPOS_CONTROLE)
        if "Paciente" not in mapa or "Data" not in mapa:
            continue
        out = pd.DataFrame(index=tabela.index)
        out["Data"] = _serie(tabela, mapa, "Data", me.padronizar_data, "-")
        out["Paciente"] = _serie(tabela, mapa, "Paciente")
        out["Plano"] = _serie(tabela, mapa, "Plano")
        out["Tempo"] = _serie(tabela, mapa, "Tempo")
        out["Quantidade"] = _serie(tabela, mapa, "Quantidade", _qtd, 1.0)
        out["Guia"] = _serie(tabela, mapa, "Guia")
        out["Lote"] = _serie(tabela, mapa, "Lote")
        out["Código"] = _serie(tabela, mapa, "Código")
        out["Procedimento"] = _serie(tabela, mapa, "Procedimento")

        # dados hierárquicos (nome/data/plano escritos só na primeira linha do bloco)
        for c in ("Data", "Paciente", "Plano"):
            out[c] = _ffill(out[c])
        out = out[out["Paciente"].notna()]
        out = out[out["Paciente"].map(_eh_nome_plausivel)]
        out["Data"] = out["Data"].fillna("-")
        out["Plano"] = out["Plano"].fillna(plano_padrao or "Não informado")
        out["Aba"] = str(nome_aba)
        if not out.empty:
            partes.append(out)
            mapa_ref = mapa_ref or mapa

    if not partes:
        dica = f" Cabeçalhos vistos: {cabecalhos[0]}" if cabecalhos else ""
        return vazio, ("Não encontrei as colunas de paciente e de data no controle de atendimento." + dica)

    df = pd.concat(partes, ignore_index=True)[COLUNAS_CONTROLE]
    df.attrs["mapeamento"] = mapa_ref
    df.attrs["abas_com_dados"] = len(partes)
    df.attrs["abas_total"] = len(abas)
    return df, None


def filtrar_competencia(df, coluna, ano, mes):
    """Mantém só as linhas da competência (mês/ano) escolhida. Datas inválidas ficam de fora."""
    if df is None or df.empty:
        return df
    dt = pd.to_datetime(df[coluna], format="%d/%m/%Y", errors="coerce")
    return df[(dt.dt.year == ano) & (dt.dt.month == mes)].reset_index(drop=True)


# --------------------------------------------------------------------------
# Demonstrativos
# --------------------------------------------------------------------------
def consolidar_demonstrativos(itens):
    """itens: lista de (nome_arquivo, DataFrame de extrair_glosas_de_arquivo).
    Junta tudo, marca Arquivo/Operadora e guarda em attrs se a quantidade foi encontrada."""
    partes, qtd_ok, mapas = [], False, {}
    for nome, d in itens:
        if d is None or d.empty:
            continue
        x = d.copy()
        # quantidade desconhecida ou zero (ex.: consultas no extrato do Bradesco) conta como 1
        q = pd.to_numeric(x["Quantidade"], errors="coerce") if "Quantidade" in x.columns else pd.Series(1.0, index=x.index)
        x["Quantidade"] = q.where(q > 0, 1.0).fillna(1.0)
        x["Arquivo"] = nome
        x["Operadora"] = d.attrs.get("operadora", "")
        partes.append(x)
        m = d.attrs.get("mapeamento") or {}
        qtd_ok = qtd_ok or ("Quantidade" in m)
        mapas.update({k: v for k, v in m.items() if k not in mapas})
    if not partes:
        out = pd.DataFrame(columns=me.COLUNAS_COMPLETAS + ["Arquivo", "Operadora"])
    else:
        out = pd.concat(partes, ignore_index=True)
    out.attrs["qtd_encontrada"] = qtd_ok
    out.attrs["mapeamento"] = mapas
    return out


def _garantir_colunas(d):
    d = d.copy()
    padrao = {"Data do evento": "-", "Protocolo": "-", "Doc Original": "-", "Nome do paciente": "",
              "Código": "-", "Procedimento": "", "Valor informado": 0.0, "Valor pago": 0.0,
              "Valor da glosa": 0.0, "Motivo da glosa": "", "Quantidade": 1.0, "Lote": "-",
              "Complemento recebido": 0.0,
              "Status da glosa": "", "Data de pagamento": "-"}
    for c, v in padrao.items():
        if c not in d.columns:
            d[c] = v
    return d


# --------------------------------------------------------------------------
# Comparação de nomes
# --------------------------------------------------------------------------
_STOP = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def _tokens(n):
    return [t for t in n.split() if t not in _STOP]


def nomes_equivalentes(a, b, limiar=0.9):
    """a e b já normalizados (_norm). Tolera nomes do meio abreviados/omitidos e pequenos erros."""
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) >= 2 and len(tb) >= 2 and ta[0] == tb[0] and ta[-1] == tb[-1]:
        sa, sb = set(ta), set(tb)
        if sa <= sb or sb <= sa:
            return True
        if SequenceMatcher(None, a, b).ratio() >= 0.8:
            return True
    return SequenceMatcher(None, a, b).ratio() >= limiar


def _mapa_nomes(nomes_origem, nomes_destino):
    """Para cada nome de origem, o nome equivalente em destino (ou ausente se não houver)."""
    destino = sorted({n for n in nomes_destino if n})
    set_dest = set(destino)
    por_inicial = {}
    for n in destino:
        por_inicial.setdefault(n[0], []).append(n)
    res = {}
    for a in {n for n in nomes_origem if n}:
        if a in set_dest:
            res[a] = a
            continue
        melhor, melhor_r = None, 0.0
        for b in por_inicial.get(a[0], []):
            if nomes_equivalentes(a, b):
                r = SequenceMatcher(None, a, b).ratio()
                if r > melhor_r:
                    melhor, melhor_r = b, r
        if melhor:
            res[a] = melhor
    return res


# --------------------------------------------------------------------------
# Agregação do demonstrativo
# --------------------------------------------------------------------------
def _jn(serie):
    vs = []
    for v in serie:
        v = str(v).strip()
        if v and v not in ("-", "nan", "None") and v not in vs:
            vs.append(v)
    return "; ".join(vs)


def _data_min(serie):
    dts = pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce").dropna()
    return dts.min().strftime("%d/%m/%Y") if len(dts) else "-"


def _meses(serie):
    dts = pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce").dropna().sort_values()
    out = []
    for d in dts:
        m = d.strftime("%m/%Y")
        if m not in out:
            out.append(m)
    return "; ".join(out) if out else "-"


def _agregar(d, chaves):
    spec = {
        "Nome do paciente": ("Nome do paciente", "first"),
        "Data do evento": ("Data do evento", "first"),
        "Código": ("Código", _jn),
        "Valor informado": ("Valor informado", "sum"),
        "Valor pago": ("Valor pago", "sum"),
        "Valor da glosa": ("Valor da glosa", "sum"),
        "Complemento recebido": ("Complemento recebido", "sum"),
        "Quantidade": ("Quantidade", "sum"),
        "Doc Original": ("Doc Original", _jn),
        "Lote": ("Lote", _jn),
        "Protocolo": ("Protocolo", _jn),
        "Motivo da glosa": ("Motivo da glosa", _jn),
        "Data de pagamento": ("Data de pagamento", _data_min),
        "Meses de pagamento": ("Data de pagamento", _meses),
    }
    if "Operadora" in d.columns:
        spec["Operadora"] = ("Operadora", "first")
    spec = {k: v for k, v in spec.items() if k not in chaves}
    return d.groupby(chaves, sort=False, dropna=False).agg(**spec).reset_index()


# --------------------------------------------------------------------------
# 1b) Cruzamento controle de atendimento x demonstrativo
# --------------------------------------------------------------------------
def _situacao_item(qtd_c, qtd_d, inf, pago, glosa, usar_qtd):
    if glosa > 0.005 and pago <= 0.005:
        return "Glosado (total)"
    if glosa > 0.005:
        return "Pago com glosa"
    if inf > 0 and pago <= 0.005:
        return "Não pago (sem glosa informada)"
    if usar_qtd and qtd_d + 1e-9 < qtd_c:
        return "Quantidade divergente"
    return "Pago"


def cruzar_controle_demonstrativo(controle, demo, usar_quantidade=None):
    """Vincula cada atendimento do controle ao que o plano informou no demonstrativo.

    Vínculo: paciente (nome equivalente) + data do atendimento. Se não achar na mesma data, tenta o
    mesmo paciente com a data mais próxima ainda não usada (marcado como 'data divergente').
    Retorna (cruzado, so_no_demonstrativo)."""
    colunas_saida = ["Data", "Paciente", "Plano", "Tempo", "Quantidade", "Qtd no demonstrativo",
                     "Valor informado", "Valor pago", "Valor da glosa", "Guia", "Lote", "Protocolo",
                     "Motivo da glosa", "Data de pagamento", "Situação", "Critério de vínculo", "Código"]
    colunas_so_demo = ["Data", "Paciente", "Guia", "Lote", "Valor informado", "Valor pago",
                       "Valor da glosa", "Motivo da glosa", "Data de pagamento"]

    c = controle.copy().reset_index(drop=True)
    c["_pk"] = c["Paciente"].map(_norm)

    if demo is None or demo.empty:
        out = pd.DataFrame({
            "Data": c["Data"], "Paciente": c["Paciente"], "Plano": c["Plano"], "Tempo": c["Tempo"],
            "Quantidade": c["Quantidade"], "Qtd no demonstrativo": float("nan"),
            "Valor informado": float("nan"), "Valor pago": float("nan"), "Valor da glosa": float("nan"),
            "Guia": c["Guia"], "Lote": c["Lote"], "Protocolo": "", "Motivo da glosa": "",
            "Data de pagamento": "-", "Situação": "Sem demonstrativo para conferir",
            "Critério de vínculo": "-", "Código": c["Código"] if "Código" in c.columns else "",
        })[colunas_saida]
        return out, pd.DataFrame(columns=colunas_so_demo)

    if usar_quantidade is None:
        usar_quantidade = bool(demo.attrs.get("qtd_encontrada", False))

    d = _garantir_colunas(demo).reset_index(drop=True)
    d["_pk"] = d["Nome do paciente"].map(_norm)
    mapa = _mapa_nomes(d["_pk"].unique(), c["_pk"].unique())
    d["_pk"] = d["_pk"].map(lambda x: mapa.get(x, x))
    g = _agregar(d, ["_pk", "Data do evento"])
    g["_usado"] = False
    idx_por_chave = dict(zip(zip(g["_pk"], g["Data do evento"]), g.index))

    c["_ordem"] = c.groupby(["_pk", "Data"]).cumcount()
    qtd_grupo = c.groupby(["_pk", "Data"])["Quantidade"].transform("sum")
    chaves_ctrl = list(dict.fromkeys(zip(c["_pk"], c["Data"])))

    vinculo = {}  # chave do controle -> (indice em g, critério)
    for k in chaves_ctrl:
        i = idx_por_chave.get(k)
        if i is not None and not g.at[i, "_usado"]:
            g.at[i, "_usado"] = True
            vinculo[k] = (i, "Paciente + data")

    def _dias(a, b):
        da = pd.to_datetime(a, format="%d/%m/%Y", errors="coerce")
        db = pd.to_datetime(b, format="%d/%m/%Y", errors="coerce")
        if pd.isna(da) or pd.isna(db):
            return 10 ** 6
        return abs((da - db).days)

    for k in chaves_ctrl:
        if k in vinculo:
            continue
        livres = g[(g["_pk"] == k[0]) & (~g["_usado"])]
        if livres.empty:
            continue
        i = min(livres.index, key=lambda ix: _dias(g.at[ix, "Data do evento"], k[1]))
        g.at[i, "_usado"] = True
        vinculo[k] = (i, "Paciente (data divergente)")

    registros = []
    for pos, r in c.iterrows():
        k = (r["_pk"], r["Data"])
        v = vinculo.get(k)
        primeira = r["_ordem"] == 0
        base = {"Data": r["Data"], "Paciente": r["Paciente"], "Plano": r["Plano"], "Tempo": r["Tempo"],
                "Quantidade": r["Quantidade"], "Código": r.get("Código", "")}
        if v is None:
            base.update({"Qtd no demonstrativo": 0.0, "Valor informado": 0.0, "Valor pago": 0.0,
                         "Valor da glosa": 0.0, "Guia": r["Guia"], "Lote": r["Lote"], "Protocolo": "",
                         "Motivo da glosa": "", "Data de pagamento": "-",
                         "Situação": "Não localizado no demonstrativo", "Critério de vínculo": "-"})
        else:
            gi, crit = v
            gr = g.loc[gi]
            if primeira:
                inf, pago, glosa, qd = (float(gr["Valor informado"]), float(gr["Valor pago"]),
                                        float(gr["Valor da glosa"]), float(gr["Quantidade"]))
            else:  # valores do lançamento ficam só no 1º registro do dia, para não somar em dobro
                inf = pago = glosa = qd = 0.0
            sit = _situacao_item(float(qtd_grupo[pos]), float(gr["Quantidade"]),
                                 float(gr["Valor informado"]), float(gr["Valor pago"]),
                                 float(gr["Valor da glosa"]), usar_quantidade)
            if not primeira:
                sit = sit + " (valores no 1º registro do dia)"
            base.update({"Qtd no demonstrativo": qd, "Valor informado": inf, "Valor pago": pago,
                         "Valor da glosa": glosa, "Guia": gr["Doc Original"] or r["Guia"],
                         "Lote": gr["Lote"] or r["Lote"], "Protocolo": gr["Protocolo"],
                         "Motivo da glosa": gr["Motivo da glosa"],
                         "Data de pagamento": gr["Data de pagamento"], "Situação": sit,
                         "Critério de vínculo": crit,
                         "Código": r.get("Código", "") or gr.get("Código", "")})
        registros.append(base)

    cruzado = pd.DataFrame(registros, columns=colunas_saida)
    sobra = g[~g["_usado"]]
    so_demo = pd.DataFrame({
        "Data": sobra["Data do evento"], "Paciente": sobra["Nome do paciente"],
        "Guia": sobra["Doc Original"], "Lote": sobra["Lote"],
        "Valor informado": sobra["Valor informado"], "Valor pago": sobra["Valor pago"],
        "Valor da glosa": sobra["Valor da glosa"], "Motivo da glosa": sobra["Motivo da glosa"],
        "Data de pagamento": sobra["Data de pagamento"],
    })[colunas_so_demo].reset_index(drop=True)
    return cruzado, so_demo


# --------------------------------------------------------------------------
# 1c) Espelho de produção (valores de tabela + o que o plano pagou/glosou)
# --------------------------------------------------------------------------
def _so_digitos(x):
    return re.sub(r"\D", "", str(x or ""))


def _valor_tabela(tab, col, plano, tempo, cache, data="", codigo=""):
    """Procura em tab (colunas plano, tempo_atendimento, <col>, vigência opcional) o valor do
    plano/tempo válido na data do atendimento. Retorna float ou None (não encontrado ou ambíguo)."""
    if tab is None or tab.empty:
        return None
    if data and ("vigencia_inicio" in tab.columns or "vigencia_fim" in tab.columns):
        ok = [me.vigente(a, b, data) for a, b in zip(tab.get("vigencia_inicio", [None] * len(tab)),
                                                     tab.get("vigencia_fim", [None] * len(tab)))]
        tab = tab[ok]
        if tab.empty:
            return None
    elif "vigencia_fim" in tab.columns:  # sem data: só o que está em vigor
        tab = tab[[not me.data_iso(f) for f in tab["vigencia_fim"]]]
    if col not in tab.columns:
        return None
    cod = _so_digitos(codigo)
    if cod and "codigo_tuss" in tab.columns:  # procedimento com código: usa o valor do código, se cadastrado
        por_cod = tab[tab["codigo_tuss"].map(lambda x: _so_digitos(me._id_txt(x)) == cod)]
        if not por_cod.empty:
            tab = por_cod
    chave = (_norm(plano), _so_digitos(tempo) or _norm(tempo), me.data_iso(data)[:10], cod, col)
    if chave in cache:
        return cache[chave]
    t = tab[tab[col].notna()].copy()
    if t.empty:
        cache[chave] = None
        return None
    t["_p"] = t["plano"].map(_norm)
    pn = chave[0]
    cand = t[t["_p"] == pn]
    if cand.empty and pn:
        cand = t[t["_p"].map(lambda x: len(x) >= 3 and (x in pn or pn in x))]
        if cand["_p"].nunique() > 1:  # vários planos parecidos: ambíguo
            cache[chave] = None
            return None
    if cand.empty:
        cand = t[t["_p"].isin(["SEM PLANO", ""])]
    res = None
    if not cand.empty:
        if len(cand) == 1:
            res = float(cand[col].iloc[0])
        else:
            if chave[1]:
                tt = cand[cand["tempo_atendimento"].map(lambda x: (_so_digitos(x) or _norm(x)) == chave[1])]
                if not tt.empty:
                    res = float(tt[col].iloc[0])
            if res is None and cand[col].nunique() == 1:
                res = float(cand[col].iloc[0])
    cache[chave] = res
    return res


def montar_espelho_producao(cruzado, tab_faturamento=None, tab_repasse=None, descontar_glosa=False):
    """Monta o espelho da produção do profissional.

    tab_faturamento: DataFrame com colunas plano, tempo_atendimento, valor_plano (valor que o plano paga)
    tab_repasse:     DataFrame com colunas plano, tempo_atendimento, valor_profissional
    descontar_glosa: se True, o repasse é reduzido na mesma proporção da glosa do atendimento.
    """
    cols = ["Data", "Paciente", "Plano", "Tempo", "Quantidade", "Valor unitário (plano)",
            "Valor total a receber", "Valor pago pelo plano", "Valor da glosa", "Repasse unitário",
            "Repasse ao profissional", "Situação", "Guia", "Lote", "Motivo da glosa", "Fonte do valor"]
    if cruzado is None or cruzado.empty:
        return pd.DataFrame(columns=cols)

    cf, cr = {}, {}
    unit, fonte, rep_unit = [], [], []
    datas = cruzado["Data"] if "Data" in cruzado.columns else [""] * len(cruzado)
    codigos = cruzado["Código"] if "Código" in cruzado.columns else [""] * len(cruzado)
    inf_unit = (pd.to_numeric(cruzado["Valor informado"], errors="coerce")
                / pd.to_numeric(cruzado["Quantidade"], errors="coerce").where(lambda q: q > 0)).round(2).tolist()
    for i, (plano, tempo, data, cod) in enumerate(zip(cruzado["Plano"], cruzado["Tempo"], datas, codigos)):
        u = _valor_tabela(tab_faturamento, "valor_plano", plano, tempo, cf, data, cod)
        rotulo = "Tabela de faturamento" if u is not None else ""
        # paciente da Rede Flex: o demonstrativo informa o valor Flex cadastrado
        f = _valor_tabela(tab_faturamento, "valor_flex", plano, tempo, cf, data, cod) if u is not None else None
        if f and pd.notna(inf_unit[i]) and abs(inf_unit[i] - f) <= TOL:
            u, rotulo = f, "Tabela de faturamento (Rede Flex)"
        unit.append(u)
        fonte.append(rotulo)
        rep_unit.append(_valor_tabela(tab_repasse, "valor_profissional", plano, tempo, cr, data, cod))

    e = cruzado.copy().reset_index(drop=True)
    e["Valor unitário (plano)"] = unit
    e["Fonte do valor"] = fonte
    # sem valor na tabela: usa o valor informado no demonstrativo (por unidade), quando houver
    sem = e["Valor unitário (plano)"].isna() & (e["Valor informado"].fillna(0) > 0) & (e["Quantidade"] > 0)
    e.loc[sem, "Valor unitário (plano)"] = (e.loc[sem, "Valor informado"] / e.loc[sem, "Quantidade"]).round(2)
    e.loc[sem, "Fonte do valor"] = "Demonstrativo"
    e.loc[e["Valor unitário (plano)"].isna(), "Fonte do valor"] = "Sem valor cadastrado"

    e["Valor total a receber"] = (e["Valor unitário (plano)"].fillna(0) * e["Quantidade"]).round(2)
    e["Repasse unitário"] = rep_unit
    rep = (pd.Series(rep_unit, dtype="float64").fillna(0) * e["Quantidade"]).round(2)
    if descontar_glosa:
        base = e["Valor total a receber"].where(e["Valor total a receber"] > 0, e["Valor informado"].fillna(0))
        fator = 1 - (e["Valor da glosa"].fillna(0) / base.where(base > 0)).clip(upper=1).fillna(0)
        rep = (rep * fator).round(2)
    e["Repasse ao profissional"] = rep
    e["Valor pago pelo plano"] = e["Valor pago"]
    return e[cols]


def resumo_producao(espelho):
    if espelho is None or espelho.empty:
        return dict(atendimentos=0, pacientes=0, receber=0.0, pago=0.0, glosa=0.0, repasse=0.0,
                    nao_localizados=0)
    return dict(
        atendimentos=float(espelho["Quantidade"].sum()),
        pacientes=int(espelho["Paciente"].map(_norm).nunique()),
        receber=float(espelho["Valor total a receber"].sum()),
        pago=float(espelho["Valor pago pelo plano"].fillna(0).sum()),
        glosa=float(espelho["Valor da glosa"].fillna(0).sum()),
        repasse=float(espelho["Repasse ao profissional"].sum()),
        nao_localizados=int(espelho["Situação"].str.startswith("Não localizado").sum()),
    )


def producao_por_plano(espelho):
    cols = ["Plano", "Pacientes", "Atendimentos", "Valor total a receber", "Valor pago pelo plano",
            "Valor da glosa", "Repasse ao profissional"]
    if espelho is None or espelho.empty:
        return pd.DataFrame(columns=cols)
    e = espelho.copy()
    e["_pk"] = e["Paciente"].map(_norm)
    t = e.groupby("Plano", sort=True).agg(
        Pacientes=("_pk", "nunique"), Atendimentos=("Quantidade", "sum"),
        **{"Valor total a receber": ("Valor total a receber", "sum"),
           "Valor pago pelo plano": ("Valor pago pelo plano", "sum"),
           "Valor da glosa": ("Valor da glosa", "sum"),
           "Repasse ao profissional": ("Repasse ao profissional", "sum")},
    ).reset_index()
    return t[cols]


# --------------------------------------------------------------------------
# 3) Faturamento (lote) x recebimento
# --------------------------------------------------------------------------
def ler_faturamento(arquivo, plano_padrao=None, lote_padrao=None):
    """Lê o arquivo de faturamento (lote com guias). Retorna (DataFrame, erro_ou_None).

    Colunas: Lote, Guia, Paciente, Plano, Data atendimento, Valor faturado, Quantidade, Data envio, Aba."""
    vazio = pd.DataFrame(columns=COLUNAS_FATURAMENTO)
    try:
        abas = _abas_brutas(arquivo)
    except Exception as e:
        return vazio, str(e)

    partes, cabecalhos, mapa_ref = [], [], {}
    for nome_aba, raw in abas:
        try:
            lote_g = me._lote_global(raw)
            envio_g = me._texto_global(raw, r"\b(ENVIO|REMESSA|FATURAMENTO)\b", me._RE_DATA)
            tabela = me._preparar_tabela(raw, CAMPOS_FATURAMENTO)
        except Exception:
            continue
        if tabela.empty or tabela.shape[1] < 2:
            continue
        cabecalhos.append([str(c) for c in tabela.columns][:12])
        mapa = _mapear(tabela, CAMPOS_FATURAMENTO)
        if "Valor faturado" not in mapa or ("Guia" not in mapa and "Paciente" not in mapa):
            continue
        out = pd.DataFrame(index=tabela.index)
        out["Lote"] = _serie(tabela, mapa, "Lote") if "Lote" in mapa else (lote_g or lote_padrao or "")
        out["Guia"] = _serie(tabela, mapa, "Guia")
        out["Paciente"] = _serie(tabela, mapa, "Paciente")
        out["Plano"] = _serie(tabela, mapa, "Plano") if "Plano" in mapa else (plano_padrao or "")
        out["Data atendimento"] = _serie(tabela, mapa, "Data atendimento", me.padronizar_data, "-")
        out["Valor faturado"] = _serie(tabela, mapa, "Valor faturado", me.limpar_valor_monetario, 0.0)
        out["Quantidade"] = _serie(tabela, mapa, "Quantidade", _qtd, 1.0)
        if "Data envio" in mapa:
            out["Data envio"] = _serie(tabela, mapa, "Data envio", me.padronizar_data, "-")
        else:
            out["Data envio"] = me.padronizar_data(envio_g) if envio_g else "-"
        for cname in ("Lote", "Guia", "Paciente", "Plano", "Data atendimento", "Data envio"):
            out[cname] = _ffill(out[cname])
        out = out[out["Valor faturado"] > 0]
        out = out[out["Guia"].notna() | out["Paciente"].notna()]
        out["Lote"] = out["Lote"].fillna(lote_padrao or "Sem lote")
        out["Guia"] = out["Guia"].fillna("")
        out["Paciente"] = out["Paciente"].fillna("Não identificado")
        out["Plano"] = out["Plano"].fillna(plano_padrao or "Não informado")
        out["Data atendimento"] = out["Data atendimento"].fillna("-")
        out["Data envio"] = out["Data envio"].fillna("-")
        out["Aba"] = str(nome_aba)
        if not out.empty:
            partes.append(out)
            mapa_ref = mapa_ref or mapa

    if not partes:
        dica = f" Cabeçalhos vistos: {cabecalhos[0]}" if cabecalhos else ""
        return vazio, ("Não encontrei, no faturamento, a coluna de valor faturado junto com guia ou paciente."
                       + dica)
    df = pd.concat(partes, ignore_index=True)[COLUNAS_FATURAMENTO]
    df.attrs["mapeamento"] = mapa_ref
    df.attrs["abas_com_dados"] = len(partes)
    df.attrs["abas_total"] = len(abas)
    return df, None


def _chave_guia(x):
    s = str(x or "").strip().upper()
    if s in ("", "-", "NAN", "NONE"):
        return ""
    dig = re.sub(r"\D", "", s)
    if dig:
        return dig.lstrip("0") or "0"
    return re.sub(r"[^A-Z0-9]", "", s)


def _situacao_recebimento(fat, pago, glosa, achou):
    if not achou:
        return "Não pago (sem retorno no demonstrativo)"
    if glosa > 0.005 and pago <= 0.005:
        return "Glosado total"
    if glosa > 0.005 and pago + glosa >= fat - TOL:
        return "Pago parcial (com glosa)"
    if pago >= fat - TOL:
        return "Pago integral"
    if pago <= 0.005:
        return "Não pago (sem motivo informado)"
    return "Pago a menor (sem glosa informada)"


def cruzar_faturamento_recebimento(fat, demo, data_envio_padrao=None):
    """Confere se tudo o que foi faturado foi pago, em que mês e com quantos dias de demora.

    Vínculo 1: número da guia do prestador. Vínculo 2 (guias que sobraram): paciente + data do atendimento.
    Prazo: data de pagamento menos a data de envio do lote (coluna do faturamento ou data_envio_padrao);
    sem nenhuma das duas, usa a data do atendimento (e isso aparece em 'Base do prazo')."""
    cols = ["Lote", "Guia", "Paciente", "Plano", "Data atendimento", "Valor faturado", "Valor pago",
            "Valor da glosa", "Valor em aberto", "Situação", "Motivo da glosa", "Data de envio",
            "Data de pagamento", "Mês de pagamento", "Dias para pagamento", "Base do prazo",
            "Critério de vínculo"]
    if fat is None or fat.empty:
        return pd.DataFrame(columns=cols)

    f = fat.copy().reset_index(drop=True)
    f["_gk"] = f["Guia"].map(_chave_guia)
    sem_guia = f["_gk"] == ""
    f.loc[sem_guia, "_gk"] = ["SG%d" % i for i in f.index[sem_guia]]
    fg = f.groupby(["Lote", "_gk"], sort=False).agg(
        Guia=("Guia", "first"), Paciente=("Paciente", "first"), Plano=("Plano", "first"),
        **{"Data atendimento": ("Data atendimento", "first"), "Valor faturado": ("Valor faturado", "sum"),
           "Data envio": ("Data envio", lambda s: next((x for x in s if x not in ("", "-")), "-"))},
    ).reset_index()

    d = _garantir_colunas(demo).reset_index(drop=True) if demo is not None and not demo.empty else None
    achou = {}  # índice em fg -> (linha agregada do demonstrativo, critério)

    if d is not None:
        d["_gk"] = d["Doc Original"].map(_chave_guia)
        com_guia = d[d["_gk"] != ""]
        dg = _agregar(com_guia, ["_gk"]) if not com_guia.empty else pd.DataFrame()
        usados = set()
        if not dg.empty:
            por_chave = {r["_gk"]: r for _, r in dg.iterrows()}
            for i, r in fg.iterrows():
                m = por_chave.get(r["_gk"])
                if m is not None:
                    achou[i] = (m, "Guia do prestador")
                    usados.add(r["_gk"])
        # 2ª rodada: paciente + data, só com o que sobrou do demonstrativo
        pendentes = [i for i in fg.index if i not in achou]
        resto = d[~d["_gk"].isin(usados)].copy()
        if pendentes and not resto.empty:
            resto["_pk"] = resto["Nome do paciente"].map(_norm)
            fg["_pk"] = fg["Paciente"].map(_norm)
            mapa = _mapa_nomes(resto["_pk"].unique(), fg.loc[pendentes, "_pk"].unique())
            resto["_pk"] = resto["_pk"].map(lambda x: mapa.get(x, x))
            g2 = _agregar(resto, ["_pk", "Data do evento"])
            por_chave2 = {(r["_pk"], r["Data do evento"]): r for _, r in g2.iterrows()}
            usados2 = set()
            for i in pendentes:
                k = (fg.at[i, "_pk"], fg.at[i, "Data atendimento"])
                if k in por_chave2 and k not in usados2:
                    achou[i] = (por_chave2[k], "Paciente + data")
                    usados2.add(k)

    registros = []
    for i, r in fg.iterrows():
        m, crit = achou.get(i, (None, "-"))
        fat_v = float(r["Valor faturado"])
        if m is not None:
            # complemento pago em outra guia (pagamento em duas partes) conta como recebido desta guia
            pago = float(m["Valor pago"]) + me._num(m.get("Complemento recebido", 0))
            glosa = float(m["Valor da glosa"])
            motivo = m["Motivo da glosa"]
            dt_pag, meses = m["Data de pagamento"], m["Meses de pagamento"]
            plano = r["Plano"] or m.get("Operadora", "")
        else:
            pago = glosa = 0.0
            motivo, dt_pag, meses = "", "-", "-"
            plano = r["Plano"]
        sit = _situacao_recebimento(fat_v, pago, glosa, m is not None)
        if not motivo:
            if sit == "Pago a menor (sem glosa informada)" or sit == "Não pago (sem motivo informado)":
                motivo = "Diferença sem justificativa no demonstrativo"
            elif sit.startswith("Não pago (sem retorno"):
                motivo = "Guia não consta no demonstrativo analisado"
        # base do prazo
        envio = r["Data envio"]
        if envio and envio != "-":
            base, base_txt = envio, "Envio do lote"
        elif data_envio_padrao is not None and str(data_envio_padrao).strip():
            base, base_txt = me.padronizar_data(data_envio_padrao), "Data de envio informada"
        else:
            base, base_txt = r["Data atendimento"], "Data do atendimento"
        dp = pd.to_datetime(dt_pag, format="%d/%m/%Y", errors="coerce")
        db = pd.to_datetime(base, format="%d/%m/%Y", errors="coerce")
        dias = float((dp - db).days) if (pd.notna(dp) and pd.notna(db)) else float("nan")
        registros.append({
            "Lote": r["Lote"], "Guia": r["Guia"] or "-", "Paciente": r["Paciente"], "Plano": plano,
            "Data atendimento": r["Data atendimento"], "Valor faturado": round(fat_v, 2),
            "Valor pago": round(pago, 2), "Valor da glosa": round(glosa, 2),
            "Valor em aberto": round(max(fat_v - pago, 0.0), 2), "Situação": sit,
            "Motivo da glosa": motivo, "Data de envio": base, "Data de pagamento": dt_pag,
            "Mês de pagamento": meses, "Dias para pagamento": dias, "Base do prazo": base_txt,
            "Critério de vínculo": crit,
        })
    return pd.DataFrame(registros, columns=cols)


def resumir_recebimento(res, por):
    """Resumo do cruzamento agrupado por 'Plano', 'Lote', 'Mês de pagamento' ou 'Situação'."""
    cols = [por, "Guias", "Valor faturado", "Valor pago", "Valor da glosa", "Valor em aberto",
            "% pago", "Prazo médio (dias)"]
    if res is None or res.empty:
        return pd.DataFrame(columns=cols)
    t = res.groupby(por, sort=True).agg(
        Guias=("Guia", "count"),
        **{"Valor faturado": ("Valor faturado", "sum"), "Valor pago": ("Valor pago", "sum"),
           "Valor da glosa": ("Valor da glosa", "sum"), "Valor em aberto": ("Valor em aberto", "sum"),
           "Prazo médio (dias)": ("Dias para pagamento", "mean")},
    ).reset_index()
    t["% pago"] = (t["Valor pago"] / t["Valor faturado"].where(t["Valor faturado"] > 0)).fillna(0.0)
    t["Prazo médio (dias)"] = t["Prazo médio (dias)"].round(0)
    return t[cols]


def lista_de_cobranca(res):
    """Guias que merecem cobrança ao plano: não pagas, pagas a menor ou glosadas."""
    if res is None or res.empty:
        return res
    ok = res["Situação"].eq("Pago integral")
    return res[~ok & (res["Valor em aberto"] > TOL)].sort_values(
        ["Plano", "Lote", "Data atendimento"]).reset_index(drop=True)

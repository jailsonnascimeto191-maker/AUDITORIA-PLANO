"""
Extrator inteligente de glosas com Forward Fill para dados hierárquicos e Trava de Quantidades.
"""
import csv
import io
import itertools
import re
import unicodedata
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

import pandas as pd

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import docx
except ImportError:
    docx = None

COLUNAS_PADRAO_GLOSAS = [
    "Data do evento",
    "Protocolo",
    "Doc Original",
    "Nome do paciente",
    "Código",
    "Procedimento",
    "Valor informado",
    "Valor pago",
    "Valor da glosa",
    "Motivo da glosa",
]

# --------------------------------------------------------------------------
# Configuração dos campos (com Trava de Colunas de Quantidade)
# --------------------------------------------------------------------------
CAMPOS = {
    "Data do evento": dict(
        tipo="data",
        sin=["DATA ATENDIMENTO", "DATA REALIZACAO", "DATA EXECUCAO", "DATA EVENTO",
             "DATA PROCEDIMENTO", "DATA SERVICO", "DT ATENDIMENTO", "DT REALIZACAO",
             "DATA", "DT"],
        excl=["NASC", "PAGAMENTO", "VENC", "PROTOCOLO", "ENVIO", "EMISSAO", "ALTA"],
    ),
    "Protocolo": dict(
        tipo="id",
        sin=["NUMERO PROTOCOLO", "NRO PROTOCOLO", "NR PROTOCOLO", "N PROTOCOLO",
             "NUM PROTOCOLO", "PROTOCOLO", "PROTOC"],
        excl=["DATA", "DT", "VALOR", "STATUS", "SITUACAO"],
    ),
    "Doc Original": dict(
        tipo="id",
        sin=["DOC ORIGINAL", "DOCUMENTO ORIGINAL", "NUMERO GUIA PRESTADOR", "GUIA PRESTADOR",
             "NUMERO GUIA", "NRO GUIA", "NR GUIA", "N GUIA", "NUM GUIA", "GUIA",
             "NUMERO DOCUMENTO", "NRO DOCUMENTO", "DOCUMENTO", "DOC", "SENHA"],
        excl=["DATA", "DT", "VALOR", "TIPO", "CPF", "CNPJ", "CARTEIRA"],
    ),
    "Nome do paciente": dict(
        tipo="nome",
        sin=["NOME PACIENTE", "NOME BENEFICIARIO", "PACIENTE", "BENEFICIARIO",
             "SEGURADO", "USUARIO", "CLIENTE", "NOME"],
        excl=["MEDICO", "PROFISSIONAL", "PLANO", "OPERADORA", "PRESTADOR", "EXECUTANTE",
              "SOLICITANTE", "CONVENIO", "MAE", "RESPONSAVEL", "PROCEDIMENTO", "HOSPITAL",
              "CLINICA", "SERVICO"],
    ),
    "Código": dict(
        tipo="codigo",
        sin=["CODIGO PROCEDIMENTO", "COD PROCEDIMENTO", "COD PROC", "CODIGO TUSS",
             "COD TUSS", "TUSS", "CODIGO", "COD", "AMB", "ITEM", "PROC"],
        excl=["GLOSA", "MOTIVO", "GUIA", "BENEFICIARIO", "CARTEIRA", "PACIENTE", "SENHA",
              "PROTOCOLO", "LOTE", "MEDICO", "CRM", "CPF", "CNPJ"],
    ),
    "Procedimento": dict(
        tipo="texto",
        sin=["DESCRICAO PROCEDIMENTO", "NOME PROCEDIMENTO", "PROCEDIMENTO", "DESCRICAO",
             "SERVICO", "EVENTO", "TRATAMENTO", "EXAME"],
        excl=["GLOSA", "MOTIVO", "CODIGO", "COD", "DATA", "VALOR"],
    ),
    "Valor informado": dict(
        tipo="dinheiro",
        sin=["VALOR INFORMADO", "VALOR APRESENTADO", "VALOR COBRADO", "VALOR FATURADO",
             "VALOR PLANO", "INFORMADO", "APRESENTADO", "COBRADO", "FATURADO",
             "VALOR", "VLR", "VL"],
        excl=["GLOSA", "PAGO", "RECEBIDO", "LIBERADO", "LIQUIDO", "RETIDO", "APROVADO",
              "PAGAMENTO", "UNIT", "QTD", "QTDE", "QUANTIDADE", "SOLICITADA", "SESSAO"],
    ),
    "Valor pago": dict(
        tipo="dinheiro",
        sin=["VALOR PAGO", "VALOR LIBERADO", "VALOR RECEBIDO", "VALOR LIQUIDO",
             "VALOR APROVADO", "VALOR ACEITO", "VL PAGO", "VLR PAGO", "PAGO",
             "RECEBIDO", "LIBERADO", "LIQUIDO", "APROVADO"],
        excl=["GLOSA", "INFORMADO", "APRESENTADO", "COBRADO", "QTD", "QTDE", "QUANTIDADE", "SOLICITADA", "SESSAO"],
    ),
    "Valor da glosa": dict(
        tipo="dinheiro",
        sin=["VALOR GLOSA", "VALOR GLOSADO", "VL GLOSA", "VLR GLOSA", "VALOR RETIDO",
             "GLOSADO", "GLOSA", "RETIDO"],
        excl=["MOTIVO", "JUSTIFICATIVA", "DESCRICAO", "CODIGO", "COD", "OBS", "TIPO", "QTD", "QTDE", "QUANTIDADE"],
    ),
    "Motivo da glosa": dict(
        tipo="texto",
        sin=["MOTIVO GLOSA", "DESCRICAO GLOSA", "DESCRICAO MOTIVO", "MOTIVO",
             "JUSTIFICATIVA", "OBSERVACAO", "OBS", "CRITICA", "CODIGO GLOSA", "GLOSA"],
        excl=["VALOR", "VL", "VLR"],
    ),
}

CAMPOS_DINHEIRO = ["Valor informado", "Valor pago", "Valor da glosa"]
LIMIAR_ATRIBUICAO = 35

# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------
_RE_DATA = re.compile(r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
_RE_DIN = re.compile(r"^(R\$\s*)?-?\(?\d{1,3}(\.\d{3})*,\d{1,2}\)?$|^(R\$\s*)?-?\(?\d+[.,]\d{1,2}\)?$")
_RE_COD = re.compile(r"^(\d{6,10}|\d{1,2}\.\d{2}\.\d{2}\.\d{2}-?\d?|\d{2}\.\d{3}\.\d{3}-?\d?)$")
_RE_NOME = re.compile(r"^[^\W\d_]+(?:[ '.-]+[^\W\d_]+)+$")
_RE_DIN_TEXTO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
_PALAVRAS_PROC = {"CONSULTA", "EXAME", "SESSAO", "PROCEDIMENTO", "TERAPIA", "HEMOGRAMA",
                  "RADIOGRAFIA", "ULTRASSONOGRAFIA", "TOMOGRAFIA", "RESSONANCIA", "CIRURGIA",
                  "AVALIACAO", "ATENDIMENTO", "DIARIA", "TAXA", "MATERIAL", "MEDICAMENTO"}

def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return s.strip()

def _txt(v):
    if v is None: return ""
    try:
        if pd.isnull(v): return ""
    except (TypeError, ValueError): pass
    if isinstance(v, float) and v.is_integer() and abs(v) >= 100000:
        return str(int(v))
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s

def limpar_valor_monetario(val):
    try:
        if pd.isnull(val): return 0.0
    except (TypeError, ValueError): pass
    if isinstance(val, (int, float)): return float(val)
    s = str(val).strip()
    negativo = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.replace("R$", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    s = re.sub(r"[^0-9.]", "", s)
    try: v = float(s) if s else 0.0
    except ValueError: v = 0.0
    return -v if negativo else v

def padronizar_data(val):
    s = _txt(val)
    if not s: return "-"
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            dt = pd.to_datetime(s[:10], errors="coerce")
        else:
            m = _RE_DATA.search(s)
            dt = pd.to_datetime(m.group(1) if m else s, errors="coerce", dayfirst=True)
        if pd.notnull(dt): return dt.strftime("%d/%m/%Y")
    except Exception: pass
    return "-"

def _score_nome(h_norm, campo):
    if not h_norm: return 0.0
    cfg = CAMPOS[campo]
    hw = h_norm.split()
    hc = h_norm.replace(" ", "")
    if any(w.startswith(e) for w in hw for e in cfg["excl"]): return 0.0
    melhor = 0.0
    for termo in cfg["sin"]:
        tw = termo.split()
        tc = termo.replace(" ", "")
        if h_norm == termo: s = 100.0
        elif hc == tc: s = 95.0
        elif all(w in hw for w in tw): s = min(95.0, 70.0 + 8 * len(tw))
        elif len(tc) >= 6 and tc in hc: s = 75.0
        else:
            r = SequenceMatcher(None, hc, tc).ratio()
            s = 60.0 * r if (r >= 0.84 and len(tc) >= 5) else 0.0
        melhor = max(melhor, s)
    return melhor

def _perfil(serie):
    pares = [(v, _txt(v)) for v in serie.tolist()]
    pares = [(v, t) for v, t in pares if t][:60]
    amostra = [t for _, t in pares]
    perfil = dict(data=0.0, dinheiro=0.0, codigo=0.0, nome=0.0, texto=0.0, id=0.0, tam=0.0, n=len(amostra))
    if not amostra: return perfil
    n = len(amostra)
    c = dict(data=0, dinheiro=0, codigo=0, nome=0, texto=0)
    for orig, v in pares:
        if isinstance(orig, (int, float)) and not isinstance(orig, bool):
            if float(orig).is_integer() and abs(orig) >= 100000: c["codigo"] += 1
            else: c["dinheiro"] += 1
        elif _RE_DATA.search(v) and not _RE_DIN.match(v): c["data"] += 1
        elif _RE_COD.match(v.replace(" ", "")): c["codigo"] += 1
        elif _RE_DIN.match(v): c["dinheiro"] += 1
        elif re.fullmatch(r"-?\d{1,5}", v): c["dinheiro"] += 1
        elif any(ch.isalpha() for ch in v):
            c["texto"] += 1
            palavras = _norm(v).split()
            if (_RE_NOME.match(v) and 6 <= len(v) <= 70 and 2 <= len(palavras) <= 6
                    and not (set(palavras) & _PALAVRAS_PROC)):
                c["nome"] += 1
    for k, v in c.items(): perfil[k] = v / n
    perfil["tam"] = sum(len(v) for v in amostra) / n
    perfil["id"] = sum(1 for v in amostra if re.fullmatch(r"[\w./-]{4,25}", v) and any(ch.isdigit() for ch in v)
                       and not _RE_DATA.search(v) and not _RE_DIN.match(v)) / n
    return perfil

def _score_campo(campo, h_norm, perfil):
    tipo = CAMPOS[campo]["tipo"]
    frac = perfil.get(tipo, 0.0)
    nome = _score_nome(h_norm, campo)
    compat = 0.3 + 0.7 * frac
    score = nome * compat
    if tipo in ("data", "codigo", "nome"): score += 50.0 * frac
    elif tipo == "texto": score += 25.0 * frac
    return score

def _preparar_tabela(raw):
    raw = raw.copy().dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    raw.columns = range(raw.shape[1])
    if raw.empty: return raw

    melhor_i, melhor_hits = None, 0
    for i in range(min(len(raw), 30)):
        hits = sum(1 for cel in raw.iloc[i].tolist() if _txt(cel) and not re.fullmatch(r"[\d.,/ R$-]+", _txt(cel)) 
                   and any(_score_nome(_norm(_txt(cel)), campo) >= 70 for campo in CAMPOS))
        if hits > melhor_hits: melhor_i, melhor_hits = i, hits

    if melhor_hits >= 2: cab_i = melhor_i
    else:
        primeira = [_txt(c) for c in raw.iloc[0].tolist() if _txt(c)]
        if primeira and all(not re.fullmatch(r"[\d.,/ R$-]+", t) for t in primeira) and len(primeira) >= 3: cab_i = 0
        else: cab_i = None

    if cab_i is None:
        df = raw.copy()
        df.columns = [f"COL_{i}" for i in range(df.shape[1])]
        return _remover_totais(df)

    nomes, usados = [], {}
    for j, cel in enumerate(raw.iloc[cab_i].tolist()):
        n = _txt(cel) or f"COL_{j}"
        usados[n] = usados.get(n, 0) + 1
        nomes.append(n if usados[n] == 1 else f"{n}_{usados[n]}")
    df = raw.iloc[cab_i + 1:].reset_index(drop=True)
    df.columns = nomes
    return _remover_totais(df)

def _remover_totais(df):
    def eh_total(linha):
        for cel in linha.tolist():
            if re.match(r"^(SUB )?TOTAL( GERAL)?$|^TOTAIS$|^TOTAL (GERAL|DA|DO|DOS|DAS)\b", _norm(_txt(cel))): return True
        return False
    if df.empty: return df
    return df[~df.apply(eh_total, axis=1)].reset_index(drop=True)

def _consistencia(df, c_inf, c_pago, c_glosa):
    a = df[c_inf].apply(limpar_valor_monetario)
    b = df[c_pago].apply(limpar_valor_monetario)
    g = df[c_glosa].apply(limpar_valor_monetario)
    if len(a) == 0: return 0.0
    return float(((a - b - g).abs() < 0.02).mean())

def _descobrir_mapeamento(df):
    cols = list(df.columns)
    perfis = {c: _perfil(df[c]) for c in cols}
    hnorm = {c: _norm(c) for c in cols}

    candidatos = []
    for campo in CAMPOS:
        for c in cols:
            s = _score_campo(campo, hnorm[c], perfis[c])
            if s >= LIMIAR_ATRIBUICAO:
                outro = max((_score_nome(hnorm[c], o) for o in CAMPOS if o != campo), default=0.0)
                if outro >= 70 and _score_nome(hnorm[c], campo) < LIMIAR_ATRIBUICAO: continue
                candidatos.append((s, campo, c))
    candidatos.sort(key=lambda x: -x[0])

    mapa, usadas = {}, set()
    for s, campo, c in candidatos:
        if campo not in mapa and c not in usadas:
            mapa[campo] = c
            usadas.add(c)

    faltam = [f for f in CAMPOS_DINHEIRO if f not in mapa]
    livres = [c for c in cols if c not in usadas and perfis[c]["dinheiro"] >= 0.6]
    if faltam and livres:
        melhor, melhor_score = None, -1.0
        for perm in itertools.permutations(livres, min(len(faltam), len(livres))):
            tentativa = dict(zip(faltam, perm))
            final = {**mapa, **tentativa}
            score = 0.0
            if all(f in final for f in CAMPOS_DINHEIRO):
                score += 10 * _consistencia(df, final["Valor informado"], final["Valor pago"], final["Valor da glosa"])
            pos = [cols.index(final[f]) for f in CAMPOS_DINHEIRO if f in final]
            score += 0.1 * sum(1 for a, b in zip(pos, pos[1:]) if a < b)
            if score > melhor_score: melhor, melhor_score = tentativa, score
        if melhor:
            for f, c in melhor.items():
                mapa[f] = c
                usadas.add(c)

    sobras = [c for c in cols if c not in usadas and perfis[c]["texto"] >= 0.6]
    for campo in ("Procedimento", "Motivo da glosa"):
        if campo not in mapa and sobras:
            c = sobras.pop(0)
            mapa[campo] = c
            usadas.add(c)

    return mapa

def _montar_saida(df, mapa):
    def col(campo): return df[mapa[campo]] if campo in mapa else None

    out = pd.DataFrame(index=df.index)
    
    # 1. Extração Bruta
    s = col("Data do evento")
    out["Data do evento"] = s.apply(padronizar_data) if s is not None else pd.NA
    s = col("Protocolo")
    out["Protocolo"] = s.apply(_txt) if s is not None else pd.NA
    s = col("Doc Original")
    out["Doc Original"] = s.apply(_txt) if s is not None else pd.NA
    s = col("Nome do paciente")
    out["Nome do paciente"] = s.apply(_txt) if s is not None else pd.NA

    # 2. Preenchimento para Baixo (Forward Fill para dados hierárquicos)
    for c in ["Data do evento", "Protocolo", "Doc Original", "Nome do paciente"]:
        out[c] = out[c].replace(["", "-", "Não identificado"], pd.NA)
        out[c] = out[c].ffill()
        if c == "Nome do paciente":
            out[c] = out[c].fillna("Não identificado")
        else:
            out[c] = out[c].fillna("-")

    s = col("Código")
    out["Código"] = s.apply(_txt) if s is not None else "-"
    s = col("Procedimento")
    out["Procedimento"] = s.apply(_txt) if s is not None else "Procedimento clínico"

    s = col("Valor informado")
    out["Valor informado"] = s.apply(limpar_valor_monetario) if s is not None else 0.0
    s = col("Valor pago")
    out["Valor pago"] = s.apply(limpar_valor_monetario) if s is not None else 0.0

    tem_inf_pago = "Valor informado" in mapa and "Valor pago" in mapa
    calculada = (out["Valor informado"] - out["Valor pago"]).clip(lower=0.0).round(2)
    s = col("Valor da glosa")
    if s is not None:
        g = s.apply(limpar_valor_monetario).abs().round(2)
        if tem_inf_pago and not (g > 0).any(): g = calculada
        out["Valor da glosa"] = g
    elif tem_inf_pago:
        out["Valor da glosa"] = calculada
    else:
        out["Valor da glosa"] = 0.0

    s = col("Motivo da glosa")
    out["Motivo da glosa"] = s.apply(_txt) if s is not None else ""
    
    # Tratamento para Glosa Silenciosa (Maria Izabel): Glosa > 0 sem justificativa no arquivo
    out.loc[(out["Motivo da glosa"] == "") & (out["Valor da glosa"] > 0), "Motivo da glosa"] = (
        "Glosa Silenciosa: Valor zerado ou cortado sem justificativa informada no demonstrativo"
    )
    
    return out[COLUNAS_PADRAO_GLOSAS]

def _limpar_linhas(out):
    if out.empty: return out
    vazio = ((out["Nome do paciente"].isin(["", "Não identificado"])) & (out["Código"].isin(["", "-"])) & 
             (out["Valor informado"] == 0) & (out["Valor pago"] == 0) & (out["Valor da glosa"] == 0))
    ref = (out["Nome do paciente"] + " " + out["Procedimento"]).map(_norm)
    total = ref.str.match(r"^(SUB ?)?TOTAL\b|^TOTAIS\b")
    return out[~(vazio | total)].reset_index(drop=True)

def _processar_bruto(raw):
    tabela = _preparar_tabela(raw)
    if tabela.empty or tabela.shape[1] < 2: return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), {}
    mapa = _descobrir_mapeamento(tabela)
    if len(mapa) < 2: return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), mapa
    return _limpar_linhas(_montar_saida(tabela, mapa)), mapa

def _com_cabecalho(df):
    if isinstance(df.columns, pd.MultiIndex): cab = [" ".join(str(x) for x in t if "Unnamed" not in str(x)) for t in df.columns]
    else: cab = ["" if str(c).startswith("Unnamed") else str(c) for c in df.columns]
    return pd.DataFrame([cab] + df.astype(object).values.tolist())

def mapear_dataframe_para_glosas(df_bruto, somente_glosas=True):
    if df_bruto is None or df_bruto.empty: return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS)
    df, mapa = _processar_bruto(_com_cabecalho(df_bruto))
    if somente_glosas: df = df[df["Valor da glosa"] > 0.005].reset_index(drop=True)
    df.attrs["mapeamento"] = mapa
    return df

# --------------------------------------------------------------------------
# Leitura de texto corrido (PDF sem tabelas) COM MEMÓRIA DE ESTADO
# --------------------------------------------------------------------------
def _linhas_texto_para_df(linhas):
    regs = []
    contexto = {"data": "-", "nome": "", "protocolo": "-", "guia": "-"}

    for ln in linhas:
        m_prot = re.search(r"(?:protocolo|prot\.)[\s:]*([A-Z0-9.-]{5,20})", ln, re.I)
        if m_prot: contexto["protocolo"] = m_prot.group(1)

        m_guia = re.search(r"(?:guia|senha|doc\.)[\s:]*([A-Z0-9.-]{5,20})", ln, re.I)
        if m_guia: contexto["guia"] = m_guia.group(1)

        m_data = _RE_DATA.search(ln)
        if m_data: contexto["data"] = m_data.group(1)

        valores = _RE_DIN_TEXTO.findall(ln)
        cod = re.search(r"\b(\d{8}|\d{1,2}\.\d{2}\.\d{2}\.\d{2}-?\d?)\b", ln)

        if not valores and not cod and len(ln) > 6 and _RE_NOME.match(ln):
            palavras = _norm(ln).split()
            if 2 <= len(palavras) <= 6 and not (set(palavras) & _PALAVRAS_PROC):
                contexto["nome"] = ln.strip()

        if len(valores) < 2:
            continue

        resto = _RE_DATA.sub(" ", ln)
        resto = _RE_DIN_TEXTO.sub(" ", resto)
        if cod: resto = resto.replace(cod.group(1), " ")
        resto = re.sub(r"\s+", " ", resto).strip(" -|;")

        v = [limpar_valor_monetario(x) for x in valores]
        inf, pago = v[0], v[1]
        glosa = v[2] if len(v) >= 3 else max(inf - pago, 0.0)

        regs.append({
            "Data do evento": contexto["data"] or "-",
            "Protocolo": contexto["protocolo"] or "-",
            "Doc Original": contexto["guia"] or "-",
            "Nome do paciente": contexto["nome"] or "Não identificado",
            "Código": cod.group(1) if cod else "-",
            "Procedimento": resto,
            "Valor informado": inf, "Valor pago": pago, "Valor da glosa": glosa,
            "Motivo da glosa": "",
        })
    return pd.DataFrame(regs, columns=COLUNAS_PADRAO_GLOSAS)

def _linhas_pdf(doc):
    linhas = []
    for pagina in doc:
        palavras = pagina.get_text("words")
        grupos = {}
        for x0, y0, x1, y1, w, *_ in palavras:
            grupos.setdefault(round(y0 / 3), []).append((x0, w))
        for y in sorted(grupos):
            linhas.append(" ".join(w for _, w in sorted(grupos[y])))
    return linhas

# --------------------------------------------------------------------------
# XML TISS (e XMLs parecidos)
# --------------------------------------------------------------------------
def _tag(t): return t.split("}")[-1]

def extrair_glosas_xml(arquivo_xml):
    arquivo_xml.seek(0)
    root = ET.parse(arquivo_xml).getroot()
    registros = []

    def folhas(el): return {_tag(c.tag): (c.text or "").strip() for c in el if len(c) == 0 and (c.text or "").strip()}

    def percorrer(el, contexto):
        proprias = folhas(el)
        ctx = {**contexto, **proprias}
        emitiu = False
        for filho in el:
            if len(filho) > 0: emitiu = percorrer(filho, ctx) or emitiu
        if not emitiu and len(proprias) >= 2:
            registros.append(ctx)
            return True
        return emitiu

    percorrer(root, {})
    if not registros: return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), {}
    df = pd.DataFrame(registros)
    return _processar_bruto(_com_cabecalho(df))

def _detectar_separador(texto):
    linhas = [l for l in texto.splitlines() if l.strip()][:40]
    melhor, melhor_score = ";", -1.0
    for sep in (";", "\t", "|", ","):
        contagens = [len(l) for l in csv.reader(linhas, delimiter=sep)]
        if not contagens: continue
        moda = max(set(contagens), key=contagens.count)
        if moda < 2: continue
        score = (contagens.count(moda) / len(contagens)) * min(moda, 10)
        if score > melhor_score + 1e-9: melhor, melhor_score = sep, score
    return melhor

def extrair_glosas_de_arquivo(arquivo_upload, plano="Identificar pelo arquivo", somente_glosas=True):
    vazio = pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS)
    try:
        nome = arquivo_upload.name.lower()
        arquivo_upload.seek(0)
        dados = arquivo_upload.read()
        resultados = []

        if nome.endswith((".xlsx", ".xlsm", ".xls")):
            abas = pd.read_excel(io.BytesIO(dados), sheet_name=None, header=None, dtype=object)
            for aba in abas.values(): resultados.append(_processar_bruto(aba))

        elif nome.endswith((".csv", ".txt", ".tsv")):
            texto = None
            for enc in ("utf-8-sig", "latin-1"):
                try:
                    texto = dados.decode(enc)
                    break
                except UnicodeDecodeError: continue
            if texto is None: return vazio, "Erro de encoding no CSV."
            sep = _detectar_separador(texto)
            linhas = [l for l in csv.reader(io.StringIO(texto), delimiter=sep) if any(c.strip() for c in l)]
            largura = max(len(l) for l in linhas)
            bruto = pd.DataFrame([l + [None] * (largura - len(l)) for l in linhas], dtype=object)
            resultados.append(_processar_bruto(bruto))

        elif nome.endswith((".html", ".htm")):
            for t in pd.read_html(io.BytesIO(dados)): resultados.append(_processar_bruto(_com_cabecalho(t)))

        elif nome.endswith(".xml"):
            resultados.append(extrair_glosas_xml(io.BytesIO(dados)))

        elif nome.endswith(".pdf"):
            if fitz is None: return vazio, "PyMuPDF não instalado."
            doc = fitz.open(stream=dados, filetype="pdf")
            for pagina in doc:
                if hasattr(pagina, "find_tables"):
                    for t in pagina.find_tables().tables: resultados.append(_processar_bruto(pd.DataFrame(t.extract())))
            if not any(not d.empty for d, _ in resultados):
                resultados.append((_limpar_linhas(_linhas_texto_para_df(_linhas_pdf(doc))), {"origem": "texto corrido"}))

        elif nome.endswith(".docx"):
            if docx is None: return vazio, "python-docx não instalado."
            d = docx.Document(io.BytesIO(dados))
            for tab in d.tables:
                linhas = [[c.text.strip() for c in lin.cells] for lin in tab.rows]
                resultados.append(_processar_bruto(pd.DataFrame(linhas)))
            if not any(not x.empty for x, _ in resultados):
                linhas = [p.text for p in d.paragraphs if p.text.strip()]
                resultados.append((_limpar_linhas(_linhas_texto_para_df(linhas)), {"origem": "texto corrido"}))
        else:
            return vazio, f"Formato não suportado: {nome}"

        dfs = [d for d, _ in resultados if not d.empty]
        mapa = next((m for d, m in resultados if not d.empty), {})
        if not dfs: return vazio, "Nenhuma glosa ou estrutura de valores encontrada."

        df = pd.concat(dfs, ignore_index=True)
        if somente_glosas: df = df[df["Valor da glosa"] > 0.005].reset_index(drop=True)
        df.attrs["mapeamento"] = mapa

        if df.empty: return df, f"Tabela lida, mas nenhuma glosa maior que zero encontrada. Colunas: {mapa}"
        return df, None

    except Exception as e: return vazio, f"Erro ao processar o arquivo: {e}"

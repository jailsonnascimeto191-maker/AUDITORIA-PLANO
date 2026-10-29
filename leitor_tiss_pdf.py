"""
Leitura dos demonstrativos TISS (padrão ANS) em PDF:

- Demonstrativo de Análise de Conta (um por lote/protocolo): guia, paciente, carteira, e cada procedimento com
  data, código, valor informado, processado, liberado, glosa e códigos de glosa.
- Demonstrativo de Pagamento: por protocolo/lote e por guia, o valor processado, liberado e glosado, e a data do
  pagamento. Não traz paciente nem procedimento: eles vêm do Demonstrativo de Análise ou do lote faturado,
  ligados pelo número da guia (ver motor_historico / motor_extracao).

Os campos são achados pelo número que o padrão TISS dá a cada um ("9 - Numero do Lote", "14 - Número da Guia no
Prestador"...), e não pela posição na página. Assim a leitura funciona com qualquer biblioteca de PDF e com
qualquer operadora que use o modelo da ANS.
"""
import re

import pandas as pd

_DATA = r"\d{2}/\d{2}/\d{4}"
_VALOR = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_ITEM = re.compile(
    rf"^\s*(\d+)-\s+({_DATA})\s+(\d+)\s+(\S+)\s+(.*?)\s+({_VALOR})\s+(\d+(?:,\d+)?)\s+({_VALOR})\s+({_VALOR})\s*$")
_RE_GLOSA_ITEM = re.compile(rf"^\s*({_VALOR})\s+(\d{{4}})\s*$")      # "95,51  3209" (logo abaixo do item)
_RE_SO_CODIGO = re.compile(r"^\s*(\d{4})\s*$")                        # códigos de glosa extras do item


def texto_do_pdf(dados):
    """Texto do PDF, página a página, mantendo as linhas. Usa pdfplumber; sem ele, PyMuPDF."""
    import io
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            return "\n".join((p.extract_text(layout=True) or "") for p in pdf.pages)
    except ImportError:
        import fitz
        with fitz.open(stream=dados, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)


def tipo_de_demonstrativo(texto):
    """'analise', 'pagamento' ou None (não é um demonstrativo TISS)."""
    t = re.sub(r"\s+", " ", texto)
    if re.search(r"25\s*-\s*Data de realiza", t) and re.search(r"33\s*-\s*Valor Liberado", t):
        return "analise"
    if "Dados do Pagamento" in t and re.search(r"48\s*-\s*Valor Processado", t):
        return "pagamento"
    return None


def _num(v):
    return float(v.replace(".", "").replace(",", ".")) if v else None


def _valores(linha):
    return re.findall(_VALOR, linha)


def _linhas(texto):
    return [l.rstrip() for l in texto.split("\n") if l.strip()]


def _depois(linhas, i):
    """Primeira linha com conteúdo depois da linha i (os valores ficam logo abaixo do rótulo)."""
    for j in range(i + 1, min(i + 4, len(linhas))):
        if linhas[j].strip():
            return linhas[j]
    return ""


def _descricoes_glosa(linhas):
    """'3209 - TEXTO, 3210 - TEXTO' (no fim do documento) -> {código: texto}."""
    texto, dentro = [], False
    for l in linhas:
        if "Descrição de Glosa" in l:
            dentro = True
            continue
        if dentro:
            texto.append(l.strip())
    junto = " ".join(texto)
    return {c: d.strip(" ,") for c, d in re.findall(r"(\d{4})\s*-\s*(.*?)(?=,\s*\d{4}\s*-|$)", junto)}


def ler_analise(texto):
    """Demonstrativo de Análise de Conta -> DataFrame, uma linha por procedimento."""
    linhas = _linhas(texto)
    descr = _descricoes_glosa(linhas)
    lote = protocolo = data_protocolo = ""
    guia = guia_op = senha = paciente = carteira = ""
    itens, atual = [], None
    for i, l in enumerate(linhas):
        if re.search(r"9\s*-\s*Numero do Lote", l):
            tok = _depois(linhas, i).split()
            lote, protocolo = (tok + ["", ""])[:2]
            data_protocolo = next((t for t in tok if re.fullmatch(_DATA, t)), "")
        elif re.search(r"14\s*-\s*Número da Guia no Prestador", l):
            tok = _depois(linhas, i).split()
            guia, guia_op, senha = (tok + ["", "", ""])[:3]
        elif re.search(r"17\s*-\s*Nome do benefici", l):
            v = _depois(linhas, i).strip()
            m = re.match(r"^(.*?)\s+(\d{8,})$", v)
            paciente, carteira = (m.group(1).strip(), m.group(2)) if m else (v, "")
        else:
            m = _RE_ITEM.match(l)
            if m:
                atual = dict(
                    Protocolo=protocolo, Lote=lote, **{"Data do protocolo": data_protocolo},
                    **{"Guia do prestador": guia, "Guia da operadora": guia_op, "Senha": senha,
                       "Paciente": paciente, "Carteira": carteira, "Data do atendimento": m.group(2),
                       "Tabela": m.group(3), "Código": m.group(4), "Descrição": m.group(5).strip(),
                       "Valor informado": _num(m.group(6)), "Quantidade": _num(m.group(7)),
                       "Valor processado": _num(m.group(8)), "Valor liberado": _num(m.group(9)),
                       "Valor glosa": 0.0, "Códigos de glosa": []})
                itens.append(atual)
                continue
            m = _RE_GLOSA_ITEM.match(l)
            if m and atual is not None:
                atual["Valor glosa"] = _num(m.group(1))
                atual["Códigos de glosa"].append(m.group(2))
                continue
            m = _RE_SO_CODIGO.match(l)
            if m and atual is not None and atual["Códigos de glosa"]:
                atual["Códigos de glosa"].append(m.group(1))
                continue
            if l.strip().startswith(("Total", "Dados", "Descrição de Glosa")):
                atual = None  # terminou a guia: códigos soltos daqui em diante não são deste item
    df = pd.DataFrame(itens)
    if df.empty:
        return df
    df["Código da glosa"] = df["Códigos de glosa"].map(lambda c: "; ".join(dict.fromkeys(c)))
    df["Motivo da glosa"] = df["Códigos de glosa"].map(
        lambda c: "; ".join(f"{x} {descr.get(x, '')}".strip() for x in dict.fromkeys(c)))
    # glosa que veio sem o valor na linha do item: o que não foi liberado
    sem_valor = (df["Valor glosa"] <= 0) & (df["Valor liberado"] < df["Valor processado"])
    df.loc[sem_valor, "Valor glosa"] = (df["Valor processado"] - df["Valor liberado"])[sem_valor].round(2)
    return df.drop(columns=["Códigos de glosa"])


def ler_pagamento(texto):
    """Demonstrativo de Pagamento -> DataFrame, uma linha por guia."""
    linhas = _linhas(texto)
    data_pag = protocolo = lote = data_protocolo = ""
    guias, atual = [], None
    for i, l in enumerate(linhas):
        if re.search(r"9\s*-\s*Data do Pagamento", l):
            data_pag = next(iter(re.findall(_DATA, _depois(linhas, i))), data_pag)
        elif re.search(r"15\s*-\s*Número do Protocolo", l):
            tok = _depois(linhas, i).split()
            if len(tok) >= 3:
                data_protocolo, protocolo, lote = tok[0], tok[1], tok[2]
        elif re.search(r"44\s*-\s*Número da Guia no Prestador", l):
            tok = _depois(linhas, i).split()
            atual = {"Data do pagamento": data_pag, "Protocolo": protocolo, "Lote": lote,
                     "Data do protocolo": data_protocolo, "Guia do prestador": (tok + [""])[0],
                     "Guia da operadora": (tok + ["", ""])[1]}
        elif re.search(r"48\s*-\s*Valor Processado", l) and atual is not None:
            v = [_num(x) for x in _valores(_depois(linhas, i))]
            if len(v) >= 3:
                atual.update({"Valor processado": v[0], "Valor liberado": v[1], "Valor glosa": v[2]})
                guias.append(atual)
            atual = None
    return pd.DataFrame(guias)


def para_planilha(df, tipo):
    """Converte para as colunas que o leitor do Azus reconhece (como uma planilha de demonstrativo)."""
    if df is None or df.empty:
        return pd.DataFrame()
    if tipo == "analise":
        return pd.DataFrame({
            "Data do Atendimento": df["Data do atendimento"], "Nome do Beneficiário": df["Paciente"],
            "Guia Prestador": df["Guia do prestador"], "Guia Operadora": df["Guia da operadora"],
            "Protocolo": df["Protocolo"], "Lote": df["Lote"], "Código do Procedimento": df["Código"],
            "Descrição do Procedimento": df["Descrição"], "Quantidade": df["Quantidade"],
            "Valor Informado": df["Valor informado"], "Valor Liberado": df["Valor liberado"],
            "Valor Glosa": df["Valor glosa"], "Código da Glosa": df["Código da glosa"],
            "Motivo da Glosa": df["Motivo da glosa"]})
    return pd.DataFrame({
        "Guia Prestador": df["Guia do prestador"], "Guia Operadora": df["Guia da operadora"],
        "Protocolo": df["Protocolo"], "Lote": df["Lote"], "Data de Pagamento": df["Data do pagamento"],
        "Valor Informado": df["Valor processado"], "Valor Liberado": df["Valor liberado"],
        "Valor Glosa": df["Valor glosa"]})

"""
Demonstrativos no padrão TISS da ANS (o mesmo para todas as operadoras), em XML ou PDF:

- Demonstrativo de Análise de Conta: um lote (protocolo) por arquivo, com cada procedimento: data, código,
  valor informado, liberado, glosado e os códigos de glosa. O XML não traz o nome do paciente (só a carteira);
  o PDF traz.
- Demonstrativo de Pagamento: as guias pagas em cada data, por protocolo, com o valor liberado e o glosado.
  Não traz paciente nem procedimento: eles vêm da análise de conta, ligada pelo protocolo + guia no histórico
  (motor_historico). Guias de recurso de glosa vêm com tipo de pagamento 2 e com a linha
  'Ajuste Ant. <protocolo do recurso> - Orig. <protocolo original>'.

ler(dados, nome) devolve as linhas já no formato interno do motor_extracao (antes da análise de glosa), ou
None quando o arquivo não é um demonstrativo TISS (aí o leitor genérico segue normalmente).
"""
import io
import re
import xml.etree.ElementTree as ET

import pandas as pd

import leitor_tiss_pdf as pdf

DOC_ANALISE = "Análise de conta"
DOC_PAGAMENTO = "Pagamento"
TIPO_PAGAMENTO_RECURSO = "2"
MOTIVO_SO_NA_ANALISE = "Motivo não informado no demonstrativo de pagamento (vem na análise de conta)"
AVISO_SEM_ANALISE = "Sem a análise de conta deste protocolo: paciente e procedimento não informados"
ALERTA_GLOSA_MAIOR = "Glosa maior que o valor processado: conferir com a operadora"
ALERTA_GUIA_FORA_PADRAO = "Número da guia fora do padrão das outras (possível erro de digitação no faturamento)"

# Significado dos códigos de glosa (tabela TUSS 38) vistos nos demonstrativos. O XML só traz o código;
# o sistema também aprende os textos dos PDFs (motor_conhecimento).
CODIGOS_GLOSA = {
    "1311": "PRESTADOR EXECUTANTE NÃO INFORMADO",
    "1818": "COBRANÇA DE PROCEDIMENTO QUE EXIGE AUTORIZAÇÃO PRÉVIA",
    "3142": "ITEM NÃO CONTRATADO",
    "3209": "COBRANÇA DE PROCEDIMENTO/ITEM ASSISTENCIAL EM DUPLICIDADE",
    "3210": "COBRANÇA DE PROCEDIMENTO/ITEM ASSISTENCIAL EM QUANTIDADE ACIMA DA MÁXIMA PERMITIDA/AUTORIZADA",
    "3279": "PRESTADOR NÃO HABILITADO/CONTRATADO PARA REALIZAR O PROCEDIMENTO",
    "3292": "QUANTIDADE SOLICITADA DE PROCEDIMENTO/ITEM ASSISTENCIAL ACIMA DA AUTORIZADA",
}

_NS = "{http://www.ans.gov.br/padroes/tiss/schemas}"


def _tag(el):
    return el.tag.split("}")[-1]


def _filho(el, *caminho):
    for nome in caminho:
        if el is None:
            return None
        el = next((c for c in el if _tag(c) == nome), None)
    return el


def _txt(el, *caminho):
    e = _filho(el, *caminho)
    return (e.text or "").strip() if e is not None and e.text else ""


def _filhos(el, nome):
    return [c for c in el if _tag(c) == nome] if el is not None else []


def _todos(el, nome):
    return [c for c in el.iter() if _tag(c) == nome]


def _f(v):
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


def _br(data_iso):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", (data_iso or "").strip()[:10])
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def _motivo(codigos, descricoes):
    return "; ".join(f"{c} {descricoes.get(c) or CODIGOS_GLOSA.get(c, '')}".strip() for c in codigos)


# --------------------------------------------------------------------------
# XML
# --------------------------------------------------------------------------
def tipo_xml(raiz):
    t = next((e.text or "" for e in raiz.iter() if _tag(e) == "tipoTransacao"), "").strip().upper()
    return {"DEMONSTRATIVO_ANALISE_CONTA": "analise", "DEMONSTRATIVO_PAGAMENTO": "pagamento"}.get(t)


def _cabecalho_xml(raiz):
    cab = next((e for e in raiz.iter() if _tag(e) == "cabecalhoDemonstrativo"), None)
    return dict(operadora=_txt(cab, "nomeOperadora"), registro_ans=_txt(cab, "registroANS"),
                numero=_txt(cab, "numeroDemonstrativo"), emissao=_br(_txt(cab, "dataEmissao")))


def ler_analise_xml(raiz):
    """Uma linha por procedimento. Vários motivos de glosa no mesmo procedimento repetem o valor cheio em cada
    motivo: a glosa do procedimento é o MAIOR deles (somar contaria a mesma glosa duas ou três vezes)."""
    itens = []
    for prot in _todos(raiz, "dadosProtocolo"):
        base = {"Protocolo": _txt(prot, "numeroProtocolo"), "Lote": _txt(prot, "numeroLotePrestador"),
                "Data do protocolo": _br(_txt(prot, "dataProtocolo"))}
        for g in _filhos(prot, "relacaoGuias"):
            guia = {"Guia do prestador": _txt(g, "numeroGuiaPrestador"), "Guia da operadora": _txt(g, "numeroGuiaOperadora"),
                    "Senha": _txt(g, "senha"), "Carteira": _txt(g, "numeroCarteira"),
                    "Paciente": _txt(g, "nomeBeneficiario")}
            for d in _filhos(g, "detalhesGuia"):
                glosas = [(_f(_txt(x, "valorGlosa")) or 0.0, _txt(x, "tipoGlosa")) for x in _filhos(d, "relacaoGlosa")]
                codigos = list(dict.fromkeys(c for _, c in glosas if c))
                itens.append({**base, **guia,
                              "Data do atendimento": _br(_txt(d, "dataRealizacao")),
                              "Tabela": _txt(d, "procedimento", "codigoTabela"),
                              "Código": _txt(d, "procedimento", "codigoProcedimento"),
                              "Descrição": _txt(d, "procedimento", "descricaoProcedimento"),
                              "Valor informado": _f(_txt(d, "valorInformado")),
                              "Quantidade": _f(_txt(d, "qtdExecutada")),
                              "Valor processado": _f(_txt(d, "valorProcessado")),
                              "Valor liberado": _f(_txt(d, "valorLiberado")),
                              "Valor glosa": max([v for v, _ in glosas], default=0.0),
                              "Código da glosa": "; ".join(codigos),
                              "Motivo da glosa": _motivo(codigos, {})})
    df = pd.DataFrame(itens)
    if not df.empty:
        # glosa sem valor no XML: o que não foi liberado
        sem = (df["Valor glosa"] <= 0) & (df["Valor liberado"] < df["Valor processado"] - 0.005)
        df.loc[sem, "Valor glosa"] = (df["Valor processado"] - df["Valor liberado"])[sem].round(2)
    return df


def ler_pagamento_xml(raiz):
    """Uma linha por guia paga (em cada data de pagamento do demonstrativo)."""
    guias = []
    for pd_ in _todos(raiz, "pagamentosPorData"):
        data = _br(_txt(pd_, "dadosPagamento", "dataPagamento"))
        ajustes = {}
        for dc in _todos(pd_, "descricaoDbCr"):
            ajustes.update(pdf.ajustes_de_recurso(dc.text or ""))
        for p in _todos(pd_, "relacaoProtocolos"):
            prot = _txt(p, "numeroProtocolo")
            for g in _filhos(p, "guiasDoLote"):
                guias.append({"Data do pagamento": data, "Protocolo": prot, "Lote": _txt(p, "numeroLote"),
                              "Data do protocolo": _br(_txt(p, "dataProtocolo")),
                              "Guia do prestador": _txt(g, "numeroGuiaPrestador"),
                              "Guia da operadora": _txt(g, "numeroGuiaOperadora"),
                              "Tipo de pagamento": _txt(g, "tipoPagamento"),
                              "Protocolo original": ajustes.get(prot, ""),
                              "Valor processado": _f(_txt(g, "valorProcessadoGuia")),
                              "Valor liberado": _f(_txt(g, "valorLiberadoGuia")),
                              "Valor glosa": _f(_txt(g, "valorGlosaGuia"))})
    return pd.DataFrame(guias)


# --------------------------------------------------------------------------
# Formato interno do motor_extracao
# --------------------------------------------------------------------------
def _avisos_guia(guias):
    """Guia com MAIS dígitos que a grande maioria das outras do arquivo (dígito a mais ao digitar; guias com menos
    dígitos são normais: são as mais antigas da numeração)."""
    tam = guias.fillna("").astype(str).str.len()
    if len(tam) < 5:
        return pd.Series(False, index=guias.index)
    moda = tam.mode().iat[0]
    return (tam > moda) & ((tam == moda).mean() >= 0.8)


def _linhas_analise(a, nome_tabela):
    fora = _avisos_guia(a["Guia do prestador"])
    avisos = []
    for i in a.index:
        x = []
        if (a.at[i, "Valor glosa"] or 0) > (a.at[i, "Valor processado"] or 0) + 0.02:
            x.append(ALERTA_GLOSA_MAIOR)
        if fora.at[i]:
            x.append(ALERTA_GUIA_FORA_PADRAO)
        avisos.append("; ".join(x))
    pac = a["Paciente"].fillna("").astype(str).str.strip()
    return pd.DataFrame({
        "Data do evento": a["Data do atendimento"].replace("", "-"),
        "Protocolo": a["Protocolo"], "Doc Original": a["Guia do prestador"].replace("", "-"),
        "Nome do paciente": pac.where(pac.ne(""), "Não identificado"),
        "Código": a["Código"], "Procedimento": a["Descrição"],
        "Motivo da glosa": a["Motivo da glosa"], "Código da glosa": a["Código da glosa"],
        "Valor informado": a["Valor informado"], "Valor pago": a["Valor liberado"].fillna(0.0),
        "Valor da glosa": a["Valor glosa"], "Quantidade": a["Quantidade"], "Quantidade liberada": float("nan"),
        "Valor unitário": float("nan"), "Lote": a["Lote"].replace("", "-"), "Data de pagamento": "-",
        "Documento": DOC_ANALISE, "Carteira": a.get("Carteira", ""), "Data do protocolo": a["Data do protocolo"],
        "Protocolo original": "",
        "_status_glosa": None, "_linha_guia": False, "_aviso_leitura": avisos,
        "_informado_no_arquivo": True, "_glosa_no_arquivo": True, "_tabela": nome_tabela,
    })


def _linhas_pagamento(p, nome_tabela):
    fora = _avisos_guia(p["Guia do prestador"])
    glosa = p["Valor glosa"].fillna(0.0)
    proc = p["Valor processado"].fillna(0.0)
    avisos = ["; ".join([AVISO_SEM_ANALISE] + ([ALERTA_GLOSA_MAIOR] if glosa.at[i] > proc.at[i] + 0.02 else [])
                        + ([ALERTA_GUIA_FORA_PADRAO] if fora.at[i] else [])) for i in p.index]
    tipo = p.get("Tipo de pagamento", pd.Series("", index=p.index)).fillna("")
    origem = p.get("Protocolo original", pd.Series("", index=p.index)).fillna("")
    # pagamento de recurso sem a linha de ajuste: marca o recurso sem saber o protocolo original
    origem = origem.where(origem.ne("") | tipo.ne(TIPO_PAGAMENTO_RECURSO), "recurso")
    return pd.DataFrame({
        "Data do evento": "-", "Protocolo": p["Protocolo"], "Doc Original": p["Guia do prestador"].replace("", "-"),
        "Nome do paciente": "Não identificado", "Código": "", "Procedimento": "",
        "Motivo da glosa": [MOTIVO_SO_NA_ANALISE if g > 0.005 else "" for g in glosa], "Código da glosa": "",
        "Valor informado": p["Valor processado"], "Valor pago": p["Valor liberado"].fillna(0.0),
        "Valor da glosa": glosa, "Quantidade": float("nan"), "Quantidade liberada": float("nan"),
        "Valor unitário": float("nan"), "Lote": p["Lote"].replace("", "-"), "Data de pagamento": p["Data do pagamento"],
        "Documento": DOC_PAGAMENTO, "Carteira": "", "Data do protocolo": p["Data do protocolo"],
        "Protocolo original": origem,
        "_status_glosa": None, "_linha_guia": False, "_aviso_leitura": avisos,
        "_informado_no_arquivo": True, "_glosa_no_arquivo": True, "_tabela": nome_tabela,
    })


def ler(dados, nome=""):
    """(linhas no formato interno, info) ou None se não for um demonstrativo TISS.
    info: tipo ('analise'/'pagamento'), operadora (nome no arquivo), registro_ans, numero, emissao."""
    nome = (nome or "").lower()
    if nome.endswith(".xml"):
        try:
            raiz = ET.parse(io.BytesIO(dados)).getroot()
        except ET.ParseError:
            return None
        tipo = tipo_xml(raiz)
        if not tipo:
            return None
        info = dict(tipo=tipo, formato="XML", **_cabecalho_xml(raiz))
        bruto = ler_analise_xml(raiz) if tipo == "analise" else ler_pagamento_xml(raiz)
    elif nome.endswith(".pdf"):
        try:
            texto = pdf.texto_do_pdf(dados)
        except Exception:
            return None
        tipo = pdf.tipo_de_demonstrativo(texto)
        if not tipo:
            return None
        info = dict(tipo=tipo, formato="PDF", operadora=pdf.nome_operadora(texto), registro_ans="", numero="",
                    emissao="")
        bruto = pdf.ler_analise(texto) if tipo == "analise" else pdf.ler_pagamento(texto)
    else:
        return None
    if bruto is None or bruto.empty:
        return pd.DataFrame(), info
    nome_tabela = f"TISS {info['formato']} ({'análise de conta' if tipo == 'analise' else 'pagamento'})"
    linhas = _linhas_analise(bruto, nome_tabela) if tipo == "analise" else _linhas_pagamento(bruto, nome_tabela)
    return linhas.reset_index(drop=True), info

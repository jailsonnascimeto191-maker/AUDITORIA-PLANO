import pandas as pd
import xml.etree.ElementTree as ET
import fitz  # PyMuPDF
import io
import re

try:
    import docx
except ImportError:
    docx = None

COLUNAS_PADRAO_GLOSAS = [
    "Data do evento",
    "Nome do paciente",
    "Código",
    "Procedimento",
    "Valor informado",
    "Valor pago",
    "Valor da glosa",
    "Motivo da glosa"
]

def extrair_texto_docx(arquivo_docx):
    if docx is None:
        return "Biblioteca python-docx não instalada.", None
    try:
        arquivo_docx.seek(0)
        doc = docx.Document(arquivo_docx)
        texto = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        return texto, None
    except Exception as e:
        return None, str(e)

def extrair_texto_pdf(arquivo_pdf):
    try:
        arquivo_pdf.seek(0)
        doc = fitz.open(stream=arquivo_pdf.read(), filetype="pdf")
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text()
        return texto_completo, None
    except Exception as e:
        return None, str(e)

def extrair_dados_xml_tiss(arquivo_xml):
    try:
        arquivo_xml.seek(0)
        tree = ET.parse(arquivo_xml)
        root = tree.getroot()
        guias = []
        for elem in root.iter():
            if 'guia' in elem.tag.lower():
                guias.append({tag.tag.split('}')[-1]: tag.text for tag in elem})
        return guias, None
    except Exception as e:
        return None, str(e)

def limpar_valor_monetario(val):
    if pd.isnull(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("R$", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9.-]", "", s)
    try:
        return float(s) if s else 0.0
    except:
        return 0.0

def padronizar_data(val):
    if pd.isnull(val):
        return "-"
    s = str(val).strip()
    try:
        dt = pd.to_datetime(val, errors='coerce', dayfirst=True)
        if pd.notnull(dt):
            return dt.strftime('%d/%m/%Y')
    except:
        pass
    return s[:10] if len(s) >= 10 else s

def mapear_dataframe_para_glosas(df_bruto):
    if df_bruto is None or df_bruto.empty:
        return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS)

    df = df_bruto.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]

    def achar_col(palavras_chave):
        for col in df.columns:
            if any(k in col for k in palavras_chave):
                return col
        return None

    col_data = achar_col(["DATA", "ATENDIMENTO", "REALIZACAO", "EXECUCAO", "DT_EVENTO"])
    col_pac = achar_col(["PACIENTE", "BENEFICIARIO", "BENEFICIÁRIO", "NOME", "SEGURADO", "USUARIO", "USUÁRIO"])
    col_cod = achar_col(["CODIGO", "CÓDIGO", "COD_PROC", "PROCEDIMENTO_COD", "TUSS", "AMB"])
    col_proc = achar_col(["PROCEDIMENTO", "DESCRICAO", "DESCRIÇÃO", "SERVICO", "SERVIÇO", "EVENTO"])
    col_v_inf = achar_col(["INFORMADO", "APRESENTADO", "COBRADO", "FATURADO", "VALOR PLANO", "VL_INF"])
    col_v_rec = achar_col(["RECEBIDO", "PAGO", "LIBERADO", "LIQUIDO", "LÍQUIDO", "VL_PAGO"])
    col_v_glo = achar_col(["VALOR DA GLOSA", "VALOR GLOSA", "VL_GLOSA", "GLOSADO", "GLOSA (R$)", "RETIDO"])
    col_m_glo = achar_col(["MOTIVO", "DESCRICAO GLOSA", "DESCRIÇÃO DA GLOSA", "JUSTIFICATIVA", "OBS"])

    df_out = pd.DataFrame()
    df_out["Data do evento"] = df[col_data].apply(padronizar_data) if col_data else "-"
    df_out["Nome do paciente"] = df[col_pac].astype(str) if col_pac else "Não identificado"
    df_out["Código"] = df[col_cod].astype(str) if col_cod else "-"
    df_out["Procedimento"] = df[col_proc].astype(str) if col_proc else "Procedimento Clínico"
    df_out["Valor informado"] = df[col_v_inf].apply(limpar_valor_monetario) if col_v_inf else 0.0
    df_out["Valor pago"] = df[col_v_rec].apply(limpar_valor_monetario) if col_v_rec else 0.0

    if col_v_glo:
        df_out["Valor da glosa"] = df[col_v_glo].apply(limpar_valor_monetario)
    else:
        df_out["Valor da glosa"] = (df_out["Valor informado"] - df_out["Valor pago"]).clip(lower=0.0)

    df_out["Motivo da glosa"] = df[col_m_glo].astype(str) if col_m_glo else "Glosa identificada no demonstrativo"

    df_glosas = df_out[(df_out["Valor da glosa"] > 0) | (df_out["Valor pago"] < df_out["Valor informado"])].copy()
    if df_glosas.empty and len(df_out) > 0:
        return df_out
    return df_glosas

def extrair_glosas_xml(arquivo_xml):
    arquivo_xml.seek(0)
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    registos = []

    def lim_tag(t):
        return t.split('}')[-1].lower() if '}' in t else t.lower()

    for elem in root.iter():
        tag_atual = lim_tag(elem.tag)
        if any(k in tag_atual for k in ['procedimento', 'item', 'detalhe', 'guia']):
            dados_no = {lim_tag(sub.tag): (sub.text.strip() if sub.text else "") for sub in elem.iter()}
            v_inf = limpar_valor_monetario(dados_no.get('valorinformado', dados_no.get('valorapresentado', 0)))
            v_pago = limpar_valor_monetario(dados_no.get('valorpago', dados_no.get('valorliberado', 0)))
            v_glosa = limpar_valor_monetario(dados_no.get('valorglosa', max(0.0, v_inf - v_pago)))
            dt_ev = padronizar_data(dados_no.get('dataatendimento', dados_no.get('data', '-')))

            if v_glosa > 0 or (v_inf > 0 and v_pago < v_inf):
                registos.append({
                    "Data do evento": dt_ev,
                    "Nome do paciente": dados_no.get('nomebeneficiario', dados_no.get('beneficiario', 'Beneficiário TISS')),
                    "Código": dados_no.get('codigoprocedimento', dados_no.get('procedimento', '-')),
                    "Procedimento": dados_no.get('descricaoprocedimento', dados_no.get('descricao', 'Procedimento TISS')),
                    "Valor informado": v_inf,
                    "Valor pago": v_pago,
                    "Valor da glosa": v_glosa if v_glosa > 0 else round(v_inf - v_pago, 2),
                    "Motivo da glosa": dados_no.get('descricaoglosa', dados_no.get('motivoglosa', 'Retenção TISS'))
                })

    return pd.DataFrame(registos, columns=COLUNAS_PADRAO_GLOSAS)

def extrair_glosas_de_arquivo(arquivo_upload, plano="Identificar pelo arquivo"):
    try:
        nome = arquivo_upload.name.lower()
        arquivo_upload.seek(0)

        if nome.endswith((".xlsx", ".xls")):
            df_bruto = pd.read_excel(arquivo_upload)
            return mapear_dataframe_para_glosas(df_bruto), None

        elif nome.endswith(".csv"):
            df_bruto = pd.read_csv(arquivo_upload, sep=None, engine="python")
            return mapear_dataframe_para_glosas(df_bruto), None

        elif nome.endswith((".html", ".htm")):
            tabelas = pd.read_html(arquivo_upload)
            if tabelas:
                return mapear_dataframe_para_glosas(tabelas[0]), None
            return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), "Nenhuma tabela encontrada no HTML."

        elif nome.endswith(".xml"):
            df_xml = extrair_glosas_xml(arquivo_upload)
            return df_xml, None

        elif nome.endswith(".pdf"):
            doc = fitz.open(stream=arquivo_upload.read(), filetype="pdf")
            dfs_pdf = []
            for pagina in doc:
                if hasattr(pagina, "find_tables"):
                    tabs = pagina.find_tables()
                    for t in tabs.tables:
                        df_t = t.to_pandas()
                        dfs_pdf.append(mapear_dataframe_para_glosas(df_t))
            if dfs_pdf:
                df_final = pd.concat(dfs_pdf, ignore_index=True)
                return df_final, None
            return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), None

        elif nome.endswith(".docx") and docx is not None:
            doc = docx.Document(arquivo_upload)
            dfs_doc = []
            for tab in doc.tables:
                dados = [[cel.text.strip() for cel in linha.cells] for linha in tab.rows]
                if len(dados) > 1:
                    df_t = pd.DataFrame(dados[1:], columns=dados[0])
                    dfs_doc.append(mapear_dataframe_para_glosas(df_t))
            if dfs_doc:
                return pd.concat(dfs_doc, ignore_index=True), None
            return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), None

        return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), f"Formato não suportado diretamente: {nome}"
    except Exception as e:
        return pd.DataFrame(columns=COLUNAS_PADRAO_GLOSAS), str(e)

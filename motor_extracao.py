import pandas as pd
import xml.etree.ElementTree as ET
import fitz  # PyMuPDF
import io

try:
    import docx
except ImportError:
    docx = None

def extrair_texto_docx(arquivo_docx):
    """Extrai texto de documentos Word (.docx)."""
    if docx is None:
        return "Biblioteca python-docx não instalada.", None
    try:
        doc = docx.Document(arquivo_docx)
        texto = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        return texto, None
    except Exception as e:
        return None, str(e)

def extrair_texto_pdf(arquivo_pdf):
    """Extrai texto e tabelas de demonstrativos ou espelhamentos em PDF usando PyMuPDF."""
    try:
        doc = fitz.open(stream=arquivo_pdf.read(), filetype="pdf")
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text()
        return texto_completo, None
    except Exception as e:
        return None, str(e)

def extrair_dados_xml_tiss(arquivo_xml):
    """Lê e extrai guias e procedimentos de arquivos XML no padrão TISS."""
    try:
        tree = ET.parse(arquivo_xml)
        root = tree.getroot()
        guias = []
        for elem in root.iter():
            if 'guia' in elem.tag.lower():
                guias.append({tag.tag: tag.text for tag in elem})
        return guias, None
    except Exception as e:
        return None, str(e)

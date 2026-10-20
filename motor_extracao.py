import pandas as pd
import xml.etree.ElementTree as ET
import fitz  # PyMuPDF

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

def extrair_texto_pdf(arquivo_pdf):
    """Extrai texto e tabelas de demonstrativos em PDF usando PyMuPDF."""
    try:
        doc = fitz.open(stream=arquivo_pdf.read(), filetype="pdf")
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text()
        return texto_completo, None
    except Exception as e:
        return None, str(e)

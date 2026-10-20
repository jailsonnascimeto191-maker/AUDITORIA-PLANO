import pandas as pd
import re
import unicodedata
import difflib
import io

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

def normalizar_nome(nome):
    """Remove acentos, converte para maiúsculas e remove espaços extras para padronização."""
    if not isinstance(nome, str):
        return ""
    nfkd = unicodedata.normalize('NFKD', nome)
    palavra_sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'\s+', ' ', palavra_sem_acento).strip().upper()

def comparar_nomes(nome1, nome2, limite_similaridade=0.85):
    """Compara dois nomes usando difflib para verificar similaridade."""
    n1 = normalizar_nome(nome1)
    n2 = normalizar_nome(nome2)
    if n1 == n2:
        return True
    similaridade = difflib.SequenceMatcher(None, n1, n2).ratio()
    return similaridade >= limite_similaridade

def gerar_excel_glosas(df):
    """Gera um ficheiro Excel (.xlsx) a partir do DataFrame de Glosas."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio_Glosas')
    return output.getvalue()

def gerar_pdf_glosas(df):
    """Gera um ficheiro PDF a partir do DataFrame de Glosas formatado para a chefia."""
    if FPDF is None:
        return None
    try:
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Título
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt="Relatório Detalhado de Glosas - Auditoria", ln=True, align='C')
        pdf.ln(5)

        # Configurar larguras das colunas (Total: ~270mm para caber em A4 Paisagem)
        colunas = df.columns.tolist()
        larguras = [35, 20, 50, 25, 25, 25, 25, 65]
        
        # Cabeçalho da Tabela
        pdf.set_font("Arial", 'B', 9)
        for i, col in enumerate(colunas):
            pdf.cell(larguras[i], 8, col, border=1, align='C')
        pdf.ln()

        # Linhas da Tabela
        pdf.set_font("Arial", '', 8)
        for index, row in df.iterrows():
            for i, col in enumerate(colunas):
                valor = row[col]
                if isinstance(valor, (float, int)):
                    if 'Valor' in col or 'Código' not in col:
                        texto = f"R$ {valor:.2f}"
                    else:
                        texto = str(valor)
                else:
                    texto = str(valor)
                
                texto = texto.encode('latin-1', 'replace').decode('latin-1')
                pdf.cell(larguras[i], 8, texto[:40], border=1)
            pdf.ln()
            
        return pdf.output(dest='S').encode('latin-1')
    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")
        return None

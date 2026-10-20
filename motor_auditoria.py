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
    if pd.isnull(nome) or not isinstance(nome, str):
        return ""
    nome = str(nome).upper()
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = re.sub(r'[^A-Z\s]', '', nome)
    return re.sub(r'\s+', ' ', nome).strip()

def simplificar_fonetica(nome):
    if not nome:
        return ""
    return " ".join([re.sub(r'(.)\1+', r'\1', p) for p in nome.split()])

def descobrir_especialidade(descricao):
    desc = str(descricao).upper()
    if 'PSICOM' in desc: return 'PSICOMOTRICIDADE'
    if 'PSICOPED' in desc: return 'PSICOPEDAGOGIA'
    if 'PSICO' in desc or 'PSICOTERAPIA' in desc: return 'PSICOLOGIA'
    if 'FONO' in desc: return 'FONOAUDIOLOGIA'
    if 'NUTRI' in desc: return 'NUTRIÇÃO'
    if 'FISIO' in desc: return 'FISIOTERAPIA'
    if 'TERAPIA OCUPACIONAL' in desc or 'TO' in desc: return 'TERAPIA OCUPACIONAL'
    return 'GERAL'

def extrair_datas_lista(data_str):
    if pd.isnull(data_str):
        return [], 1.0
    texto = str(data_str)
    if hasattr(data_str, 'strftime'):
        return [data_str.strftime('%Y-%m-%d')], 1.0
    padroes = re.findall(r'\d{1,2}[/-]\d{1,2}', texto)
    if len(padroes) > 1:
        return [], float(len(padroes))
    try:
        dt = pd.to_datetime(data_str, errors='coerce', dayfirst=True)
        if pd.notnull(dt):
            return [dt.strftime('%Y-%m-%d')], 1.0
    except:
        pass
    virgulas = texto.count(',') + texto.count(' E ') + texto.count('E\n')
    return [], max(1.0, float(virgulas + 1))

def encontrar_melhor_nome(nome_planilha, lista_nomes_piscina):
    n1 = normalizar_nome(nome_planilha)
    if not n1:
        return ""
    if n1 in lista_nomes_piscina:
        return n1

    def remove_preposicoes(n):
        for p in [' DE ', ' DA ', ' DO ', ' DOS ', ' DAS ']:
            n = f" {n} ".replace(p, ' ')
        return re.sub(r'\s+', ' ', n).strip()

    n1_limpo = remove_preposicoes(n1)
    n1_fon = simplificar_fonetica(n1_limpo)
    w1 = n1_limpo.split()
    melhor_match, maior_sim = None, 0.0

    for n2_orig in lista_nomes_piscina:
        n2 = remove_preposicoes(normalizar_nome(n2_orig))
        n2_fon, w2 = simplificar_fonetica(n2), n2.split()
        if n1_fon == n2_fon:
            return n2_orig
        if len(w1) <= len(w2) and " ".join(w2[:len(w1)]) == n1_limpo:
            return n2_orig
        elif len(w2) < len(w1) and " ".join(w1[:len(w2)]) == n2:
            return n2_orig
        sim = max(
            difflib.SequenceMatcher(None, n1_limpo, n2).ratio(),
            difflib.SequenceMatcher(None, n1_fon, n2_fon).ratio()
        )
        if len(w1) > 0 and len(w2) > 0 and w1[0] == w2[0] and w1[-1] == w2[-1]:
            sim = max(sim, 0.82)
        if sim > maior_sim:
            maior_sim, melhor_match = sim, n2_orig

    return melhor_match if maior_sim >= 0.65 else n1

def comparar_nomes(nome1, nome2, limite_similaridade=0.85):
    n1 = normalizar_nome(nome1)
    n2 = normalizar_nome(nome2)
    if n1 == n2:
        return True
    similaridade = difflib.SequenceMatcher(None, n1, n2).ratio()
    return similaridade >= limite_similaridade

def extrair_nome_operadora(texto):
    t = str(texto).upper()
    if 'BRAD' in t: return 'BRADESCO'
    if 'FOX' in t: return 'FOX'
    if 'MEDS' in t or 'MED S' in t: return 'MEDSERVICE'
    if 'UNIMED' in t: return 'UNIMED'
    if 'CASSI' in t: return 'CASSI'
    if 'SUL' in t: return 'SULAMÉRICA'
    return 'INDEFINIDO'

def gerar_excel_glosas(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio_Glosas')
    return output.getvalue()

def gerar_pdf_glosas(df):
    if FPDF is None:
        return None
    try:
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()

        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt="Relatório Detalhado de Glosas - Auditoria", ln=True, align='C')
        pdf.ln(5)

        colunas = df.columns.tolist()
        # Larguras ajustadas para as 8 colunas (Total: ~277mm para A4 Paisagem)
        larguras = [25, 45, 20, 50, 24, 24, 24, 65]

        pdf.set_font("Arial", 'B', 9)
        for i, col in enumerate(colunas):
            larg = larguras[i] if i < len(larguras) else 30
            col_txt = str(col).encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(larg, 8, col_txt, border=1, align='C')
        pdf.ln()

        pdf.set_font("Arial", '', 8)
        for index, row in df.iterrows():
            for i, col in enumerate(colunas):
                larg = larguras[i] if i < len(larguras) else 30
                valor = row[col]
                if isinstance(valor, (float, int)):
                    if 'Valor' in col:
                        texto = f"R$ {valor:.2f}"
                    else:
                        texto = str(valor)
                else:
                    texto = str(valor)
                texto = texto.encode('latin-1', 'replace').decode('latin-1')
                pdf.cell(larg, 8, texto[:40], border=1)
            pdf.ln()

        return pdf.output(dest='S').encode('latin-1')
    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")
        return None

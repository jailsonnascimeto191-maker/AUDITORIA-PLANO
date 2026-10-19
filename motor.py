import pandas as pd
import openpyxl
import re
import unicodedata
import difflib

def normalizar_nome(nome):
    if pd.isnull(nome): return ""
    nome = str(nome).upper()
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = re.sub(r'[^A-Z\s]', ' ', nome)
    return re.sub(r'\s+', ' ', nome).strip()

def simplificar_fonetica(nome):
    if not nome: return ""
    return " ".join([re.sub(r'(.)\1+', r'\1', p) for p in nome.split()])

def descobrir_especialidade(descricao):
    desc = str(descricao).upper()
    if 'PSICOM' in desc: return 'PSICOMOTRICIDADE'
    if 'PSICOPED' in desc: return 'PSICOPEDAGOGIA'
    if 'PSICO' in desc or 'PSICOTERAPIA' in desc: return 'PSICOLOGIA'
    if 'FONO' in desc: return 'FONOAUDIOLOGIA'
    if 'NUTRI' in desc: return 'NUTRICAO'
    if 'FISIO' in desc: return 'FISIOTERAPIA'
    if 'TERAPIA OCUPACIONAL' in desc or 'TO' in desc: return 'TERAPIA OCUPACIONAL'
    return 'GERAL'

def extrair_datas_lista(data_str):
    if pd.isnull(data_str): return [], 1.0
    texto = str(data_str)
    if hasattr(data_str, 'strftime'): return [data_str.strftime('%Y-%m-%d')], 1.0
    padroes = re.findall(r'\d{1,2}[/-]\d{1,2}', texto)
    if len(padroes) > 1: return [], float(len(padroes))
    try:
        dt = pd.to_datetime(data_str, errors='coerce', dayfirst=True)
        if pd.notnull(dt): return [dt.strftime('%Y-%m-%d')], 1.0
    except: pass
    virgulas = texto.count(',') + texto.count(' E ') + texto.count(' E\n')
    return [], max(1.0, float(virgulas + 1))

def encontrar_melhor_nome(nome_planilha, lista_nomes_piscina):
    n1 = normalizar_nome(nome_planilha)
    if not n1: return ""
    if n1 in lista_nomes_piscina: return n1
        
    def remove_preposicoes(n):
        for p in [' DE ', ' DA ', ' DO ', ' DOS ', ' DAS ']: n = f" {n} ".replace(p, ' ')
        return re.sub(r'\s+', ' ', n).strip()
        
    n1_limpo, n1_fon = remove_preposicoes(n1), simplificar_fonetica(remove_preposicoes(n1))
    w1 = n1_limpo.split()
    
    melhor_match, maior_sim = None, 0.0
    for n2_orig in lista_nomes_piscina:
        n2 = remove_preposicoes(n2_orig)
        n2_fon, w2 = simplificar_fonetica(n2), n2.split()
        
        if n1_fon == n2_fon: return n2_orig
        if len(w1) <= len(w2) and " ".join(w2[:len(w1)]) == n1_limpo: return n2_orig
        elif len(w2) < len(w1) and " ".join(w1[:len(w2)]) == n2: return n2_orig

        sim = max(difflib.SequenceMatcher(None, n1_limpo, n2).ratio(), difflib.SequenceMatcher(None, n1_fon, n2_fon).ratio())
        if len(w1) > 0 and len(w2) > 0 and w1[0] == w2[0] and w1[-1] == w2[-1]: sim = max(sim, 0.82)
        if sim > maior_sim: maior_sim, melhor_match = sim, n2_orig
            
    return melhor_match if maior_sim >= 0.65 else n1

def extrair_nome_operadora(texto):
    t = str(texto).upper()
    if 'BRAD' in t: return 'BRADESCO'
    if 'FOX' in t: return 'FOX'
    if 'MEDS' in t or 'MED S' in t: return 'MEDSERVICE'
    if 'UNIMED' in t: return 'UNIMED'
    if 'CASSI' in t: return 'CASSI'
    return 'INDEFINIDO'

def processar_tabela_valores_por_abas(arquivo_upload):
    """
    Lê um Excel enviado pelo usuário onde cada aba (sheet) representa uma especialidade 
    e traduz as colunas para o padrão do sistema.
    """
    try:
        xl = pd.ExcelFile(arquivo_upload)
        dados_por_especialidade = {}
        
        for aba in xl.sheet_names:
            df_aba = xl.parse(aba)
            
            # Limpeza básica e localização de cabeçalhos
            df_aba.columns = [str(c).strip().upper() for c in df_aba.columns]
            
            # Tenta mapear colunas flexivelmente
            col_plano = next((c for c in df_aba.columns if any(k in c for k in ['PLANO', 'CONVENIO', 'OPERADORA'])), None)
            col_tempo = next((c for c in df_aba.columns if any(k in c for k in ['TEMPO', 'MIN', 'DURACAO'])), None)
            col_v_plano = next((c for c in df_aba.columns if any(k in c for k in ['VALOR PLANO', 'PLANO (R$)', 'VALOR (R$)'])), None)
            col_v_prof = next((c for c in df_aba.columns if any(k in c for k in ['PROF', 'REPASSE', 'VALOR PROF'])), None)
            
            if col_plano and col_tempo:
                df_formatado = pd.DataFrame({
                    "PLANO DE SAÚDE": df_aba[col_plano],
                    "TEMPO": df_aba[col_tempo],
                    "VALOR PLANO (R$)": pd.to_numeric(df_aba[col_v_plano], errors='coerce').fillna(0.0) if col_v_plano else 0.0,
                    "VALOR PROF (R$)": pd.to_numeric(df_aba[col_v_prof], errors='coerce').fillna(0.0) if col_v_prof else 0.0
                })
                # Remove linhas vazias
                df_formatado = df_formatado.dropna(subset=["PLANO DE SAÚDE"])
                dados_por_especialidade[aba.upper()] = df_formatado
                
        return dados_por_especialidade, None
    except Exception as e:
        return None, str(e)

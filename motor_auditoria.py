import pandas as pd
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

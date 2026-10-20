import pandas as pd
import openpyxl

def processar_tabela_valores_por_abas(arquivo_upload):
    """
    Motor dedicado a ler o Excel de valores da clínica, varrendo cada aba (especialidade) 
    e estruturando os planos, tempos e valores.
    """
    try:
        xl = pd.ExcelFile(arquivo_upload)
        dados_por_especialidade = {}
        
        for aba in xl.sheet_names:
            df_raw = xl.parse(aba, header=None)
            
            planos_extraidos = []
            tempos_extraidos = []
            val_plano_extraidos = []
            val_prof_extraidos = []
            
            plano_atual = "GERAL"
            
            for index, row in df_raw.iterrows():
                linha_txt = " ".join([str(val) for val in row.values if pd.notnull(val)]).upper()
                
                if any(op in linha_txt for op in ['BRADESCO', 'UNIMED', 'CASSI', 'FOX', 'SULAMÉRICA', 'SULAMERICA', 'MEDSERVICE', 'PROASA', 'FACHESF']):
                    for op in ['BRADESCO', 'UNIMED', 'CASSI', 'FOX', 'SULAMÉRICA', 'SULAMERICA', 'MEDSERVICE', 'PROASA', 'FACHESF']:
                        if op in linha_txt:
                            plano_atual = op
                            break
                
                col_texto_linha = [str(val) for val in row.values if pd.notnull(val)]
                tempo_encontrado = None
                nums_linha = []
                
                for val in col_texto_linha:
                    v_str = str(val).upper()
                    if '30' in v_str: tempo_encontrado = "30 MIN"
                    elif '60' in v_str or '1H' in v_str: tempo_encontrado = "60 MIN"
                    elif '45' in v_str: tempo_encontrado = "45 MIN"
                    
                    try:
                        num_limpo = float(str(val).replace('R$', '').replace('.', '').replace(',', '.').strip())
                        if num_limpo > 0 and num_limpo < 10000:
                            nums_linha.append(num_limpo)
                    except:
                        pass
                
                if tempo_encontrado and len(nums_linha) >= 1:
                    planos_extraidos.append(plano_atual)
                    tempos_extraidos.append(tempo_encontrado)
                    val_plano_extraidos.append(nums_linha[0])
                    val_prof_extraidos.append(nums_linha[1] if len(nums_linha) > 1 else round(nums_linha[0] / 2, 2))

            if len(planos_extraidos) > 0:
                df_formatado = pd.DataFrame({
                    "PLANO DE SAÚDE": planos_extraidos,
                    "TEMPO": tempos_extraidos,
                    "VALOR PLANO (R$)": val_plano_extraidos,
                    "VALOR PROF (R$)": val_prof_extraidos
                })
            else:
                df_aba = xl.parse(aba)
                df_aba.columns = [str(c).strip().upper() for c in df_aba.columns]
                col_plano = next((c for c in df_aba.columns if any(k in c for k in ['PLANO', 'CONVENIO', 'OPERADORA'])), df_aba.columns[0])
                col_tempo = next((c for c in df_aba.columns if any(k in c for k in ['TEMPO', 'MIN', 'DURACAO'])), df_aba.columns[1] if len(df_aba.columns) > 1 else df_aba.columns[0])
                col_v_plano = next((c for c in df_aba.columns if any(k in c for k in ['VALOR PLANO', 'PLANO (R$)', 'VALOR (R$)'])), None)
                col_v_prof = next((c for c in df_aba.columns if any(k in c for k in ['PROF', 'REPASSE', 'VALOR PROF'])), None)
                
                df_formatado = pd.DataFrame({
                    "PLANO DE SAÚDE": df_aba[col_plano],
                    "TEMPO": df_aba[col_tempo],
                    "VALOR PLANO (R$)": pd.to_numeric(df_aba[col_v_plano], errors='coerce').fillna(0.0) if col_v_plano else 0.0,
                    "VALOR PROF (R$)": pd.to_numeric(df_aba[col_v_prof], errors='coerce').fillna(0.0) if col_v_prof else 0.0
                })
                df_formatado = df_formatado.dropna(subset=["PLANO DE SAÚDE"])
                
            dados_por_especialidade[aba.upper()] = df_formatado
                
        return dados_por_especialidade, None
    except Exception as e:
        return None, str(e)

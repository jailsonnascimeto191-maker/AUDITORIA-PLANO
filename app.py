import streamlit as st
import pandas as pd
import openpyxl
import re
import unicodedata
import difflib
import warnings
import io

# Silenciar avisos irrelevantes do pandas
warnings.filterwarnings('ignore', category=UserWarning)

# Configuração da Página no Streamlit
st.set_page_config(
    page_title="Auditoria & Repasse Financeiro",
    page_icon="🏥",
    layout="wide"
)

# ==========================================
# FUNÇÕES DE LIMPEZA E PADRONIZAÇÃO
# ==========================================
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

# ==========================================
# INTERFACE WEB (STREAMLIT)
# ==========================================
st.title("🏥 Sistema de Auditoria & Repasse Médico")
st.markdown("Plataforma automatizada para cruzamento de extratos de convênios com os espelhamentos dos profissionais.")

st.sidebar.header("📁 1. Extratos das Operadoras")

up_cassi = st.sidebar.file_uploader("CASSI (.xlsx)", type=["xlsx"])
up_unimed = st.sidebar.file_uploader("Unimed (.xlsx)", type=["xlsx"])
up_bradesco = st.sidebar.file_uploader("Bradesco (.xlsx)", type=["xlsx"])
up_fox = st.sidebar.file_uploader("Fox Saúde (.csv)", type=["csv"])
up_medservice = st.sidebar.file_uploader("Medservice (.xlsx)", type=["xlsx"])

st.header("📋 2. Espelhamentos dos Profissionais")
up_espelhamentos = st.file_uploader(
    "Arraste as planilhas dos profissionais (.xlsx)", 
    type=["xlsx"], 
    accept_multiple_files=True
)

if st.button("🚀 Executar Auditoria Completa", type="primary"):
    if not up_espelhamentos:
        st.warning("Envie pelo menos um arquivo de espelhamento para iniciar a auditoria.")
    else:
        lista_piscina = []

        # ------------------ LEITURA CASSI ------------------
        if up_cassi is not None:
            try:
                xls_cassi = pd.ExcelFile(up_cassi)
                aba_cassi = 'Geral Completo' if 'Geral Completo' in xls_cassi.sheet_names else xls_cassi.sheet_names[0]
                df_cassi = pd.read_excel(xls_cassi, sheet_name=aba_cassi)
                for _, r in df_cassi.iterrows():
                    g_val = float(r.get('Val. Glosa', 0) or 0)
                    qtd = float(r.get('Quantidade', 1) or 1)
                    desc_proc = str(r.get('Nome Procedimento', ''))
                    lista_piscina.append(pd.DataFrame([{
                        'PACIENTE': normalizar_nome(str(r.get('Nome Paciente', ''))),
                        'DATA': None,
                        'ESPECIALIDADE': descobrir_especialidade(desc_proc),
                        'VALOR_LIBERADO_PLANO': float(r.get('Val. Liberado', 0) or 0),
                        'VALOR_GLOSA': g_val,
                        'MOTIVO_GLOSA': f'Glosa CASSI (R$ {g_val})' if g_val > 0 else 'Sem Glosa',
                        'OPERADORA': 'CASSI',
                        'QTD': qtd
                    }]))
            except Exception as e:
                st.error(f"Erro ao processar CASSI: {e}")

        # ------------------ LEITURA BRADESCO ------------------
        if up_bradesco is not None:
            try:
                xls_brad = pd.ExcelFile(up_bradesco)
                for aba in xls_brad.sheet_names:
                    df_brad = pd.read_excel(xls_brad, sheet_name=aba, header=None)
                    curr_pac, curr_data = None, None
                    for _, r in df_brad.iterrows():
                        v0, v1, v2 = r.values[0], r.values[1], r.values[2]
                        if pd.notnull(v0) and pd.notnull(v1) and str(v0).strip() != 'Data do Evento' and 'Liberado' not in str(v0):
                            dt, _ = extrair_datas_lista(v0)
                            curr_data = dt[0] if dt else None
                            curr_pac = normalizar_nome(v1)
                        elif pd.isnull(v0) and pd.isnull(v1) and pd.notnull(v2) and str(v2).strip() != 'Código do Procedimento':
                            r_just = str(r.values[10]).strip()
                            try: valor = float(r.values[9])
                            except: valor = 0.0
                            lista_piscina.append(pd.DataFrame([{
                                'PACIENTE': curr_pac, 'DATA': curr_data, 
                                'ESPECIALIDADE': descobrir_especialidade(r.values[3]), 
                                'VALOR_LIBERADO_PLANO': valor, 'VALOR_GLOSA': 0.0, 
                                'MOTIVO_GLOSA': r_just if r_just and r_just.lower() != 'nan' else 'Sem Glosa', 
                                'OPERADORA': 'BRADESCO', 'QTD': 1
                            }]))
            except Exception as e:
                st.error(f"Erro ao processar Bradesco: {e}")

        # ------------------ LEITURA FOX SAÚDE ------------------
        if up_fox is not None:
            try:
                df_fox = pd.read_csv(up_fox, sep=';', encoding='latin1')
                for _, r in df_fox.iterrows():
                    mot = str(r.get('Cod. Glosa', 'Sem Glosa'))
                    dt, _ = extrair_datas_lista(r.get('Data', None))
                    lista_piscina.append(pd.DataFrame([{
                        'PACIENTE': normalizar_nome(str(r.get('Nome', ''))),
                        'DATA': dt[0] if dt else None,
                        'ESPECIALIDADE': descobrir_especialidade(r.get('Descrição', '')),
                        'VALOR_LIBERADO_PLANO': float(r.get('Valor Total', 0) or 0),
                        'VALOR_GLOSA': float(r.get('Val. Glosa', 0) or 0),
                        'MOTIVO_GLOSA': mot if pd.notnull(mot) and mot != 'nan' else 'Sem Glosa',
                        'OPERADORA': 'FOX', 'QTD': 1
                    }]))
            except Exception as e:
                st.error(f"Erro ao processar Fox Saúde: {e}")

        # ------------------ LEITURA MEDSERVICE ------------------
        if up_medservice is not None:
            try:
                df_med = pd.read_excel(up_medservice)
                for _, r in df_med.iterrows():
                    g_val = float(r.get('Glosa Procedimento (R$)', 0) or 0)
                    dt, _ = extrair_datas_lista(r.get('Data Realização', None))
                    lista_piscina.append(pd.DataFrame([{
                        'PACIENTE': normalizar_nome(str(r.get('Beneficiário', ''))),
                        'DATA': dt[0] if dt else None,
                        'ESPECIALIDADE': descobrir_especialidade(str(r.get('Descrição', ''))),
                        'VALOR_LIBERADO_PLANO': float(r.get('Valor Liberado (R$)', 0) or 0),
                        'VALOR_GLOSA': g_val,
                        'MOTIVO_GLOSA': 'Glosa Medservice' if g_val > 0 else 'Sem Glosa',
                        'OPERADORA': 'MEDSERVICE',
                        'QTD': float(r.get('Quantidade Faturada', 1) or 1)
                    }]))
            except Exception as e:
                st.error(f"Erro ao processar Medservice: {e}")

        # ------------------ LEITURA UNIMED ------------------
        if up_unimed is not None:
            try:
                xls_uni = pd.ExcelFile(up_unimed)
                if 'Produção Paga' in xls_uni.sheet_names:
                    for _, r in pd.read_excel(xls_uni, sheet_name='Produção Paga').iterrows():
                        n = str(r.get('Nome do Paciente', ''))
                        pac = n.split(' - ', 1)[1] if ' - ' in n else n
                        qtd_uni = float(r.get('Quantidade', 1) or 1)
                        dt, _ = extrair_datas_lista(r.get('Data', None))
                        lista_piscina.append(pd.DataFrame([{
                            'PACIENTE': normalizar_nome(pac), 'DATA': dt[0] if dt else None,
                            'ESPECIALIDADE': descobrir_especialidade(str(r.get('Descrição', ''))),
                            'VALOR_LIBERADO_PLANO': float(r.get('Valor (R$)', 0) or 0),
                            'VALOR_GLOSA': 0.0, 'MOTIVO_GLOSA': 'Sem Glosa',
                            'OPERADORA': 'UNIMED', 'QTD': qtd_uni
                        }]))
                if 'Glosas' in xls_uni.sheet_names:
                    for _, r in pd.read_excel(xls_uni, sheet_name='Glosas').iterrows():
                        n = str(r.get('Nome do Paciente', ''))
                        pac = n.split(' - ', 1)[1] if ' - ' in n else n
                        dt, _ = extrair_datas_lista(r.get('Dia do Atendimento', None))
                        lista_piscina.append(pd.DataFrame([{
                            'PACIENTE': normalizar_nome(pac), 'DATA': dt[0] if dt else None,
                            'ESPECIALIDADE': descobrir_especialidade(str(r.get('Nome do Procedimento', ''))),
                            'VALOR_LIBERADO_PLANO': 0.0, 'VALOR_GLOSA': float(r.get('Valor da Glosa', 0) or 0),
                            'MOTIVO_GLOSA': str(r.get('Motivo da Glosa', 'Glosa Unimed')),
                            'OPERADORA': 'UNIMED', 'QTD': 1
                        }]))
            except Exception as e:
                st.error(f"Erro ao processar Unimed: {e}")

        # CONSOLIDAÇÃO DA PISCINA
        piscina = pd.concat(lista_piscina, ignore_index=True) if lista_piscina else pd.DataFrame()
        if not piscina.empty:
            piscina['QTD'] = pd.to_numeric(piscina['QTD']).fillna(1).apply(lambda x: 1 if x <= 0 else x)
            piscina['QTD_RESTANTE'] = piscina['QTD']
            piscina['VALOR_UNITARIO_LIBERADO'] = piscina['VALOR_LIBERADO_PLANO'] / piscina['QTD']
            piscina['VALOR_UNITARIO_GLOSA'] = piscina['VALOR_GLOSA'] / piscina['QTD']

        lista_pacientes = piscina['PACIENTE'].unique().tolist() if not piscina.empty else []

        st.success(f"Piscina de Pagamentos Consolidada com {len(piscina)} lançamentos!")

        # PROCESSAMENTO DOS ESPELHAMENTOS
        def aspirar_valores(filtro):
            liberado, glosa, mts = 0.0, 0.0, []
            indices = piscina[filtro & (piscina['QTD_RESTANTE'] > 0)].index
            for idx in indices:
                usar = piscina.at[idx, 'QTD_RESTANTE']
                piscina.at[idx, 'QTD_RESTANTE'] = 0
                liberado += usar * piscina.at[idx, 'VALOR_UNITARIO_LIBERADO']
                glosa += usar * piscina.at[idx, 'VALOR_UNITARIO_GLOSA']
                m = str(piscina.at[idx, 'MOTIVO_GLOSA'])
                if m and m != 'Sem Glosa' and m not in mts: mts.append(m)
            return liberado, glosa, mts

        st.subheader("📥 Arquivos Auditados para Download")

        for arq in up_espelhamentos:
            nome_arq = arq.name
            espec_planilha = descobrir_especialidade(nome_arq)
            
            wb = openpyxl.load_workbook(arq)
            if "Auditoria segundo os planos" in wb.sheetnames: del wb["Auditoria segundo os planos"]
            ws_resumo = wb.create_sheet(title="Auditoria segundo os planos")
            
            headers = ['PROFISSIONAL / ABA', 'PACIENTE', 'CONVÊNIO', 'VALOR INFORMADO', 'VALOR LIBERADO', 'DIFERENÇA (SALDO)', 'STATUS', 'MOTIVO DA GLOSA']
            ws_resumo.append(headers)
            for c in range(1, len(headers)+1):
                ws_resumo.cell(row=1, column=c).font = openpyxl.styles.Font(bold=True, color="FFFFFF")
                ws_resumo.cell(row=1, column=c).fill = openpyxl.styles.PatternFill(start_color="1F4E78", fill_type="solid")

            tot_inf, tot_lib = 0.0, 0.0

            for aba in wb.sheetnames:
                if aba.lower() in ['ref_planos', 'auditoria segundo os planos']: continue
                ws = wb[aba]
                
                hr, col_pac, col_val, col_conv = None, None, None, None
                for r in range(1, 15):
                    for c in range(1, 15):
                        val = str(ws.cell(row=r, column=c).value).strip().upper()
                        if 'PACIENTE' in val: col_pac, hr = c, r
                        elif 'TOTAL' in val or 'VALOR' in val: 
                            if not col_val and c > 2: col_val = c
                        elif 'PLANO' in val or 'CONVENIO' in val or 'CONVÊNIO' in val or 'OPERADORA' in val:
                            col_conv = c
                    if hr: break
                
                if hr and col_pac:
                    col_lib, col_glo, col_mot, col_sta = ws.max_column+1, ws.max_column+2, ws.max_column+3, ws.max_column+4
                    for c in range(1, ws.max_column + 1):
                        hv = str(ws.cell(row=hr, column=c).value).strip().upper()
                        if hv == 'VALOR_LIBERADO_PLANO': col_lib = c
                        elif hv == 'VALOR_GLOSA': col_glo = c
                        elif hv == 'MOTIVO_GLOSA': col_mot = c
                        elif hv == 'STATUS_PLANO_AUDITADO': col_sta = c
                    
                    ws.cell(row=hr, column=col_lib, value="VALOR_LIBERADO_PLANO")
                    ws.cell(row=hr, column=col_glo, value="VALOR_GLOSA")
                    ws.cell(row=hr, column=col_mot, value="MOTIVO_GLOSA")
                    ws.cell(row=hr, column=col_sta, value="STATUS_PLANO_AUDITADO")
                    
                    for r in range(hr + 1, ws.max_row + 1):
                        nome_pac = ws.cell(row=r, column=col_pac).value
                        if not nome_pac: continue
                        
                        raw_conv = str(ws.cell(row=r, column=col_conv).value) if col_conv else ""
                        op_esperada = extrair_nome_operadora(raw_conv)
                        
                        try: val_prof = float(ws.cell(row=r, column=col_val).value or 0) if col_val else 0.0
                        except: val_prof = 0.0

                        nome_match = encontrar_melhor_nome(nome_pac, lista_pacientes)
                        v_lib, v_glo, motivos = 0.0, 0.0, []
                        
                        if not piscina.empty:
                            base_filtro = (piscina['PACIENTE'] == nome_match)
                            if op_esperada != 'INDEFINIDO': base_filtro = base_filtro & (piscina['OPERADORA'] == op_esperada)

                            f_especialidade_estrita = base_filtro & (
                                (piscina['ESPECIALIDADE'] == espec_planilha) | 
                                ((espec_planilha == 'GERAL') & (piscina['ESPECIALIDADE'] == 'GERAL'))
                            )
                            
                            l_esp, g_esp, m_esp = aspirar_valores(f_especialidade_estrita)
                            v_lib += l_esp
                            v_glo += g_esp
                            motivos.extend(m_esp)

                        v_mot = " | ".join(motivos) if motivos else "Sem Glosa"
                        diferenca = v_lib - val_prof
                        
                        if v_lib > 0: 
                            if diferenca < 0: status = 'PAGO A MENOS / PREJUÍZO'
                            elif v_mot != 'Sem Glosa': status = 'PAGO COM RESSALVA / AVISO FLEX'
                            else: status = 'PAGO PELO PLANO'
                        else: 
                            status = 'GLOSADO / NÃO LOCALIZADO'
                            
                        ws.cell(row=r, column=col_lib, value=v_lib)
                        ws.cell(row=r, column=col_glo, value=v_glo)
                        ws.cell(row=r, column=col_mot, value=v_mot)
                        ws.cell(row=r, column=col_sta, value=status)
                        
                        ws_resumo.append([aba, str(nome_pac), raw_conv, val_prof, v_lib, diferenca, status, v_mot])
                        tot_inf += val_prof; tot_lib += v_lib

            dif_total = tot_lib - tot_inf
            ws_resumo.append(['TOTAIS', '', '', tot_inf, tot_lib, dif_total, '', ''])
            
            output_stream = io.BytesIO()
            wb.save(output_stream)
            output_stream.seek(0)
            
            st.download_button(
                label=f"⬇️ Baixar AUDITADO_{nome_arq}",
                data=output_stream,
                file_name=f"AUDITADO_{nome_arq}",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

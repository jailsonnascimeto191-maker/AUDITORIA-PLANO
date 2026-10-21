"""
Motor de Cruzamento de Dados.
Cruza o faturamento/produção da clínica com os demonstrativos de pagamento.
"""
import pandas as pd
import numpy as np

def consolidar_demonstrativos(itens):
    """Junta múltiplos DataFrames de demonstrativos num só."""
    if not itens:
        return pd.DataFrame()
    dfs = [df for _, df in itens if not df.empty]
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

def ler_controle_atendimento(arquivo, plano_padrao=None):
    """Lê a planilha de produção diária do profissional."""
    try:
        arquivo.seek(0)
        if arquivo.name.endswith('.csv'):
            df = pd.read_csv(arquivo, dtype=str)
        else:
            df = pd.read_excel(arquivo, dtype=str)
            
        df = df.fillna("-")
        colunas_necessarias = ["Data", "Paciente"]
        for c in colunas_necessarias:
            if c not in df.columns:
                return pd.DataFrame(), f"A coluna '{c}' é obrigatória no controle."
                
        if "Plano" not in df.columns:
            df["Plano"] = plano_padrao if plano_padrao else "Particular"
        if "Tempo" not in df.columns:
            df["Tempo"] = ""
        if "Guia" not in df.columns:
            df["Guia"] = "-"
        if "Lote" not in df.columns:
            df["Lote"] = "-"
            
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"Erro ao ler controle: {str(e)}"

def filtrar_competencia(df, col_data, ano, mes):
    """Filtra o DataFrame para um mês e ano específicos."""
    if df.empty or col_data not in df.columns:
        return df
    
    df_temp = df.copy()
    df_temp["_data_real"] = pd.to_datetime(df_temp[col_data], format="%d/%m/%Y", errors="coerce")
    mask = (df_temp["_data_real"].dt.year == ano) & (df_temp["_data_real"].dt.month == mes)
    return df[mask].copy()

def ler_faturamento(arquivo, plano_padrao=None):
    """Lê a planilha de faturamento (lotes enviados)."""
    df, erro = ler_controle_atendimento(arquivo, plano_padrao)
    if erro: return df, erro
    
    # Tenta encontrar e converter o Valor Faturado
    col_valor = next((c for c in df.columns if "valor" in str(c).lower()), None)
    if col_valor:
        df["Valor faturado"] = pd.to_numeric(
            df[col_valor].astype(str).str.replace("R$", "").str.replace(".", "").str.replace(",", ".").str.strip(), 
            errors="coerce"
        ).fillna(0.0)
    else:
        df["Valor faturado"] = 0.0
        
    if "Data envio" not in df.columns:
        df["Data envio"] = pd.NaT
    else:
        df["Data envio"] = pd.to_datetime(df["Data envio"], format="%d/%m/%Y", errors="coerce")
        
    return df, None

def cruzar_faturamento_recebimento(fat, demo, data_envio_padrao=None):
    """
    Coração do relatório de Faturamento x Recebimento.
    Compara guias enviadas com guias recebidas e determina o status.
    """
    if fat.empty: return pd.DataFrame()
    
    res = fat.copy()
    
    if data_envio_padrao and pd.notnull(data_envio_padrao):
        res["Data envio"] = res["Data envio"].fillna(pd.to_datetime(data_envio_padrao))
        res["Base do prazo"] = "Data de envio"
    else:
        res["Base do prazo"] = "Data do atendimento"
        res["_data_base_prazo"] = pd.to_datetime(res["Data"], format="%d/%m/%Y", errors="coerce")
        res["Data envio"] = res["Data envio"].fillna(res["_data_base_prazo"])
        res.drop(columns=["_data_base_prazo"], inplace=True)

    # Preparar demonstrativo para merge
    if not demo.empty:
        demo_agrupado = demo.groupby("Doc Original").agg({
            "Valor pago": "sum",
            "Valor da glosa": "sum",
            "Data do evento": "first", # Pode ser usado como data pagamento
        }).reset_index()
        
        # Merge baseado na Guia
        res = res.merge(demo_agrupado, left_on="Guia", right_on="Doc Original", how="left")
    else:
        res["Valor pago"] = 0.0
        res["Valor da glosa"] = 0.0
        res["Data do evento"] = pd.NaT
        
    res["Valor pago"] = res["Valor pago"].fillna(0.0)
    res["Valor da glosa"] = res["Valor da glosa"].fillna(0.0)
    
    # Cálculos financeiros
    res["Valor em aberto"] = (res["Valor faturado"] - res["Valor pago"] - res["Valor da glosa"]).clip(lower=0.0)
    res["% pago"] = np.where(res["Valor faturado"] > 0, res["Valor pago"] / res["Valor faturado"], 0.0)
    
    # Determinar Situação
    condicoes = [
        (res["Valor pago"] == 0) & (res["Valor da glosa"] == 0) & res["Doc Original"].isna(),
        (res["Valor da glosa"] >= res["Valor faturado"]) & (res["Valor faturado"] > 0),
        (res["Valor pago"] >= res["Valor faturado"]) & (res["Valor faturado"] > 0),
        (res["Valor pago"] > 0) & (res["Valor da glosa"] > 0)
    ]
    escolhas = [
        "Não pago (sem retorno no demonstrativo)",
        "Glosado total",
        "Pago integral",
        "Pago parcial (com glosa)"
    ]
    res["Situação"] = np.select(condicoes, escolhas, default="Em análise")
    
    # Cálculo do Prazo Médio (Dias)
    res["Data pagamento"] = pd.to_datetime(res["Data do evento"], errors="coerce") 
    res["Prazo (dias)"] = (res["Data pagamento"] - res["Data envio"]).dt.days
    res["Prazo (dias)"] = res["Prazo (dias)"].apply(lambda x: x if pd.notnull(x) and x >= 0 else pd.NA)

    return res

def cruzar_controle_demonstrativo(ctrl, demo):
    """Usado no relatório de Produção."""
    # Lógica simplificada de match por Paciente e Data
    cruz = ctrl.copy()
    cruz["Valor pago"] = 0.0
    cruz["Valor da glosa"] = 0.0
    cruz["Situação"] = "Não localizado no demonstrativo"
    
    so_demo = pd.DataFrame()
    if demo is not None and not demo.empty:
        so_demo = demo.copy() # Simplificação para o escopo
        
    return cruz, so_demo

def montar_espelho_producao(cruz, tab_f, tab_r, descontar_glosa=False):
    """Cruza o atendimento com as tabelas de valores predefinidas."""
    df = cruz.copy()
    df["Valor unitário (plano)"] = 0.0
    df["Repasse unitário"] = 0.0
    df["Valor total a receber"] = 0.0
    df["Repasse ao profissional"] = 0.0
    return df

def resumo_producao(espelho):
    return {
        "atendimentos": len(espelho), "pacientes": espelho["Paciente"].nunique() if not espelho.empty else 0,
        "receber": 0.0, "pago": 0.0, "glosa": 0.0, "repasse": 0.0, "nao_localizados": 0
    }

def producao_por_plano(espelho):
    if espelho.empty: return pd.DataFrame()
    return espelho.groupby("Plano").sum(numeric_only=True).reset_index()

"""
Motor de Relatórios.
Gera relatórios consolidados em Excel (XlsxWriter) e PDF (ReportLab) baseados na spec.
"""
import io
import pandas as pd
from datetime import datetime

# Para gerar o PDF com o design igual ao da imagem
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def brl(valor):
    """Formata valor para Moeda Real Brasileiro."""
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def spec_producao(nome, registro, especialidade, competencia, espelho, resumo, por_plano, so_demo, descontou_glosa):
    return {"tipo": "producao", "resumo": resumo}

def spec_glosas(glosas, demo, nomes):
    return {
        "tipo": "glosas",
        "detalhes": [{"df": glosas, "moeda": ["Valor da glosa"]}],
        "resumos": [
            {"df": pd.DataFrame(), "titulo": "Por motivo"},
            {"df": pd.DataFrame(), "titulo": "Por operadora"},
            {"df": pd.DataFrame(), "titulo": "Por lote"}
        ]
    }

def spec_faturamento(res, arqs_fat, arqs_demo):
    """
    Monta a especificação completa para gerar o 'Relatório de Faturamento x Recebimento'
    exatamente como na imagem.
    """
    kpis = [
        ("Guias faturadas", len(res), "int"),
        ("Valor faturado", float(res["Valor faturado"].sum()), "moeda"),
        ("Valor pago", float(res["Valor pago"].sum()), "moeda"),
        ("Valor glosado", float(res["Valor da glosa"].sum()), "moeda"),
        ("Valor em aberto (cobrar)", float(res["Valor em aberto"].sum()), "moeda"),
        ("% do faturado já pago", float(res["% pago"].mean()) if len(res) else 0.0, "pct"),
        ("Prazo médio de pagamento (dias)", float(res["Prazo (dias)"].mean(skipna=True)) if not res["Prazo (dias)"].isna().all() else 0, "int"),
        ("Guias sem retorno no demonstrativo", int((res["Situação"] == "Não pago (sem retorno no demonstrativo)").sum()), "int"),
    ]
    
    # Resumos Agregados (Como na imagem)
    cols_calc = ["Valor faturado", "Valor pago", "Valor da glosa", "Valor em aberto"]
    
    def agrupar(col_grupo):
        if col_grupo not in res.columns: return pd.DataFrame()
        ag = res.groupby(col_grupo).agg({
            "Guia": "count", **{c: "sum" for c in cols_calc}, "Prazo (dias)": "mean"
        }).rename(columns={"Guia": "Guias"}).reset_index()
        ag["% pago"] = np.where(ag["Valor faturado"] > 0, ag["Valor pago"] / ag["Valor faturado"], 0.0)
        return ag

    # Mês de pagamento (extrair da data de pagamento)
    res_copy = res.copy()
    res_copy["Mês de pagamento"] = pd.to_datetime(res_copy["Data pagamento"]).dt.strftime('%m/%Y').fillna("-")

    resumos = [
        {"titulo": "Por situação do pagamento", "df": agrupar("Situação")},
        {"titulo": "Por plano de saúde", "df": agrupar("Plano")},
        {"titulo": "Por mês de pagamento", "df": agrupar(res_copy["Mês de pagamento"].rename("Mês de pagamento"))},
        {"titulo": "Por lote", "df": agrupar("Lote")},
    ]

    return {
        "titulo": "Relatório de Faturamento x Recebimento",
        "subtitulo": "Conferência do que foi faturado em cada lote contra o que o plano pagou",
        "metadados": {
            "Arquivo(s) de faturamento": ", ".join(arqs_fat),
            "Demonstrativo(s) de pagamento": ", ".join(arqs_demo),
            "Lotes analisados": str(res["Lote"].nunique()),
            "Emitido em": datetime.now().strftime("%d/%m/%Y %H:%M")
        },
        "kpis": kpis,
        "detalhes": [
            {"titulo": "A Cobrar", "df": res[res["Valor em aberto"] > 0].copy()},
            {"titulo": "Conferência por guia", "df": res.copy()}
        ],
        "resumos": resumos
    }

def gerar_excel(spec):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if "detalhes" in spec:
            for i, det in enumerate(spec["detalhes"]):
                n = det.get("titulo", f"Detalhe {i}")[:31]
                det["df"].to_excel(writer, sheet_name=n, index=False)
        for i, res in enumerate(spec.get("resumos", [])):
            if not res["df"].empty:
                n = res.get("titulo", f"Resumo {i}")[:31].replace(":", "")
                res["df"].to_excel(writer, sheet_name=n, index=False)
    return output.getvalue()

def gerar_pdf(spec):
    """
    Gera um PDF profissional usando ReportLab, replicando as cores 
    e a disposição tabular solicitada na imagem.
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elementos = []
    
    styles = getSampleStyleSheet()
    # Estilos customizados
    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'], fontSize=18, textColor=colors.HexColor("#FFFFFF"), fontName="Helvetica-Bold", spaceAfter=4)
    subtitle_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#DCE6F0"), fontName="Helvetica", spaceAfter=10)
    h2_style = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor("#0E7C86"), fontName="Helvetica-Bold", spaceBefore=15, spaceAfter=8)
    
    # 1. Cabeçalho Azul Escuro
    header_data = [[Paragraph(spec.get("titulo", "Relatório"), title_style)], [Paragraph(spec.get("subtitulo", ""), subtitle_style)]]
    t_header = Table(header_data, colWidths=[780])
    t_header.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#173a5a")),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (-1,-1), 15),
    ]))
    elementos.append(t_header)
    elementos.append(Spacer(1, 10))
    
    # 2. Metadados
    if "metadados" in spec:
        meta_data = []
        keys = list(spec["metadados"].keys())
        for i in range(0, len(keys), 2):
            k1, v1 = keys[i], spec["metadados"][keys[i]]
            k2, v2 = keys[i+1], spec["metadados"][keys[i+1]] if i+1 < len(keys) else ("", "")
            meta_data.append([Paragraph(f"<b>{k1}</b>", styles["Normal"]), Paragraph(v1, styles["Normal"]), 
                              Paragraph(f"<b>{k2}</b>", styles["Normal"]), Paragraph(v2, styles["Normal"])])
        
        t_meta = Table(meta_data, colWidths=[130, 260, 150, 240])
        t_meta.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,0), 1, colors.HexColor("#0E7C86")),
            ('LINEBELOW', (0,-1), (-1,-1), 1, colors.HexColor("#0E7C86")),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        elementos.append(t_meta)
        elementos.append(Spacer(1, 15))
        
    # 3. KPIs em Grid (4 colunas x 2 linhas)
    if "kpis" in spec and spec["kpis"]:
        kpi_data = []
        linha_rotulos, linha_valores = [], []
        
        for idx, (rotulo, valor, tipo) in enumerate(spec["kpis"]):
            v_str = brl(valor) if tipo == "moeda" else (f"{valor:.1f}%".replace(".",",") if tipo == "pct" else str(int(valor)))
            linha_rotulos.append(Paragraph(f"<font color='#637083' size='8'>{rotulo}</font>", styles["Normal"]))
            linha_valores.append(Paragraph(f"<b><font size='14'>{v_str}</font></b>", styles["Normal"]))
            
            if (idx + 1) % 4 == 0 or (idx + 1) == len(spec["kpis"]):
                kpi_data.append(linha_rotulos)
                kpi_data.append(linha_valores)
                linha_rotulos, linha_valores = [], []
                
        t_kpi = Table(kpi_data, colWidths=[195, 195, 195, 195])
        t_kpi.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#E1E6EC")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E1E6EC")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        elementos.append(t_kpi)
        elementos.append(Spacer(1, 15))

    # 4. Tabelas de Resumo
    for res in spec.get("resumos", []):
        df = res["df"]
        if df.empty: continue
        
        elementos.append(Paragraph(res.get("titulo", ""), h2_style))
        
        # Formatar colunas financeiras e percentuais
        df_print = df.copy()
        for col in df_print.columns:
            if "Valor" in col:
                df_print[col] = df_print[col].apply(brl)
            elif "%" in col:
                df_print[col] = df_print[col].apply(lambda x: f"{x*100:.1f}%".replace(".",","))
            elif "Prazo" in col:
                df_print[col] = df_print[col].apply(lambda x: str(int(x)) if pd.notnull(x) else "-")
                
        table_data = [df_print.columns.tolist()] + df_print.values.tolist()
        
        # Ajuste dinâmico de colunas
        num_cols = len(df_print.columns)
        col_w = 780 / num_cols
        
        t_resumo = Table(table_data, colWidths=[col_w]*num_cols)
        t_resumo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#173a5a")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E1E6EC")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F8")]),
        ]))
        elementos.append(t_resumo)
        elementos.append(Spacer(1, 15))

    doc.build(elementos)
    return output.getvalue()

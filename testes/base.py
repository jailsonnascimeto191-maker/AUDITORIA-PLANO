"""Apoio comum aos testes automáticos. Dados 100% sintéticos (nenhum paciente real)."""
import io
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(AQUI)
sys.path.insert(0, REPO)
sys.dont_write_bytecode = True
# bancos SQLite dos testes numa pasta temporária (nunca dentro do repositório) e sem PostgreSQL
os.environ["AZUS_PASTA_DADOS"] = tempfile.mkdtemp(prefix="azus_testes_")
os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("ADMIN_PASSWORD", "Testes2026x")
import logging  # noqa: E402

logging.getLogger("azus").setLevel(logging.CRITICAL)  # erros esperados dos testes de arquivos ruins

import pandas as pd
from openpyxl import Workbook

import motor_extracao as me  # noqa: E402

CAB = ["Data Atendimento", "Protocolo", "Guia", "Beneficiário", "Código", "Descrição",
       "Valor Apresentado", "Valor Pago", "Valor Glosa", "Motivo", "Data Pagamento"]


class Up(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name


def xlsx(abas):
    """abas: {nome: [[linha], ...]} -> bytes .xlsx"""
    wb = Workbook()
    wb.remove(wb.active)
    for nome, linhas in abas.items():
        ws = wb.create_sheet(nome)
        for l in linhas:
            ws.append(l)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def ler(abas_ou_bytes, nome="demo_bradesco.xlsx", conhecimento=None, plano=me.PLANO_AUTOMATICO):
    dados = abas_ou_bytes if isinstance(abas_ou_bytes, bytes) else xlsx(abas_ou_bytes)
    return me.extrair_glosas_de_arquivo(Up(dados, nome), plano=plano, somente_glosas=False,
                                        conhecimento=conhecimento)


def linha(data="05/01/2025", prot="1100000001", guia="900001", pac="ANA TESTE SILVA", cod="50000470",
          proc="SESSAO DE PSICOTERAPIA", inf=100.0, pago=100.0, glosa=0.0, motivo="", dtpag="20/02/2025"):
    return [data, prot, guia, pac, cod, proc, inf, pago, glosa, motivo, dtpag]


def analisado(rows):
    """DataFrame já no formato de saída do motor (para testar funções de ligação diretamente)."""
    base = {c: "" for c in me.COLUNAS_COMPLETAS}
    base.update({"Valor informado": 0.0, "Valor pago": 0.0, "Valor da glosa": 0.0,
                 "Diferença sem justificativa": 0.0, "Complemento recebido": 0.0,
                 "Glosa original": 0.0, "Recebido no recurso": 0.0, "Vínculo": "", "Alertas": ""})
    df = pd.DataFrame([{**base, **r} for r in rows])
    return df


def tabela_valores(linhas):
    """linhas: dicts com plano, especialidade, codigo_tuss, valor_plano, valor_flex, vigencia_inicio, vigencia_fim"""
    cols = ["especialidade", "plano", "tempo_atendimento", "valor_plano", "codigo_tuss", "vigencia_inicio",
            "vigencia_fim", "valor_flex", "procedimento"]
    return pd.DataFrame([{c: l.get(c) for c in cols} for l in linhas], columns=cols)

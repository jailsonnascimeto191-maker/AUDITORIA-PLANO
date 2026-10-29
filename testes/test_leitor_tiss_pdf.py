"""Leitor dos demonstrativos TISS em PDF (texto sintético no formato do modelo da ANS)."""
import unittest

import leitor_tiss_pdf as lt

ANALISE = """
  Dados do Lote/Protocolo
  9 - Numero do Lote    10 - Número do Protocolo 11 - Data do Protocolo 12 - Código da Glosa do Protocolo
           1000001               2000001        01/07/2025                                           6
  Dados da Guia
  14 - Número da Guia no Prestador      15 - Número da Guia Atribuído pela operadora 16 - Senha
    30000001                             40000001                              1234567
  17 - Nome do beneficiário                                                   18 - Número da Carteira
   PACIENTE TESTE UM                                               5000000000000001
   25-Data de realização 26-Tabela 27-Código do procedimento/ 28-Descrição 29-Grau 30-Valor Informado 31-Quant. Executada 32-Valor Processado 33-Valor Liberado
  1-   21/05/2025 22      20104219  SESSAO TESTE           56,88        1        56,88     56,88
  2-   23/05/2025 22      20104219  SESSAO TESTE           56,88        1        56,88      0,00
        56,88  1818
  3-
               3279
  Total da Guia
  Dados da Guia
  14 - Número da Guia no Prestador      15 - Número da Guia Atribuído pela operadora 16 - Senha
    30000002                             40000002
  17 - Nome do beneficiário                                                   18 - Número da Carteira
   PACIENTE TESTE DOIS                                               5000000000000002
  1-   02/06/2025 22      10101012  CONSULTA TESTE           1.095,51        1        1.095,51     1.095,51
  Total da Guia
  Descrição de Glosa
  1818 - COBRANÇA QUE EXIGE AUTORIZAÇÃO PRÉVIA, 3279 - PRESTADOR NÃO HABILITADO
"""

PAGAMENTO = """
  Dados do Pagamento
  9 - Data do Pagamento        10 - Forma de Pagamento
         21/07/2025                  1 - Depósito
  Dados do Resumo
  14-Data de Protocolo       15-Número do Protocolo              16-Número do Lote                17-Valor Informado
       01/06/2025                       2000001                             1000001                                4.550,67
  Dados da Guia
  44 - Número da Guia no Prestador                        45 - Número da Guia Atribuído pela Operadora
                                              30000001                                             40000001        1
  48 - Valor Processado                                   49 - Valor Liberado                                   50 - Valor da Glosa
                                                 113,76                                                 56,88                                                   56,88
"""


class TestLeitorTiss(unittest.TestCase):
    def test_tipo(self):
        self.assertEqual(lt.tipo_de_demonstrativo(ANALISE), "analise")
        self.assertEqual(lt.tipo_de_demonstrativo(PAGAMENTO), "pagamento")
        self.assertIsNone(lt.tipo_de_demonstrativo("qualquer texto"))

    def test_analise(self):
        df = lt.ler_analise(ANALISE)
        self.assertEqual(len(df), 3)
        self.assertEqual(list(df["Guia do prestador"]), ["30000001", "30000001", "30000002"])
        self.assertEqual(df.loc[1, "Valor glosa"], 56.88)
        self.assertEqual(df.loc[1, "Código da glosa"], "1818; 3279")
        self.assertIn("AUTORIZAÇÃO PRÉVIA", df.loc[1, "Motivo da glosa"])
        self.assertEqual(df.loc[2, "Valor informado"], 1095.51)
        self.assertEqual(df.loc[2, "Paciente"], "PACIENTE TESTE DOIS")
        self.assertEqual(df.loc[0, "Lote"], "1000001")

    def test_pagamento(self):
        df = lt.ler_pagamento(PAGAMENTO)
        self.assertEqual(len(df), 1)
        r = df.iloc[0]
        self.assertEqual((r["Data do pagamento"], r["Protocolo"], r["Lote"], r["Guia do prestador"]),
                         ("21/07/2025", "2000001", "1000001", "30000001"))
        self.assertEqual((r["Valor processado"], r["Valor liberado"], r["Valor glosa"]), (113.76, 56.88, 56.88))


if __name__ == "__main__":
    unittest.main(verbosity=2)

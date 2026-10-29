"""Leitura robusta de demonstrativos, glosa x diferença, quantidade, arquivos vazios/corrompidos."""
import unittest

from base import CAB, Up, ler, linha, me, pd, tabela_valores, xlsx

MOT = "1705 VALOR APRESENTADO A MAIOR"


def _so(df, **filtro):
    m = pd.Series(True, index=df.index)
    for c, v in filtro.items():
        m &= df[c].astype(str) == str(v)
    return df[m]


class TestEstrutura(unittest.TestCase):
    def test_cabecalho_em_qualquer_linha(self):
        abas = {"a": [["DEMONSTRATIVO DE ANALISE DE CONTA"], ["Prestador: CLINICA X"], [], [],
                      CAB, linha(), linha(guia="900002", pac="BRUNO TESTE LIMA", pago=60, glosa=40, motivo=MOT)]}
        df, e = ler(abas)
        self.assertIsNone(e)
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(df["Valor da glosa"].sum(), 40.0)

    def test_cabecalho_em_duas_linhas(self):
        # títulos "Valor Pago" e "Motivo" estão na linha de cima; a de baixo tem os demais
        cima = ["", "", "", "", "", "", "", "Valor Pago", "", "Motivo", ""]
        baixo = ["Data Atendimento", "Protocolo", "Guia", "Beneficiário", "Código", "Descrição",
                 "Valor Apresentado", "", "Valor Glosa", "", "Data Pagamento"]
        df, e = ler({"a": [cima, baixo, linha(pago=60, glosa=40, motivo=MOT)]})
        self.assertIsNone(e)
        self.assertEqual(df["Valor pago"].iloc[0], 60.0)
        self.assertEqual(df["Motivo da glosa"].iloc[0], MOT)

    def test_blocos_por_credito(self):
        cab = CAB[:-1]  # sem coluna de data de pagamento: vem do título do bloco
        l1 = linha()[:-1]
        l2 = linha(guia="900002", pac="BRUNO TESTE LIMA", pago=0, glosa=100, motivo=MOT)[:-1]
        abas = {"a": [["Liberado para crédito em 03/06/2025"], cab, l1,
                      ["Liberado para crédito em 10/07/2025"], cab, l2]}
        df, e = ler(abas)
        self.assertIsNone(e)
        self.assertEqual(sorted(df["Data de pagamento"]), ["03/06/2025", "10/07/2025"])
        self.assertEqual(_so(df, **{"Doc Original": "900002"})["Data de pagamento"].iloc[0], "10/07/2025")

    def test_linha_da_guia_mais_procedimentos(self):
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Valor Apresentado",
               "Valor Pago", "Valor Glosa", "Data Pagamento"]
        abas = {"a": [cab,
                      ["05/01/2025", "900001", "ANA TESTE SILVA", "", "", 300, 260, 40, "20/02/2025"],
                      ["", "", "", "50000470", "SESSAO DE PSICOTERAPIA", 100, 100, 0, ""],
                      ["", "", "", "50000500", "AVALIACAO PSICOLOGICA", 200, 160, 40, ""],
                      ["06/01/2025", "900002", "BRUNO TESTE LIMA", "", "", 100, 100, 0, "20/02/2025"],
                      ["", "", "", "50000470", "SESSAO DE PSICOTERAPIA", 100, 100, 0, ""]]}
        df, e = ler(abas)
        self.assertIsNone(e)
        self.assertEqual(len(df), 3, "a linha da guia não pode contar como atendimento")
        self.assertAlmostEqual(df["Valor informado"].sum(), 400.0)
        self.assertEqual(set(df["Doc Original"]), {"900001", "900002"})
        self.assertEqual(set(df["Nome do paciente"]), {"ANA TESTE SILVA", "BRUNO TESTE LIMA"})

    def test_copia_entre_abas_conta_uma_vez(self):
        linhas = [CAB, linha(), linha(guia="900002", pac="BRUNO TESTE LIMA", pago=60, glosa=40, motivo=MOT)]
        df, e = ler({"Junho": linhas, "Copia": linhas})
        self.assertIsNone(e)
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(df["Valor informado"].sum(), 200.0)
        self.assertEqual(df.attrs["resumo"]["copias_removidas"], 2)

    def test_resultado_independe_da_ordem_das_linhas(self):
        ls = [linha(), linha(guia="900002", pac="BRUNO TESTE LIMA", pago=0, glosa=100, motivo=MOT),
              linha(guia="900002", pac="BRUNO TESTE LIMA", pago=100, glosa=0, dtpag="20/04/2025", prot="1100000009"),
              linha(guia="900003", pac="CAIO TESTE ROCHA", pago=60, glosa=40, motivo=MOT)]
        cols = ["Doc Original", "Valor informado", "Valor pago", "Valor da glosa", "Status da glosa",
                "Situação do recurso", "Recebido no recurso"]
        a, _ = ler({"a": [CAB] + ls})
        b, _ = ler({"a": [CAB] + ls[::-1]})
        ka = a[cols].sort_values("Doc Original").reset_index(drop=True)
        kb = b[cols].sort_values("Doc Original").reset_index(drop=True)
        pd.testing.assert_frame_equal(ka, kb)


class TestGlosaXDiferenca(unittest.TestCase):
    def test_glosa_do_arquivo(self):
        df, _ = ler({"a": [CAB, linha(pago=60, glosa=40, motivo=MOT)]})
        r = df.iloc[0]
        self.assertEqual((r["Valor da glosa"], r["Diferença sem justificativa"], r["Status da glosa"]),
                         (40.0, 0.0, "Glosa parcial"))

    def test_glosa_total(self):
        df, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT)]})
        self.assertEqual(df["Status da glosa"].iloc[0], "Glosa total")

    def test_borda_tolerancia_2_centavos_nao_e_glosa(self):
        cab = [c for c in CAB if c != "Valor Glosa"]
        l = linha(pago=99.98); del l[8]
        df, _ = ler({"a": [cab, l]})
        self.assertEqual(df["Status da glosa"].iloc[0], "Sem glosa")
        self.assertEqual(df["Valor da glosa"].iloc[0] + df["Diferença sem justificativa"].iloc[0], 0.0)

    def test_borda_3_centavos_conta(self):
        cab = [c for c in CAB if c != "Valor Glosa"]
        l = linha(pago=99.97); del l[8]
        df, _ = ler({"a": [cab, l]})
        r = df.iloc[0]
        self.assertAlmostEqual(r["Valor da glosa"] + r["Diferença sem justificativa"], 0.03, places=2)

    def _cad(self, valor=100.0):
        return {"tabela_valores": tabela_valores([dict(plano="Bradesco Saúde", especialidade="PSICOLOGIA",
                                                       codigo_tuss="50000470", valor_plano=valor)])}

    def test_sem_justificativa_vira_diferenca_nao_glosa(self):
        # arquivo só com valor pago; referência pela tabela cadastrada; sem motivo -> diferença sem justificativa
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Valor Pago", "Data Pagamento"]
        df, _ = ler({"a": [cab, ["05/01/2025", "900001", "ANA TESTE SILVA", "50000470", "SESSAO", 70, "20/02/2025"]]},
                    conhecimento=self._cad())
        r = df.iloc[0]
        self.assertEqual(r["Fonte do valor informado"], me.FONTE_CADASTRO)
        self.assertEqual((r["Valor da glosa"], r["Diferença sem justificativa"]), (0.0, 30.0))
        self.assertEqual(r["Status da glosa"], "Pago a menor sem justificativa")

    def test_com_justificativa_vira_glosa(self):
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Valor Pago", "Motivo",
               "Data Pagamento"]
        df, _ = ler({"a": [cab, ["05/01/2025", "900001", "ANA TESTE SILVA", "50000470", "SESSAO", 70, MOT,
                                 "20/02/2025"]]}, conhecimento=self._cad())
        r = df.iloc[0]
        self.assertEqual((r["Valor da glosa"], r["Diferença sem justificativa"]), (30.0, 0.0))

    def test_prioridade_arquivo_sobre_tabela(self):
        df, _ = ler({"a": [CAB, linha(inf=100, pago=100)]}, conhecimento=self._cad(150.0))
        r = df.iloc[0]
        self.assertEqual(r["Fonte do valor informado"], me.FONTE_ARQUIVO)
        self.assertEqual(r["Valor informado"], 100.0)

    def test_prioridade_tabela_sobre_aprendido(self):
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Valor Pago", "Data Pagamento"]
        rows = [["05/01/2025", f"90000{i}", f"PAC TESTE {chr(65 + i)}", "50000470", "SESSAO", 80, "20/02/2025"]
                for i in range(5)]
        df, _ = ler({"a": [cab] + rows}, conhecimento=self._cad(100.0))
        self.assertTrue((df["Fonte do valor informado"] == me.FONTE_CADASTRO).all())
        self.assertTrue((df["Valor informado"] == 100.0).all())

    def test_aprendido_quando_nao_ha_tabela(self):
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Valor Pago", "Data Pagamento"]
        rows = [["05/01/2025", f"90000{i}", f"PAC TESTE {chr(65 + i)}", "50000470", "SESSAO", 80, "20/02/2025"]
                for i in range(4)]
        rows.append(["05/01/2025", "900009", "PAC TESTE Z", "50000470", "SESSAO", 50, "20/02/2025"])
        df, _ = ler({"a": [cab] + rows})
        z = _so(df, **{"Doc Original": "900009"}).iloc[0]
        self.assertEqual(z["Fonte do valor informado"], me.FONTE_APRENDIDO)
        self.assertEqual(z["Valor informado"], 80.0)
        self.assertEqual(z["Diferença sem justificativa"], 30.0)


class TestQuantidade(unittest.TestCase):
    def test_quantidade_com_virgula_nao_vira_dinheiro(self):
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Qtde", "Qtd Liberada",
               "Valor Apresentado", "Valor Pago", "Data Pagamento"]
        rows = [cab, ["05/01/2025", "900001", "ANA TESTE SILVA", "50000470", "SESSAO", "4,00", "3,00", "400,00",
                      "300,00", "20/02/2025"]]
        df, _ = ler({"a": rows})
        m = df.attrs["mapeamento"]
        self.assertEqual(m.get("Quantidade"), "Qtde")
        self.assertEqual(m.get("Quantidade liberada"), "Qtd Liberada")
        r = df.iloc[0]
        self.assertEqual((r["Valor informado"], r["Valor pago"], r["Valor da glosa"]), (400.0, 300.0, 100.0))

    def test_quantidade_solta_sem_titulo_nao_vira_valor(self):
        # coluna "Sessões" com 1..4 e um único valor em dinheiro
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Sessões", "Valor Pago",
               "Data Pagamento"]
        rows = [cab] + [["05/01/2025", f"90000{i}", f"PAC TESTE {chr(65 + i)}", "50000470", "SESSAO", i + 1,
                         80.0 * (i + 1), "20/02/2025"] for i in range(4)]
        df, _ = ler({"a": rows})
        self.assertNotIn("Sessões", [v for k, v in df.attrs["mapeamento"].items() if k in me.CAMPOS_DINHEIRO])
        self.assertAlmostEqual(df["Valor pago"].sum(), 800.0)

    def test_quantidade_cortada_vira_glosa(self):
        cab = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Quantidade", "Qtd Liberada",
               "Valor Pago", "Data Pagamento"]
        rows = [cab, ["05/01/2025", "900001", "ANA TESTE SILVA", "50000470", "SESSAO", 4, 3, 300, "20/02/2025"]]
        cad = {"tabela_valores": tabela_valores([dict(plano="Bradesco", especialidade="PSICOLOGIA",
                                                      codigo_tuss="50000470", valor_plano=100.0)])}
        df, _ = ler({"a": rows}, conhecimento=cad)
        r = df.iloc[0]
        self.assertEqual(r["Valor informado"], 400.0)
        self.assertEqual(r["Valor da glosa"], 100.0)
        self.assertTrue(str(r["Motivo da glosa"]).startswith("Quantidade liberada menor"))


class TestArquivosRuins(unittest.TestCase):
    def _chk(self, dados, nome):
        try:
            df, e = me.extrair_glosas_de_arquivo(Up(dados, nome), somente_glosas=False)
        except Exception as ex:  # nunca pode estourar exceção para a tela
            self.fail(f"exceção em {nome}: {type(ex).__name__}: {ex}")
        self.assertTrue(df.empty)
        self.assertTrue(e, f"{nome}: sem mensagem de erro")
        self.assertEqual(list(df.columns), me.COLUNAS_COMPLETAS)
        return e

    def test_vazio(self):
        self.assertIn("vazio", self._chk(b"", "x.xlsx"))

    def test_xlsx_corrompido(self):
        self._chk(b"PK\x03\x04lixo" * 50, "x.xlsx")

    def test_xlsx_so_cabecalho(self):
        self._chk(xlsx({"a": [CAB]}), "x.xlsx")

    def test_xlsx_sem_abas_com_dados(self):
        self._chk(xlsx({"a": [], "b": [[None]]}), "x.xlsx")

    def test_csv_so_separadores(self):
        self._chk(b";;;\n;;;\n", "x.csv")

    def test_csv_binario(self):
        self._chk(bytes(range(256)) * 4, "x.csv")

    def test_xml_malformado(self):
        self._chk(b"<ans:mensagemTISS><abc>", "x.xml")

    def test_html_sem_tabela(self):
        self._chk(b"<html><body><p>nada</p></body></html>", "x.html")

    def test_pdf_corrompido(self):
        self._chk(b"%PDF-1.4 lixo", "x.pdf")

    def test_docx_corrompido(self):
        self._chk(b"PK lixo", "x.docx")

    def test_extensao_nao_suportada(self):
        self._chk(b"abc", "x.doc")

    def test_sem_nome(self):
        import io
        try:
            df, e = me.extrair_glosas_de_arquivo(io.BytesIO(b"abc"))
        except Exception as ex:
            self.fail(f"{type(ex).__name__}: {ex}")
        self.assertTrue(e)


if __name__ == "__main__":
    unittest.main(verbosity=2)

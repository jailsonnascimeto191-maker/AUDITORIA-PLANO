"""Valor cadastrado: vigência pela data do atendimento (datas limite), código TUSS, Rede Nacional x Flex."""
import unittest

from base import ler, me, tabela_valores

CAB = ["Data Atendimento", "Guia", "Beneficiário", "Código", "Descrição", "Valor Pago", "Motivo", "Data Pagamento"]


def _l(data, guia, pago, pac="ANA TESTE SILVA", motivo="", cod="50000470", dtpag="20/03/2025"):
    return [data, guia, pac, cod, "SESSAO DE PSICOTERAPIA", pago, motivo, dtpag]


def _tab(*linhas):
    return {"tabela_valores": tabela_valores([dict(plano="Bradesco Saúde", especialidade="PSICOLOGIA",
                                                   codigo_tuss="50000470", **l) for l in linhas])}


class TestVigente(unittest.TestCase):
    def test_limites_inclusivos(self):
        self.assertTrue(me.vigente("2025-01-01", "2025-12-31", "01/01/2025"))
        self.assertTrue(me.vigente("2025-01-01", "2025-12-31", "31/12/2025"))
        self.assertFalse(me.vigente("2025-01-01", "2025-12-31", "01/01/2026"))
        self.assertFalse(me.vigente("2025-01-01", "2025-12-31", "31/12/2024"))

    def test_formatos_misturados(self):
        self.assertTrue(me.vigente("01/01/2025", "2025-12-31", "2025-06-01"))
        import datetime
        self.assertTrue(me.vigente(datetime.date(2025, 1, 1), None, "15/03/2025"))

    def test_sem_data_vale_o_sem_fim(self):
        self.assertTrue(me.vigente("2025-01-01", None, "-"))
        self.assertFalse(me.vigente("2024-01-01", "2024-12-31", "-"))


class TestVigenciaNoMotor(unittest.TestCase):
    TAB = _tab(dict(valor_plano=100.0, vigencia_inicio="2024-01-01", vigencia_fim="2024-12-31"),
               dict(valor_plano=120.0, vigencia_inicio="2025-01-01", vigencia_fim=None))

    def _ref(self, data, tab=None):
        df, e = ler({"a": [CAB, _l(data, "900001", 50.0, motivo="1705 VALOR")]}, conhecimento=tab or self.TAB)
        self.assertIsNone(e)
        return df.iloc[0]

    def test_ultimo_dia_da_vigencia_antiga(self):
        r = self._ref("31/12/2024")
        self.assertEqual((r["Valor informado"], r["Fonte do valor informado"]), (100.0, me.FONTE_CADASTRO))

    def test_primeiro_dia_da_vigencia_nova(self):
        self.assertEqual(self._ref("01/01/2025")["Valor informado"], 120.0)

    def test_vigencias_que_se_encostam_no_mesmo_dia(self):
        # fim da antiga = início da nova (erro comum de cadastro): não pode cair em silêncio para 'sem valor'
        tab = _tab(dict(valor_plano=100.0, vigencia_inicio="2024-01-01", vigencia_fim="2025-01-01"),
                   dict(valor_plano=120.0, vigencia_inicio="2025-01-01", vigencia_fim=None))
        r = self._ref("01/01/2025", tab)
        self.assertEqual(r["Fonte do valor informado"], me.FONTE_CADASTRO,
                         f"no dia de troca ficou '{r['Fonte do valor informado']}' / alertas='{r['Alertas']}'")

    def test_atendimento_antes_de_qualquer_vigencia(self):
        r = self._ref("15/06/2023")
        self.assertNotEqual(r["Fonte do valor informado"], me.FONTE_CADASTRO)

    def test_codigo_com_pontuacao(self):
        tab = {"tabela_valores": tabela_valores([dict(plano="Bradesco", especialidade="PSICOLOGIA",
                                                      codigo_tuss="50.00.04.70", valor_plano=90.0)])}
        self.assertEqual(self._ref("01/03/2025", tab)["Valor informado"], 90.0)

    def test_codigo_vale_mais_que_especialidade(self):
        tab = {"tabela_valores": tabela_valores([
            dict(plano="Bradesco", especialidade="PSICOLOGIA", codigo_tuss="", valor_plano=70.0),
            dict(plano="Bradesco", especialidade="PSICOLOGIA", codigo_tuss="50000470", valor_plano=90.0)])}
        self.assertEqual(self._ref("01/03/2025", tab)["Valor informado"], 90.0)

    def test_plano_de_outra_operadora_mesmo_prefixo_nao_vale(self):
        # tabela da 'Unimed Recife' não pode valer para a 'Unimed Caruaru'
        tab = {"tabela_valores": tabela_valores([dict(plano="Unimed Recife", especialidade="PSICOLOGIA",
                                                      codigo_tuss="50000470", valor_plano=90.0)])}
        df, _ = ler({"a": [CAB, _l("01/03/2025", "900001", 50.0, motivo="1705 VALOR")]}, conhecimento=tab,
                    plano="Unimed Caruaru")
        self.assertNotEqual(df.iloc[0]["Fonte do valor informado"], me.FONTE_CADASTRO,
                            "valor da Unimed Recife aplicado à Unimed Caruaru")


class TestFlex(unittest.TestCase):
    TAB = _tab(dict(valor_plano=100.0, valor_flex=80.0, vigencia_inicio="2025-01-01"))

    def _ler(self, linhas):
        df, e = ler({"a": [CAB] + linhas}, conhecimento=self.TAB)
        self.assertIsNone(e)
        return df.set_index("Doc Original")

    def test_pago_flex_sem_glosa(self):
        r = self._ler([_l("01/03/2025", "900001", 80.0)]).loc["900001"]
        self.assertEqual((r["Rede"], r["Valor informado"], r["Status da glosa"]), ("Flex", 80.0, "Sem glosa"))

    def test_pago_nacional_sem_glosa(self):
        r = self._ler([_l("01/03/2025", "900001", 100.0)]).loc["900001"]
        self.assertEqual((r["Rede"], r["Valor informado"], r["Status da glosa"]), ("Nacional", 100.0, "Sem glosa"))

    def test_glosa_total_paciente_flex_usa_valor_flex(self):
        df = self._ler([_l("01/03/2025", "900001", 80.0), _l("08/03/2025", "900002", 80.0),
                        _l("15/03/2025", "900003", 0.0, motivo="1705 VALOR")])
        r = df.loc["900003"]
        self.assertEqual((r["Rede"], r["Valor informado"], r["Valor da glosa"]), ("Flex", 80.0, 80.0))

    def test_glosa_total_paciente_sem_historico_e_nacional(self):
        r = self._ler([_l("15/03/2025", "900003", 0.0, motivo="1705 VALOR")]).loc["900003"]
        self.assertEqual((r["Rede"], r["Valor informado"], r["Valor da glosa"]), ("Nacional", 100.0, 100.0))

    def test_flex_nao_contamina_outro_paciente(self):
        df = self._ler([_l("01/03/2025", "900001", 80.0, pac="ANA TESTE SILVA"),
                        _l("15/03/2025", "900003", 0.0, pac="BRUNO TESTE LIMA", motivo="1705 VALOR")])
        self.assertEqual(df.loc["900003", "Valor informado"], 100.0)

    def test_pago_parcial_flex(self):
        df = self._ler([_l("01/03/2025", "900001", 80.0), _l("08/03/2025", "900002", 50.0, motivo="1705 VALOR")])
        r = df.loc["900002"]
        self.assertEqual((r["Rede"], r["Valor da glosa"]), ("Flex", 30.0))

    def test_sem_valor_flex_cadastrado_paciente_flex_paga_nacional(self):
        tab = {"tabela_valores": tabela_valores([
            dict(plano="Bradesco", especialidade="PSICOLOGIA", codigo_tuss="50000470", valor_plano=100.0, valor_flex=80.0),
            dict(plano="Bradesco", especialidade="CONSULTA", codigo_tuss="10101012", valor_plano=150.0)])}
        df, _ = ler({"a": [CAB, _l("01/03/2025", "900001", 80.0),
                           _l("02/03/2025", "900002", 150.0, cod="10101012")]}, conhecimento=tab)
        r = df.set_index("Doc Original").loc["900002"]
        self.assertEqual((r["Valor informado"], r["Status da glosa"]), (150.0, "Sem glosa"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

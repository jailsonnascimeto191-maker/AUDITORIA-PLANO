"""Pagamento em 2 partes, mesma guia em vários créditos, recurso de glosa (dentro do arquivo e entre arquivos)."""
import unittest

from base import CAB, analisado, ler, linha, me, pd

MOT = "1705 VALOR APRESENTADO A MAIOR"


def _ap(df, r):
    a, seg, tipo, ref = r
    return me.aplicar_vinculo_guia(df, a, seg, tipo, None, ref)


def _p(guia, pago, dtpag, inf=100.0, pac="ANA TESTE SILVA", **kw):
    falta = round(inf - pago, 2)
    r = {"Data do evento": "05/01/2025", "Nome do paciente": pac, "Código": "50000470", "Doc Original": guia,
         "Protocolo": kw.pop("prot", "1100000001"), "Valor informado": inf, "Valor pago": pago,
         "Diferença sem justificativa": falta if not kw.get("Motivo da glosa") else 0.0,
         "Valor da glosa": falta if kw.get("Motivo da glosa") else 0.0,
         "Status da glosa": "Pago a menor sem justificativa" if falta > 0 else "Sem glosa",
         "Data de pagamento": dtpag}
    r.update(kw)
    return r


class TestPares(unittest.TestCase):
    def test_par_fecha_no_centavo(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 40, "10/03/2025")])
        pares, amb = me.encontrar_pares(df)
        self.assertEqual(pares, [(0, 1)])
        self.assertEqual(amb, set())

    def test_par_nao_fecha_3_centavos(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 39.97, "10/03/2025")])
        self.assertEqual(me.encontrar_pares(df)[0], [])

    def test_par_nao_fecha_2_centavos(self):
        # regra: "ligado só quando a soma fecha no centavo". 60 + 39,98 = 99,98 != 100,00
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 39.98, "10/03/2025")])
        self.assertEqual(me.encontrar_pares(df)[0], [], "soma 99,98 não fecha 100,00 no centavo")

    def test_par_nao_fecha_1_centavo(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 39.99, "10/03/2025")])
        self.assertEqual(me.encontrar_pares(df)[0], [], "soma 99,99 não fecha 100,00 no centavo")

    def test_ambiguo_nao_liga(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 40, "10/03/2025"), _p("A3", 40, "10/04/2025")])
        pares, amb = me.encontrar_pares(df)
        self.assertEqual(pares, [])
        self.assertEqual(amb, {0, 1, 2})

    def test_ambiguo_marca_alerta_no_arquivo(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 40, "10/03/2025"), _p("A3", 40, "10/04/2025")])
        out, n = me._juntar_complementos(df)
        self.assertEqual(n, 0)
        self.assertTrue(out["Alertas"].str.contains(me.ALERTA_POSSIVEL_PARTES, regex=False).all())

    def test_principal_e_o_primeiro_pagamento(self):
        df = analisado([_p("A2", 40, "10/03/2025"), _p("A1", 60, "10/02/2025")])
        self.assertEqual(me.encontrar_pares(df)[0], [(1, 0)])

    def test_mesma_guia_nao_e_par(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A1", 40, "10/03/2025")])
        self.assertEqual(me.encontrar_pares(df)[0], [])

    def test_ja_vinculado_nao_entra(self):
        df = analisado([_p("A1", 60, "10/02/2025", **{"Vínculo": "x"}), _p("A2", 40, "10/03/2025")])
        self.assertEqual(me.encontrar_pares(df)[0], [])

    def test_aplicar_par_nao_soma_atendimento_duas_vezes(self):
        df = analisado([_p("A1", 60, "10/02/2025"), _p("A2", 40, "10/03/2025")])
        me.aplicar_vinculo(df, 0, 1)
        self.assertEqual(df["Valor informado"].sum(), 100.0)
        self.assertEqual(df["Valor pago"].sum(), 100.0)
        self.assertEqual(df["Valor da glosa"].sum() + df["Diferença sem justificativa"].sum(), 0.0)
        self.assertEqual(df.at[0, "Status da glosa"], me.STATUS_PAGO_EM_PARTES)
        self.assertEqual(df.at[1, "Status da glosa"], me.STATUS_COMPLEMENTO)

    def test_par_dentro_do_arquivo(self):
        ls = [linha(guia="900001", pago=60, glosa=0, dtpag="10/02/2025"),
              linha(guia="900002", pago=40, glosa=0, dtpag="10/03/2025")]
        cab = [c for c in CAB if c != "Valor Glosa"]
        rows = [cab] + [l[:8] + l[9:] for l in ls]
        df, _ = ler({"a": rows})
        # arquivo traz informado e pago: cada linha veio com informado 100 -> ligadas em 2 partes
        self.assertEqual(df["Valor informado"].sum(), 100.0, df[["Doc Original", "Valor informado", "Status da glosa"]])
        self.assertIn(me.STATUS_PAGO_EM_PARTES, set(df["Status da glosa"]))


class TestMesmaGuiaEntreArquivos(unittest.TestCase):
    def _grupo(self, df, grupos):
        return pd.Series(grupos, index=df.index)

    def test_recurso_recebido(self):
        df = analisado([_p("G1", 0, "10/02/2025", **{"Motivo da glosa": MOT}), _p("G1", 100, "10/04/2025", prot="2200000001")])
        res, conf = me.encontrar_mesma_guia(df, self._grupo(df, [1, 2]))
        self.assertEqual(conf, set())
        self.assertEqual([(a, s, t) for a, s, t, _ in res], [(0, [1], "recurso")])
        _ap(df, res[0])
        r = df.loc[0]
        self.assertEqual((r["Situação do recurso"], r["Glosa original"], r["Recebido no recurso"]),
                         (me.RECURSO_RECEBIDO, 100.0, 100.0))
        self.assertEqual(r["Status da glosa"], me.STATUS_RECURSO_PAGO)
        self.assertEqual(r["Data da glosa"], "10/02/2025")
        self.assertEqual(r["Data do recurso"], "10/04/2025")
        self.assertEqual(r["Protocolo do recurso"], "2200000001")
        self.assertEqual(df["Valor informado"].sum(), 100.0)

    def test_recurso_nao_pago(self):
        df = analisado([_p("G1", 0, "10/02/2025", **{"Motivo da glosa": MOT}), _p("G1", 0, "10/04/2025", **{"Motivo da glosa": MOT})])
        res, conf = me.encontrar_mesma_guia(df, self._grupo(df, [1, 2]))
        self.assertEqual(res[0][2], "glosa")
        _ap(df, res[0])
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_NAO_PAGO)
        self.assertEqual(df.at[0, "Recebido no recurso"], 0.0)
        self.assertEqual(df["Valor da glosa"].sum(), 100.0, "glosa mantida conta uma vez")

    def test_recurso_em_parte_entre_arquivos(self):
        # glosado 100 no 1º crédito, recurso pagou 40 no 2º arquivo -> 'Recebido em parte'
        df = analisado([_p("G1", 0, "10/02/2025", **{"Motivo da glosa": MOT}), _p("G1", 40, "10/04/2025")])
        res, conf = me.encontrar_mesma_guia(df, self._grupo(df, [1, 2]))
        self.assertEqual(conf, set(), "recurso pago em parte não deveria ficar só 'para conferir'")
        self.assertEqual(len(res), 1)
        _ap(df, res[0])
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_PARCIAL)

    def test_tres_creditos_recurso_em_duas_vezes(self):
        df = analisado([_p("G1", 0, "10/02/2025", **{"Motivo da glosa": MOT}),
                        _p("G1", 30, "10/04/2025", prot="2200000001"),
                        _p("G1", 70, "10/05/2025", prot="2200000002")])
        res, conf = me.encontrar_mesma_guia(df, self._grupo(df, [1, 2, 3]))
        self.assertEqual([(a, s, t) for a, s, t, _ in res], [(0, [1, 2], "recurso")])
        _ap(df, res[0])
        self.assertEqual(df.at[0, "Recebido no recurso"], 100.0)
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(df.at[0, "Protocolo do recurso"], "2200000001; 2200000002")
        self.assertEqual(df.at[0, "Data do recurso"], "10/05/2025")
        self.assertEqual(df["Valor informado"].sum(), 100.0)

    def test_ordem_das_linhas_nao_muda_o_principal(self):
        df = analisado([_p("G1", 100, "10/04/2025"), _p("G1", 0, "10/02/2025", **{"Motivo da glosa": MOT})])
        res, _ = me.encontrar_mesma_guia(df, self._grupo(df, [2, 1]))
        self.assertEqual(res[0][0], 1)

    def test_duplicidade(self):
        df = analisado([_p("G1", 100, "10/02/2025"), _p("G1", 100, "10/04/2025")])
        res, _ = me.encontrar_mesma_guia(df, self._grupo(df, [1, 2]))
        self.assertEqual(res[0][2], "duplicidade")
        _ap(df, res[0])
        self.assertEqual(df.at[1, "Status da glosa"], me.STATUS_DUPLICIDADE)
        self.assertEqual(df["Valor informado"].sum(), 100.0)

    def test_mesmo_grupo_nao_liga(self):
        df = analisado([_p("G1", 0, "10/02/2025", **{"Motivo da glosa": MOT}), _p("G1", 100, "10/04/2025")])
        res, conf = me.encontrar_mesma_guia(df, self._grupo(df, [1, 1]))
        self.assertEqual(res, [])


class TestMesmaGuiaNoArquivo(unittest.TestCase):
    """Mesma guia em 2/3 créditos dentro do MESMO arquivo: um atendimento, com a história do recurso."""

    def test_dois_creditos_recurso_recebido(self):
        df, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025"),
                           linha(pago=100, glosa=0, dtpag="10/04/2025", prot="2200000001")]})
        self.assertEqual(len(df), 1)
        r = df.iloc[0]
        self.assertEqual(r["Valor informado"], 100.0)
        self.assertEqual(r["Valor pago"], 100.0)
        self.assertEqual(r["Valor da glosa"], 0.0)
        self.assertEqual(r["Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(r["Glosa original"], 100.0)
        self.assertEqual(r["Data da glosa"], "10/02/2025")
        self.assertEqual(r["Protocolo do recurso"], "2200000001")

    def test_dois_creditos_recurso_em_parte(self):
        df, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025"),
                           linha(pago=40, glosa=60, motivo=MOT, dtpag="10/04/2025", prot="2200000001")]})
        r = df.iloc[0]
        self.assertEqual(r["Situação do recurso"], me.RECURSO_PARCIAL)
        self.assertEqual(r["Recebido no recurso"], 40.0)
        self.assertEqual(r["Valor da glosa"], 60.0)

    def test_dois_creditos_nao_pago(self):
        df, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025"),
                           linha(pago=0, glosa=100, motivo=MOT, dtpag="10/04/2025", prot="2200000001")]})
        r = df.iloc[0]
        self.assertEqual(r["Situação do recurso"], me.RECURSO_NAO_PAGO)
        self.assertEqual(r["Valor da glosa"], 100.0, "glosa mantida não pode contar em dobro")
        self.assertEqual(r["Valor informado"], 100.0)

    def test_tres_creditos(self):
        df, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025"),
                           linha(pago=30, glosa=70, motivo=MOT, dtpag="10/04/2025", prot="2200000001"),
                           linha(pago=70, glosa=0, dtpag="10/05/2025", prot="2200000002")]})
        self.assertEqual(len(df), 1)
        r = df.iloc[0]
        self.assertEqual((r["Valor informado"], r["Valor pago"], r["Valor da glosa"]), (100.0, 100.0, 0.0))
        self.assertEqual(r["Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(r["Recebido no recurso"], 100.0)

    def test_mesmo_resultado_no_arquivo_e_entre_arquivos(self):
        """Recurso pago em parte: no mesmo arquivo dá 'Recebido em parte'; entre arquivos tem de dar o mesmo."""
        um, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025"),
                           linha(pago=40, glosa=60, motivo=MOT, dtpag="10/04/2025")]})
        a, _ = ler({"a": [CAB, linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025")]})
        b, _ = ler({"a": [CAB, linha(pago=40, glosa=60, motivo=MOT, dtpag="10/04/2025")]})
        df = pd.concat([a, b], ignore_index=True)
        res, conf = me.encontrar_mesma_guia(df, pd.Series([1, 2]))
        for x in res:
            _ap(df, x)
        self.assertEqual(df.at[0, "Situação do recurso"], um.iloc[0]["Situação do recurso"])
        self.assertAlmostEqual(df["Valor da glosa"].sum(), um["Valor da glosa"].sum())


if __name__ == "__main__":
    unittest.main(verbosity=2)

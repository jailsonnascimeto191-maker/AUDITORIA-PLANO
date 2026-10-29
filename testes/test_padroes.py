"""Famílias de protocolo (motor_padroes) e lotes de reapresentação ligados ao original."""
import unittest

import pandas as pd

from base import analisado, me
import motor_padroes as mp

MOT = "1705 VALOR APRESENTADO A MAIOR"
FAM = ["11", "22"]
TIPOS = {"11": mp.TIPO_NORMAL, "22": mp.TIPO_REAPRESENTACAO}


def _r(prot, guia, pago, dtpag, pac="ANA TESTE SILVA", inf=100.0, glosa=None, motivo=MOT, data="05/01/2025"):
    g = (inf - pago) if glosa is None else glosa
    return {"Data do evento": data, "Nome do paciente": pac, "Código": "50000470", "Doc Original": guia,
            "Protocolo": prot, "Valor informado": inf, "Valor pago": pago, "Valor da glosa": g,
            "Motivo da glosa": motivo if g > 0 else "", "Data de pagamento": dtpag,
            "Status da glosa": "Glosa total" if pago == 0 else ("Glosa parcial" if g > 0 else "Sem glosa")}


class TestTokens(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(mp.tokens("1100000001"), ["1100000001"])
        self.assertEqual(mp.tokens("1100000001; 2200000002"), ["1100000001", "2200000002"])
        self.assertEqual(mp.tokens("12.345.678"), ["12345678"])

    def test_tokens_curtos_nao_numericos_vazios(self):
        for p in ["123", "12345", "ABCDEF", "", "-", None, float("nan"), "   ", "PROT-ABC"]:
            self.assertEqual(mp.tokens(p), [], repr(p))

    def test_familia_de(self):
        self.assertEqual(mp.familia_de("2200001", ["220", "22", "1"]), "220")
        self.assertEqual(mp.familia_de("3300001", ["22", "1"]), "")


def _historico_sintetico(n=30):
    """Família '1...' (lotes normais, contador mudando com o tempo) e '2...' (reapresentação: todos os
    atendimentos já pagos antes na família 1). As duas convivem no tempo."""
    rows = []
    for i in range(n):
        mes = 1 + (i % 10)
        pac = f"PACIENTE TESTE {chr(65 + i % 26)}{chr(65 + i // 26)}"
        data = f"{1 + i % 27:02d}/{mes:02d}/2025"
        rows.append(_r(f"1{mes:02d}{i:07d}", f"8{i:05d}", 0.0, f"15/{mes:02d}/2025", pac=pac, data=data))
        mes2 = min(mes + 1, 12)
        rows.append(_r(f"2{mes2:02d}{i:07d}", f"9{i:05d}", 100.0, f"28/{mes2:02d}/2025", pac=pac, data=data,
                       glosa=0.0))
    return analisado(rows)


class TestFamilias(unittest.TestCase):
    def test_poucos_protocolos_nao_concluem(self):
        df = analisado([_r("1100000001", "1", 0, "10/01/2025")] * 5)
        self.assertEqual(mp.descobrir_familias(df), [])

    def test_protocolos_vazios_curtos_texto(self):
        rows = [_r(p, str(i), 0, "10/01/2025") for i, p in enumerate(["", "-", "123", "ABC", None, "12345"] * 5)]
        df = analisado(rows)
        self.assertEqual(mp.descobrir_familias(df), [])
        fam, analise, tipos = mp.preparar(df)
        self.assertEqual((fam, tipos), ([], {}))

    def test_sem_coluna_protocolo(self):
        df = analisado([_r("1100000001", "1", 0, "10/01/2025")] * 20).drop(columns=["Protocolo"])
        self.assertEqual(mp.descobrir_familias(df), [])

    def test_duas_familias_e_tipo_pela_evidencia(self):
        df = _historico_sintetico()
        fam, analise, tipos = mp.preparar(df)
        self.assertIn("1", fam)
        self.assertIn("2", fam)
        self.assertEqual(tipos.get("2"), mp.TIPO_REAPRESENTACAO, analise.to_string())
        self.assertEqual(tipos.get("1"), mp.TIPO_NORMAL, analise.to_string())

    def test_usuario_manda_mais_que_evidencia(self):
        df = _historico_sintetico()
        _, _, tipos = mp.preparar(df, {"2": {"tipo": mp.TIPO_NORMAL, "usuario": True}})
        self.assertEqual(tipos["2"], mp.TIPO_NORMAL)

    def test_aprendido_nao_sobrepoe_evidencia(self):
        df = _historico_sintetico()
        _, _, tipos = mp.preparar(df, {"2": {"tipo": mp.TIPO_NORMAL, "usuario": False}})
        self.assertEqual(tipos["2"], mp.TIPO_REAPRESENTACAO)

    def test_ligar_no_arquivo_sintetico(self):
        df = _historico_sintetico()
        fam, analise, tipos = mp.preparar(df)
        out, res = mp.ligar_no_arquivo(df, fam, tipos, analise)
        self.assertEqual(res["ligadas"], 30)
        self.assertAlmostEqual(out["Valor informado"].sum(), 3000.0)
        self.assertAlmostEqual(out["Valor da glosa"].sum(), 0.0)
        self.assertTrue((out.loc[out["Situação do recurso"] != "", "Situação do recurso"] == me.RECURSO_RECEBIDO).all())


class TestReapresentacao(unittest.TestCase):
    def _ligar(self, rows):
        df = analisado(rows)
        lig, sem, varios = mp.encontrar_reapresentacoes(df, FAM, TIPOS)
        return df, lig, sem, varios

    def test_zero_originais(self):
        df, lig, sem, varios = self._ligar([_r("2200000001", "G2", 100, "10/04/2025", glosa=0)])
        self.assertEqual((lig, sem, varios), ([], {0}, set()))
        mp.marcar_avisos(df, sem, varios)
        self.assertIn(mp.ALERTA_SEM_ORIGINAL, df.at[0, "Alertas"])

    def test_um_original_recebido(self):
        df, lig, sem, varios = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                             _r("2200000001", "G2", 100, "10/04/2025", glosa=0)])
        self.assertEqual(lig, [(0, 1)])
        mp.aplicar_reapresentacao(df, 0, 1)
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(df.at[0, "Status da glosa"], me.STATUS_RECURSO_PAGO)
        self.assertEqual(df.at[0, "Glosa original"], 100.0)
        self.assertEqual(df.at[0, "Valor da glosa"], 0.0)
        self.assertEqual(df.at[1, "Valor informado"], 0.0)
        self.assertEqual(df["Valor informado"].sum(), 100.0)

    def test_um_original_em_parte(self):
        df, lig, _, _ = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                     _r("2200000001", "G2", 40, "10/04/2025", glosa=60)])
        mp.aplicar_reapresentacao(df, *lig[0])
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_PARCIAL)
        self.assertEqual(df.at[0, "Valor da glosa"], 60.0)
        self.assertEqual(df["Valor da glosa"].sum(), 60.0, "glosa do lote de reapresentação não pode somar de novo")

    def test_um_original_nao_pago(self):
        df, lig, _, _ = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                     _r("2200000001", "G2", 0, "10/04/2025")])
        mp.aplicar_reapresentacao(df, *lig[0])
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_NAO_PAGO)
        self.assertEqual(df["Valor da glosa"].sum(), 100.0)
        self.assertEqual(df.at[1, "Status da glosa"], me.STATUS_GLOSA_MANTIDA)

    def test_dois_originais_ambiguo(self):
        df, lig, sem, varios = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                             _r("1100000002", "G3", 0, "12/02/2025"),
                                             _r("2200000001", "G2", 50, "10/04/2025", glosa=0)])
        self.assertEqual((lig, varios), ([], {2}))
        mp.marcar_avisos(df, sem, varios)
        self.assertIn(mp.ALERTA_VARIOS_ORIGINAIS, df.at[2, "Alertas"])

    def test_dois_originais_desempate_exato(self):
        df, lig, sem, varios = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                             _r("1100000002", "G3", 60, "12/02/2025"),
                                             _r("2200000001", "G2", 40, "10/04/2025", glosa=0)])
        self.assertEqual(lig, [(1, 2)])

    def test_reapresentacao_antes_do_original_nao_liga(self):
        df, lig, sem, varios = self._ligar([_r("1100000001", "G1", 0, "10/05/2025"),
                                             _r("2200000001", "G2", 100, "10/04/2025", glosa=0)])
        self.assertEqual((lig, sem), ([], {1}))

    def test_original_reapresentado_duas_vezes(self):
        df, lig, sem, varios = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                             _r("2200000002", "G2", 70, "10/05/2025", glosa=0),
                                             _r("2200000001", "G2", 30, "10/04/2025", glosa=0)])
        self.assertEqual(lig, [(0, 2), (0, 1)])
        for a, k in lig:
            mp.aplicar_reapresentacao(df, a, k)
        self.assertEqual(df.at[0, "Recebido no recurso"], 100.0)
        self.assertEqual(df.at[0, "Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(df.at[0, "Protocolo do recurso"], "2200000001; 2200000002")
        self.assertEqual(df["Valor informado"].sum(), 100.0)

    def test_recebeu_acima_gera_alerta(self):
        df, lig, _, _ = self._ligar([_r("1100000001", "G1", 60, "10/02/2025"),
                                     _r("2200000001", "G2", 60, "10/04/2025", glosa=0)])
        mp.aplicar_reapresentacao(df, *lig[0])
        self.assertIn(mp.ALERTA_ACIMA, df.at[0, "Alertas"])

    def test_protocolo_vazio_nunca_e_reapresentacao(self):
        df, lig, sem, varios = self._ligar([_r("1100000001", "G1", 0, "10/02/2025"),
                                             _r("", "G2", 100, "10/04/2025", glosa=0)])
        self.assertEqual((lig, sem, varios), ([], set(), set()))


if __name__ == "__main__":
    unittest.main(verbosity=2)

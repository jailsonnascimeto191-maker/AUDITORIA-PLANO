"""Histórico (SQLite): ligações entre arquivos, desfazer ao remover, mesmo resultado em qualquer ordem."""
import itertools
import os
import shutil
import tempfile
import unittest

import pandas as pd

from base import AQUI, CAB, ler, linha, me
import motor_conhecimento as mk
import motor_historico as mh

MOT = "1705 VALOR APRESENTADO A MAIOR"
OP = "Bradesco Saúde"
CHAVE = ["Doc Original", "Código", "Data do evento", "Nome do paciente", "Data de pagamento"]
VER = ["Valor informado", "Valor pago", "Valor da glosa", "Diferença sem justificativa", "Status da glosa",
       "Situação do recurso", "Glosa original", "Recebido no recurso"]

TMP_RAIZ = os.path.join(os.environ["AZUS_PASTA_DADOS"], "historico")


class Base(unittest.TestCase):
    def setUp(self):
        os.makedirs(TMP_RAIZ, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=TMP_RAIZ)
        mh.DB = mk.DB = os.path.join(self.dir, "valores_clinica.db")  # caminho ABSOLUTO: nada no repositório
        mh.init_historico()
        mk.init_conhecimento()
        self.ids = {}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def enviar(self, nome, linhas, cab=CAB):
        df, e = ler({"a": [cab] + linhas}, nome=nome + ".xlsx")
        self.assertIsNone(e, e)
        df["Operadora"] = OP
        did, _, ign = mh.salvar_demonstrativo(df, nome, "hash-" + nome, "teste", OP)
        mh.vincular_historico(OP, did)
        self.ids[nome] = did
        return did, ign

    def excluir(self, nome):
        mh.excluir_demonstrativo(self.ids.pop(nome))

    def itens(self):
        it = mh.carregar_itens()
        return it.sort_values(CHAVE).reset_index(drop=True)

    def estado(self):
        it = self.itens()
        return it[CHAVE + VER].reset_index(drop=True)


A_GLOSA = linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025", prot="1100000001")
B_REC = linha(pago=100, glosa=0, dtpag="10/04/2025", prot="2200000001")
B_PARTE = linha(pago=40, glosa=60, motivo=MOT, dtpag="10/04/2025", prot="2200000001")


class TestRecursoEntreArquivos(Base):
    def test_recurso_recebido_liga(self):
        self.enviar("A", [A_GLOSA])
        self.enviar("B", [B_REC])
        it = self.itens()
        a = it[it["Data de pagamento"] == "10/02/2025"].iloc[0]
        self.assertEqual(a["Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(a["Glosa original"], 100.0)
        self.assertEqual(it["Valor informado"].sum(), 100.0)
        self.assertEqual(it["Valor da glosa"].sum(), 0.0)

    def test_remover_arquivo_desfaz(self):
        self.enviar("A", [A_GLOSA])
        antes = self.estado()
        self.enviar("B", [B_REC])
        self.excluir("B")
        pd.testing.assert_frame_equal(self.estado(), antes)
        self.assertEqual(self.itens()["Vínculo"].iloc[0], "")

    def test_remover_original_restaura_o_recurso(self):
        self.enviar("B", [B_REC])
        so_b = self.estado()
        self.enviar("A", [A_GLOSA])
        self.excluir("A")
        pd.testing.assert_frame_equal(self.estado(), so_b)

    def test_ordem_de_envio_nao_importa(self):
        self.enviar("A", [A_GLOSA]); self.enviar("B", [B_REC])
        ab = self.estado()
        self.excluir("A"); self.excluir("B")
        self.enviar("B", [B_REC]); self.enviar("A", [A_GLOSA])
        pd.testing.assert_frame_equal(self.estado(), ab)

    def test_reenviar_o_mesmo_arquivo_nao_duplica(self):
        self.enviar("A", [A_GLOSA]); self.enviar("B", [B_REC])
        antes = self.estado()
        self.enviar("B", [B_REC])
        pd.testing.assert_frame_equal(self.estado(), antes)

    def test_recurso_em_parte_nao_conta_atendimento_duas_vezes(self):
        self.enviar("A", [A_GLOSA])
        self.enviar("B", [B_PARTE])
        it = self.itens()
        self.assertEqual(it["Valor informado"].sum(), 100.0, it[VER].to_string())
        self.assertEqual(it["Valor da glosa"].sum() + it["Diferença sem justificativa"].sum(), 60.0)
        a = it[it["Data de pagamento"] == "10/02/2025"].iloc[0]
        self.assertEqual(a["Situação do recurso"], me.RECURSO_PARCIAL)

    def test_recurso_em_parte_igual_ao_arquivo_unico(self):
        um, _ = ler({"a": [CAB, A_GLOSA, B_PARTE]})
        self.enviar("A", [A_GLOSA]); self.enviar("B", [B_PARTE])
        it = self.itens()
        self.assertAlmostEqual(it["Valor informado"].sum(), um["Valor informado"].sum())
        self.assertAlmostEqual(it["Valor da glosa"].sum() + it["Diferença sem justificativa"].sum(),
                               um["Valor da glosa"].sum() + um["Diferença sem justificativa"].sum())


class TestTresCreditos(Base):
    L = {"A": linha(pago=0, glosa=100, motivo=MOT, dtpag="10/02/2025", prot="1100000001"),
         "B": linha(pago=30, glosa=70, motivo=MOT, dtpag="10/04/2025", prot="2200000001"),
         "C": linha(pago=70, glosa=30, motivo=MOT, dtpag="10/05/2025", prot="2200000002")}

    def test_tres_arquivos_qualquer_ordem(self):
        resultados = {}
        for ordem in itertools.permutations("ABC"):
            for n in list(self.ids):
                self.excluir(n)
            for n in ordem:
                self.enviar(n, [self.L[n]])
            resultados["".join(ordem)] = self.estado()
        ref = resultados["ABC"]
        self.assertEqual(ref["Valor informado"].sum(), 100.0, ref.to_string())
        self.assertEqual(ref["Valor da glosa"].sum(), 0.0, ref.to_string())
        for k, v in resultados.items():
            with self.subTest(ordem=k):
                pd.testing.assert_frame_equal(v, ref)

    def test_remover_do_meio_e_reenviar(self):
        for n in "ABC":
            self.enviar(n, [self.L[n]])
        completo = self.estado()
        self.excluir("B")
        self.enviar("B", [self.L["B"]])
        pd.testing.assert_frame_equal(self.estado(), completo)

    def test_pago_de_novo_depois_do_recurso(self):
        # glosa -> recurso pago -> o plano paga a mesma guia outra vez (duplicidade)
        um, _ = ler({"a": [CAB, A_GLOSA, B_REC, linha(pago=100, glosa=0, dtpag="10/06/2025", prot="2200000003")]})
        self.assertEqual(um.iloc[0]["Status da glosa"], me.STATUS_DUPLICIDADE)  # no mesmo arquivo: detecta
        self.enviar("A", [A_GLOSA]); self.enviar("B", [B_REC])
        self.enviar("C", [linha(pago=100, glosa=0, dtpag="10/06/2025", prot="2200000003")])
        it = self.itens()
        self.assertEqual(it["Valor informado"].sum(), 100.0, it[VER].to_string())
        self.assertGreater(len(mh.possiveis_duplicidades()), 0, "pagamento repetido entre arquivos não detectado")


class TestParesEntreArquivos(Base):
    CAB2 = [c for c in CAB if c != "Valor Glosa"]

    def _l(self, guia, pago, dtpag):
        l = linha(guia=guia, pago=pago, dtpag=dtpag)
        return l[:8] + l[9:]

    def test_par_liga_e_desfaz(self):
        self.enviar("A", [self._l("900001", 60, "10/02/2025")], cab=self.CAB2)
        antes = self.estado()
        self.enviar("B", [self._l("900002", 40, "10/03/2025")], cab=self.CAB2)
        it = self.itens()
        self.assertEqual(it["Valor informado"].sum(), 100.0)
        self.assertIn(me.STATUS_PAGO_EM_PARTES, set(it["Status da glosa"]))
        self.excluir("B")
        pd.testing.assert_frame_equal(self.estado(), antes)

    def test_ambiguo_entre_arquivos_avisa_e_limpa(self):
        self.enviar("A", [self._l("900001", 60, "10/02/2025")], cab=self.CAB2)
        self.enviar("B", [self._l("900002", 40, "10/03/2025")], cab=self.CAB2)
        self.enviar("C", [self._l("900003", 40, "10/04/2025")], cab=self.CAB2)
        it = self.itens()
        # A já foi ligado a B antes de C chegar; C fica sem par: tem de ficar sinalizado para conferir
        c = it[it["Doc Original"] == "900003"].iloc[0]
        self.assertTrue(c["Vínculo"] or me.ALERTA_POSSIVEL_PARTES in c["Alertas"],
                        "terceira parte candidata ficou sem aviso")


class TestRemocaoNaoPerdeDados(Base):
    def test_linha_ignorada_por_ja_existir_volta_ao_remover_o_outro(self):
        r1 = linha(guia="900001", pago=100, glosa=0, dtpag="10/02/2025")
        r2 = linha(guia="900002", pac="BRUNO TESTE LIMA", pago=100, glosa=0, dtpag="10/02/2025")
        self.enviar("A", [r1])
        _, ign = self.enviar("B", [r1, r2])  # B é um arquivo maior que contém o mesmo crédito de A
        self.assertEqual(ign, 1)
        self.excluir("A")
        it = self.itens()
        self.assertEqual(sorted(it["Doc Original"]), ["900001", "900002"],
                         "o atendimento 900001 está no arquivo B mas sumiu do histórico ao remover A")


if __name__ == "__main__":
    unittest.main(verbosity=2)

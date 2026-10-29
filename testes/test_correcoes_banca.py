"""Testes das correções pedidas pela banca de revisão (segurança, leitura, histórico, valores).
Dados 100% sintéticos."""
import io
import os
import shutil
import tempfile
import unittest

import openpyxl

from base import CAB, ler, linha, me
import motor_conhecimento as mk
import motor_cruzamento as mc
import motor_historico as mh
import motor_relatorios as mr
import motor_seguranca as ms
import motor_verificacao as mv

OP = "Bradesco Saúde"
CSV_CAB = "Data Atendimento;Paciente;Guia;Codigo;Valor Apresentado;Valor Pago;Data Pagamento\n"


def ler_csv(texto, nome="t.csv"):
    b = io.BytesIO(texto.encode())
    b.name = nome
    return me.extrair_glosas_de_arquivo(b, OP, somente_glosas=False)


class BancoTemporario(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=os.environ["AZUS_PASTA_DADOS"])
        mh.DB = mk.DB = os.path.join(self.dir, "valores_clinica.db")
        ms.DB_SEGURANCA = os.path.join(self.dir, "seguranca.db")
        mh.init_historico()
        mk.init_conhecimento()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def salvar(self, df, nome):
        df = df.copy()
        df["Operadora"] = OP
        r = mh.salvar_demonstrativo(df, nome, "hash-" + nome, "teste", OP)
        mh.vincular_historico(OP)
        return r


class TestSeguranca(BancoTemporario):
    def test_sem_admin_password_nao_cria_admin_com_senha_padrao(self):
        senha = os.environ.pop("ADMIN_PASSWORD", None)
        try:
            ms.init_db_seguranca()
            self.assertFalse(ms.existe_administrador())
            self.assertFalse(ms.autenticar_usuario("admin", "admin123")[0])
        finally:
            if senha:
                os.environ["ADMIN_PASSWORD"] = senha

    def test_senha_antiga_admin123_nao_entra(self):
        ms.init_db_seguranca()
        with ms._conn() as c:
            cur = c.cursor()
            ms._inserir(cur, "velho", "admin123", "Administrador", trocar=False)
            c.commit()
        self.assertFalse(ms.autenticar_usuario("velho", "admin123")[0])

    def test_usuario_inexistente_responde_igual_ao_existente(self):
        ms.init_db_seguranca()
        a = [ms.autenticar_usuario("fantasma", "x")[2] for _ in range(6)]
        b = [ms.autenticar_usuario("admin", "errada1")[2] for _ in range(6)]
        self.assertEqual(a, b)

    def test_desativado_aparece_na_hora(self):
        ms.init_db_seguranca()
        ms.criar_usuario("maria", "Maria2026x", "Comum", trocar_senha=False)
        ms.atualizar_usuario("maria", "Comum", False, "admin")
        self.assertEqual(ms.situacao_usuario("maria"), (False, "Comum"))

    def test_formula_do_arquivo_nao_vai_ativa_para_excel_e_csv(self):
        csv = ("Data Atendimento;Paciente;Guia;Codigo;Valor Apresentado;Valor Pago;Motivo Glosa\n"
               '05/03/2026;ANA PAULA SOUZA;100200301;50000470;100;0;=HYPERLINK("http://x")\n')
        df, e = ler_csv(csv)
        self.assertIsNone(e)
        wb = openpyxl.load_workbook(io.BytesIO(mr.gerar_excel(mr.spec_glosas(df[df["Valor da glosa"] > 0], df))))
        formulas = [c.value for ws in wb for row in ws.iter_rows() for c in row
                    if isinstance(c.value, str) and c.value.startswith("=") and "SUBTOTAL" not in c.value]
        self.assertEqual(formulas, [])
        self.assertNotIn(";=HYPERLINK", mr.sem_formulas_df(df).to_csv(sep=";"))
        self.assertEqual(mr.sem_formula("-12,50"), "-12,50")


class TestHistorico(BancoTemporario):
    LINHAS = ["05/03/2026;ANA PAULA SOUZA;100200301;50000470;100;100;20/04/2026",
              "06/03/2026;BEATRIZ LIMA COSTA;100200302;50000470;100;60;20/04/2026"]

    def test_copia_nao_grava_e_remover_original_nao_apaga(self):
        a, _ = ler_csv(CSV_CAB + "\n".join(self.LINHAS) + "\n")
        self.salvar(a, "a.csv")
        did, _, repetidos = mh.salvar_demonstrativo(a.assign(Operadora=OP), "a (1).csv", "outro-hash", "t", OP)
        self.assertIsNone(did)
        self.assertEqual(repetidos, 2)
        b, _ = ler_csv(CSV_CAB + "\n".join(self.LINHAS + [
            "07/03/2026;CARLOS DIAS MOTA;100200303;50000470;100;100;20/04/2026"]) + "\n")
        self.salvar(b, "b.csv")
        self.assertEqual(len(mh.carregar_itens()), 3)
        did_a = mh.listar_demonstrativos().set_index("Arquivo").loc["a.csv", "id"]
        mh.excluir_demonstrativo(did_a)
        self.assertEqual(len(mh.carregar_itens()), 3)  # b.csv assume as linhas que eram repetidas

    def test_sem_guia_reenvio_nao_duplica(self):
        cab = "Data Atendimento;Paciente;Codigo;Valor Apresentado;Valor Pago;Data Pagamento\n"
        duas = "10/03/2026;DANIEL REIS ALVES;50000470;100;100;20/04/2026\n" * 2
        for k in range(3):
            df, _ = ler_csv(cab + duas + "\n" * k)
            mh.salvar_demonstrativo(df.assign(Operadora=OP), f"s{k}.csv", f"h{k}", "t", OP)
        self.assertEqual(len(mh.carregar_itens()), 2)  # duas sessões no mesmo dia continuam contando

    def test_glosa_sem_valor_aparece(self):
        csv = ("Data Atendimento;Paciente;Guia;Codigo;Valor Pago;Motivo Glosa;Data Pagamento\n"
               "05/03/2026;ANA PAULA SOUZA;100200301;99999999;0;1705 VALOR A MAIOR;20/04/2026\n")
        df, _ = ler_csv(csv)
        self.salvar(df, "s.csv")
        self.assertEqual(len(mh.carregar_itens(somente_glosas=True)), 1)
        self.assertEqual(mh.resumo_painel(mh.carregar_itens())["itens_sem_valor"], 1)

    def test_valores_aprendidos_saem_com_o_arquivo(self):
        csv = CSV_CAB + "".join(f"0{d}/03/2026;PACIENTE NUMERO {d} SILVA;10020040{d};50000470;;10;20/04/2026\n"
                                for d in range(1, 8))
        df, _ = ler_csv(csv)
        mk.aprender(df)
        self.assertGreater(mk.resumo_aprendizado()["referencias"], 0)
        self.salvar(df, "errado.csv")
        mh.excluir_demonstrativo(mh.listar_demonstrativos()["id"].iloc[0])
        mk.reaprender_referencias(OP, mh.carregar_itens(operadoras_sel=[OP]))
        self.assertEqual(mk.resumo_aprendizado()["referencias"], 0)


class TestLeitura(unittest.TestCase):
    def test_planilha_de_valores_e_recusada(self):
        csv = ("Código do procedimento;Nome do procedimento;Valor Rede Nacional;Valor Rede Flex;Vigência início;Plano\n"
               "50000470;SESSAO DE PSICOTERAPIA;48,24;38,59;01/01/2026;Bradesco Saúde\n")
        df, e = ler_csv(csv)
        self.assertTrue(df.empty)
        self.assertIn("tabela de valores", e)

    def test_data_impossivel_e_vazia_ficam_com_aviso(self):
        csv = (CSV_CAB + "31/02/2026;ANA PAULA SOUZA;100200301;50000470;100;100;20/04/2026\n"
               ";BEATRIZ LIMA COSTA;100200302;50000470;100;60;20/04/2026\n"
               "10/03/2026;CARLOS DIAS MOTA;100200303;50000470;100;100;20/04/2026\n")
        df, _ = ler_csv(csv)
        self.assertEqual(list(df["Data do evento"]), ["-", "-", "10/03/2026"])
        self.assertIn("inválida", df.loc[0, "Alertas"])
        self.assertIn("Sem data", df.loc[1, "Alertas"])

    def test_coluna_repetida_e_valores_incoerentes(self):
        csv = ("Data Atendimento;Paciente;Guia;Codigo;Valor Apresentado;Valor Pago;Valor Glosa;Valor Glosa\n"
               "05/03/2026;ANA PAULA SOUZA;100200301;50000470;100;60;40;999\n"
               "06/03/2026;BEATRIZ LIMA COSTA;100200302;50000470;100;-100;0;0\n"
               "07/03/2026;CARLOS DIAS MOTA;100200303;50000470;100;150;0;0\n")
        df, _ = ler_csv(csv)
        self.assertEqual(df.loc[0, "Valor informado"], 100)
        self.assertIn("negativo", df.loc[1, "Alertas"])
        self.assertIn("acima do valor apresentado", df.loc[2, "Alertas"])

    def test_demonstrativo_no_campo_de_faturamento_e_recusado(self):
        b = io.BytesIO((CSV_CAB.replace("Valor Pago", "Valor Pago;Valor Glosa").strip() + "\n"
                        "05/03/2026;ANA PAULA SOUZA;100200301;50000470;100;100;0;20/04/2026\n").encode())
        b.name = "d.csv"
        df, e = mc.ler_faturamento(b)
        self.assertTrue(df.empty)
        self.assertIn("demonstrativo", e)

    def test_plano_parecido_nao_usa_tabela_do_outro(self):
        self.assertTrue(me._plano_casa("Bradesco", "Bradesco Saúde S.A."))
        self.assertTrue(me._plano_casa("SulAmérica", "Sul América Saúde"))
        self.assertFalse(me._plano_casa("Unimed Recife", "Unimed Caruaru"))
        self.assertFalse(me._plano_casa("Bradesco Saúde", "Bradesco Dental"))

    def test_anomalias_sem_colunas_opcionais(self):
        df, _ = ler({"a": [CAB, linha()]})
        self.assertIsNotNone(mv.anomalias(df.drop(columns=["Protocolo", "Alertas"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)

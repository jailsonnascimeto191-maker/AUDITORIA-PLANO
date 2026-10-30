"""Demonstrativos TISS (análise de conta + pagamento + recurso) lidos e ligados no histórico.
Dados 100% sintéticos (nenhum paciente real)."""
import io
import os
import shutil
import tempfile
import unittest

from base import me  # noqa: F401  (prepara o ambiente dos testes)
import leitor_tiss as lt
import motor_conhecimento as mk
import motor_historico as mh
import motor_tiss as mt
import motor_verificacao as mv

NS = 'xmlns="http://www.ans.gov.br/padroes/tiss/schemas"'


def _cab(tipo, n):
    return (f'<?xml version="1.0" encoding="iso-8859-1"?><mensagemTISS {NS}><cabecalho><identificacaoTransacao>'
            f"<tipoTransacao>{tipo}</tipoTransacao><sequencialTransacao>{n}</sequencialTransacao>"
            "</identificacaoTransacao></cabecalho><operadoraParaPrestador><demonstrativosRetorno>")


def analise(protocolo, data_prot, guias, n=1):
    """guias: [(guia, [(data, codigo, informado, liberado, [(valor_glosa, codigo_glosa), ...]), ...]), ...]"""
    x = [_cab("DEMONSTRATIVO_ANALISE_CONTA", n),
         "<demonstrativoAnaliseConta><cabecalhoDemonstrativo><numeroDemonstrativo>9</numeroDemonstrativo>"
         "<nomeOperadora>Caixa de Assistencia Teste - CAMED</nomeOperadora><dataEmissao>2026-10-01</dataEmissao>"
         "</cabecalhoDemonstrativo><dadosConta><dadosProtocolo>"
         f"<numeroLotePrestador>L{protocolo}</numeroLotePrestador><numeroProtocolo>{protocolo}</numeroProtocolo>"
         f"<dataProtocolo>{data_prot}</dataProtocolo>"]
    for guia, itens in guias:
        x.append(f"<relacaoGuias><numeroGuiaPrestador>{guia}</numeroGuiaPrestador>"
                 f"<numeroGuiaOperadora>9{guia}</numeroGuiaOperadora><numeroCarteira>500{guia}</numeroCarteira>")
        for seq, (data, cod, inf, lib, glosas) in enumerate(itens, start=1):
            x.append(f"<detalhesGuia><sequencialItem>{seq}</sequencialItem><dataRealizacao>{data}</dataRealizacao>"
                     f"<procedimento><codigoTabela>22</codigoTabela><codigoProcedimento>{cod}</codigoProcedimento>"
                     f"<descricaoProcedimento>SESSAO TESTE</descricaoProcedimento></procedimento>"
                     f"<valorInformado>{inf}</valorInformado><qtdExecutada>1</qtdExecutada>"
                     f"<valorProcessado>{inf}</valorProcessado><valorLiberado>{lib}</valorLiberado>"
                     + "".join(f"<relacaoGlosa><valorGlosa>{v}</valorGlosa><tipoGlosa>{c}</tipoGlosa></relacaoGlosa>"
                               for v, c in glosas)
                     + "</detalhesGuia>")
        x.append("</relacaoGuias>")
    x.append("</dadosProtocolo></dadosConta></demonstrativoAnaliseConta>"
             "</demonstrativosRetorno></operadoraParaPrestador></mensagemTISS>")
    return "".join(x).encode("latin-1")


def pagamento(data_pag, protocolos, ajustes=(), n=1):
    """protocolos: [(protocolo, data_prot, [(guia, processado, liberado, glosa, tipo), ...]), ...]"""
    x = [_cab("DEMONSTRATIVO_PAGAMENTO", n),
         "<demonstrativoPagamento><cabecalhoDemonstrativo><nomeOperadora>Caixa de Assistencia Teste - CAMED"
         "</nomeOperadora></cabecalhoDemonstrativo><pagamentos><pagamentosPorData><dadosPagamento>"
         f"<dataPagamento>{data_pag}</dataPagamento></dadosPagamento><dadosResumo>"]
    for prot, data_prot, guias in protocolos:
        x.append(f"<relacaoProtocolos><dataProtocolo>{data_prot}</dataProtocolo><numeroProtocolo>{prot}"
                 f"</numeroProtocolo><numeroLote>L{prot}</numeroLote>")
        for guia, proc, lib, gl, tipo in guias:
            x.append(f"<guiasDoLote><numeroGuiaPrestador>{guia}</numeroGuiaPrestador><tipoPagamento>{tipo}"
                     f"</tipoPagamento><valorProcessadoGuia>{proc}</valorProcessadoGuia><valorLiberadoGuia>{lib}"
                     f"</valorLiberadoGuia><valorGlosaGuia>{gl}</valorGlosaGuia></guiasDoLote>")
        x.append("</relacaoProtocolos>")
    x.append("</dadosResumo><debitosCreditosPorData>")
    for rec, orig in ajustes:
        x.append(f"<debitosCreditos><descricaoDbCr>Ajuste Ant. {rec} - Orig. {orig}</descricaoDbCr></debitosCreditos>")
    x.append("</debitosCreditosPorData></pagamentosPorData></pagamentos></demonstrativoPagamento>"
             "</demonstrativosRetorno></operadoraParaPrestador></mensagemTISS>")
    return "".join(x).encode("latin-1")


def ler(dados, nome):
    b = io.BytesIO(dados)
    b.name = nome
    return me.extrair_glosas_de_arquivo(b, me.PLANO_AUTOMATICO, somente_glosas=False)


# análise do protocolo 100: guia 11 com uma sessão glosada por dois motivos (valor repetido em cada motivo)
A100 = analise("100", "2026-02-02", [("11", [("2026-01-10", "20104219", 58.02, 58.02, []),
                                             ("2026-01-12", "20104219", 58.02, 0, [(58.02, "3209"), (58.02, "3210")])]),
                                     ("12", [("2026-01-15", "10101012", 97.42, 97.42, [])])])
P100 = pagamento("2026-03-20", [("100", "2026-02-02", [("11", 116.04, 58.02, 58.02, 1), ("12", 97.42, 97.42, 0, 1)])])
# recurso da glosa da guia 11, pago no protocolo 200
P200 = pagamento("2026-05-20", [("200", "2026-04-01", [("11", 58.02, 58.02, 0, 2)])], ajustes=[("200", "100")], n=2)


class TestLeitorTiss(unittest.TestCase):
    def test_analise_xml(self):
        df, e = ler(A100, "resposta.xml")
        self.assertIsNone(e)
        self.assertEqual(df.attrs["operadora"], "CAMED")
        self.assertEqual(len(df), 3)
        self.assertAlmostEqual(df["Valor da glosa"].sum(), 58.02)  # dois motivos não dobram a glosa
        g = df[df["Valor da glosa"] > 0].iloc[0]
        self.assertEqual(g["Código da glosa"], "3209; 3210")
        self.assertIn("DUPLICIDADE", g["Motivo da glosa"])
        self.assertEqual(g["Carteira"], "50011")
        self.assertEqual(g["Documento"], lt.DOC_ANALISE)
        self.assertEqual(g["Data do protocolo"], "02/02/2026")

    def test_pagamento_xml_com_recurso(self):
        df, e = ler(P200, "resposta.xml")
        self.assertIsNone(e)
        r = df.iloc[0]
        self.assertEqual((r["Documento"], r["Protocolo original"], r["Data de pagamento"]),
                         (lt.DOC_PAGAMENTO, "100", "20/05/2026"))

    def test_xml_comum_continua_no_leitor_generico(self):
        self.assertIsNone(lt.ler(b"<raiz><item><valor>1</valor></item></raiz>", "x.xml"))


class TestHistoricoTiss(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=os.environ["AZUS_PASTA_DADOS"])
        mh.DB = mk.DB = os.path.join(self.dir, "valores_clinica.db")
        mh.init_historico()
        mk.init_conhecimento()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def enviar(self, *arquivos):
        for i, dados in enumerate(arquivos):
            df, _ = ler(dados, f"a{i}.xml")
            df["Operadora"] = "CAMED"
            mh.salvar_demonstrativo(df, f"a{i}.xml", mh.hash_arquivo(dados), "t", "CAMED")
            mh.vincular_historico("CAMED")
        return mh.carregar_itens()

    def test_pagamento_confirma_analise_sem_contar_duas_vezes(self):
        for ordem in ((A100, P100), (P100, A100)):
            self.setUp()
            it = self.enviar(*ordem)
            a = it[it["Documento"] == lt.DOC_ANALISE]
            self.assertEqual(set(a["Data de pagamento"]), {"20/03/2026"})
            self.assertAlmostEqual(it["Valor informado"].sum(), 213.46)
            self.assertAlmostEqual(it["Valor pago"].sum(), 155.44)
            self.assertAlmostEqual(it["Valor da glosa"].sum(), 58.02)
            p = it[it["Documento"] == lt.DOC_PAGAMENTO]
            self.assertTrue((p["Status da glosa"] == mt.STATUS_PAGAMENTO_CONFERIDO).all())

    def test_recurso_pago_volta_para_a_glosa_original(self):
        it = self.enviar(P200, A100, P100)
        g = it[it["Situação do recurso"] != ""]
        self.assertEqual(len(g), 1)
        self.assertEqual(g.iloc[0]["Situação do recurso"], me.RECURSO_RECEBIDO)
        self.assertEqual(g.iloc[0]["Protocolo do recurso"], "200")
        self.assertAlmostEqual(it["Valor da glosa"].sum(), 0.0)
        self.assertAlmostEqual(it["Valor pago"].sum(), 213.46)  # pago + recurso
        self.assertEqual(len(mv.recursos(it)), 1)

    def test_recurso_negado(self):
        negado = pagamento("2026-05-20", [("200", "2026-04-01", [("11", 58.02, 0, 58.02, 2)])],
                           ajustes=[("200", "100")])
        it = self.enviar(A100, P100, negado)
        g = it[it["Situação do recurso"] != ""].iloc[0]
        self.assertEqual(g["Situação do recurso"], me.RECURSO_NAO_PAGO)
        self.assertAlmostEqual(it["Valor da glosa"].sum(), 58.02)  # a glosa negada não conta duas vezes

    def test_mesma_analise_com_glosa_diferente_vai_para_conferir(self):
        outra = A100.replace(b"<tipoGlosa>3210</tipoGlosa>", b"<tipoGlosa>1702</tipoGlosa>").replace(
            b"<sequencialTransacao>1", b"<sequencialTransacao>7")
        it = self.enviar(A100, outra)
        self.assertEqual(len(it), 3)  # a outra versão não conta de novo
        self.assertEqual(it["Alertas"].str.contains(mt.ALERTA_DIVERGENCIA, regex=False).sum(), 1)
        self.assertIn(mv.TIPO_VERSOES, set(mv.anomalias(it)["Tipo"]))

    def test_guia_sem_pagamento_depois_do_prazo_fica_atrasada(self):
        lotes = [analise(str(p), f"2026-0{m}-02", [(str(p), [(f"2026-0{m}-01", "10101012", 97.42, 97.42, [])])])
                 for p, m in ((300, 1), (301, 2), (302, 3))]
        pags = [pagamento(f"2026-0{m + 1}-20", [(str(p), f"2026-0{m}-02", [(str(p), 97.42, 97.42, 0, 1)])])
                for p, m in ((300, 1), (301, 2), (302, 3))]
        sem = analise("303", "2026-04-02", [("303", [("2026-04-01", "10101012", 97.42, 97.42, [])])])
        depois = pagamento("2026-07-20", [("304", "2026-06-02", [("304", 97.42, 97.42, 0, 1)])])
        it = self.enviar(*lotes, *pags, sem, depois)
        atraso = it[it["Alertas"].str.contains(mt.ALERTA_ATRASADO, regex=False)]
        self.assertEqual(list(atraso["Doc Original"]), ["303"])
        self.assertIn(mv.TIPO_ATRASADO, set(mv.anomalias(it)["Tipo"]))

    def test_remover_o_pagamento_desfaz_a_ligacao(self):
        self.enviar(A100, P100)
        did = mh.listar_demonstrativos().set_index("Arquivo").loc["a1.xml", "id"]
        mh.excluir_demonstrativo(did)
        it = mh.carregar_itens()
        self.assertEqual(set(it["Data de pagamento"]), {"-"})
        self.assertAlmostEqual(it["Valor pago"].sum(), 155.44)


if __name__ == "__main__":
    unittest.main(verbosity=2)

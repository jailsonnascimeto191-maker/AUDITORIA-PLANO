"""
Manual do sistema, apresentado pelo mascote. Cada seção explica uma parte do sistema com passos curtos.
"""
import html

import streamlit as st

import marca

SECOES = [
    dict(
        titulo="Primeiros passos", onde="Acessos e Valores", pose=("feliz", None),
        texto="Antes de enviar o primeiro demonstrativo, deixe o sistema com a cara da sua clínica e com os valores "
              "que cada plano paga. É isso que permite calcular a glosa com precisão.",
        passos=["Em Acessos → Dados da clínica, informe o nome da clínica. Ele aparece na entrada, no menu e nos relatórios.",
                "Em Acessos → Usuários, crie um acesso para cada pessoa da equipe.",
                "Em Valores → Valores recebidos por plano, cadastre o valor de cada procedimento (Rede Nacional e Rede Flex).",
                "Em Cadastros, cadastre os profissionais. Em Valores → Repasse, o valor que cada um recebe."],
        dica="Não tem a tabela de valores à mão? Envie um demonstrativo e use Valores → Sugerir pelos demonstrativos: "
             "o sistema monta a tabela a partir do que o plano pagou.",
    ),
    dict(
        titulo="Conferir um demonstrativo", onde="Casa das Máquinas", pose=("atenta", "lupa"),
        texto="Envie o demonstrativo ou extrato de pagamento do convênio. O sistema entende a estrutura do arquivo "
              "sozinho, mesmo com colunas fora do padrão, várias abas ou blocos por data de crédito.",
        passos=["Escolha a operadora (ou deixe Identificar pelo arquivo).",
                "Envie o arquivo: Excel, CSV, PDF, XML TISS, Word ou HTML. Pode enviar vários de uma vez.",
                "Clique em Processar e auditar e aguarde o tatu terminar de rolar.",
                "Use Exibir para ver só os itens com glosa, as diferenças a conferir ou todos os atendimentos."],
        dica="Enviar o mesmo arquivo de novo substitui a versão anterior no histórico. Nada é contado em dobro.",
    ),
    dict(
        titulo="Convênios no padrão TISS (análise de conta + pagamento)", onde="Casa das Máquinas",
        pose=("atenta", "lupa"),
        texto="Alguns convênios (como a CAMED) mandam dois documentos: a análise de conta de cada lote, com paciente, "
              "procedimento e glosa, e o demonstrativo de pagamento, só com as guias e o valor pago. Envie os dois, "
              "em PDF ou XML: o sistema liga um ao outro pelo protocolo e pela guia.",
        passos=["Baixe no portal do convênio as análises de conta e os demonstrativos de pagamento.",
                "Envie todos de uma vez na Casa das Máquinas, na ordem que quiser.",
                "Cada guia da análise ganha a data em que foi paga; o pagamento não conta o atendimento duas vezes.",
                "Pagamento de recurso de glosa é reconhecido sozinho e volta para a glosa original (Recursos de glosa).",
                "Guia sem pagamento depois do prazo que o convênio costuma levar aparece em Para verificar."],
        dica="O XML não traz o nome do paciente. Enviando também o PDF da mesma análise, o nome é completado e os "
             "dois são conferidos um com o outro.",
    ),
    dict(
        titulo="Corrigir a leitura de um arquivo", onde="Casa das Máquinas → Conferência da leitura",
        pose=("desconfiada", None),
        texto="Toda leitura mostra quais colunas do arquivo foram reconhecidas para cada informação. Se uma coluna foi "
              "entendida errado, corrija ali mesmo.",
        passos=["Abra Conferência da leitura logo abaixo do resultado.",
                "Na tabela do layout, escolha a coluna certa para o campo que estiver errado.",
                "Clique em Salvar este padrão e reprocessar."],
        dica="O padrão fica guardado: todo arquivo com o mesmo layout passa a ser lido assim, sem precisar corrigir de novo.",
    ),
    dict(
        titulo="Acompanhar as glosas", onde="Painel e Lupa de Glosas", pose=("normal", "prancheta"),
        texto="O Painel junta todos os demonstrativos já conferidos: valor apresentado, valor glosado, glosa por mês, "
              "por operadora e os principais motivos. A Lupa pesquisa qualquer atendimento do histórico.",
        passos=["No Painel, escolha o período e as operadoras.",
                "Abra Pagamentos em partes para ver complementos, pagos a menor e possíveis duplicidades.",
                "Na Lupa de Glosas, busque por paciente, guia, procedimento ou motivo e baixe o resultado."],
        dica=None,
    ),
    dict(
        titulo="Valores recebidos por plano", onde="Valores → Valores recebidos por plano", pose=("feliz", "moeda"),
        texto="Cada procedimento tem o valor da Rede Nacional e, quando existe, o da Rede Flex. Cada valor tem vigência "
              "pela data do atendimento, então o sistema usa o valor certo de cada época.",
        passos=["Tabela por plano: edite código, nome do procedimento, valores e vigência direto na tabela.",
                "Reajuste: escolha o plano, a data e o percentual; os valores atuais são encerrados no dia anterior.",
                "Importar planilha: envie um Excel com Código, Nome, Valor Rede Nacional, Valor Rede Flex e vigência.",
                "Sugerir pelos demonstrativos: o sistema propõe os valores e os reajustes que encontrou."],
        dica="Depois de cadastrar ou reajustar valores, envie os demonstrativos de novo para recalcular as glosas.",
    ),
    dict(
        titulo="Pagamentos em partes, recursos e duplicidades", onde="Painel → Pagamentos em partes",
        pose=("atenta", "bola"),
        texto="Às vezes o plano paga um atendimento em duas partes, paga depois de uma glosa (recurso) ou paga a mesma "
              "guia duas vezes. O sistema liga esses pagamentos, mesmo quando chegam em arquivos e meses diferentes.",
        passos=["Ele só liga quando paciente, procedimento e data são os mesmos e a soma fecha no centavo.",
                "Se houver mais de um candidato, nada é ligado: o caso aparece em Possíveis, para conferir.",
                "Remover um demonstrativo do histórico desfaz os vínculos dele automaticamente."],
        dica="Possível pagamento em duplicidade lista as guias pagas por inteiro mais de uma vez. Confira com o extrato.",
    ),
    dict(
        titulo="Recursos e lotes de reapresentação", onde="Acessos → Aprendizado da leitura → Padrões de lote",
        pose=("desconfiada", "lupa"),
        texto="Quando uma glosa é recorrida, o plano costuma pagar depois em outro lote, às vezes com outro número de "
              "guia. O sistema observa os números de protocolo de cada operadora, separa em famílias e descobre "
              "sozinho quais famílias trazem atendimentos que já tinham aparecido antes.",
        passos=["Envie os demonstrativos normalmente. O padrão é aprendido com o próprio arquivo e com o histórico.",
                "Nas famílias de reapresentação, cada linha é ligada ao atendimento original e não conta como "
                "atendimento novo.",
                "O original mostra o que foi recuperado: glosa revertida, recurso pago em parte ou não pago.",
                "Se a evidência não bastar, a família fica sem definição. Você pode escolher o tipo e aplicar ao "
                "histórico."],
        dica="O sistema não inventa nada: só liga quando paciente, procedimento e data são os mesmos e há um único "
             "atendimento original. Os demais casos ficam com aviso para conferir.",
    ),
    dict(
        titulo="Acompanhar recursos e casos para verificar", onde="Painel e Casa das Máquinas", pose=("atenta", "alerta"),
        texto="Para cada guia glosada que volta em outro crédito, o sistema guarda a história: quando e em que "
              "protocolo glosou, o motivo, em que protocolo voltou e quanto foi recebido. E quando encontra algo fora "
              "do padrão, pede para vocês verificarem em vez de decidir sozinho.",
        passos=["Em Recursos de glosa, filtre por situação: Recebido, Recebido em parte ou Não pago.",
                "Em Para verificar, cada caso traz o que conferir e as guias envolvidas.",
                "Exemplo: glosa por duplicidade que o plano pagou no recurso, mas com outra guia já paga do mesmo "
                "paciente, procedimento e dia. Confira se foram duas sessões; se não, o plano pode pedir devolução.",
                "O Relatório de Glosas em Excel traz as abas Recursos de glosa e Para verificar."],
        dica="Glosa sem recurso identificado não entra em Recursos de glosa: o sistema só sabe que houve recurso "
             "quando a guia volta num demonstrativo.",
    ),
    dict(
        titulo="Relatórios", onde="Produção do Profissional, Relatório de Glosas, Faturamento x Recebimento",
        pose=("normal", "prancheta"),
        texto="Os três relatórios saem em Excel e PDF, com o nome da clínica.",
        passos=["Produção do Profissional: cruza o controle de atendimento com o demonstrativo e calcula o repasse.",
                "Relatório de Glosas: relação de glosas com motivo, guia e protocolo, para recorrer.",
                "Faturamento x Recebimento: confere guia por guia se o que foi faturado nos lotes foi pago."],
        dica=None,
    ),
    dict(
        titulo="Acessos e segurança", onde="Acessos", pose=("desconfiada", "alerta"),
        texto="Cada pessoa entra com o próprio usuário. Depois de 5 senhas erradas o acesso fica bloqueado por 15 minutos, "
              "e a sessão se encerra após 30 minutos sem uso.",
        passos=["Usuários: crie, desative ou gere uma senha temporária.",
                "Acessos e Histórico de alterações: veja quem entrou e o que foi alterado.",
                "Aprendizado da leitura: veja e apague os padrões de leitura salvos."],
        dica=None,
    ),
]

STATUS = [
    ("Sem glosa", "O plano pagou o valor esperado."),
    ("Glosa parcial / Glosa total", "Parte ou todo o valor foi cortado, com o motivo informado pelo plano."),
    ("Pago a menor sem justificativa", "Pago abaixo do valor cadastrado sem motivo. Pode estar aguardando complemento ou "
                                       "ser cobrado."),
    ("Pago em 2 partes", "O valor foi pago em duas vezes; a linha mostra o complemento recebido."),
    ("Complemento de pagamento", "A segunda parte de um pagamento. Não conta como atendimento novo."),
    ("Possível pagamento em duplicidade", "A mesma guia foi paga por inteiro mais de uma vez."),
    ("Glosa mantida em novo crédito", "A guia voltou em outro crédito e continuou glosada."),
    ("Glosa revertida em recurso", "Glosado com justificativa e pago depois num lote de reapresentação."),
    ("Recurso pago em parte", "Parte do valor glosado foi recuperada num lote de reapresentação; o resto continua glosado."),
    ("Glosa (valor não identificado)", "Houve glosa, mas falta o valor do procedimento no cadastro."),
]


def render():
    st.markdown(
        f"<div class='zu-vazio'>{marca.mascote_svg(170, 'feliz')}"
        f"<div><h1 class='pagina-titulo'>Manual do {marca.NOME}</h1>"
        f"<p>Oi, eu sou o {marca.MASCOTE}. Vou mostrar como cada parte do sistema funciona. Quando o sistema está "
        f"trabalhando, eu me enrolo e saio rolando.</p></div></div>",
        unsafe_allow_html=True,
    )
    nomes = [s["titulo"] for s in SECOES] + ["O que cada situação significa"]
    escolha = st.radio("Assunto", nomes, horizontal=True, label_visibility="collapsed", key="manual_assunto")
    if escolha == nomes[-1]:
        linhas = "".join(f"<li><b>{html.escape(a)}</b>: {html.escape(b)}</li>" for a, b in STATUS)
        st.markdown(f"<div class='manual-item'>{marca.mascote_svg(200, 'normal', 'prancheta')}"
                    f"<div><h3>O que cada situação significa</h3><div class='onde'>Coluna Status da glosa</div>"
                    f"<ul>{linhas}</ul></div></div>", unsafe_allow_html=True)
        return
    s = next(x for x in SECOES if x["titulo"] == escolha)
    passos = "".join(f"<li>{html.escape(p)}</li>" for p in s["passos"])
    dica = f"<div class='dica'><b>Dica:</b> {html.escape(s['dica'])}</div>" if s.get("dica") else ""
    st.markdown(
        f"<div class='manual-item'>{marca.mascote_svg(200, *s['pose'])}"
        f"<div><h3>{html.escape(s['titulo'])}</h3><div class='onde'>Onde: {html.escape(s['onde'])}</div>"
        f"<p>{html.escape(s['texto'])}</p><ol>{passos}</ol>{dica}</div></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Ajuda rápida de cada tela (o "?" ao lado do título): o Zu explica o que a tela faz, como faz, onde achar
# cada coisa e como fazer, em passos curtos.
# --------------------------------------------------------------------------
AJUDA = {
    "Painel": dict(
        o_que="Mostra o resumo de todos os demonstrativos já conferidos: quanto foi apresentado, quanto foi "
              "glosado, a glosa por mês, por operadora e os principais motivos.",
        como="Soma os atendimentos guardados no histórico, pela data do atendimento.",
        onde=["Período e operadoras: no alto da tela.",
              "Pagamentos em partes, recursos e duplicidades: no quadro Pagamentos em partes.",
              "Recursos de glosa e Para verificar: logo abaixo dos gráficos.",
              "Arquivos já enviados (e remover um): no fim da tela, em Demonstrativos processados."],
        passos=["Escolha o período e as operadoras.",
                "Confira o valor glosado e os motivos que mais aparecem.",
                "Abra Para verificar e confira cada caso apontado.",
                "Para ver um atendimento específico, use a Lupa de Glosas."],
    ),
    "Casa das Máquinas": dict(
        o_que="Confere um demonstrativo de pagamento do convênio: encontra glosas, pagamentos a menor, "
              "recursos, pagamentos em partes e duplicidades, e guarda tudo no histórico.",
        como="Lê o arquivo sozinho (Excel, CSV, PDF, XML TISS, Word ou HTML), compara cada atendimento com a "
             "tabela de valores do plano e liga os pagamentos que voltam em outro crédito.",
        onde=["Resultado: na tabela, logo abaixo dos indicadores.",
              "Exibir: escolha Itens com glosa, Diferenças a conferir ou Todos os itens.",
              "Buscar: encontra protocolo, guia ou paciente em todos os atendimentos do arquivo.",
              "Como o arquivo foi lido: em Conferência da leitura."],
        passos=["Escolha a operadora (ou deixe Identificar pelo arquivo).",
                "Envie o arquivo (ou vários de uma vez) e clique em Processar e auditar.",
                "Use Exibir → Todos os itens para ver também o que foi pago normalmente.",
                "Procurando um protocolo ou uma guia? Digite em Buscar."],
    ),
    "Lupa de Glosas": dict(
        o_que="Pesquisa qualquer atendimento: no último demonstrativo conferido ou em todo o histórico.",
        como="Procura o texto digitado em todas as colunas (paciente, guia, protocolo, procedimento, motivo).",
        onde=["Onde pesquisar: todo o histórico ou o último demonstrativo.",
              "Só itens com glosa: desmarque para ver também os pagos normalmente."],
        passos=["Escolha onde pesquisar, o período e as operadoras.",
                "Digite o que procura (pode ser só um pedaço do número ou do nome).",
                "Baixe o resultado em CSV, se precisar."],
    ),
    "Produção do Profissional": dict(
        o_que="Monta o espelho da produção do mês de um profissional e calcula o repasse.",
        como="Cruza o controle de atendimentos da clínica com o demonstrativo do plano, atendimento por "
             "atendimento, e aplica o valor de repasse cadastrado.",
        onde=["Valores de repasse: em Valores → Repasse ao profissional.",
              "Profissionais: em Cadastros."],
        passos=["Escolha o profissional analisado e o mês de produção.",
                "Envie o controle de atendimento e, se tiver, o demonstrativo de pagamento.",
                "Clique em Gerar relatório de produção.",
                "Confira os atendimentos não localizados e baixe o Excel ou o PDF."],
    ),
    "Relatório de Glosas": dict(
        o_que="Gera a relação de glosas para recorrer: data, paciente, guia, protocolo, motivo e valor, com os "
              "recursos e os casos para verificar.",
        como="Usa o último demonstrativo, o histórico ou arquivos enviados aqui. Só entram os itens glosados.",
        onde=["Abas do Excel: Resumo, Glosas, Recursos de glosa e Para verificar.",
              "Filtrar: por operadora e pela busca (paciente, guia, motivo)."],
        passos=["Escolha a origem dos dados e clique em Gerar relatório de glosas.",
                "Filtre se precisar.",
                "Baixe o Excel (com todas as abas) ou o PDF."],
    ),
    "Faturamento x Recebimento": dict(
        o_que="Confere se tudo o que a clínica faturou nos lotes foi pago, em que mês e com quantos dias de demora.",
        como="Liga cada guia do arquivo de faturamento à mesma guia nos demonstrativos de pagamento.",
        onde=["Campo Faturamento: o arquivo dos lotes/guias que a clínica enviou.",
              "Campo Demonstrativo(s) de pagamento: o que o convênio pagou."],
        passos=["Envie o arquivo de faturamento e os demonstrativos, cada um no seu campo.",
                "Clique em Analisar faturamento x recebimento.",
                "Veja as guias não pagas e baixe o relatório."],
    ),
    "Valores": dict(
        o_que="Guarda quanto cada plano paga por procedimento (Rede Nacional e Rede Flex) e quanto a clínica "
              "repassa ao profissional, com vigência.",
        como="O valor que vale é o da data do atendimento. É com ele que o sistema calcula a glosa.",
        onde=["Tabela por plano: ver e editar os valores.",
              "Reajuste: aplicar um percentual a partir de uma data.",
              "Importar planilha e Sugerir pelos demonstrativos: cadastrar muitos valores de uma vez."],
        passos=["Cadastre ou importe os valores de cada plano.",
                "No reajuste, escolha a data e o percentual: o valor antigo termina no dia anterior.",
                "Depois de mudar valores, envie os demonstrativos de novo para recalcular."],
    ),
    "Cadastros": dict(
        o_que="Cadastra os profissionais da clínica, usados na Produção do Profissional.",
        como="Cada profissional tem nome, registro e especialidade; pode ser desativado sem perder o histórico.",
        onde=["Novo profissional: primeira aba.", "Editar ou desativar: Profissionais cadastrados."],
        passos=["Cadastre nome, registro e especialidade.",
                "Para alguém que saiu, marque como inativo em vez de excluir."],
    ),
    "Acessos": dict(
        o_que="Cuida de quem usa o sistema: dados da clínica, usuários, registro de acessos, histórico de "
              "alterações e o que o sistema aprendeu lendo os arquivos.",
        como="Cada pessoa tem o próprio usuário. Só o administrador vê esta tela.",
        onde=["Dados da clínica: nome que aparece na entrada e nos relatórios.",
              "Usuários: criar, desativar, mudar perfil e gerar senha temporária.",
              "Aprendizado da leitura: padrões de leitura e padrões de lote."],
        passos=["Crie um usuário para cada pessoa da equipe.",
                "Quando alguém sair, desative o usuário: o acesso cai na hora.",
                "Confira de vez em quando o Histórico de alterações."],
    ),
}


def ajuda_html(tela):
    """Conteúdo do "?" de uma tela, com o Zu perguntando "Posso te ajudar?"."""
    a = AJUDA.get(tela)
    if not a:
        return ""
    lista = lambda itens: "".join(f"<li>{html.escape(x)}</li>" for x in itens)
    return (f"<div class='ajuda-zu'>{marca.mascote_svg(120, 'feliz', 'pergunta')}"
            f"<div class='ajuda-balao'>Posso te ajudar?</div></div>"
            f"<div class='ajuda-bloco'><b>O que esta tela faz</b><p>{html.escape(a['o_que'])}</p>"
            f"<b>Como ela faz</b><p>{html.escape(a['como'])}</p>"
            f"<b>Onde achar</b><ul>{lista(a['onde'])}</ul>"
            f"<b>Como fazer</b><ol>{lista(a['passos'])}</ol></div>")

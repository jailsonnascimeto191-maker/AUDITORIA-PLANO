"""
Identidade visual do sistema: nome, cores, logotipo e o mascote (o tatu Zu).

Tudo é desenhado em SVG (fica nítido em qualquer tela e não depende de arquivos de imagem).
Para mudar o nome ou as cores do produto, altere só este arquivo.
"""
NOME = "Azus"
SLOGAN = "Auditoria de convênios para clínicas"
MASCOTE = "Zu"

CORES = dict(
    musgo="#24463F",       # base: menu, botões principais
    musgo_2="#305A51",     # hover
    musgo_3="#3E6E63",
    caramelo="#C9935B",    # carapaça do tatu
    faixa="#A8743F",       # faixas da carapaça
    destaque="#E0A65C",    # item ativo, foco
    pele="#F1DCC0",        # rosto e patas do tatu
    nariz="#D98C8C",
    fundo="#F2F4F3",       # fundo das telas
    tinta="#1F2B28",       # texto
    suave="#62706C",       # texto secundário
    linha="#DCE3E0",
    ok="#2E8B6A",
    glosa="#C4473A",
)
C = CORES


# --------------------------------------------------------------------------
# Logotipo: o tatu enrolado em bola, espiando de óculos
# --------------------------------------------------------------------------
def logo_svg(tamanho=40, fundo=True):
    bg = f"<rect width='64' height='64' rx='16' fill='{C['musgo']}'/>" if fundo else ""
    return (
        f"<svg width='{tamanho}' height='{tamanho}' viewBox='0 0 64 64' xmlns='http://www.w3.org/2000/svg' "
        f"role='img' aria-label='{NOME}'>{bg}"
        f"<circle cx='32' cy='33' r='21' fill='{C['caramelo']}'/>"
        # faixas da carapaça
        f"<path d='M20 16.5 Q14 33 20 49.5 M27 12.5 Q21 33 27 53.5 M34 12 Q28 33 34 54' fill='none' "
        f"stroke='{C['faixa']}' stroke-width='3' stroke-linecap='round'/>"
        # rostinho espiando
        f"<path d='M37 22 Q53 22 53 35 Q53 46 40 46 Q35 34 37 22 Z' fill='{C['pele']}'/>"
        f"<circle cx='45' cy='31' r='6' fill='#FFFFFF' stroke='{C['tinta']}' stroke-width='2.2'/>"
        f"<circle cx='46' cy='31' r='2.6' fill='{C['tinta']}'/>"
        f"<path d='M39 31 L37 30.5' stroke='{C['tinta']}' stroke-width='2.2' stroke-linecap='round'/>"
        f"<circle cx='51.5' cy='40' r='2.2' fill='{C['nariz']}'/>"
        "</svg>"
    )


def marca_html(tamanho=34, claro=True):
    """Logotipo + nome, para o menu e a tela de entrada."""
    cor = "#FFFFFF" if claro else C["tinta"]
    return (f"<span class='vg-marca'>{logo_svg(tamanho)}"
            f"<span class='vg-marca-nome' style='color:{cor}'>{NOME.lower()}</span></span>")


# --------------------------------------------------------------------------
# Mascote: o tatu Zu (de perfil, olhando para a direita)
# --------------------------------------------------------------------------
def _olho(expressao):
    cx, cy = 181, 74
    lente = (f"<circle cx='{cx}' cy='{cy}' r='18' fill='#FFFFFF' fill-opacity='.18' stroke='{C['tinta']}' stroke-width='4'/>"
             f"<path d='M{cx - 12} {cy - 9} Q{cx - 6} {cy - 14} {cx + 1} {cy - 14}' stroke='#FFFFFF' stroke-width='3' "
             f"fill='none' stroke-linecap='round' stroke-opacity='.9'/>")
    haste = f"<path d='M{cx - 18} {cy - 2} L148 66' stroke='{C['tinta']}' stroke-width='4' stroke-linecap='round'/>"
    if expressao == "feliz":
        olho = (f"<path d='M{cx - 9} {cy + 3} Q{cx} {cy - 7} {cx + 9} {cy + 3}' fill='none' stroke='{C['tinta']}' "
                f"stroke-width='4.5' stroke-linecap='round'/>")
    else:
        dx = {"atenta": 3, "desconfiada": -2}.get(expressao, 0)
        olho = (f"<circle cx='{cx + dx}' cy='{cy + 1}' r='10' fill='{C['tinta']}'/>"
                f"<circle cx='{cx + dx - 3.5}' cy='{cy - 3}' r='3.4' fill='#FFFFFF'/>"
                f"<circle cx='{cx + dx + 3}' cy='{cy + 4}' r='1.6' fill='#FFFFFF'/>")
        if expressao == "desconfiada":
            olho += (f"<path d='M{cx - 12} {cy - 4} Q{cx} {cy - 10} {cx + 12} {cy - 4} L{cx + 12} {cy - 13} "
                     f"L{cx - 12} {cy - 13} Z' fill='{C['pele']}'/>")
    sobrancelha = ""
    if expressao == "preocupada":
        sobrancelha = f"<path d='M168 48 L190 55' stroke='{C['faixa']}' stroke-width='4.5' stroke-linecap='round'/>"
    elif expressao == "desconfiada":
        sobrancelha = f"<path d='M168 52 L194 50' stroke='{C['faixa']}' stroke-width='4.5' stroke-linecap='round'/>"
    return olho + lente + haste + sobrancelha


def _item(item):
    if item == "lupa":
        return (f"<g class='zu-lupa'><path d='M196 128 L214 146' stroke='{C['faixa']}' stroke-width='8' stroke-linecap='round'/>"
                f"<circle cx='212' cy='108' r='18' fill='#FFFFFF' fill-opacity='.4' stroke='{C['destaque']}' stroke-width='6'/>"
                f"<path d='M202 102 Q206 96 214 96' stroke='#FFFFFF' stroke-width='3.5' fill='none' stroke-linecap='round'/></g>")
    if item == "prancheta":
        return (f"<g><rect x='186' y='92' width='44' height='54' rx='6' fill='#FFFFFF' stroke='{C['faixa']}' stroke-width='3'/>"
                f"<rect x='198' y='87' width='20' height='10' rx='3' fill='{C['faixa']}'/>"
                f"<path d='M194 110 L208 110 M194 121 L222 121 M194 132 L216 132' stroke='{C['suave']}' stroke-width='3.5' stroke-linecap='round'/>"
                f"<path d='M210 106 L215 112 L225 101' stroke='{C['ok']}' stroke-width='4.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/></g>")
    if item == "moeda":
        return (f"<g><circle cx='214' cy='120' r='20' fill='{C['destaque']}' stroke='{C['faixa']}' stroke-width='4'/>"
                f"<text x='214' y='128' text-anchor='middle' font-family='Figtree, sans-serif' font-weight='800' "
                f"font-size='20' fill='#6E4519'>R$</text></g>")
    if item == "alerta":
        return (f"<g><path d='M212 22 L236 64 L188 64 Z' fill='{C['destaque']}' stroke='{C['faixa']}' stroke-width='3' stroke-linejoin='round'/>"
                f"<path d='M212 36 L212 50' stroke='{C['tinta']}' stroke-width='5.5' stroke-linecap='round'/>"
                f"<circle cx='212' cy='57' r='3.2' fill='{C['tinta']}'/></g>")
    return ""


def _tatu(expressao="normal", item=None):
    """Tatu de perfil (área 0 0 240 160)."""
    faixas = "".join(
        f"<path d='M{x} {y1} Q{x - 10} 84 {x} 132' fill='none' stroke='{C['faixa']}' stroke-width='5' stroke-linecap='round'/>"
        for x, y1 in ((66, 52), (88, 40), (110, 36), (132, 40)))
    escamas = "".join(f"<circle cx='{cx}' cy='{cy}' r='3' fill='{C['faixa']}' fill-opacity='.55'/>"
                      for cx, cy in ((54, 96), (76, 70), (98, 60), (120, 60), (142, 70), (77, 108), (99, 100), (121, 100)))
    return (
        # rabo
        f"<path d='M34 112 Q14 118 8 104' fill='none' stroke='{C['caramelo']}' stroke-width='10' stroke-linecap='round'/>"
        f"<path d='M20 112 Q14 112 12 107' fill='none' stroke='{C['faixa']}' stroke-width='3' stroke-linecap='round'/>"
        # patas
        + "".join(f"<rect x='{x}' y='122' width='18' height='24' rx='8' fill='{C['pele']}'/>"
                  f"<path d='M{x + 3} 146 l3 -4 l3 4 l3 -4 l3 4' fill='none' stroke='{C['faixa']}' stroke-width='2'/>"
                  for x in (46, 76, 120, 146))
        # carapaça
        + f"<path d='M32 128 Q30 40 104 34 Q170 36 168 128 Z' fill='{C['caramelo']}'/>"
        + faixas + escamas
        + f"<path d='M32 128 L168 128' stroke='{C['faixa']}' stroke-width='5' stroke-linecap='round'/>"
        # cabeça
        + f"<g class='zu-cabeca'>"
          f"<path d='M148 60 Q162 44 186 50 Q210 58 216 84 Q220 102 206 106 Q184 112 158 104 Q142 84 148 60 Z' fill='{C['pele']}'/>"
          # escudo da cabeça
          f"<path d='M152 58 Q168 46 188 52 Q194 56 190 62 Q170 58 156 68 Z' fill='{C['caramelo']}'/>"
          # orelha
          f"<ellipse cx='162' cy='50' rx='9' ry='15' fill='{C['pele']}' transform='rotate(-20 162 50)'/>"
          f"<ellipse cx='162' cy='51' rx='4.5' ry='9' fill='{C['nariz']}' fill-opacity='.6' transform='rotate(-20 162 51)'/>"
          # nariz, boca e bochecha
          f"<ellipse cx='214' cy='90' rx='7' ry='6' fill='{C['nariz']}'/>"
          f"<path d='M196 100 Q202 105 208 100' fill='none' stroke='{C['tinta']}' stroke-width='3' stroke-linecap='round'/>"
          f"<ellipse cx='170' cy='97' rx='8' ry='5' fill='{C['nariz']}' fill-opacity='.4'/>"
        + _olho(expressao) + "</g>"
        + _item(item)
    )


def _bola():
    """Tatu enrolado (área centrada em 0,0, raio 46)."""
    faixas = "".join(
        f"<path d='M{x} {-r} Q{x + 18} 0 {x} {r}' fill='none' stroke='{C['faixa']}' stroke-width='5' stroke-linecap='round'/>"
        for x, r in ((-26, 37), (-8, 45), (10, 44)))
    return (f"<circle r='46' fill='{C['caramelo']}'/>{faixas}"
            # escudos da cabeça e do rabo se encaixando, como no tatu-bola
            f"<path d='M22 -36 Q46 -20 44 4 Q30 8 24 -4 Q20 -20 22 -36 Z' fill='{C['faixa']}'/>"
            f"<path d='M26 8 Q42 12 40 26 Q30 34 22 24 Z' fill='{C['pele']}'/>"
            f"<circle cx='33' cy='18' r='5.5' fill='#FFFFFF' stroke='{C['tinta']}' stroke-width='2.5'/>"
            f"<circle cx='34' cy='18' r='2.4' fill='{C['tinta']}'/>")


def mascote_svg(tamanho=200, expressao="normal", item=None, rotulo=None):
    """O tatu Zu de óculos.
    expressao: 'normal' | 'atenta' | 'feliz' | 'preocupada' | 'desconfiada'
    item: None | 'lupa' | 'prancheta' | 'moeda' | 'alerta' | 'bola' (enrolado)."""
    altura = round(tamanho * 160 / 240)
    rotulo = rotulo or MASCOTE
    miolo = f"<g transform='translate(120 92)'>{_bola()}</g>" if item == "bola" else _tatu(expressao, item)
    return (f"<svg class='zu-mascote' width='{tamanho}' height='{altura}' viewBox='0 0 240 160' "
            f"xmlns='http://www.w3.org/2000/svg' role='img' aria-label='{rotulo}'><title>{rotulo}</title>{miolo}</svg>")


# --------------------------------------------------------------------------
# Carregamento: o Zu se enrola, rola pela tela e desenrola
# --------------------------------------------------------------------------
_CSS_CARREGANDO = """
<style>
.zu-pista { position: relative; width: 100%; max-width: 520px; height: 130px; overflow: hidden; }
.zu-pista svg { position: absolute; left: 0; top: 0; }
/* 0-14%: em pé na esquerda | 14-18%: enrola | 18-78%: rola | 78-82%: desenrola na direita | 82-92%: em pé | 92-100%: some */
@keyframes zu-pe-opacidade { 0% { opacity: 0 } 4%, 13% { opacity: 1 } 16%, 80% { opacity: 0 } 83%, 91% { opacity: 1 } 97%, 100% { opacity: 0 } }
@keyframes zu-pe-posicao { 0%, 79.9% { transform: translateX(0) } 80%, 100% { transform: translateX(var(--zu-dist, 340px)) } }
@keyframes zu-bola-opacidade { 0%, 13% { opacity: 0 } 16%, 80% { opacity: 1 } 83%, 100% { opacity: 0 } }
@keyframes zu-bola-rolar { 0%, 17% { transform: translateX(0) rotate(0deg) }
                           79%, 100% { transform: translateX(var(--zu-dist, 340px)) rotate(780deg) } }
@keyframes zu-sombra { 0%, 17% { transform: translateX(0) } 79%, 100% { transform: translateX(var(--zu-dist, 340px)) } }
.zu-anim-pe { animation: zu-pe-opacidade 4.4s linear infinite, zu-pe-posicao 4.4s linear infinite; }
.zu-anim-bola { animation: zu-bola-opacidade 4.4s linear infinite; }
.zu-anim-bola .zu-roda { animation: zu-bola-rolar 4.4s cubic-bezier(.4,0,.6,1) infinite; }
.zu-anim-sombra { animation: zu-sombra 4.4s cubic-bezier(.4,0,.6,1) infinite; }
@media (prefers-reduced-motion: reduce) {
  .zu-anim-pe, .zu-anim-bola, .zu-anim-bola .zu-roda, .zu-anim-sombra { animation: none; }
  .zu-anim-bola { opacity: 0; }
}
</style>
"""


def carregando_html(texto="Conferindo o demonstrativo...",
                    detalhe=None):
    """Tela de espera: o Zu se enrola em bola, rola pela pista e desenrola do outro lado."""
    detalhe = detalhe or f"{MASCOTE} está conferindo guia por guia. Arquivos grandes levam até um minuto."
    sombra = (f"<svg class='zu-anim-sombra' width='140' height='130' viewBox='0 0 140 130'>"
              f"<ellipse cx='70' cy='122' rx='44' ry='6' fill='{C['tinta']}' fill-opacity='.12'/></svg>")
    em_pe = (f"<svg class='zu-anim-pe' width='140' height='130' viewBox='0 0 240 222'>"
             f"<g transform='translate(0 58)'>{_tatu('atenta')}</g></svg>")
    bola = (f"<div class='zu-anim-bola' style='position:absolute;left:0;top:0'>"
            f"<div class='zu-roda' style='width:140px;height:130px;transform-origin:70px 70px'>"
            f"<svg width='140' height='130' viewBox='0 0 140 130'><g transform='translate(70 70)'>{_bola()}</g></svg>"
            f"</div></div>")
    return (_CSS_CARREGANDO +
            f"<div class='zu-carregando' role='status' aria-live='polite'>"
            f"<div class='zu-pista' style='--zu-dist: 340px'>{sombra}{em_pe}{bola}</div>"
            f"<div class='zu-carregando-titulo'>{texto}</div>"
            f"<div class='zu-carregando-sub'>{detalhe}</div></div>")

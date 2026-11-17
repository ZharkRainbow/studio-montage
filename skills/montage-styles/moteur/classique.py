"""Style « classique » : génère la composition HyperFrames d'un plan.

Calques, de l'arrière vers l'avant : image étalonnée, mots en profondeur (dégradé bleu, étirés), personne détourée,
sous-titres ZT Nature et blocs en avant, panneau, listes qui défilent, cartons bleus, habillage (coins).
Le CSS et le JS sont ceux de la version validée (styles/classique.css, styles/classique.js) : ne pas les réécrire,
les régler par le plan.
"""
import json, shutil
from commun import MARQUE, STYLES, esc, copier_polices, ecrire

ROUE_CLASSES = {'encre': ' ink', 'blanc': ' halo', 'bleu': ' bleu', 'blanc-uni': ' uni-blanc', 'bleu-uni': ' uni-bleu', 'blanc-glow': ' glow'}


def generer(P, prj, plan, V):
    NF, FPS = prj['nf'], prj['fps']
    D = NF / FPS
    MOTS = {int(k): v for k, v in json.load(open(P / 'mots.json', encoding='utf-8')).items()}
    CORR = plan.get('corrections', {})
    FUSION = {int(k): v for k, v in plan.get('fusion', {}).items()}

    def mot(i):
        w = FUSION.get(i, MOTS[i]['w'])
        return CORR.get(w, w)

    def f(i):
        return MOTS[i]['f']

    def spans(ids, cls='w', em=(), ponct=None):
        ponct = {int(k): v for k, v in (ponct or {}).items()}
        out = []
        for i in ids:
            t = mot(i)
            if not t:
                continue
            out.append(f'<span class="{cls}{" em" if i in em else ""}" data-f="{f(i)}" data-i="{i}">{esc(t + ponct.get(i, ""))}</span>')
        return ' '.join(out)

    # sous-titres : groupes de 1 à 4 mots ; fin = début du groupe suivant, ou fin forcée
    groupes = plan['groupes']
    fin_forcee = {int(k): v for k, v in plan.get('fin_forcee', {}).items()}
    el = []
    debuts = [f(g[0]) for g in groupes]
    for k, g in enumerate(groupes):
        nxt = debuts[k + 1] if k + 1 < len(groupes) else NF
        f1 = fin_forcee.get(g[-1], nxt)
        el.append(f'<div class="cap" data-f0="{f(g[0])}" data-f1="{f1}"><div class="ln">{spans(g)}</div></div>')
    for b in plan.get('blocs', []):
        stat = b.get('statique', False)
        el.append(f'<div class="bloc{" statique" if stat else ""}{" fx" if b.get("fx") else ""}" id="b-{b["id"]}" '
                  f'data-f0="{0 if stat else f(b["lead"][0])}" data-f1="{b["fin"]}">'
                  f'<div class="lead">{spans(b["lead"])}</div><div class="big">{spans(b["big"])}</div></div>')

    def interieur(p):
        if p.get('chiffre') is not None:
            n = int(p['chiffre'])
            return '<span class="roll"><span class="col">' + ''.join(f'<span class="dg dw">{d}</span>' for d in range(n + 1)) + '</span></span>'
        return f'<span class="dw">{esc(p["texte"])}</span>'
    prof = '\n'.join(
        f'<div class="depth{" chiffre" if p.get("chiffre") is not None else ""} v3" id="d-{p["id"]}" data-f0="{p["f0"]}" data-f1="{p["f1"]}" '
        f'data-sommet="{p.get("sommet", 0)}" data-cx="{p.get("cx", 540)}" data-haut="{p.get("haut", 300)}" data-chiffre="{p.get("chiffre", "")}" '
        f'data-brille=\'{json.dumps(p.get("brille", []))}\'>{interieur(p)}</div>' for p in plan.get('profondeur', []))

    cartons = []
    for c in plan.get('cartons', []):
        ph = []
        for p in c['phrases']:
            lignes = ''.join(f'<div class="ql">{spans(l, em=p.get("em", []), ponct=p.get("ponct"))}</div>' for l in p['lignes'])
            ph.append(f'<div class="q" data-f0="{p["f0"]}" data-f1="{p["f1"]}">{lignes}</div>')
        cartons.append(f'<div class="card{" stack" if len(c["phrases"]) > 1 else ""}" id="{c["id"]}" data-f0="{c["f0"]}" data-f1="{c["f1"]}">'
                       f'<div class="clabel"><span class="rule"></span>{esc(c["label"])}</div><div class="cnum">{esc(c["num"])}</div>{"".join(ph)}</div>')

    panneau = ''
    p = plan.get('panneau')
    if p:
        lignes = ''.join(
            f'<div class="pl{" acc" if l.get("accent") else ""}" data-f="{l["f"]}"><span class="sq"></span><span class="pn">{esc(l["n"])}</span>'
            f'<span class="pt">{esc(l["txt"])}</span><span class="ptag" data-f="{l["ftag"]}">{esc(l["tag"])}</span></div>' for l in p['lignes'])
        panneau = (f'<div class="panel{" bas" if p.get("position", "bas") == "bas" else ""}" data-f0="{p["f0"]}" data-f1="{p["f1"]}">'
                   f'<div class="ph"><span>{esc(p["titre"])}</span><span class="pbig">{esc(p.get("chiffre", ""))}</span></div>{lignes}</div>')

    roues = []
    for r in plan.get('roues', []):
        items = ''.join(f'<div class="it">{esc(t)}</div>' for t in r['items'])
        tag = ''
        if r.get('tag'):
            tag = f'<div class="wtag" data-f="{r["tag"]["f"]}" data-item="{r["tag"]["item"]}">{esc(r["tag"]["txt"])}</div>'
        roues.append(f'<div class="wheel{ROUE_CLASSES[r.get("style", "blanc-glow")]}" id="w-{r["id"]}" data-f0="{r["f0"]}" data-f1="{r["f1"]}" '
                     f'data-pas=\'{json.dumps(r["pas"])}\' style="top:{r["y"]}px"><div class="arrow">→</div><div class="list">{items}</div>{tag}</div>')

    hud = plan.get('habillage', 'epure')
    if hud == 'epure':
        hud_html = '<div class="hud epure"><div class="c tl"></div><div class="c tr"></div><div class="c bl"></div><div class="c br"></div></div>'
    else:
        h = plan.get('hud', {})
        hud_html = ('<div class="hud"><div class="c tl"></div><div class="c tr"></div><div class="c bl"></div><div class="c br"></div>'
                    f'<div class="lab">{esc(h.get("titre", MARQUE))}<small>{esc(h.get("sous_titre", ""))}</small></div>'
                    '<div class="tc"><i class="rec"></i><span>00:00:00:00</span></div>'
                    + (f'<div class="vert">{esc(h["vertical"])}</div>' if h.get('vertical') else '') + '</div>')

    cfg = dict(FPS=FPS, NF=NF, COUPES=prj['coupes'], PUNCHS=plan.get('punchs', []), TRACES=plan.get('traces', []), ETIRE=1.55, V3=True)
    comp = V / 'composition'
    copier_polices(comp / 'assets')
    shutil.copy2(P / 'assets/base.mp4', comp / 'assets/base.mp4')
    fg = ''
    if plan.get('profondeur'):
        shutil.copy2(P / 'assets/fg.webm', comp / 'assets/fg.webm')
        fg = f'<video id="fg" class="clip" src="assets/fg.webm" data-start="0" data-duration="{D:.4f}" data-track-index="1" muted playsinline></video>'
    css = (STYLES / 'classique.css').read_text(encoding='utf-8')
    js = (STYLES / 'classique.js').read_text(encoding='utf-8') + (STYLES / 'qa.js').read_text(encoding='utf-8')
    doc = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>{esc(prj['rush'])} · classique</title>
<script src="assets/gsap.min.js"></script><style>{css}</style></head><body>
<div id="root" data-composition-id="main" data-width="1080" data-height="1920" data-fps="{FPS}" data-duration="{D:.4f}" data-style="classique">
<div id="cam"><div id="punch">
<video id="base" class="clip" src="assets/base.mp4" data-start="0" data-duration="{D:.4f}" data-track-index="0" muted playsinline></video>
{prof}
{fg}
</div></div>
{chr(10).join(el)}
{panneau}
{chr(10).join(roues)}
{chr(10).join(cartons)}
{hud_html}
</div>
<script>window.CFG={json.dumps(cfg)};</script>
<script>{js}</script></body></html>"""
    (comp / 'index.html').write_text(doc, encoding='utf-8')
    ecrire(comp / 'hyperframes.json', {"authoringSkill": "general-video", "media": {"autoProxy": True}})
    ecrire(comp / 'package.json', {"private": True, "scripts": {"render": "npx --yes hyperframes@0.8.162 render"}})
    return comp

"""Contrôle d'une version avant dépôt : défauts bloquants (code 1) et points à regarder sur la planche.

Bloquant :
  - police ZT Nature (ou Instrument Serif en classique) non chargée : le texte s'affiche dans une autre police ;
  - texte coupé par le bord de l’image (le frôlement de la marge de 20 px est seulement signalé) ;
  - deux textes affichés en même temps qui se chevauchent ;
  - texte posé à plus de 10 % sur la tête (masque du détourage ; les mots en profondeur du classique sont exclus, ils sont voulus derrière) ;
  - son hors de -15 à -13 LUFS, ou bruitage absent du mix.
À regarder : texte blanc sur fond très clair, texte qui frôle le visage, écartements faits automatiquement.
"""
import json, re, subprocess, sys
from pathlib import Path
from commun import chrome, ecrire, lire, run, sha


def rapport_page(comp):
    url = (comp / 'index.html').as_uri() + '?qa=1'
    out = subprocess.run([chrome(), '--headless', '--disable-gpu', '--hide-scrollbars', '--window-size=1080,1920', '--virtual-time-budget=9000',
                          '--dump-dom', url], capture_output=True, text=True, timeout=180).stdout
    m = re.search(r'<pre id="qa-rapport">(.*?)</pre>', out, re.S)
    if not m:
        sys.exit('Rapport de mise en page introuvable : la page n’a pas fini de se construire (police manquante ou erreur JS ?).')
    import html as h
    return json.loads(h.unescape(m.group(1)))


def image(path, fr, fps, gris=True):
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{fr / fps:.4f}', '-i', str(path), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(1920, 1080) if raw else None


def tete(m):
    import numpy as np
    rows = np.where((m[:, 324:756] > 127).sum(1) > 4)[0]
    if not len(rows):
        return None
    t = int(rows[0]); zone = np.zeros_like(m, bool); zone[t:t + 300] = m[t:t + 300] > 127
    return zone


def controler(P, prj, V, vu=False):
    import numpy as np
    fps, NF = prj['fps'], prj['nf']
    comp = V / 'composition'
    final = V / 'export' / f'{prj["rush"]}-{prj["style"]}-{V.name}.mp4'
    if not final.exists():
        sys.exit(f'Version non rendue : {final}')
    bloq, avert, infos = [], [], []
    r = rapport_page(comp)
    if not r['polices'].get('ZTN') and not r['polices'].get('ITight'):
        bloq.append('Ni ZT Nature ni Inter Tight chargée : le texte s’affiche dans une police de remplacement.')
    if r['style'] == 'classique' and not r['polices'].get('ISerif'):
        bloq.append('Instrument Serif non chargée.')
    els = r['elements']
    for e in els:
        x0, y0, x1, y1 = e['box']
        if x0 < 0 or x1 > 1080 or y0 < 0 or y1 > 1920:
            bloq.append(f'Coupé par le bord de l’image : {e["type"]} « {e["id"]} » boîte {e["box"]} (images {e["f0"]}-{e["f1"]}).')
        elif x0 < 20 or x1 > 1060 or y0 < 100 or y1 > 1820:
            avert.append(f'Dans la marge (moins de 20 px du bord, ou sous l’interface Instagram) : {e["type"]} « {e["id"]} » boîte {e["box"]}.')
    for i, a in enumerate(els):
        for b in els[i + 1:]:
            if a['f1'] <= b['f0'] or b['f1'] <= a['f0']:
                continue
            if a['id'].split(' ')[0].split('-')[0] == b['id'].split(' ')[0].split('-')[0] and a['id'].startswith('blk'):
                continue
            ix = max(0, min(a['box'][2], b['box'][2]) - max(a['box'][0], b['box'][0]))
            iy = max(0, min(a['box'][3], b['box'][3]) - max(a['box'][1], b['box'][1]))
            aire = lambda e: max(1, (e['box'][2] - e['box'][0]) * (e['box'][3] - e['box'][1]))
            if ix * iy > 0.08 * min(aire(a), aire(b)):
                bloq.append(f'Chevauchement : « {a["id"]} » et « {b["id"]} » aux images {max(a["f0"], b["f0"])}-{min(a["f1"], b["f1"])}.')
    for bl in r.get('blocs', []):
        for c in bl.get('collisions', []):
            bloq.append(f'Lettres qui se touchent encore : « {c["texte"]} » ({c["pixels"]} px) dans le bloc des images {bl["f0"]}-{bl["f1"]}.')
        for aj in bl.get('ajustements', []):
            infos.append(f'Écarté automatiquement de {aj["ecart_ajoute"]} px : « {aj["texte"]} » (images {bl["f0"]}-{bl["f1"]}).')
        if bl.get('echelle', 1) < 0.8:
            avert.append(f'Bloc des images {bl["f0"]}-{bl["f1"]} réduit à {bl["echelle"]:.0%} pour tenir en largeur : trop de texte ?')
    # visage et lisibilité, sur la vidéo seulement
    masque, base = P / 'assets/masque.mp4', P / 'assets/base.mp4'
    for e in els:
        if not e['surVideo'] or e['type'] == 'profondeur':
            continue
        x0, y0, x1, y1 = [max(0, v) for v in e['box']]
        x1, y1 = min(x1, 1080), min(y1, 1920)
        pire = 0
        for fr in sorted({e['f0'] + 2, (e['f0'] + e['f1']) // 2, e['f1'] - 3}):
            if not 0 <= fr < NF:
                continue
            m = image(masque, fr, fps)
            z = tete(m) if m is not None else None
            if z is not None and x1 > x0 and y1 > y0:
                pire = max(pire, float(z[y0:y1, x0:x1].mean()))
        if pire > .10:
            bloq.append(f'Texte sur le visage ({pire:.0%}) : {e["type"]} « {e["id"]} », images {e["f0"]}-{e["f1"]}.')
        elif pire > .03:
            avert.append(f'Texte qui frôle le visage ({pire:.0%}) : {e["type"]} « {e["id"]} », images {e["f0"]}-{e["f1"]}.')
        if e.get('blanc') and x1 > x0 and y1 > y0:
            y = image(base, (e['f0'] + e['f1']) // 2, fps)
            if y is not None and float(np.median(y[y0:y1, x0:x1])) / 255 > .75:
                avert.append(f'Texte blanc sur fond très clair : {e["type"]} « {e["id"]} », images {e["f0"]}-{e["f1"]}.')
    son = lire(V / 'son.json')
    if not -15 <= son['lufs'] <= -13:
        bloq.append(f'Son à {son["lufs"]} LUFS au lieu de -14.')
    for s in son['sfx']:
        if s['db'] < -55:
            bloq.append(f'Bruitage absent du mix : {s["son"]} à l’image {s["image"]}.')
    # planche : une image au milieu de chaque texte important (blocs, mots en profondeur, cartons, listes, panneau)
    cle = [e for e in els if e['type'] in ('bloc', 'profondeur', 'carton', 'liste', 'panneau', 'piece')]
    vus, temps = set(), []
    for e in sorted(cle, key=lambda e: e['f0']):
        fr = e.get('fplein', e['f0'] + 6)
        if all(abs(fr - t) > 8 for t in vus):
            vus.add(fr); temps.append(fr)
    if len(temps) > 24:
        temps = [temps[round(i * (len(temps) - 1) / 23)] for i in range(24)]
    d = V / 'controle'; d.mkdir(exist_ok=True)
    for f in d.glob('i-*.png'):
        f.unlink()
    for fr in temps:
        run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{fr / fps + .001:.4f}', '-i', final, '-frames:v', '1', '-vf', 'scale=270:480', d / f'i-{fr:05d}.png'])
    imgs = sorted(d.glob('i-*.png'))
    if imgs:
        run(['magick', 'montage', *imgs, '-tile', '8x', '-geometry', '+3+3', '-background', '#111', '-fill', 'white', '-pointsize', '14',
             '-font', str(Path(__file__).resolve().parent / 'assets' / 'InterTight.ttf'), '-label', '%t', d / 'planche.png'])
    res = dict(version=V.name, fichier=str(final), sha=sha(final), bloquants=bloq, avertissements=avert, infos=infos,
               planche=str(d / 'planche.png'), images=temps, planche_vue=bool(vu and not bloq))
    ecrire(d / 'controle.json', res)
    print(f'Contrôle {V.name} : {len(bloq)} bloquant(s), {len(avert)} à regarder, {len(infos)} info(s)')
    for t, l in (('BLOQUANT', bloq), ('À REGARDER', avert), ('INFO', infos)):
        for x in l:
            print(f'  {t} : {x}')
    print(f'  Planche à regarder : {d / "planche.png"}')
    if not vu and not bloq:
        print('  Regarder la planche (liste de contrôle du skill), puis relancer avec --vu pour autoriser le dépôt.')
    return 1 if bloq else 0

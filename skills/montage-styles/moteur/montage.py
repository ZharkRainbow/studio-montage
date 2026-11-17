#!/usr/bin/env python3
"""Moteur du style de montage « classique ».

  PY=~/.venv-studio-montage/bin/python ; M=~/.claude/skills/montage-styles/moteur/montage.py
  $PY -I $M decouper  --projet P --rush RUSH --source /chemin/rush.mp4 [--garder 3.2-41.0,55-80] [--blanc 0.35]
  $PY -I $M preparer  --projet P --rush RUSH --source /chemin/rush.mp4 --style classique
  $PY -I $M mesurer   --projet P --plages 66-144,690-718
  $PY -I $M generer   --projet P --version v1          (lit P/plan.json)
  $PY -I $M rendre    --projet P --version v1          (rendu + son)
  $PY -I $M controler --projet P --version v1          (bloquant : code 1 s'il reste un défaut)
  $PY -I $M deposer   --projet P --version v1 --dossier "Style classique" [--nom "…"] [--projet-atelier ID]
"""
import argparse, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from commun import (ATELIER, HF, LUT_709, LUT_LOG, LUTS, MUSIQUE_DEFAUT, MUSIQUE_DIR, SFX, SFX_DIR, ecrire, env_node, lire, projet,
                    run, sha, version_dir)


# ------------------------------------------------------------------ découper (mots + coupes des blancs)
def decouper(a):
    """Transcrit le rush au mot (whisper.cpp), garde les plages choisies et coupe les blancs entre les mots.
    Écrit P/job/montage/RUSH-analysis-minimale.json et RUSH-cuts.json, que « preparer » lit ensuite."""
    import tempfile
    P = Path(a.projet).expanduser().resolve(); R = a.rush
    src = Path(a.source).expanduser().resolve()
    if not src.exists():
        sys.exit(f'Source introuvable : {src}')
    job = P / 'job' / 'montage'; job.mkdir(parents=True, exist_ok=True)
    num, den = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate', '-of', 'csv=p=0', src],
                              capture_output=True, text=True).stdout.strip().split('/')
    fps = round(float(num) / float(den or 1), 3)
    fps = round(fps) if abs(fps - round(fps)) < .01 else fps
    duree = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', src],
                                 capture_output=True, text=True).stdout.strip())
    modele = Path(os.environ.get('WHISPER_MODEL', Path.home() / '.cache/whisper-cpp/ggml-large-v3-turbo.bin')).expanduser()
    if not modele.exists():
        sys.exit(f'Modèle whisper introuvable : {modele} (voir l’installation du studio)')
    with tempfile.TemporaryDirectory() as t:
        wav = Path(t) / 'voix.wav'
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', src, '-vn', '-ac', '1', '-ar', '16000', wav])
        run(['whisper-cli', '-m', modele, '-l', a.langue, '-f', wav, '-ml', '1', '-sow', '-ojf', '-of', Path(t) / 'mots', '-np'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        brut = json.load(open(Path(t) / 'mots.json', encoding='utf-8', errors='replace'))
    mots = []
    for seg in brut.get('transcription', []):
        txt = seg.get('text', '').strip()
        if not txt or txt.startswith('['):
            continue
        t0, t1 = seg['offsets']['from'] / 1000, seg['offsets']['to'] / 1000
        if t1 > t0:
            mots.append((t0, t1, txt))
    if not mots:
        sys.exit('Aucun mot reconnu dans le rush.')
    garder = [tuple(float(x) for x in g.split('-')) for g in a.garder.split(',')] if a.garder else [(mots[0][0] - .1, mots[-1][1] + .3)]
    # les blancs se mesurent dans le son (whisper étire les mots sur les pauses) : silences de plus de --blanc secondes
    sortie = subprocess.run(['ffmpeg', '-nostdin', '-v', 'info', '-i', src, '-vn', '-af', f'silencedetect=noise={a.seuil}dB:d={a.blanc}', '-f', 'null', '-'],
                            capture_output=True, text=True).stderr
    debuts = [float(x) for x in re.findall(r'silence_start: (-?[\d.]+)', sortie)]
    fins = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', sortie)] + [duree]
    silences = [(d + .06, f - .08) for d, f in zip(debuts, fins) if f - .08 > d + .06]
    blocs = []
    for g0, g1 in garder:
        g0, g1 = max(0, g0), min(duree, g1)
        t = g0
        for d, f in silences:
            if f <= g0 or d >= g1:
                continue
            if d > t:
                blocs.append([t, d, (g0, g1)])
            t = max(t, f)
        if g1 > t:
            blocs.append([t, g1, (g0, g1)])
    blocs = [b for b in blocs if b[1] - b[0] > .12]
    segments = [dict(startFrame=int(round(d * fps)), endFrame=int(round(f * fps))) for d, f, _ in blocs]
    segments = [x for x in segments if x['endFrame'] > x['startFrame']]
    words = [dict(id=f'w{i + 1}', text=w, startFrame=int(round(t0 * fps)), endFrame=int(round(t1 * fps))) for i, (t0, t1, w) in enumerate(mots)]
    ecrire(job / f'{R}-analysis-minimale.json', dict(fps=fps, source=str(src), words=words))
    ecrire(job / f'{R}-cuts.json', dict(source=str(src), segments=segments))
    garde = sum(x['endFrame'] - x['startFrame'] for x in segments) / fps
    print(f'{len(words)} mots, {len(segments)} morceaux gardés, {garde:.1f} s sur {duree:.1f} s')
    print(f'  {job / (R + "-cuts.json")}')


# ------------------------------------------------------------------ préparer
def preparer(a):
    P = Path(a.projet).expanduser().resolve()
    R = a.rush
    job = P / 'job' / 'montage'
    cuts = lire(job / f'{R}-cuts.json')['segments']
    ana = lire(job / f'{R}-analysis-minimale.json')
    src = Path(a.source).expanduser() if a.source else P / 'job' / 'sources' / f'{R}.mov'
    if not src.exists():
        sys.exit(f'Source introuvable : {src}')
    fps = ana.get('fps', 30)
    N, offs, mots = 0, [], {}
    for s in cuts:
        offs.append(N)
        for w in ana['words']:
            # un mot qui commence juste avant le morceau (whisper décale les débuts de quelques images) y est rattaché
            if s['startFrame'] - 6 <= w['startFrame'] < s['endFrame'] and int(w['id'][1:]) not in mots:
                mots[int(w['id'][1:])] = dict(f=N + max(0, w['startFrame'] - s['startFrame']), w=w['text'])
        N += s['endFrame'] - s['startFrame']
    (P / 'assets').mkdir(parents=True, exist_ok=True)
    ecrire(P / 'mots.json', {str(k): v for k, v in sorted(mots.items())})
    lignes = []
    debuts = {o: n for n, o in enumerate(offs)}
    for fr in range(N):
        if fr in debuts:
            lignes.append(f'--- coupe {debuts[fr] + 1}/{len(cuts)} : image {fr}')
        for i, w in sorted(mots.items()):
            if w['f'] == fr:
                lignes.append(f"{i:4d}  image {fr:5d}  {fr / fps:6.2f} s  {w['w']}")
    lignes.append(f'{len(mots)} mots, {N} images, {N / fps:.2f} s')
    (P / 'mots.txt').write_text('\n'.join(lignes) + '\n', encoding='utf-8')
    coupes = P / 'assets' / 'coupes.mp4'
    if not coupes.exists():
        filt = ''.join(f"[0:v]trim=start_frame={s['startFrame']}:end_frame={s['endFrame']},setpts=PTS-STARTPTS[v{n}];"
                       f"[0:a]atrim=start={s['startFrame'] / fps:.6f}:end={s['endFrame'] / fps:.6f},asetpts=PTS-STARTPTS[a{n}];" for n, s in enumerate(cuts))
        filt += ''.join(f'[v{n}][a{n}]' for n in range(len(cuts))) + f'concat=n={len(cuts)}:v=1:a=1[v][a]'
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', src, '-filter_complex', filt, '-map', '[v]', '-map', '[a]', '-r', fps,
             '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k', coupes])
    # colo : la source décide de la LUT (rush en Log -> LUT de conversion du profil ; déjà en Rec.709 -> rien)
    pr = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,color_primaries',
                                    '-of', 'json', src], capture_output=True, text=True).stdout)['streams'][0]
    if pr.get('color_primaries') == 'bt2020':
        sys.exit('Rush iPhone HDR (bt2020) : le convertir d’abord en SDR Rec.709 (par exemple avec avconvert sur Mac), puis relancer.')
    ymin, ymax = [], []
    for k in range(1, 9):
        out = subprocess.run(['ffmpeg', '-v', 'info', '-ss', f'{N / fps * k / 9:.2f}', '-i', coupes, '-frames:v', '1', '-vf', 'signalstats,metadata=mode=print',
                              '-f', 'null', '-'], capture_output=True, text=True).stderr
        ymin += [float(x) for x in re.findall(r'YLOW=([\d.]+)', out)[:1]]
        ymax += [float(x) for x in re.findall(r'YHIGH=([\d.]+)', out)[:1]]
    log = bool(ymin) and min(ymin) > 45 and max(ymax) < 205
    # pas de colorimétrie : rush en Log -> conversion Rec.709 seule (LUT du profil) ; source déjà en Rec.709 -> rien
    lut = a.lut or (LUT_LOG if log else LUT_709)
    if lut in (None, 'aucune'):
        lut = None
    elif not LUT_LOG and lut == LUT_LOG:
        lut = None
    elif not (LUTS / lut).exists():
        sys.exit(f'LUT introuvable : {LUTS / lut}')
    base = P / 'assets' / 'base.mp4'
    tmp = P / 'assets' / 'lut.cube'
    if lut:
        shutil.copy2(LUTS / lut, tmp)
    vf = f'[0:v]format=gbrp,lut3d=file={tmp}:interp=tetrahedral,format=yuv420p[v]' if lut else '[0:v]format=yuv420p[v]'
    run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', coupes, '-filter_complex', vf,
         '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-g', '15', '-colorspace', 'bt709', '-color_primaries', 'bt709',
         '-color_trc', 'bt709', '-movflags', '+faststart', base])
    # détourage : masque pour le contrôle (visage) et, en classique, la personne étalonnée pour les mots en profondeur
    masque = P / 'assets' / 'masque.mp4'
    if not masque.exists():
        det = P / 'assets' / 'detoure.webm'
        run(['npx', '--yes', HF, 'remove-background', coupes, '-o', det, '--quality', 'best'], env=env_node(), stdout=subprocess.DEVNULL)
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-c:v', 'libvpx-vp9', '-i', det, '-vf', 'alphaextract,format=gray', '-c:v', 'libx264', '-crf', '10',
             '-preset', 'fast', '-pix_fmt', 'yuv420p', masque])
    if a.style == 'classique':
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', base, '-i', masque, '-filter_complex', '[1:v]format=gray[m];[0:v][m]alphamerge,format=yuva420p[v]',
             '-map', '[v]', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '22', '-deadline', 'good', '-cpu-used', '4', '-row-mt', '1',
             '-auto-alt-ref', '0', '-metadata:s:v:0', 'alpha_mode=1', P / 'assets' / 'fg.webm'])
    ecrire(P / 'projet.json', dict(rush=R, source=str(src), style=a.style, fps=fps, nf=N, coupes=offs + [N], lut=lut or 'aucune (source déjà en Rec.709)',
                                   mesure_source=dict(ylow_min=min(ymin) if ymin else None, yhigh_max=max(ymax) if ymax else None)))
    print(f'Projet prêt : {P}\n  {len(mots)} mots, {N} images ({N / fps:.1f} s), {len(cuts)} coupes, LUT « {lut or 'aucune'} »')
    print(f'  Mots et images : {P / "mots.txt"} (à lire en entier avant d’écrire {P / "plan.json"})')


# ------------------------------------------------------------------ mesurer
def mesurer(a):
    import numpy as np
    P, prj = projet(a.projet)
    fps = prj['fps']

    def images(path, f0, f1, pas):
        n = max(1, (f1 - f0) // pas)
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{f0 / fps:.4f}', '-t', f'{(f1 - f0) / fps:.4f}', '-i', path, '-vf', f'select=not(mod(n\\,{pas}))',
                              '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
        if not raw:
            sys.exit(f'Lecture impossible de {path} entre les images {f0} et {f1}.')
        return np.frombuffer(raw, np.uint8).reshape(-1, 1920, 1080)
    zones = {'haut-gauche': (60, 280, 400, 290), 'haut-droite': (620, 280, 400, 290), 'bas (panneau)': (60, 1255, 960, 330), 'centre (blocs)': (60, 900, 960, 340)}
    for pl in a.plages.split(','):
        f0, f1 = [int(x) for x in pl.split('-')]
        M = images(P / 'assets/masque.mp4', f0, f1, a.pas) > 127
        Y = images(P / 'assets/base.mp4', f0, f1, a.pas) / 255.0
        print(f'--- images {f0} à {f1}')
        for j, (m, y) in enumerate(zip(M, Y)):
            rows = np.where(m[:, 324:756].sum(1) > 4)[0]
            if not len(rows):
                print(f'  {f0 + a.pas * j:5d}  personne absente du centre'); continue
            t = int(rows[0]); cols = np.where(m[t:t + 280].any(0))[0]
            bande = y[max(0, t - 120):t + 20]; libre = ~m[max(0, t - 120):t + 20]
            print(f'  {f0 + a.pas * j:5d}  sommet tête {t:4d}  tête x {cols[0]:4d}-{cols[-1]:4d}  luminosité au-dessus de la tête {float(bande[libre].mean()):.2f}')
        for nom, (x, yy, w, h) in zones.items():
            ov = M[:, yy:yy + h, x:x + w].mean(axis=(1, 2))
            print(f'  zone {nom:15s} personne max {ov.max():4.0%}   luminosité {float(Y[:, yy:yy + h, x:x + w].mean()):.2f}')


# ------------------------------------------------------------------ générer
def generer(a):
    P, prj = projet(a.projet)
    plan = lire(P / 'plan.json')
    V = version_dir(P, a.version)
    if (V / 'composition' / 'index.html').exists():
        sys.exit(f'{V} existe déjà : créer {a.version[0]}{int(a.version[1:]) + 1} plutôt que d’écraser une version.')
    style = plan.get('style', prj['style'])
    if style != 'classique':
        sys.exit(f'Style inconnu : {style} (seul « classique » est livré)')
    import classique
    comp = classique.generer(P, prj, plan, V)
    ecrire(V / 'sfx-plan.json', dict(SFX=plan.get('sfx', []), musique=plan.get('musique', MUSIQUE_DEFAUT), carte_fin=plan.get('carte_fin')))
    shutil.copy2(P / 'plan.json', V / 'plan.json')
    print(f'Composition : {comp / "index.html"}')


# ------------------------------------------------------------------ rendre (image) + son
def lufs(args):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats'] + [str(x) for x in args] + ['-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True)
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)[-1])


def pics_sfx(dest):
    import numpy as np
    cache = dest / 'pics.json'
    pics = lire(cache) if cache.exists() else {}
    for nom, rel in SFX.items():
        if nom in pics:
            continue
        src = SFX_DIR / rel
        if not src.exists():
            continue
        shutil.copy2(src, dest / nom)
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', dest / nom, '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'], capture_output=True).stdout
        x = np.frombuffer(raw, np.float32); env = np.sqrt(np.convolve(x * x, np.ones(480) / 480, 'same'))
        k = int(np.argmax(env)); pics[nom] = dict(pic=round(k / 48000, 3), rms_pic_db=round(float(20 * np.log10(env[k] + 1e-9)), 1))
    ecrire(cache, pics)
    return pics


def rendre(a):
    import numpy as np
    P, prj = projet(a.projet)
    V = version_dir(P, a.version)
    comp, exp = V / 'composition', V / 'export'
    exp.mkdir(parents=True, exist_ok=True)
    muet = exp / 'rendu-sans-son.mp4'
    log = V / 'render.log'
    if getattr(a, 'video_de', None):
        # même image qu'une version déjà rendue (seuls le son ou la carte de fin changent) : on reprend son rendu sans son,
        # à condition que la composition soit identique octet pour octet
        W = version_dir(P, a.video_de)
        if (W / 'composition' / 'index.html').read_bytes() != (comp / 'index.html').read_bytes():
            sys.exit(f'--video-de {a.video_de} refusé : la composition a changé, il faut refaire le rendu de l’image.')
        shutil.copy2(W / 'export' / 'rendu-sans-son.mp4', muet)
        print(f'Image reprise de {a.video_de} (composition identique)')
    else:
        with open(log, 'w') as fl:
            r = subprocess.run(['npx', '--yes', HF, 'render', '.', '-o', muet], cwd=comp, env=env_node(), stdout=fl, stderr=subprocess.STDOUT)
        if r.returncode:
            sys.exit(f'Rendu en échec (code {r.returncode}) : lire {log}')
    sp = lire(V / 'sfx-plan.json')
    mus = sp.get('musique') or MUSIQUE_DEFAUT
    D = prj['nf'] / prj['fps']
    # carte de fin (« Retrouve la vidéo complète », 3 s) : collée après le reel, la musique continue dessous et s'éteint
    # sur sa fin ; la voix se tait ; les sons de la carte gardent leur niveau
    carte = Path(sp['carte_fin']).expanduser() if sp.get('carte_fin') else None
    Dv = D
    if carte:
        if not carte.exists():
            sys.exit(f'Carte de fin introuvable : {carte}')
        dc = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', carte],
                                  capture_output=True, text=True).stdout.strip())
        avec = exp / 'rendu-sans-son-carte.mp4'
        run(['ffmpeg', '-v', 'error', '-y', '-nostdin', '-i', muet, '-i', carte, '-filter_complex',
             f'[0:v]fps={prj["fps"]},format=yuv420p,setsar=1[a];[1:v]scale=1080:1920,fps={prj["fps"]},format=yuv420p,setsar=1[b];[a][b]concat=n=2:v=1:a=0[v]',
             '-map', '[v]', '-c:v', 'libx264', '-preset', 'fast', '-crf', '14', '-colorspace', 'bt709', '-color_primaries', 'bt709',
             '-color_trc', 'bt709', '-color_range', 'tv', avec])
        muet, D = avec, D + dc
    sfxdir = P / 'assets' / 'sfx'; sfxdir.mkdir(exist_ok=True)
    pics = pics_sfx(sfxdir)
    voix = P / 'assets/coupes.mp4'
    gv = -14 - lufs(['-i', voix, '-vn'])
    if mus.get('fichier'):
        musique = MUSIQUE_DIR / mus['fichier']
        dm = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', musique],
                                  capture_output=True, text=True).stdout.strip())
        if dm - float(mus['debut']) < D:   # vu le 10/11 : « Let it burn » (2:09) s'arrêtait avant la fin d'un reel de 2:17 + carte
            sys.exit(f'Musique trop courte : « {mus["fichier"]} » dure {dm:.0f} s, il en faut {D + float(mus["debut"]):.0f} (reel + carte + départ). Choisir une piste plus longue.')
        gm = -34 - lufs(['-ss', mus['debut'], '-t', f'{Dv:.3f}', '-i', musique, '-vn'])
        entrees = ['-i', muet, '-i', voix, '-ss', mus['debut'], '-t', f'{D + .5:.3f}', '-i', musique]
    else:  # « musique »: {"fichier": null} : sans musique (un silence garde la même chaîne de mixage)
        gm = 0
        entrees = ['-i', muet, '-i', voix, '-f', 'lavfi', '-t', f'{D + .5:.3f}', '-i', 'anullsrc=r=48000:cl=stereo']
    fc = [f'[1:a]highpass=f=70,volume={gv:.2f}dB,apad,atrim=0:{D:.3f}[voix]',
          f'[2:a]atrim=0:{D:.3f},asetpts=PTS-STARTPTS,volume={gm:.2f}dB,afade=t=in:d=0.6,afade=t=out:st={D - 1.5:.3f}:d=1.5[mus]']
    noms = []
    for k, (fr, nom, cible) in enumerate(sp['SFX']):
        if nom not in pics:
            sys.exit(f'Bruitage inconnu : {nom} (noms permis : {", ".join(SFX)})')
        debut = fr / prj['fps'] - pics[nom]['pic']
        entrees += ['-i', sfxdir / nom]
        coupe = f'atrim=start={-debut:.3f},asetpts=PTS-STARTPTS,' if debut < 0 else ''
        ms = max(0, int(round(debut * 1000)))
        fc.append(f'[{3 + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,{coupe}volume={cible - pics[nom]["rms_pic_db"]:.2f}dB,adelay={ms}|{ms}[s{k}]')
        noms.append(f'[s{k}]')
    if carte:
        k = len(sp['SFX']); ms = int(round(Dv * 1000))
        entrees += ['-i', carte]
        fc.append(f'[{3 + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[s{k}]')
        noms.append(f'[s{k}]')
    if noms:
        fc.append(f'{"".join(noms)}amix=inputs={len(noms)}:normalize=0:duration=longest,atrim=0:{D:.3f},asplit=2[sfxa][sfxb]')
        fc.append(f'[voix][mus][sfxa]amix=inputs=3:normalize=0:duration=first,atrim=0:{D:.3f},alimiter=limit=0.89:level=false,aresample=48000[a]')
    else:
        fc.append(f'[voix][mus]amix=inputs=2:normalize=0:duration=first,atrim=0:{D:.3f},alimiter=limit=0.89:level=false,aresample=48000[a]')
    fc.append('[0:v]format=yuv420p[v]')
    final = exp / f'{prj["rush"]}-{prj["style"]}-{a.version}.mp4'
    cmd = ['ffmpeg', '-v', 'error', '-y', '-nostdin'] + entrees + ['-filter_complex', ';'.join(fc), '-map', '[v]', '-map', '[a]', '-c:v', 'libx264',
                                                                   '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709',
                                                                   '-color_trc', 'bt709', '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', final]
    if noms:
        cmd += ['-map', '[sfxb]', '-c:a', 'pcm_s16le', V / 'sfx-seuls.wav']
    run(cmd)
    rapport = dict(fichier=str(final), lufs=round(lufs(['-i', final, '-vn']), 1), sfx=[])
    if noms:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', V / 'sfx-seuls.wav', '-ac', '1', '-f', 'f32le', '-'], capture_output=True).stdout
        x = np.frombuffer(raw, np.float32)
        for fr, nom, _ in sp['SFX']:
            i = int(fr / prj['fps'] * 48000); seg = x[max(0, i - 2400):i + 2400]
            rapport['sfx'].append(dict(image=fr, son=nom, db=round(float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)), 1)))
    ecrire(V / 'son.json', rapport)
    print(f'Rendu : {final}  ({rapport["lufs"]} LUFS, {len(rapport["sfx"])} bruitages)')


# ------------------------------------------------------------------ contrôler
def controler(a):
    import controle
    P, prj = projet(a.projet)
    sys.exit(controle.controler(P, prj, version_dir(P, a.version), vu=a.vu))


# ------------------------------------------------------------------ déposer dans l'Atelier de relecture
def api(chemin, data=None, methode=None):
    req = urllib.request.Request(ATELIER + chemin, data=None if data is None else json.dumps(data).encode(),
                                 headers={'Content-Type': 'application/json', 'Origin': ATELIER}, method=methode or ('POST' if data is not None else 'GET'))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b'{}')


def deposer(a):
    P, prj = projet(a.projet)
    V = version_dir(P, a.version)
    final = V / 'export' / f'{prj["rush"]}-{prj["style"]}-{a.version}.mp4'
    ctl = V / 'controle' / 'controle.json'
    if not ctl.exists():
        sys.exit('Pas de contrôle pour cette version : lancer « controler » d’abord.')
    c = lire(ctl)
    if c['bloquants']:
        sys.exit(f'Dépôt refusé : {len(c["bloquants"])} défaut(s) bloquant(s) dans {ctl}.')
    if c.get('sha') != sha(final):
        sys.exit('Dépôt refusé : le fichier a changé depuis le contrôle. Relancer « controler ».')
    if not c.get('planche_vue'):
        sys.exit(f'Dépôt refusé : la planche {V / "controle/planche.png"} n’a pas été regardée. La regarder, puis lancer « controler --vu ».')
    try:
        jobs = api('/api/jobs').get('jobs', [])
    except OSError:
        sys.exit(f'L’Atelier de relecture ne répond pas sur {ATELIER} : le lancer (skill outils-montage-video), puis relancer « deposer ».')
    if any(j['state'] in ('queued', 'running') for j in jobs):
        print('Note : l’Atelier a des tâches en cours, le dépôt s’ajoute à la file.')
    if a.projet_atelier:
        pid = a.projet_atelier
    else:
        dossiers = api('/api/folders')
        dossiers = dossiers.get('folders', dossiers) if isinstance(dossiers, dict) else dossiers
        fid = next((d['id'] for d in dossiers if d['name'] == a.dossier), None) or api('/api/folders', {'name': a.dossier})['id']
        nom = a.nom or f'{prj["rush"]} - Style classique {a.version.upper()}'
        pid = api('/api/projects', {'name': nom, 'folder_id': fid})['id']
        api(f'/api/projects/{pid}/sources', {'path': str(final)})
    api(f'/api/projects/{pid}/versions', {'path': str(final)})
    p = api(f'/api/projects/{pid}')
    v = [x for x in p['versions'] if x['id'] == p.get('active_version')] or p['versions'][-1:]
    ok = sha(v[0]['path']) == sha(final)
    print(f'{"DÉPOSÉE" if ok else "PAS DÉPOSÉE"} : projet {pid}, version active {v[0]["path"]}')
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('decouper'); p.add_argument('--projet', required=True); p.add_argument('--rush', required=True)
    p.add_argument('--source', required=True); p.add_argument('--garder', help='plages gardées en secondes : 3.2-41,55-80 (les bonnes prises)')
    p.add_argument('--blanc', type=float, default=.35, help='un silence plus long que ça (s) est coupé')
    p.add_argument('--seuil', type=float, default=-35, help='niveau sous lequel le son compte comme silence (dB)')
    p.add_argument('--langue', default='fr')
    p = sp.add_parser('preparer'); p.add_argument('--projet', required=True); p.add_argument('--rush', required=True)
    p.add_argument('--style', choices=['classique'], required=True); p.add_argument('--source'); p.add_argument('--lut')
    p = sp.add_parser('mesurer'); p.add_argument('--projet', required=True); p.add_argument('--plages', required=True)
    p.add_argument('--pas', type=int, default=3, help='une mesure toutes les N images (1 = chaque image)')
    for n in ('generer', 'rendre', 'controler'):
        p = sp.add_parser(n); p.add_argument('--projet', required=True); p.add_argument('--version', required=True)
        if n == 'controler':
            p.add_argument('--vu', action='store_true', help='la planche a été regardée et validée')
        if n == 'rendre':
            p.add_argument('--video-de', help='reprendre le rendu sans son d’une version déjà rendue (composition identique)')
    p = sp.add_parser('deposer'); p.add_argument('--projet', required=True); p.add_argument('--version', required=True)
    p.add_argument('--dossier', default='Style classique'); p.add_argument('--nom'); p.add_argument('--projet-atelier')
    a = ap.parse_args()
    dict(decouper=decouper, preparer=preparer, mesurer=mesurer, generer=generer, rendre=rendre, controler=controler, deposer=deposer)[a.cmd](a)


if __name__ == '__main__':
    main()

"""Chemins, outils et petites fonctions partagés par le moteur du style « classique »."""
import hashlib, html, json, os, re, shutil, subprocess, sys
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
STYLES = MOTEUR / 'styles'
ASSETS = MOTEUR / 'assets'
HOME = Path.home()
# Réglages de la personne qui monte : ~/.config/studio-montage/profil.json (modèle : profil.exemple.json du skill).
# Rien n'est obligatoire : sans LUT, sans sons et sans musique, le reel sort quand même.
PROFIL_FICHIER = Path(os.environ.get('STUDIO_MONTAGE_PROFIL', HOME / '.config/studio-montage/profil.json')).expanduser()
PROFIL = json.load(open(PROFIL_FICHIER, encoding='utf-8')) if PROFIL_FICHIER.exists() else {}


def _dossier(cle):
    v = PROFIL.get(cle)
    return Path(v).expanduser() if v else None


LUTS = _dossier('luts_dir') or HOME / '.config/studio-montage/luts'
LUT_709 = None           # source déjà en Rec.709 : aucune LUT
LUT_LOG = PROFIL.get('lut_log')   # LUT de conversion pour une caméra en Log (ex. la LUT officielle du fabricant), sinon rien
SFX_DIR = _dossier('sfx_dir') or HOME / '.config/studio-montage/sfx'
MUSIQUE_DIR = _dossier('musique_dir') or HOME / '.config/studio-montage/musiques'
MUSIQUE_DEFAUT = PROFIL.get('musique_defaut') or dict(fichier=None, debut=0)
MARQUE = PROFIL.get('marque', '')
POLICES_SYS = _dossier('polices_dir') or HOME / 'Library/Fonts'
ZT = ['Medium', 'MediumItalic', 'SemiBold', 'SemiBoldItalic', 'Bold', 'BoldItalic', 'ExtraBold']
HF = 'hyperframes@0.8.162'
ATELIER = PROFIL.get('atelier', 'http://localhost:8768')

# bruitages par nom court -> fichier dans SFX_DIR. Par défaut, le nom court EST le nom du fichier.
SFX = PROFIL.get('sfx') or {n: n for n in (
    'whoosh-doux.mp3', 'whoosh-rapide.wav', 'whoosh-court.mp3', 'whoosh-sub.mp3', 'impact-moyen.wav', 'impact-boom.mp3',
    'riser-punch.wav', 'shine.wav', 'clic.mp3', 'clic-num.wav', 'clic-souris.wav')}


def esc(s):
    return html.escape(str(s), quote=True)


def lire(p):
    return json.load(open(p, encoding='utf-8'))


def ecrire(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    json.dump(obj, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def env_node():
    e = dict(os.environ)
    e['PATH'] = f"{HOME}/.local/bin:{e.get('PATH', '')}"
    return e


def chrome():
    base = HOME / '.cache/hyperframes/chrome/chrome-headless-shell'
    for p in sorted(base.glob('*/chrome-headless-shell-mac-arm64/chrome-headless-shell')):
        return p
    sys.exit('Chrome headless introuvable : lancer une fois un rendu HyperFrames pour l’installer.')


def projet(P):
    P = Path(P).expanduser().resolve()
    if not (P / 'projet.json').exists():
        sys.exit(f'{P} n’est pas un projet préparé : lancer d’abord « montage.py preparer ».')
    return P, lire(P / 'projet.json')


def version_dir(P, v):
    if not re.fullmatch(r'v\d+', v):
        sys.exit('Version attendue sous la forme v1, v2…')
    return P / v


def copier_polices(dest, extra=()):
    """Polices OFL du moteur, plus ZT Nature si elle est installée (police sous licence, jamais copiée dans le skill).
    Sans ZT Nature, les sous-titres et les blocs passent sur Inter Tight (OFL, livrée avec le moteur)."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in ASSETS.glob('*.ttf'):
        shutil.copy2(p, dest / p.name)
    for w in ZT + list(extra):
        src = POLICES_SYS / f'ZTNature-{w}.otf'
        if src.exists():
            shutil.copy2(src, dest / src.name)
    for n in ('gsap.min.js', 'fond-bleu.png'):
        shutil.copy2(ASSETS / n, dest / n)

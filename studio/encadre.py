"""L'encadré d'accroche posé sur le montage envoyé en relecture.

Repris de deux scripts d'origine (``~/projets/medias-test/encadre.py`` et ``poser-encadre.py``,
design A validé le 14/10/2026), avec leurs règles telles quelles :

- deux étages : un bloc bleu ajusté au texte (940 px au plus, même marge en haut et sur
  les côtés), puis une étiquette blanche à texte bleu qui chevauche le bas du bloc ;
- l'ensemble centré sur la jonction 50/50 de l'image, en ZT Nature Bold ;
- visible DÈS LA PREMIÈRE IMAGE — les miniatures sont prises sur la 1re frame —, aucune animation
  d'entrée, 4 s à l'écran, fondu de sortie de 3,7 s à 4 s.

Le dessin est fait par Chrome sans interface, comme dans le script d'origine : c'est lui qui sait
équilibrer les lignes (``text-wrap:balance``) et mesurer la boîte autour du texte.

Les tailles du design sont données pour un petit côté de 1080 px ; elles sont mises à l'échelle de
la vidéo, ce qui donne le même encadré sur un rush 1080×1920 et sur un short de test 540×960.
"""
from __future__ import annotations

import html
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .media import MediaError, _font_dirs, _required_tool

# Les règles de temps de l'encadré, en secondes.
CARD_SECONDS = 4.0
FADE_SECONDS = 0.3
FADE_START = CARD_SECONDS - FADE_SECONDS

FONT_FILE = 'ZTNature-Bold.otf'
FALLBACK_FONT = Path(__file__).resolve().parent / 'polices' / 'InterTight.ttf'
# Le design a été réglé sur un short vertical de 1080 px de large : tout est exprimé par rapport à ce côté.
DESIGN_SHORT_EDGE = 1080

CHROME_CANDIDATES = (
    '/opt/google/chrome/chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
)


def _noop() -> None:
    return None


def split_hook(hook: str | None) -> tuple[str, str]:
    """L'accroche du montage se coupe sur « / » : avant l'annonce, après l'étiquette.

    L'étiquette est rendue entre parenthèses, comme dans le script d'origine. Une accroche vide,
    ou qui n'a rien avant le « / », ne donne pas d'encadré.
    """
    text = ' '.join(str(hook or '').split())
    if not text:
        return '', ''
    annonce, _, suite = text.partition('/')
    annonce = annonce.strip()
    etiquette = suite.strip().strip('()').strip()
    return annonce, f'({etiquette})' if etiquette and annonce else ''


def font_path(polices_dir: str | os.PathLike[str] | None = None) -> Path:
    """ZTNature-Bold.otf, cherché d'abord dans le dossier des Réglages, puis là où vivent les polices.

    La police est sous licence : elle n'est jamais dans le dépôt, on la lit sur la machine.
    """
    directories = []
    if polices_dir:
        directories.append(Path(polices_dir).expanduser())
    directories += _font_dirs()
    for directory in directories:
        candidate = directory / FONT_FILE
        if candidate.is_file():
            return candidate.resolve()
    # Sans ZT Nature (police sous licence), l'encadré passe sur Inter Tight, livrée avec le studio (licence OFL).
    if FALLBACK_FONT.is_file():
        return FALLBACK_FONT.resolve()
    cherche = ', '.join(str(d) for d in directories[:3])
    raise MediaError(
        f'Police {FONT_FILE} introuvable, et la police de secours {FALLBACK_FONT} manque aussi. '
        f'Copie une police dans {default_font_dir()} ou indique son dossier dans les Réglages. Cherchée dans : {cherche}.'
    )


def default_font_dir() -> Path:
    """Là où ZT Nature est attendue sur cette machine : ~/Library/Fonts sur Mac."""
    return Path.home() / ('Library/Fonts' if platform.system() == 'Darwin' else '.local/share/fonts')


def chrome_binary() -> str:
    """Chrome dessine l'encadré. STUDIO_CHROME ou CHROME passent avant les emplacements connus."""
    for name in ('STUDIO_CHROME', 'CHROME'):
        value = os.environ.get(name)
        if value and Path(value).expanduser().is_file():
            return str(Path(value).expanduser())
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    found = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    if found:
        return found
    raise MediaError('Google Chrome est introuvable : c’est lui qui dessine l’encadré d’accroche.')


def video_encoder() -> str:
    """h264_videotoolbox sur Mac quand ffmpeg le propose, libx264 partout ailleurs."""
    if platform.system() != 'Darwin':
        return 'libx264'
    ffmpeg = _required_tool('ffmpeg')
    try:
        listing = subprocess.run([ffmpeg, '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 'libx264'
    return 'h264_videotoolbox' if 'h264_videotoolbox' in listing else 'libx264'


def encoder_args(encoder: str, fps: float) -> list[str]:
    """Les réglages d'encodage de la vidéo qui porte l'encadré, par encodeur."""
    if encoder == 'h264_videotoolbox':
        return ['-c:v', 'h264_videotoolbox', '-b:v', '12M', '-pix_fmt', 'yuv420p', '-r', f'{fps:.6f}']
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', f'{fps:.6f}']


def _page(annonce: str, etiquette: str, font: Path, width: int, height: int) -> str:
    """La page du script d'origine, mise à l'échelle de la vidéo."""
    # Guillemets français insécables : jamais un « ou un » seul en bout de ligne.
    annonce = annonce.replace('« ', '« ').replace(' »', ' »')
    echelle = min(width, height) / DESIGN_SHORT_EDGE
    px = lambda value: round(value * echelle, 2)
    # L'étiquette tient toujours sur une ligne : au-delà d'environ 44 caractères, la police se réduit.
    taille = 44 if len(etiquette) <= 44 else max(34, int(44 * 44 / len(etiquette)))
    etiquette_html = f'<div class="t">{html.escape(etiquette.replace(chr(39), "’"))}</div>' if etiquette else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:ZTN;src:url("{font.as_uri()}");font-weight:700}}
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:transparent}}
.w{{position:absolute;left:0;right:0;top:{height / 2}px;transform:translateY(-50%);display:flex;flex-direction:column;align-items:center;font-family:ZTN}}
.b{{background:#2322E0;color:#fff;font-weight:700;font-size:{px(64)}px;line-height:1.08;padding:{px(22)}px {px(26)}px {px(26)}px;width:fit-content;max-width:{px(940)}px;box-sizing:border-box;
    text-align:center;text-wrap:balance;border-radius:{px(20)}px;box-shadow:0 {px(14)}px {px(40)}px rgba(0,0,0,.35)}}
.t{{margin-top:-{px(22)}px;background:#fff;color:#2322E0;font-weight:700;font-size:{px(taille)}px;white-space:nowrap;padding:{px(12)}px {px(28)}px;border-radius:{px(14)}px;box-shadow:0 {px(10)}px {px(26)}px rgba(0,0,0,.25);
    max-width:{px(960)}px;text-align:center}}
</style></head><body><div class="w"><div class="b">{html.escape(annonce.replace("'", "’"))}</div>{etiquette_html}</div><script>
const ECHELLE = {echelle};
document.fonts.ready.then(() => {{
  const b = document.querySelector('.b'), t = document.querySelector('.t');
  // Le bloc épouse ses lignes : même marge en haut et sur les côtés (text-wrap:balance ne rétrécit pas la boîte).
  const r = document.createRange(); r.selectNodeContents(b);
  const rs = [...r.getClientRects()];
  const w = Math.max(...rs.map(x => x.right)) - Math.min(...rs.map(x => x.left));
  b.style.width = Math.ceil(w + 52 * ECHELLE) + 'px';
  if (t) {{
    // L'étiquette ne dépasse jamais le bloc : on réduit sa police (40 px mini), sinon on élargit le bloc.
    let f = parseFloat(getComputedStyle(t).fontSize);
    while (t.offsetWidth > b.offsetWidth - 24 * ECHELLE && f > 40 * ECHELLE) {{ f -= 1; t.style.fontSize = f + 'px'; }}
    if (t.offsetWidth > b.offsetWidth - 24 * ECHELLE) b.style.width = (t.offsetWidth + 24 * ECHELLE) + 'px';
  }}
  document.body.dataset.pret = '1';
}});
</script></body></html>'''


def ink_fraction(png: Path, check: Callable[[], None] = _noop) -> float:
    """La part de l'image qui est peinte : un encadré vide veut dire que le dessin a raté."""
    ffmpeg = _required_tool('ffmpeg')
    result = subprocess.run([ffmpeg, '-hide_banner', '-v', 'error', '-i', str(png),
                             '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'],
                            capture_output=True, timeout=120)
    check()
    if result.returncode != 0 or not result.stdout:
        raise MediaError('L’encadré d’accroche produit est illisible.')
    alpha = result.stdout[3::4]
    return sum(1 for value in alpha if value) / max(1, len(alpha))


def render_card(annonce: str, etiquette: str, target: Path, size: tuple[int, int],
                *, polices_dir: str | None = None, check: Callable[[], None] = _noop) -> Path:
    """Le PNG transparent de l'encadré, à la définition de la vidéo."""
    width, height = int(size[0]), int(size[1])
    if width < 2 or height < 2:
        raise MediaError('Définition de vidéo invalide pour l’encadré d’accroche.')
    font = font_path(polices_dir)
    chrome = chrome_binary()
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    check()
    with tempfile.TemporaryDirectory(prefix='.encadre-', dir=target.parent) as temp_name:
        page = Path(temp_name) / 'encadre.html'
        page.write_text(_page(annonce, etiquette, font, width, height), encoding='utf-8')
        staged = Path(temp_name) / 'encadre.png'
        # Profil jetable : le Chrome de débogage du studio tourne en permanence, on n'y touche pas.
        result = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--allow-file-access-from-files',
             '--no-first-run', '--no-default-browser-check', f'--user-data-dir={Path(temp_name) / "chrome"}',
             '--default-background-color=00000000', '--virtual-time-budget=4000',
             f'--window-size={width},{height}', f'--screenshot={staged}', page.as_uri()],
            capture_output=True, timeout=120)
        check()
        if not staged.is_file() or not staged.stat().st_size:
            detail = (result.stderr or b'').decode('utf-8', 'replace').strip()[-400:]
            raise MediaError(f'Chrome n’a pas dessiné l’encadré d’accroche : {detail or "aucun diagnostic"}')
        painted = ink_fraction(staged, check)
        if painted < 0.002:
            raise MediaError('L’encadré d’accroche est vide : la police ZT Nature n’a sans doute pas été chargée.')
        os.replace(staged, target)
    return target


def overlay_spec(png: str | os.PathLike[str]) -> dict[str, Any]:
    """Ce que ``media.export_montage`` doit savoir de l'encadré : l'image, sa durée, son fondu."""
    return dict(path=str(Path(png).resolve()), seconds=CARD_SECONDS,
                fade_start=FADE_START, fade_seconds=FADE_SECONDS)


def card_for_montage(montage: dict[str, Any], out_dir: Path, size: tuple[int, int],
                     *, polices_dir: str | None = None, check: Callable[[], None] = _noop) -> Path | None:
    """L'encadré du montage, ou rien du tout quand l'accroche est vide."""
    annonce, etiquette = split_hook((montage or {}).get('hook'))
    if not annonce:
        return None
    return render_card(annonce, etiquette, Path(out_dir) / 'encadre.png', size,
                       polices_dir=polices_dir, check=check)


__all__ = ['CARD_SECONDS', 'FADE_SECONDS', 'FADE_START', 'card_for_montage', 'chrome_binary', 'default_font_dir',
           'encoder_args', 'font_path', 'ink_fraction', 'overlay_spec', 'render_card', 'split_hook', 'video_encoder']

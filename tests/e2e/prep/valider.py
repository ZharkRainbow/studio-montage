"""Fabrique un dossier de trois shorts de test, celui que le scénario « valider » enchaîne.

Les trois rushes sont découpés une fois pour toutes dans ~/projets/medias-test, en petit format
pour que l'export tienne en quelques secondes sur cette machine. Leur proxy est gardé au même
endroit : un scénario ne doit pas refabriquer trois proxys à chaque passage.
    python3 tests/e2e/prep/valider.py <dossier de données>
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio import media  # noqa: E402
from studio.store import Store, uid  # noqa: E402

RUSH = Path(os.environ.get('E2E_RUSH', Path.home() / 'projets/medias-test/P1-02-brut.mp4'))
# Sur disque, pas dans /tmp : les exports des trois shorts atterrissent à côté de ces rushes, et /tmp
# est un disque en mémoire déjà bien rempli sur cette machine.
CACHE = Path(os.environ.get('E2E_SHORTS', Path.home() / '.cache/atelier-e2e-shorts'))
# Les mots du rush, déjà transcrits une fois : les redemander à whisper coûterait une minute et demie
# par short, pour le même résultat. Chaque short reçoit la tranche de mots qui le concerne.
MOTS = Path(os.environ.get('E2E_MOTS', Path.home() / '.cache/atelier-mesures/P1-02-brut/mots.json'))
# Un short entier (une seule borne, export remuxé) et un short recoupé (deux morceaux, un ré-encodage).
SHORTS = [('Short 1 · plateau', 2.0, 8.0, None),
          ('Short 2 · plateau recoupé', 12.0, 8.0, [(0.4, 3.0), (4.2, 7.6)]),
          ('Short 3 · plateau', 22.0, 8.0, None)]


def _rush(index, start, seconds):
    """Un rush de test, coupé petit et avec des images-clés fréquentes, gardé en cache."""
    target = CACHE / 'rushes' / f'short-{index + 1}.mp4'
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.3f}',
                    '-i', str(RUSH), '-t', f'{seconds:.3f}', '-vf', 'scale=540:960',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-g', '10', '-keyint_min', '10',
                    '-sc_threshold', '0', '-c:a', 'aac', '-b:a', '128k', '-ar', '48000',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)],
                   check=True, capture_output=True, timeout=300)
    return target


def _proxy(index, source):
    """Le proxy de lecture, gardé en cache lui aussi : il ne dépend que du rush."""
    out = CACHE / 'proxys' / f'short-{index + 1}'
    kept = out / '.format'
    if kept.is_file() and kept.read_text() == media.PROXY_FORMAT:
        return next(out.glob('*.mp4'))
    shutil.rmtree(out, ignore_errors=True)
    made = media.make_proxy(source, out, lambda *_: None, lambda: None)
    kept.write_text(media.PROXY_FORMAT)
    return Path(made['path'])


def _mots(start, seconds):
    """La tranche de mots du rush qui tombe dans ce short, ramenée à zéro."""
    if not MOTS.is_file():
        return None
    mots = [m for m in json.loads(MOTS.read_text()) if m['start'] >= start and m['end'] <= start + seconds]
    return [dict(m, start=round(m['start'] - start, 3), end=round(m['end'] - start, 3)) for m in mots] or None


def main(data_dir: Path) -> None:
    if not RUSH.is_file():
        raise SystemExit(f'Rush de test introuvable : {RUSH}')
    # Les exports des passages précédents partent : « 1 / 3 validés » doit se lire sur un dossier neuf.
    shutil.rmtree(CACHE / 'rushes' / 'Montages validés', ignore_errors=True)
    store = Store(data_dir)
    folder = store.create_folder('Trois shorts de test')
    for index, (name, start, seconds, segments) in enumerate(SHORTS):
        rush = _rush(index, start, seconds)
        source = dict(media.probe(rush), id=uid(), path=str(rush), name=rush.name, offset=0)
        proxy = _proxy(index, source)
        project = store.create(name)

        mots = _mots(start, seconds)

        def prepare(p, source=source, proxy=proxy, segments=segments, mots=mots):
            duration = float(source['duration'])
            p.update(sources=[source], proxy_path=str(proxy), proxy_format=media.PROXY_FORMAT,
                     folder_id=folder['id'])
            p['montage'] = dict(segments=[dict(start=a, end=b) for a, b in (segments or [(0.0, duration)])],
                                silence_backup=None, title='', hook='')
            if mots:
                p['source_transcript'] = mots
                p['source_transcript_state'] = 'ready'
        store.mutate(project['id'], prepare)
    print(folder['id'])


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())

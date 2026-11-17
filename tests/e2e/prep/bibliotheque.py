"""Pose le projet à trois versions que le scénario « bibliotheque » lit sur une carte.

Le scénario vérifie le badge de version active, la liste des versions et l'ouverture d'une version
depuis la carte. Il lui faut donc un projet rangé dans un dossier, avec trois versions datées et
trois fichiers lisibles : trois mires de une seconde, fabriquées ici, suffisent.
    python3 tests/e2e/prep/bibliotheque.py <dossier de données>
"""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio import media  # noqa: E402
from studio.store import Store  # noqa: E402

VERSIONS = [('v1', 'V1', '2026-10-18T09:12:00+00:00'),
            ('v2', 'V2', '2026-10-20T16:40:00+00:00'),
            ('v3', 'V3', '2026-10-22T11:05:00+00:00')]


def _mire(target: Path) -> Path:
    """Une mire de une seconde au format d'un short : aucun rush, aucune personne réelle."""
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'testsrc2=size=540x960:rate=25', '-t', '1', '-pix_fmt', 'yuv420p',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-movflags', '+faststart', str(target)],
                   check=True, capture_output=True, timeout=120)
    return target


def main(data_dir: Path) -> None:
    store = Store(data_dir)
    folder = store.create_folder('Dossier de test')
    project = store.create('Projet à trois versions')
    rendus = data_dir / 'projects' / project['id'] / 'rendus'
    versions = []
    for index, (ident, label, date) in enumerate(VERSIONS):
        mire = _mire(rendus / f'{ident}.mp4')
        # La durée sert à la Relecture, et son absence ferait échouer la transcription à l'ouverture.
        versions.append(dict(id=ident, index=index + 1, created_at=date, label=label, path=str(mire),
                             duration=float(media.probe(mire)['duration']), transcript_state='failed'))

    def prepare(p):
        p.update(versions=versions, active_version='v3', folder_id=folder['id'])
    store.mutate(project['id'], prepare)
    print(project['id'])


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())

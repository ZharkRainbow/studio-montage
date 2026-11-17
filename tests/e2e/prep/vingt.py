"""Sonde du tour 1 : un dossier de vingt projets, pour les actions de dossier et le CSV."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio.store import Store  # noqa: E402

NOMS = ['Podcast épisode {}', 'Masterclass partie {}', 'Table ronde {}', 'Atelier démonstration {}']


def main(data):
    store = Store(Path(data).resolve())
    folder = store.create_folder('Série de vingt')
    for i in range(20):
        p = store.create(NOMS[i % 4].format(i + 1))
        p['sources'] = [dict(id='s1', path=f'/local/rush-{i}.mp4', duration=60.0 + i, width=1080, height=1920)]
        p['folder_id'] = folder['id']
        if i % 3 == 0:
            p['versions'] = [dict(id='v1', index=1, label='V1', path=f'/local/v{i}.mp4', duration=30.0,
                                  created_at='2026-10-22T10:00:00Z', transcript_state='failed')]
            p['active_version'] = 'v1'
        if i % 5 == 0:
            p['validated_at'] = '2026-10-22T12:00:00Z'
            p['export'] = dict(path=f'/local/exports/reel-{i}.mp4', state='done')
        store.save(p['id'], p, internal=True)
    print(folder['id'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))

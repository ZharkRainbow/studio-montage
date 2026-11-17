"""Jeu de donnees du parcours final : un dossier, huit projets, un fichier vraiment deplace."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio.store import Store


def main(root):
    store = Store(root)
    folder = store.create_folder('Clients, semaine 43')
    before = root / 'avant'
    after = root / 'apres'
    before.mkdir()
    after.mkdir()
    for name, content in [('rush.mp4', b'rush'), ('v1.mp4', b'version'), ('final.mp4', b'export')]:
        (before / name).write_bytes(content)
    noms = ['01 Rush range ailleurs', '02 Accroche prospection', '03 Entretien, partie 1',
            '04 Entretien, partie 2', '05 Temoignage', '06 Coulisses', '07 Annonce', '08 Rappel']
    for index, nom in enumerate(noms):
        p = store.create(nom)
        p['folder_id'] = folder['id']
        if index == 0:
            p['sources'] = [{'id': 'source1', 'path': str(before / 'rush.mp4'), 'duration': 12.0}]
            p['versions'] = [{'id': 'version1', 'index': 1, 'path': str(before / 'v1.mp4'),
                              'created_at': '2026-10-22T12:00:00Z', 'duration': 12.0}]
            p['active_version'] = 'version1'
            p['export'] = {'path': str(before / 'final.mp4'), 'state': 'done'}
        store.save(p['id'], p, internal=True)
    for file in before.iterdir():
        file.rename(after / file.name)
    print(f'Dossier {folder["id"]} : huit projets ; trois fichiers deplaces pour de vrai.')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())

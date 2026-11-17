"""Pose le dossier de trois projets que le scénario « dossier » lit.

Le scénario ouvre un dossier depuis le menu, puis demande le point d'avancement et l'export
CSV de sa liste : il lui faut un dossier et exactement trois projets rangés dedans, avec des
états différents pour que les colonnes du CSV ne soient pas vides. Aucun média n'est
nécessaire : ces deux lectures ne regardent que les fiches déjà enregistrées.
    python3 tests/e2e/prep/dossier.py <dossier de données>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio.store import Store  # noqa: E402

DOSSIER = 'Clients octobre'


def main(data):
    store = Store(Path(data).resolve())
    folder = store.create_folder(DOSSIER)
    # Un validé avec son fichier final, un en relecture, un à monter : les cinq colonnes du CSV
    # (Nom, Durée, Version, Fichier final, Statut) portent chacune une vraie valeur.
    valide = store.create('Masterclass partie 3')
    valide['sources'] = [dict(id='s1', path='/local/masterclass.mp4', duration=94.0, width=1080, height=1920)]
    valide['montage'] = dict(valide['montage'], title='Masterclass partie 3')
    valide['versions'] = [dict(id='v1', index=1, label='V1', path='/local/masterclass-v1.mp4', duration=61.0,
                               created_at='2026-10-20T09:00:00Z', transcript_state='failed'),
                          dict(id='v2', index=2, label='V2', path='/local/masterclass-v2.mp4', duration=58.0,
                               created_at='2026-10-21T18:30:00Z', transcript_state='failed')]
    valide['active_version'] = 'v2'
    valide['validated_at'] = '2026-10-22T08:15:00Z'
    valide['export'] = dict(path='/local/exports/masterclass-partie-3.mp4', state='done')
    valide['folder_id'] = folder['id']

    relecture = store.create('Podcast épisode 12')
    relecture['sources'] = [dict(id='s1', path='/local/podcast.mp4', duration=132.0, width=1080, height=1920)]
    relecture['versions'] = [dict(id='v1', index=1, label='V1', path='/local/podcast-v1.mp4', duration=47.0,
                                  created_at='2026-10-22T11:05:00Z', transcript_state='failed')]
    relecture['active_version'] = 'v1'
    relecture['folder_id'] = folder['id']

    a_monter = store.create('Table ronde des régies')
    a_monter['sources'] = [dict(id='s1', path='/local/table-ronde.mp4', duration=210.0, width=1080, height=1920)]
    a_monter['folder_id'] = folder['id']

    for projet in (valide, relecture, a_monter):
        store.save(projet['id'], projet, internal=True)
    print(folder['id'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))

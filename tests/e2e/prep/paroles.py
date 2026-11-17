"""Deux projets qui ont des paroles, pour éprouver la recherche de la palette.

Les transcripts sont écrits à la main, mot par mot, comme whisper les rend. Aucun média
n'est nécessaire : la recherche ne lit que le texte déjà enregistré.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio.store import Store  # noqa: E402

PHRASES = {
    'Entretien client': "on a changé de méthode l an dernier et le budget a suivi tout seul",
    'Atelier canapé': "le canapé arrive jeudi et le budget du tournage est déjà bouclé",
}


def cues(phrase, depart=0.0):
    return [dict(id=f'c{i}', start=round(depart + i * 0.5, 3), end=round(depart + i * 0.5 + 0.4, 3), text=mot)
            for i, mot in enumerate(phrase.split())]


# Une version déposée parle aussi : la recherche doit dire laquelle des deux pistes répond.
VERSION = "la lumière du soir change tout sur ce canapé"


def main(data):
    store = Store(data)
    for nom, phrase in PHRASES.items():
        p = store.create(nom)
        p['sources'] = [dict(id='s1', path='/local/rush.mp4', duration=120.0, width=1080, height=1920)]
        p['source_transcript'] = cues(phrase)
        p['source_transcript_state'] = 'ready'
        if nom == 'Atelier canapé':
            p['versions'] = [dict(id='v1', index=1, path='/local/v1.mp4', duration=30.0,
                                  created_at='2026-10-21T10:00:00Z', transcript=cues(VERSION),
                                  transcript_state='ready')]
            p['active_version'] = 'v1'
        store.save(p['id'], p, internal=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))

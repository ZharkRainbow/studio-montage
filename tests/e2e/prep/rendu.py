"""Un projet prêt à partir en relecture, pour que la suite fasse un vrai rendu.

Le rush de test fait une minute : l'encoder en entier prendrait la machine, qui porte
d'autres sessions. On en taille donc six secondes, re-encodées une fois ici, et c'est ce
clip que la relecture rend pour de vrai. Le but du parcours est de prouver la chaîne
complète et son bandeau, pas d'éprouver la vitesse de FFmpeg.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from studio import media  # noqa: E402
from studio.store import Store, default_montage, uid  # noqa: E402

SOURCE = Path.home() / 'projets/medias-test/P1-02-brut.mp4'
SECONDES = 6


def main(root):
    if not SOURCE.is_file():
        print(f'Rush de test absent : {SOURCE}')
        return 2
    rush = root / 'media' / 'rush-court.mp4'
    rush.parent.mkdir(parents=True, exist_ok=True)
    taille = subprocess.run(
        ['nice', '-n', '10', 'ffmpeg', '-y', '-v', 'error', '-i', str(SOURCE),
         '-t', str(SECONDES), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
         '-c:a', 'aac', '-b:a', '96k', str(rush)],
        capture_output=True, text=True)
    if taille.returncode or not rush.is_file():
        print('Découpe du clip impossible :', taille.stderr[:400])
        return 2

    store = Store(root)
    p = store.create('Rendu de bout en bout')
    source = dict(media.probe(rush), id=uid(), path=str(rush), name=rush.name, offset=0)
    p['sources'] = [source]
    p['montage'] = default_montage(source)
    # On coupe un morceau au milieu : le rendu doit assembler deux segments, pas recopier.
    fin = float(source['duration'])
    p['montage']['segments'] = [dict(start=0.0, end=round(fin / 3, 3)),
                                dict(start=round(2 * fin / 3, 3), end=round(fin, 3))]
    p['montage']['hook'] = 'Le studio rend pour de vrai'
    p['proxy_path'] = str(rush)
    p['proxy_format'] = media.PROXY_FORMAT
    store.save(p['id'], p, internal=True)
    print('Projet de rendu réel :', p['id'], '· clip', rush)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve()))

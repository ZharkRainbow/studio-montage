"""Prépare, une fois par changement, la copie du projet de référence que les scénarios rejouent.

Sans elle, chaque scénario refabriquerait le proxy 720p et attendrait sa tâche. La copie repart aussi
d'un montage intact — segments d'origine, ni titre, ni accroche, ni retour — pour qu'un scénario ne
dépende jamais de ce que le précédent a laissé.
    python3 tests/e2e/seed.py <projet de référence> <dossier de la copie>   → affiche le projet copié
"""
from pathlib import Path
import hashlib
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from studio import media  # noqa: E402
from studio.store import Store  # noqa: E402

STAMP = 2  # À incrémenter quand la remise à zéro ci-dessous change.


def _reset(project: dict) -> None:
    source = (project.get("sources") or [{}])[0]
    duration = float(source.get("duration") or 0)
    project["montage"] = dict(segments=[dict(start=0.0, end=duration)] if duration else [],
                              silence_backup=None, title="", hook="")


def main(reference: Path, seed_root: Path) -> Path:
    stamp = hashlib.sha1((reference / "project.json").read_bytes()
                         + f'{media.PROXY_FORMAT}:{STAMP}'.encode()).hexdigest()
    target = seed_root / "projects" / reference.name
    marker = seed_root / ".stamp"
    if marker.is_file() and marker.read_text() == stamp and target.is_dir():
        return target
    shutil.rmtree(seed_root, ignore_errors=True)
    target.parent.mkdir(parents=True)
    shutil.copytree(reference, target, copy_function=shutil.copy2)
    shutil.rmtree(target / "retours", ignore_errors=True)
    store = Store(seed_root)
    project = store.get(reference.name)
    if project["sources"] and project.get("proxy_format") != media.PROXY_FORMAT:
        result = media.make_proxy(project["sources"][0], target / "artifacts" / "e2e-proxy", lambda *_: None, lambda: None)
        store.mutate(project["id"], lambda p: p.update(proxy_path=str(result["path"]), proxy_format=media.PROXY_FORMAT))
    store.mutate(project["id"], _reset)
    marker.write_text(stamp)
    return target


if __name__ == "__main__":
    print(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))

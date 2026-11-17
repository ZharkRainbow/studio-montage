"""Native macOS file picker that reopens in the last folder the user chose, per kind of media."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import threading
from typing import Any

from .store import atomic_json

KINDS = {
    "video": {"types": ('"public.movie"',), "prompt": "Choisir un rush vidéo"},
}
FOLDER_NAMES = {"Downloads": "Téléchargements", "Desktop": "Bureau", "Movies": "Vidéos", "Music": "Musique", "Documents": "Documents"}


class PickerUnavailable(ValueError):
    pass


_lock = threading.RLock()


def memory_path(root: Path) -> Path:
    return Path(root) / "dossiers-recents.json"


def _read(root: Path) -> dict[str, Any]:
    """The last folder chosen per kind of media. A missing or broken file simply means no memory."""
    try:
        data = json.loads(memory_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def default_directory(root: Path, kind: str) -> Path:
    remembered = _read(root).get(kind)
    if remembered and Path(remembered).is_dir():
        return Path(remembered)
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def remember(root: Path, kind: str, chosen: Path) -> None:
    with _lock:
        data = _read(root)
        data[kind] = str(Path(chosen).parent)
        atomic_json(memory_path(root), data)


def folder_label(directory: Path) -> str:
    directory, home = Path(directory).resolve(), Path.home().resolve()
    if directory == home:
        return "Dossier personnel"
    if directory.parent == home and directory.name in FOLDER_NAMES:
        return FOLDER_NAMES[directory.name]
    if directory.is_relative_to(home):
        parts = directory.relative_to(home).parts
        first = FOLDER_NAMES.get(parts[0], parts[0])
        return " › ".join([first, *parts[1:]][-2:])
    return directory.name or str(directory)


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_script(kind: str, directory: Path) -> list[str]:
    spec = KINDS[kind]
    choose = (
        f"POSIX path of (choose file with prompt {_applescript_string(spec['prompt'])} "
        f"of type {{{', '.join(spec['types'])}}} "
        f"default location (POSIX file {_applescript_string(str(directory))} as alias))"
    )
    # "activate" brings the picker in front of the browser instead of behind it.
    return ["osascript", "-e", "activate", "-e", choose]


def describe(root: Path, kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError("Type de média inconnu.")
    directory = default_directory(root, kind)
    return {"available": platform.system() == "Darwin", "directory": str(directory), "label": folder_label(directory)}


def pick(root: Path, kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError("Type de média inconnu.")
    if platform.system() != "Darwin":
        raise PickerUnavailable("Le Finder n’est disponible que sur macOS. Colle le chemin du fichier.")
    directory = default_directory(root, kind)
    result = subprocess.run(build_script(kind, directory), capture_output=True, text=True, timeout=900)
    if result.returncode:
        if "-128" in result.stderr:
            return {"cancelled": True, **describe(root, kind)}
        raise PickerUnavailable("Le sélecteur du Finder n’a pas pu s’ouvrir. Colle le chemin du fichier.")
    chosen = Path(result.stdout.strip()).resolve()
    if not chosen.is_file():
        raise FileNotFoundError("Fichier introuvable.")
    remember(root, kind, chosen)
    return {"path": str(chosen), "name": chosen.name, **describe(root, kind)}

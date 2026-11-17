"""What a machine needs to run the Atelier: checked live, then turned into copy-paste instructions."""
from __future__ import annotations

from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from . import media, speech

ROOT = Path(__file__).resolve().parent.parent
WHISPER_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
WHISPER_MODEL_BYTES = 1_624_555_275
HOMEBREW_INSTALL = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
BRAND_FONTS = ("ZTNature-MediumItalic.otf", "ZTNature-Bold.otf")


def _git(*args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def repository() -> dict[str, str]:
    url = _git("remote", "get-url", "origin")
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.removeprefix("git@github.com:")
    return {"url": url or "https://github.com/ZharkRainbow/studio-montage.git",
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "main"}


def _tool(name: str, env: str | None, detail_flag: str | None) -> dict[str, Any]:
    path = media._tool(name, env)
    if not path and name == "brew":
        # A server started from Finder may not inherit the shell PATH that exposes Homebrew.
        path = next((str(p) for p in (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew")) if p.is_file()), None)
    detail = ""
    if path and detail_flag:
        try:
            result = subprocess.run([path, detail_flag], capture_output=True, text=True, timeout=8)
            detail = ((result.stdout or result.stderr).strip().splitlines() or [""])[0][:120]
        except (OSError, subprocess.TimeoutExpired):
            detail = ""
    return {"available": bool(path), "path": path, "detail": detail}


def _fonts_folder(data_dir: Path | str | None = None) -> Path:
    """Le dossier des polices : celui des Réglages s'il est renseigné, sinon celui de la machine."""
    if data_dir:
        from . import reglages
        configured = reglages.load(data_dir).get("polices_dir")
        if configured:
            return Path(configured).expanduser()
    return Path.home() / ("Library/Fonts" if platform.system() == "Darwin" else ".local/share/fonts")


def _chrome() -> dict[str, Any]:
    from . import encadre
    try:
        path = encadre.chrome_binary()
    except media.MediaError:
        return {"available": False, "path": "", "detail": "absent"}
    return {"available": True, "path": path, "detail": Path(path).name}


def requirements(data_dir: Path | str | None = None) -> list[dict[str, Any]]:
    folder = _fonts_folder(data_dir)
    fonts = {Path(font).name for font in media._installed_fonts()}
    fonts |= {font.name for font in folder.glob("*.otf")} if folder.is_dir() else set()
    model = speech._whisper_model()
    model_ok = model.is_file() and model.stat().st_size > 100_000_000
    ffmpeg, ffprobe = _tool("ffmpeg", None, "-version"), _tool("ffprobe", None, "-version")
    items = [
        {"id": "python", "label": "Python 3.10 ou plus", "group": "Base", "required": True,
         "why": "Fait tourner le serveur local du studio, sans aucune dépendance pip.",
         "available": sys.version_info >= (3, 10), "path": sys.executable,
         "detail": f"Python {platform.python_version()}", "install": "brew install python"},
        {"id": "ffmpeg", "label": "FFmpeg et FFprobe", "group": "Médias", "required": True,
         "why": "Proxy 720p, forme d’onde, détection des blancs et vignettes.",
         "available": ffmpeg["available"] and ffprobe["available"], "path": ffmpeg["path"], "detail": ffmpeg["detail"],
         "install": "brew install ffmpeg"},
        {"id": "whisper", "label": "whisper.cpp", "group": "Transcription", "required": True,
         "why": "Transcrit mot à mot la version relue, entièrement en local.",
         **_tool("whisper-cli", "WHISPER_CLI", None), "install": "brew install whisper-cpp"},
        {"id": "whisper-model", "label": "Modèle Whisper", "group": "Transcription", "required": True,
         "why": "Le modèle de reconnaissance vocale utilisé par whisper.cpp.",
         "available": model_ok, "path": str(model),
         "detail": f"{model.name} ({model.stat().st_size / 1_000_000:.0f} Mo)" if model.is_file() else "absent",
         "install": f"mkdir -p ~/.cache/whisper-cpp && curl -L --fail -o {model} {WHISPER_MODEL_URL}"},
        {"id": "fonts", "label": "Polices ZT Nature (facultatif)", "group": "Marque", "required": False,
         "why": "Facultatif : sans elle, l’interface et l’encadré d’accroche passent sur Inter Tight, livrée avec le studio.",
         "available": all(font in fonts for font in BRAND_FONTS), "path": str(folder),
         "detail": ", ".join(f"{font} {'OK' if font in fonts else 'absente'}" for font in BRAND_FONTS),
         "install": f"mkdir -p {folder}   # puis y copier les fichiers ZTNature-*.otf du kit de marque"},
        {"id": "chrome", "label": "Google Chrome", "group": "Marque", "required": True,
         "why": "Dessine l’encadré d’accroche : lui seul équilibre les lignes du bloc bleu.",
         **_chrome(), "install": "brew install --cask google-chrome"},
    ]
    if platform.system() == "Darwin":
        items.insert(0, {"id": "homebrew", "label": "Homebrew", "group": "Base", "required": True,
                         "why": "Le gestionnaire de paquets macOS qui installe les outils ci-dessous.",
                         **_tool("brew", None, "--version"), "install": HOMEBREW_INSTALL})
    return items


def install_script(repo: dict[str, str]) -> str:
    return f"""#!/bin/zsh
# Atelier · Studio de montage — installation sur macOS
set -e

if ! command -v brew >/dev/null 2>&1; then
  {HOMEBREW_INSTALL}
fi
[ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"

brew install python ffmpeg whisper-cpp
brew install --cask google-chrome   # dessine l’encadré d’accroche

mkdir -p ~/.cache/whisper-cpp
if [ ! -s ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin ]; then
  curl -L --fail -o ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin {WHISPER_MODEL_URL}
fi

if [ ! -d ~/Documents/studio-montage ]; then
  git clone {repo['url']} ~/Documents/studio-montage
fi
cd ~/Documents/studio-montage
git checkout {repo['branch']}

echo ""
echo "Dernière étape manuelle : copier les polices ZTNature-*.otf dans ~/Library/Fonts"
python3 -m studio doctor
echo "Lancement : python3 -m studio --open"
"""


def install_prompt(repo: dict[str, str]) -> str:
    return f"""Installe l’Atelier (studio de montage), un studio de montage et de relecture qui tourne en local, sur ce Mac. Avance étape par étape et vérifie chaque installation avant de passer à la suivante.

1. Homebrew : s’il est absent, installe-le avec la commande officielle ({HOMEBREW_INSTALL}), puis charge-le dans le shell.
2. Outils : brew install python ffmpeg whisper-cpp, puis brew install --cask google-chrome (il dessine l’encadré d’accroche ; saute-le s’il est déjà installé).
3. Modèle Whisper : télécharge {WHISPER_MODEL_URL} vers ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin. Il pèse 1,6 Go ({WHISPER_MODEL_BYTES} octets) : ne le retélécharge pas s’il est déjà présent avec cette taille.
4. Code : clone {repo['url']} dans ~/Documents/studio-montage et place-toi sur la branche {repo['branch']}.
5. Polices : les fichiers ZT Nature sont sous licence et ne sont pas dans le repo. Demande-moi où se trouvent les fichiers ZTNature-*.otf, puis copie-les dans ~/Library/Fonts.
6. Vérification : dans le dossier du repo, lance `python3 -m studio doctor` et montre-moi le résultat. Chaque outil doit afficher "available": true.
7. Lancement : `python3 -m studio --open`, puis ouvre http://localhost:8768.

Contraintes : pas de sudo sauf si Homebrew l’exige, ne modifie aucun fichier du repo, et arrête-toi pour me demander si une étape échoue."""


def report(data_dir: Path | str | None = None) -> dict[str, Any]:
    repo = repository()
    items = requirements(data_dir)
    required = [item for item in items if item["required"]]
    system = f"macOS {platform.mac_ver()[0]}".strip() if platform.system() == "Darwin" else f"{platform.system()} {platform.release()}"
    return {
        "requirements": items,
        "ready": sum(1 for item in required if item["available"]),
        "required": len(required),
        "repository": repo,
        "script": install_script(repo),
        "prompt": install_prompt(repo),
        "machine": {"system": system, "arch": platform.machine()},
    }

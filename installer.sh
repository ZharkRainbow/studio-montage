#!/bin/bash
# Installe le studio de montage sur un Mac (Apple Silicon conseillé) : outils, modèle de transcription,
# skills pour Claude Code. Relançable sans risque : ce qui est déjà là est gardé.
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
info() { printf '  ..   %s\n' "$1"; }
non()  { printf '  \033[31mNON\033[0m  %s\n' "$1"; MANQUE=1; }
MANQUE=0

echo "1. Outils"
if ! command -v brew >/dev/null; then
  non "Homebrew absent : l'installer depuis https://brew.sh puis relancer ce script"; exit 1
fi
for paquet in python@3.12:python3 ffmpeg:ffmpeg whisper-cpp:whisper-cli node:node imagemagick:magick yt-dlp:yt-dlp; do
  p="${paquet%%:*}"; cmd="${paquet##*:}"
  if command -v "$cmd" >/dev/null; then ok "$cmd"; else info "installation de $p"; brew install "$p" >/dev/null && ok "$cmd" || non "$cmd (brew install $p)"; fi
done
if [ -d "/Applications/Google Chrome.app" ]; then ok "Google Chrome"; else info "installation de Google Chrome"; brew install --cask google-chrome >/dev/null && ok "Google Chrome" || non "Google Chrome"; fi

echo "2. Modèle de transcription (1,6 Go, une seule fois)"
MODELE="$HOME/.cache/whisper-cpp/ggml-large-v3-turbo.bin"
if [ -s "$MODELE" ]; then ok "modèle whisper"; else
  mkdir -p "$(dirname "$MODELE")"
  curl -L --fail -C - -o "$MODELE" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin && ok "modèle whisper" || non "modèle whisper"
fi

echo "3. Python du moteur de styles"
VENV="$HOME/.venv-studio-montage"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip numpy && ok "$VENV (numpy)" || non "$VENV"

echo "4. Skills pour Claude Code"
CIBLE="$HOME/.claude/skills"; mkdir -p "$CIBLE"
for s in "$ICI"/skills/*/; do
  nom="$(basename "$s")"
  if [ -e "$CIBLE/$nom" ]; then info "$nom déjà présent, gardé tel quel"; else cp -R "$s" "$CIBLE/$nom" && ok "$nom"; fi
done
info "HyperFrames, media-use, embedded-captions (dépôt officiel de HeyGen)"
npx --yes skills add heygen-com/hyperframes -g -a claude-code -s '*' -y >/dev/null 2>&1 && ok "skills HyperFrames" || non "skills HyperFrames (npx skills add heygen-com/hyperframes -g -a claude-code)"
if [ -e "$CIBLE/analyze-editing-inspiration" ]; then info "analyze-editing-inspiration déjà présent"; else
  T="$(mktemp -d)"
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/AISTUDIOOSS/ai-studio-skills-gratuits.git "$T/src" \
    && git -C "$T/src" sparse-checkout set skills/analyze-editing-inspiration \
    && cp -R "$T/src/skills/analyze-editing-inspiration" "$CIBLE/" && ok "analyze-editing-inspiration (dépôt public d'AI Studio)" \
    || non "analyze-editing-inspiration"
fi

echo "5. Réglages"
PROFIL="$HOME/.config/studio-montage/profil.json"
mkdir -p "$HOME/.config/studio-montage/luts" "$HOME/.config/studio-montage/sfx" "$HOME/.config/studio-montage/musiques"
if [ -f "$PROFIL" ]; then ok "profil gardé : $PROFIL"; else cp "$ICI/skills/montage-styles/profil.exemple.json" "$PROFIL" && ok "profil créé : $PROFIL (à remplir)"; fi

echo "6. Vérification"
DIAG=$(cat <<'PY'
import json, sys
for c in json.load(sys.stdin).get('requirements', []):
    etat = 'OK  ' if c.get('available') else ('NON ' if c.get('required') else '--  ')
    suite = '' if c.get('available') else '  ->  ' + c.get('install', '')
    print('  ' + etat + ' ' + c.get('label', '') + suite)
PY
)
cd "$ICI" && python3 -m studio doctor | python3 -c "$DIAG"
echo
if [ "$MANQUE" = 0 ]; then
  echo "Tout est prêt. Lancer l'Atelier : double-clic sur « Ouvrir Studio.command », ou python3 -m studio --open"
  echo "Puis fermer et rouvrir Claude Code pour qu'il voie les nouveaux skills."
else
  echo "Il manque des éléments (lignes NON ci-dessus). Les installer puis relancer : bash installer.sh"
fi

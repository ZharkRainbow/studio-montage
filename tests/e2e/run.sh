#!/bin/bash
# Rejoue les scénarios navigateur sur un studio isolé : copie du projet de référence, dossier de
# données à part, port 8769. Le serveur habituel et ses données ne sont jamais touchés.
#   tests/e2e/run.sh                                   tous les scénarios
#   tests/e2e/run.sh tests/e2e/scenarios/montage.json  un seul
# Un scénario peut avoir une préparation : tests/e2e/prep/<nom>.py, appelée avec le dossier de données.
# Réglages : E2E_PROJECT (projet de référence, hors repo), E2E_PORT, E2E_OUT, E2E_SEED, CHROME.
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PORT=${E2E_PORT:-8769}
TMP=${TMPDIR:-/tmp}
PROJECT=${E2E_PROJECT:-}
OUT=${E2E_OUT:-$TMP/atelier-e2e-captures}
if [[ -z "$PROJECT" ]]; then
  echo "E2E_PROJECT n'est pas réglé : donne le dossier d'un projet préparé (source, proxy, version relue)."
  echo "Exemple : E2E_PROJECT=~/.cache/atelier-qa/projects/13a4ad5adeb845a9 tests/e2e/run.sh"
  exit 2
fi
[[ -d "$PROJECT" ]] || { echo "Projet de référence introuvable : $PROJECT"; exit 2; }
mkdir -p "$OUT"
if ! python3 -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', $PORT)) else 1)"; then
  echo "Le port $PORT est déjà occupé."; exit 2
fi
for candidate in "${CHROME:-}" /opt/google/chrome/chrome /usr/bin/google-chrome \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
  [[ -n "$candidate" && -x "$candidate" ]] && { CHROME=$candidate; break; }
done
[[ -n "${CHROME:-}" && -x "${CHROME:-}" ]] || { echo "Chrome introuvable : règle CHROME=/chemin/vers/chrome"; exit 2; }
export CHROME

# Le proxy de la copie est au format courant et son montage repart intact (voir seed.py).
SEED=${E2E_SEED:-$TMP/atelier-e2e-seed}
echo "Préparation de la copie de référence (une fois par changement)…"
PROJECT=$(cd "$ROOT" && python3 tests/e2e/seed.py "$PROJECT" "$SEED") || { echo "Copie de référence impossible."; exit 2; }

scenarios=("$@")
(( ${#scenarios[@]} )) || scenarios=("$ROOT"/tests/e2e/scenarios/*.json)
failed=0
for scenario in "${scenarios[@]}"; do
  data=$(mktemp -d "$TMP/atelier-e2e-data.XXXXXX")
  mkdir -p "$data/projects" && cp -R "$PROJECT" "$data/projects/"
  # Un scénario qui a besoin de plus d'un short pose sa préparation dans tests/e2e/prep/<nom>.py.
  prep="$ROOT/tests/e2e/prep/$(basename "$scenario" .json).py"
  if [[ -f "$prep" ]] && ! (cd "$ROOT" && python3 "$prep" "$data"); then
    echo "Préparation $prep impossible."; rm -rf "$data"; failed=1; continue
  fi
  (cd "$ROOT" && exec python3 -m studio --port "$PORT" --data-dir "$data" >"$data/server.log" 2>&1) &
  server=$!
  for _ in {1..50}; do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 0.2; done
  if ! node "$ROOT/tests/e2e/driver.mjs" "http://127.0.0.1:$PORT" "$scenario" "$OUT"; then
    failed=1
    echo "--- tâches du serveur ---"
    curl -s "http://127.0.0.1:$PORT/api/jobs" | python3 -c 'import json,sys
for j in json.load(sys.stdin).get("jobs", []): print(" ", j["type"], j["state"], (j.get("error") or "")[:400])'
    echo "--- journal serveur ---"; grep -v -E "^ |^Traceback|ConnectionResetError|BrokenPipeError|^-{5,}" "$data/server.log" | tail -20
  fi
  kill $server 2>/dev/null; wait $server 2>/dev/null
  rm -rf "$data"
done
echo "Captures : $OUT"
exit $failed

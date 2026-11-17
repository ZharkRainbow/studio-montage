#!/usr/bin/env python3
"""Verifie que le debut d'un reel rendu est celui choisi au Montage. Lecture seule.

    python3 verifier-debut.py <dossier du projet Atelier> <mp4 rendu> [--secondes 4]

La reference n'est PAS une fenetre continue sur la source : le rendu ne colle que les morceaux
gardes. On reconstruit donc l'audio attendu en collant les `morceaux_gardes` de montage.json
jusqu'a --secondes, on prend le meme nombre de secondes au debut du rendu, on transcrit les deux
(un seul appel whisper) et on compare les premiers mots.
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

MODELE = os.path.expanduser("~/.cache/whisper-cpp/ggml-large-v3-turbo.bin")


def mots(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9']+", t)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    projet, rendu = sys.argv[1], sys.argv[2]
    n = float(sys.argv[sys.argv.index("--secondes") + 1]) if "--secondes" in sys.argv else 4.0
    m = json.load(open(os.path.join(projet, "montage.json"), encoding="utf-8"))
    source, gardes = m["fichier"], m.get("morceaux_gardes") or []
    if not gardes:
        sys.exit("montage.json sans morceaux_gardes")

    # les morceaux gardes, colles, jusqu'a n secondes
    filtres, reste, k = [], n, 0
    for s in gardes:
        d = min(s["end"] - s["start"], reste)
        filtres.append(f"[0:a]atrim=start={s['start']:.3f}:end={s['start'] + d:.3f},asetpts=PTS-STARTPTS[a{k}]")
        k, reste = k + 1, reste - d
        if reste <= 0.001:
            break
    graphe = ";".join(filtres) + ";" + "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[out]"

    with tempfile.TemporaryDirectory() as td:
        attendu, entendu = os.path.join(td, "attendu.wav"), os.path.join(td, "rendu.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source, "-filter_complex", graphe, "-map", "[out]",
                        "-ar", "16000", "-ac", "1", attendu], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", rendu, "-t", str(n), "-vn", "-ar", "16000", "-ac", "1",
                        entendu], check=True)
        subprocess.run(["whisper-cli", "-m", MODELE, "-l", "fr", "-np", "-nt", "-otxt", attendu, entendu],
                       capture_output=True, text=True)
        ta = " ".join(open(attendu + ".txt", encoding="utf-8").read().split())
        tr = " ".join(open(entendu + ".txt", encoding="utf-8").read().split())

    print(f"morceaux colles : {k} (coupe dans les {n:.0f} s : {'oui' if k > 1 else 'non'})")
    print(f"attendu : {ta}")
    print(f"rendu   : {tr}")
    # whisper varie d'un mot sur deux decodages du meme son (« je n'y suis » / « j'y suis ») :
    # on compare la suite de mots, pas l'egalite stricte
    ratio = difflib.SequenceMatcher(None, mots(ta), mots(tr)).ratio()
    ok = ratio >= 0.6
    print(f"ressemblance {ratio:.2f} : " + ("OK, meme debut" if ok else
          "DIFFERENT, le rendu ne commence pas comme le montage valide"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

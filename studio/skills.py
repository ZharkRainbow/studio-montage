"""Les skills que le studio demande, lus dans `skills/` du depot.

Le studio ne lance pas les skills : il les montre et les donne. Une personne qui recupere
l'Atelier doit pouvoir les installer sans deviner ou ils vivent.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent / 'skills'
NOM = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')

# A quoi sert chaque skill dans le studio. Ecrit ici, pas devine : la description du skill
# parle a l'agent, cette phrase parle a la personne qui installe.
ROLES = {
    'montage-reels': "Appliquer les retours de la Relecture (« Copier la consigne ») et déposer la nouvelle version.",
    'hooks-shorts': "Trouver les bons passages d'une vidéo longue et écrire leurs accroches.",
    'viral-hooks': "Écrire des accroches de shorts qui retiennent dès la première seconde.",
    'classique': "Monter un reel face caméra dans le style classique.",
    'montage-styles': "Le moteur du style classique : préparer, rendre, contrôler, déposer dans l'Atelier.",
    'embedded-captions': "Incruster les sous-titres, avec leurs thèmes.",
    'media-use': "Traiter l'image et le son : LUT, étalonnage, musique.",
    'hyperframes': "Concevoir une vidéo dans HyperFrames, du storyboard au rendu.",
    'analyze-editing-inspiration': "Analyser le reel d'un concurrent et en tirer une fiche de montage.",
}


def _entete(fichier: Path) -> dict:
    """Le `name` et la `description` du SKILL.md, sans dependance YAML."""
    texte = fichier.read_text(encoding='utf-8', errors='replace')
    if not texte.startswith('---'):
        return {}
    fin = texte.find('\n---', 3)
    entete, champs, cle = texte[3:fin if fin > 0 else len(texte)], {}, None
    for ligne in entete.splitlines():
        trouve = re.match(r'^([a-z_]+):\s*(.*)$', ligne)
        if trouve:
            cle, valeur = trouve.group(1), trouve.group(2).strip()
            champs[cle] = valeur
        elif cle and ligne.startswith(' '):
            champs[cle] = f"{champs[cle]} {ligne.strip()}".strip()
    return champs


def _poids(dossier: Path) -> tuple[int, int, float]:
    fichiers = [f for f in dossier.rglob('*') if f.is_file()]
    return len(fichiers), sum(f.stat().st_size for f in fichiers), max((f.stat().st_mtime for f in fichiers), default=0)


def liste() -> list[dict]:
    if not RACINE.is_dir():
        return []
    fiches = []
    for dossier in sorted(RACINE.iterdir()):
        fichier = dossier / 'SKILL.md'
        if not dossier.is_dir() or not fichier.is_file():
            continue
        champs = _entete(fichier)
        nombre, octets, horodatage = _poids(dossier)
        fiches.append(dict(
            id=dossier.name,
            nom=champs.get('name') or dossier.name,
            role=ROLES.get(dossier.name, ''),
            description=champs.get('description', ''),
            fichiers=nombre,
            octets=octets,
            maj=datetime.fromtimestamp(horodatage, timezone.utc).isoformat(timespec='seconds'),
            # Ce que le skill demande en plus de lui-meme, lu dans son propre texte.
            dependances=sorted({outil for outil in ('ffmpeg', 'ffprobe', 'python3', 'node', 'whisper')
                                if re.search(rf'\b{outil}\b', fichier.read_text(encoding='utf-8', errors='replace'))}),
        ))
    return fiches


def archive(ident: str) -> tuple[str, bytes]:
    """Le skill en zip, fabrique a la demande. Rien n'est ecrit sur le disque."""
    if not NOM.fullmatch(ident or ''):
        raise ValueError('Identifiant de skill invalide.')
    dossier = (RACINE / ident).resolve()
    if not dossier.is_dir() or not dossier.is_relative_to(RACINE.resolve()):
        raise FileNotFoundError('Skill introuvable.')
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED) as zip_:
        for fichier in sorted(dossier.rglob('*')):
            if fichier.is_file():
                zip_.write(fichier, Path(ident) / fichier.relative_to(dossier))
    return f'{ident}.zip', tampon.getvalue()

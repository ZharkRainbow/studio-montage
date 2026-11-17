"""Les réglages de l'Atelier : un petit fichier à côté des projets, que le serveur relit à chaque fois.

Deux réglages aujourd'hui. Lancer Claude tout seul après une validation est éteint par défaut :
c'est un choix, pas une surprise. Le dossier des polices ZT Nature est vide par défaut, ce qui
veut dire « cherche-les là où les polices vivent sur cette machine ».
"""
from __future__ import annotations
import json
from pathlib import Path

from .store import atomic_json

# Chaque réglage donne sa valeur par défaut, donc son type : vrai/faux ou texte.
DEFAULTS = {'production_claude': False, 'polices_dir': ''}


def path(root) -> Path:
    return Path(root) / 'reglages.json'


def _clean(key, value):
    default = DEFAULTS[key]
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError('Ce réglage vaut vrai ou faux.')
        return value
    if not isinstance(value, str):
        raise ValueError('Ce réglage attend un texte.')
    return value.strip()


def load(root) -> dict:
    try:
        data = json.loads(path(root).read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    out = {}
    for key, default in DEFAULTS.items():
        try:
            out[key] = _clean(key, data[key])
        except (KeyError, ValueError):
            out[key] = default
    return out


def save(root, values) -> dict:
    if not isinstance(values, dict):
        raise ValueError('Réglages invalides.')
    current = load(root)
    for key, value in values.items():
        if key not in DEFAULTS:
            raise ValueError(f'Réglage inconnu : {key}.')
        current[key] = _clean(key, value)
    atomic_json(path(root), current)
    return current

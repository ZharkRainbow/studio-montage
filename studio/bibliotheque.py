"""La bibliothèque d'animations et les presets, lus dans le dépôt.

Les fiches vivent dans ``bibliotheque/animations/<id>/meta.json`` et les presets dans
``bibliotheque/presets/<id>.json``. Ce sont des fichiers du dépôt, pas des données de
l'utilisateur : on les lit, on ne les écrit jamais depuis le serveur, sauf un preset
enregistré depuis un projet, qui va lui aussi dans ce dossier.

Les aperçus (``apercu.mp4``, ``apercu.jpg``) sont servis par la même route que les
médias : chemin résolu puis jugé, jamais l'inverse.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parent.parent / 'bibliotheque'

CATEGORIES = ('Textes', 'Caméra', 'Compositions', 'Graphismes', 'Interfaces', 'Médias', 'Sous-titres')
COLLECTIONS = ('Mes styles', 'Inspirations')
NIVEAUX = ('Simple', 'Avancé')
ETATS = ('Validé', 'Prototype', 'À construire', 'Média à fournir')

# Un identifiant de la bibliothèque ne contient que des minuscules, des chiffres et des tirets :
# il sert de nom de dossier et arrive par l'URL.
IDENT = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')

# Les seuls fichiers qu'une fiche peut servir au navigateur.
APERCUS = {'apercu.mp4': 'video/mp4', 'apercu.jpg': 'image/jpeg',
           'reference.jpg': 'image/jpeg'}

# Le preset de départ tant que personne n'en a choisi un autre.
PRESET_DEPART = ''
# Le choix du preset par défaut, posé à côté des presets. Le tiret bas le met hors de la liste.
DEFAUT = '_defaut.json'
SCHEMA = 1
BLOCS = ('polices', 'couleurs', 'sous_titres', 'encadre', 'titre', 'son', 'image')
# Un preset neuf ne décide rien à la place de personne : tout est nul tant que l'utilisateur n'a pas rempli.
SQUELETTE = {'schema': SCHEMA, 'nom': '', 'description': '',
             **{bloc: {} for bloc in BLOCS}, 'animations_par_defaut': []}


class BibliothequeError(ValueError):
    pass


def _ident(value: str) -> str:
    value = str(value or '')
    if not IDENT.fullmatch(value):
        raise BibliothequeError('Identifiant de bibliothèque invalide.')
    return value


def _lire(fichier: Path) -> dict[str, Any]:
    try:
        data = json.loads(fichier.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise BibliothequeError(f'Fiche illisible : {fichier.name} ({exc}).') from exc
    if not isinstance(data, dict):
        raise BibliothequeError(f'Fiche invalide : {fichier.name}.')
    return data


def dossier_animation(ident: str, racine: Path | None = None) -> Path:
    directory = (racine or RACINE) / 'animations' / _ident(ident)
    if not (directory / 'meta.json').is_file():
        raise FileNotFoundError('Animation introuvable.')
    return directory


def animation(ident: str, racine: Path | None = None) -> dict[str, Any]:
    directory = dossier_animation(ident, racine)
    fiche = _lire(directory / 'meta.json')
    fiche['id'] = directory.name
    fiche['apercu'] = (directory / 'apercu.mp4').is_file()
    fiche['vignette'] = (directory / 'apercu.jpg').is_file()
    fiche['composition'] = (directory / 'composition' / 'index.html').is_file()
    # L'image de la source d'inspiration, quand le depot la porte. Le champ `reference`
    # reste la phrase qui dit d'ou elle vient.
    fiche['reference_image'] = (directory / 'reference.jpg').is_file()
    return fiche


def animations(racine: Path | None = None) -> list[dict[str, Any]]:
    """Toutes les fiches, triées par collection puis par nom. Une fiche cassée ne cache pas les autres."""
    directory = (racine or RACINE) / 'animations'
    if not directory.is_dir():
        return []
    fiches = []
    for enfant in sorted(directory.iterdir()):
        if not enfant.is_dir() or not IDENT.fullmatch(enfant.name):
            continue
        try:
            fiches.append(animation(enfant.name, racine))
        except (BibliothequeError, FileNotFoundError) as exc:
            fiches.append(dict(id=enfant.name, nom=enfant.name, etat='À construire',
                               categorie='Textes', collection='Mes styles', niveau='Simple',
                               description='', quand_l_utiliser='', parametres={}, duree_s=0,
                               erreur=str(exc), apercu=False, vignette=False, composition=False))
    rang = {nom: index for index, nom in enumerate(COLLECTIONS)}
    fiches.sort(key=lambda f: (rang.get(f.get('collection'), len(COLLECTIONS)), f.get('nom', '')))
    return fiches


def fichier_apercu(ident: str, nom: str, racine: Path | None = None) -> Path:
    """Le MP4 ou la vignette d'une fiche. Seuls ces deux noms sortent du dossier."""
    if nom not in APERCUS:
        raise BibliothequeError('Aperçu inconnu.')
    directory = dossier_animation(ident, racine)
    cible = (directory / nom).resolve()
    if not cible.is_relative_to(directory.resolve()) or not cible.is_file():
        raise FileNotFoundError('Aperçu indisponible.')
    return cible


def presets(racine: Path | None = None) -> list[dict[str, Any]]:
    directory = (racine or RACINE) / 'presets'
    if not directory.is_dir():
        return []
    trouves = []
    for fichier in sorted(directory.glob('*.json')):
        if not IDENT.fullmatch(fichier.stem):
            continue
        preset = _lire(fichier)
        preset['id'] = fichier.stem
        trouves.append(preset)
    trouves.sort(key=lambda p: p.get('nom', p['id']))
    return trouves


def preset(ident: str, racine: Path | None = None) -> dict[str, Any]:
    fichier = (racine or RACINE) / 'presets' / f'{_ident(ident)}.json'
    if not fichier.is_file():
        raise FileNotFoundError('Preset introuvable.')
    return dict(_lire(fichier), id=ident)


def preset_defaut(racine: Path | None = None) -> dict[str, Any] | None:
    """Le preset de départ : celui qui est marqué par défaut, sinon celui des shorts podcast."""
    for ident in (defaut_id(racine), PRESET_DEPART):
        if not ident:
            continue
        try:
            return preset(ident, racine)
        except (FileNotFoundError, BibliothequeError):
            continue
    trouves = presets(racine)
    return trouves[0] if trouves else None


def defaut_id(racine: Path | None = None) -> str | None:
    """Le preset marqué par défaut. Son nom commence par un tiret bas : il n'est pas un preset lui-même."""
    fichier = (racine or RACINE) / 'presets' / DEFAUT
    if not fichier.is_file():
        return None
    try:
        return _ident(str(json.loads(fichier.read_text(encoding='utf-8')).get('preset_id') or ''))
    except (OSError, json.JSONDecodeError, AttributeError, BibliothequeError):
        return None


def definir_defaut(ident: str, racine: Path | None = None) -> str:
    preset(ident, racine)  # un preset qui n'existe pas ne devient pas le défaut
    fichier = (racine or RACINE) / 'presets' / DEFAUT
    fichier.parent.mkdir(parents=True, exist_ok=True)
    _ecrire_json(fichier, dict(preset_id=ident))
    return ident


def _ecrire_json(fichier: Path, data: dict[str, Any]) -> None:
    """Écriture en deux temps : un fichier à moitié écrit ne remplace jamais le précédent."""
    provisoire = fichier.with_name(fichier.name + '.tmp')
    provisoire.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    provisoire.replace(fichier)


def _nouvel_ident(nom: str, racine: Path | None = None) -> str:
    """Un identifiant de fichier tiré du nom, sans jamais écraser un preset existant."""
    base = unicodedata.normalize('NFD', str(nom or '')).encode('ascii', 'ignore').decode('ascii').lower()
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-')[:48] or 'preset'
    if not base[0].isalnum():
        base = f'p{base}'
    directory = (racine or RACINE) / 'presets'
    candidat, numero = base, 2
    while (directory / f'{candidat}.json').exists():
        candidat = f'{base}-{numero}'
        numero += 1
    return _ident(candidat)


def creer_preset(nom: str, depuis: str | None = None, valeurs: dict[str, Any] | None = None,
                 racine: Path | None = None) -> dict[str, Any]:
    """Un nouveau preset, copié d'un autre ou monté de toutes pièces."""
    nom = ' '.join(str(nom or '').split())
    if not nom:
        raise BibliothequeError('Un preset a besoin d’un nom.')
    data = dict(preset(depuis, racine)) if depuis else dict(SQUELETTE)
    data.update(valeurs or {})
    ident = _nouvel_ident(nom, racine)
    data['schema'] = SCHEMA
    data['nom'] = nom
    data.pop('id', None)
    if depuis:
        data['description'] = f'Copie de {preset(depuis, racine).get("nom", depuis)}.'
    fichier = (racine or RACINE) / 'presets' / f'{ident}.json'
    fichier.parent.mkdir(parents=True, exist_ok=True)
    _ecrire_json(fichier, data)
    return dict(data, id=ident)


def modifier_preset(ident: str, bloc: str, cle: str, valeur: Any, racine: Path | None = None) -> dict[str, Any]:
    """Change une valeur, une seule. Une valeur vidée redevient nulle, pas zéro."""
    if bloc not in BLOCS:
        raise BibliothequeError('Bloc de preset inconnu.')
    if not isinstance(cle, str) or cle.startswith('_') or not cle:
        raise BibliothequeError('Clé de preset invalide.')
    data = preset(ident, racine)
    contenu = dict(data.get(bloc) or {})
    if cle not in contenu:
        raise BibliothequeError(f'« {cle} » n’existe pas dans {bloc}.')
    if valeur is not None and isinstance(contenu[cle], (int, float)) and not isinstance(contenu[cle], bool):
        try:
            valeur = float(str(valeur).replace(',', '.'))
        except ValueError:
            raise BibliothequeError(f'« {cle} » attend un nombre.') from None
        if isinstance(contenu[cle], int) and valeur.is_integer():
            valeur = int(valeur)
    contenu[cle] = valeur
    data[bloc] = contenu
    ident = data.pop('id')
    _ecrire_json((racine or RACINE) / 'presets' / f'{ident}.json', data)
    return dict(data, id=ident)


def animations_du_preset(ident: str, animation_id: str, retirer: bool = False,
                         racine: Path | None = None) -> dict[str, Any]:
    """Ajoute ou retire une animation de la liste par défaut du preset."""
    animation_id = _ident(animation_id)
    if not retirer:
        animation(animation_id, racine)  # on n'ajoute pas une animation qui n'existe pas
    data = preset(ident, racine)
    liste = [a for a in (data.get('animations_par_defaut') or []) if a != animation_id]
    if not retirer:
        liste.append(animation_id)
    data['animations_par_defaut'] = liste
    ident = data.pop('id')
    _ecrire_json((racine or RACINE) / 'presets' / f'{ident}.json', data)
    return dict(data, id=ident)


def supprimer_preset(ident: str, racine: Path | None = None) -> None:
    fichier = (racine or RACINE) / 'presets' / f'{_ident(ident)}.json'
    if not fichier.is_file():
        raise FileNotFoundError('Preset introuvable.')
    if len(presets(racine)) <= 1:
        raise BibliothequeError('Le dernier preset ne se supprime pas.')
    fichier.unlink()
    if defaut_id(racine) == ident:
        (racine or RACINE).joinpath('presets', DEFAUT).unlink(missing_ok=True)


__all__ = ['APERCUS', 'BLOCS', 'BibliothequeError', 'CATEGORIES', 'COLLECTIONS', 'DEFAUT', 'ETATS',
           'NIVEAUX', 'RACINE', 'SCHEMA', 'animation', 'animations', 'animations_du_preset', 'creer_preset',
           'defaut_id', 'definir_defaut', 'dossier_animation', 'fichier_apercu', 'modifier_preset', 'preset',
           'preset_defaut', 'presets', 'supprimer_preset']

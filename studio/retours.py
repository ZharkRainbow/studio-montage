"""Timestamped feedback on a reviewed version, and the instruction text it produces for Claude."""
from __future__ import annotations
import base64
import binascii
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .store import atomic_json, finite, montage_duration, now, reel_to_source, source_table, uid

TYPES = {'comment': 'COMMENTAIRE', 'cut': 'COUPE'}
MAX_RETOURS = 400
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MONTHS = ('janv.', 'févr.', 'mars', 'avril', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.')


class RetourError(ValueError):
    pass


def timecode(seconds):
    """00:10.50 — minutes, seconds and hundredths, as in the reference studio."""
    total = max(0.0, float(seconds))
    return f'{int(total // 60):02d}:{total % 60:05.2f}'


def short_timecode(seconds):
    """0:36 — what the feedback list shows, without hundredths."""
    total = int(max(0.0, float(seconds)))
    return f'{total // 60}:{total % 60:02d}'


def french_datetime(iso):
    try:
        moment = datetime.fromisoformat(str(iso)).astimezone()
    except (TypeError, ValueError):
        return 'date inconnue'
    return f'{moment.day} {MONTHS[moment.month - 1]} à {moment:%H:%M}'


def directory(store, project_id):
    return store.directory(project_id) / 'retours'


def path_for(store, project_id, index):
    if not isinstance(index, int) or not 1 <= index <= 50:
        raise RetourError('Numéro de version invalide.')
    return directory(store, project_id) / f'v{index}.json'


def load(store, project_id, index):
    path = path_for(store, project_id, index)
    if not path.is_file():
        return dict(version=index, retours=[], updated_at=None)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise RetourError('Fichier de retours illisible.') from None
    items = data.get('retours') if isinstance(data, dict) else None
    return dict(version=index, retours=[i for i in (items or []) if isinstance(i, dict)],
                updated_at=(data or {}).get('updated_at'))


def save(store, project_id, index, retours):
    if len(retours) > MAX_RETOURS:
        raise RetourError(f'Au plus {MAX_RETOURS} retours par version.')
    payload = dict(version=index, retours=retours, updated_at=now())
    atomic_json(path_for(store, project_id, index), payload)
    return payload


def counts(store, project_id, index):
    items = load(store, project_id, index)['retours']
    open_count = sum(1 for i in items if not i.get('resolved'))
    return dict(total=len(items), open=open_count, resolved=len(items) - open_count)


def _text(value, name, limit, required=True):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise RetourError(f'{name} : texte attendu.')
    value = value.strip()
    if required and not value:
        raise RetourError(f'{name} est obligatoire.')
    if len(value) > limit:
        raise RetourError(f'{name} dépasse {limit} caractères.')
    return value


def _store_images(store, project_id, images, existing=()):
    """A drawing or a pasted capture arrives as a data URL and lands beside the feedback."""
    if images is None:
        return list(existing)
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise RetourError(f'Au plus {MAX_IMAGES} captures par retour.')
    kept = []
    folder = directory(store, project_id) / 'images'
    for image in images:
        if isinstance(image, str) and image in existing:
            kept.append(image)
            continue
        if not isinstance(image, str) or not image.startswith('data:image/png;base64,'):
            raise RetourError('Capture invalide : PNG attendu.')
        raw = image.split(',', 1)[1]
        if len(raw) > MAX_IMAGE_BYTES * 4 // 3 + 8:
            raise RetourError('Capture trop lourde (4 Mo maximum).')
        try:
            data = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise RetourError('Capture illisible.') from None
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RetourError('Capture invalide : PNG attendu.')
        folder.mkdir(parents=True, exist_ok=True)
        name = f'{uid()}.png'
        (folder / name).write_bytes(data)
        kept.append(f'images/{name}')
    return kept


def validate_entry(store, project_id, data, duration, existing=None):
    existing = existing or {}
    kind = data.get('type', existing.get('type', 'comment'))
    if kind not in TYPES:
        raise RetourError('Type de retour inconnu.')
    start = finite(data.get('start', existing.get('start', 0)), 'Début du retour', 0, max(duration, 0.001) + 1)
    end = data.get('end', existing.get('end'))
    if end is not None:
        end = finite(end, 'Fin du retour', 0, max(duration, 0.001) + 1)
        if end <= start + 0.01:
            end = None
    entry = dict(existing)
    entry.update(
        id=existing.get('id') or uid(), type=kind, start=round(float(start), 2),
        end=None if end is None else round(float(end), 2),
        text=_text(data.get('text', existing.get('text')), 'Le retour', 2000),
        quote=_text(data.get('quote', existing.get('quote')), 'La citation', 1200, required=False),
        images=_store_images(store, project_id, data.get('images'), existing.get('images') or []),
        resolved=bool(data.get('resolved', existing.get('resolved', False))),
        created_at=existing.get('created_at') or now(), updated_at=now())
    return entry


def source_notice(project: dict[str, Any], version: dict[str, Any]) -> str | None:
    """Pourquoi cette vidéo n'a pas de temps SOURCE, quand c'est le cas. None quand tout va bien."""
    if source_table(version, project.get('montage')) is not None:
        return None
    montage = (version.get('montage') if isinstance(version.get('montage'), dict) else None) or project.get('montage') or {}
    reel, length = montage_duration(montage), float(version.get('duration') or 0)
    if not (montage.get('segments') or []):
        return ('Temps SOURCE indisponibles : aucun montage n’est enregistré pour ce projet, '
                'donc rien ne dit où retrouver ces passages dans le fichier d’origine.')
    return (f'Temps SOURCE indisponibles : les morceaux gardés durent {reel:.2f} s, la vidéo relue '
            f'{length:.2f} s. Ce montage ne décrit pas ce rendu ; les temps ci-dessous sont ceux de '
            'la vidéo relue. Dépose le rendu du montage courant pour retrouver les temps SOURCE.')


def _source(table, start, end):
    """Le bout « · SOURCE … » de la ligne : un temps, une plage, ou pourquoi il n'y en a pas."""
    if table is None:
        return 'SOURCE indisponible'
    first = reel_to_source(table, start)
    last = None if end is None else reel_to_source(table, end)
    if first is None or (end is not None and last is None):
        return 'SOURCE hors des morceaux gardés'
    return f'SOURCE {first:.2f} s' if end is None else f'SOURCE {first:.2f} s → {last:.2f} s'


def consigne(project: dict[str, Any], version: dict[str, Any], retours: list[dict[str, Any]], project_dir: Path) -> str:
    """The exact text pasted into Claude. SOURCE times come back from the cut blanks."""
    montage = project.get('montage') or {}
    table = source_table(version, montage)
    length = float(version.get('duration') or 0) or montage_duration(montage)
    lines = [
        f'/montage-reels applique ces retours au reel {project["name"]} ({project_dir})',
        '',
        f'Vidéo relue : {version.get("path")}, version du {french_datetime(version.get("added_at"))}, '
        f'durée {timecode(length)} ({length:.2f} s).',
        f'{len(retours)} changement{"s" if len(retours) > 1 else ""} à appliquer :',
        '',
    ]
    notice = source_notice(project, version)
    if notice:
        lines.insert(3, notice)
    for number, item in enumerate(retours, 1):
        label = TYPES[item.get('type', 'comment')]
        start = float(item.get('start') or 0)
        end = None if item.get('end') is None else float(item['end'])
        source = _source(table, start, end)
        if end is None:
            head = f'{number}. {label} à {timecode(start)} (REEL {start:.2f} s) · {source} [id {item["id"]}]'
        else:
            head = (f'{number}. {label} de {timecode(start)} à {timecode(end)}'
                    f' (REEL {start:.2f} s → {end:.2f} s, {end - start:.2f} s)'
                    f' · {source} [id {item["id"]}]')
        lines.append(head)
        if item.get('quote'):
            lines.append(f'   Mots : "{item["quote"]}"')
        lines.append(f'   Demande : {item.get("text", "")}')
        if item.get('images'):
            lines.append('   Captures : ' + ', '.join(str(project_dir / 'retours' / i) for i in item['images']))
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'

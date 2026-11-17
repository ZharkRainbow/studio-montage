"""Single-writer project state with optimistic revisions and atomic publication."""
from __future__ import annotations
import bisect
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import unicodedata
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = 3
# Le titre reste affiché une durée fixe, réglée dans le skill de montage. L'Atelier ne fait que la montrer.
TITLE_SECONDS = 3.5


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex[:16]


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + uid() + '.tmp')
    try:
        with tmp.open('w', encoding='utf8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Conflict(ValueError):
    pass


def finite(v, name, low=None, high=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f'{name} : nombre fini requis.')
    if low is not None and v < low or high is not None and v > high:
        raise ValueError(f'{name} hors limites ({low} à {high}).')
    return v


def default_montage(source=None):
    """Un montage neuf garde tout le fichier : il arrive déjà découpé."""
    duration = float((source or {}).get('duration') or 0) or 0.0
    segments = [dict(start=0.0, end=round(duration, 3))] if duration > 0 else []
    return dict(segments=segments, silence_backup=None, blanks=[], title='', hook='')


def montage_empreinte(montage):
    """Ce qui change l'image envoyée en relecture : les morceaux gardés et l'accroche.

    Le titre, les blancs repérés ou la sauvegarde d'avant-coupe ne touchent pas au rendu : les
    faire entrer dans l'empreinte ferait crier « ancien montage » pour rien.
    """
    montage = montage or {}
    segments = [dict(start=round(float(s['start']), 3), end=round(float(s['end']), 3))
                for s in montage.get('segments') or []]
    return dict(segments=segments, hook=(montage.get('hook') or '').strip())


def montage_hash(montage):
    """L'empreinte courte du montage : c'est elle que la relecture compare à celle de sa version."""
    return fingerprint(montage_empreinte(montage))[:16]


def montage_duration(montage):
    return round(sum(max(0.0, s['end'] - s['start']) for s in (montage or {}).get('segments') or []), 3)


def reel_to_source(montage, reel_time):
    """Le temps dans le fichier d'origine, en suivant les morceaux gardés.

    None au-delà du dernier morceau : il n'y a pas de correspondance, et en inventer une
    (la dernière image gardée) donnerait à Claude un temps SOURCE faux, sans le dire.
    """
    left = max(0.0, float(reel_time))
    segments = (montage or {}).get('segments') or []
    for segment in segments:
        length = segment['end'] - segment['start']
        if left <= length + 1e-6:
            return round(segment['start'] + left, 3)
        left -= length
    return None


# Un rendu ne décrit le même reel que si sa durée vaut celle des morceaux gardés, au chouïa près.
SOURCE_TOLERANCE = 0.5


def source_table(version, montage=None):
    """Les morceaux qui expliquent ce rendu : ceux figés à son dépôt, sinon le montage courant.

    None quand la durée du rendu ne correspond pas à celle des morceaux : la table ne décrit
    alors pas cette vidéo, et aucun temps SOURCE ne doit en sortir.
    """
    frozen = (version or {}).get('montage')
    table = frozen if isinstance(frozen, dict) and frozen.get('segments') else (montage or {})
    if not (table.get('segments') or []):
        return None
    length = float((version or {}).get('duration') or 0)
    if length and abs(length - montage_duration(table)) > SOURCE_TOLERANCE:
        return None
    return table


def source_to_reel(montage, source_time):
    total = 0.0
    for segment in (montage or {}).get('segments') or []:
        if source_time <= segment['end']:
            return round(total + max(0.0, source_time - segment['start']), 3)
        total += segment['end'] - segment['start']
    return round(total, 3)


def _validate_segments(segments, source_duration):
    if not isinstance(segments, list) or len(segments) > 200:
        raise ValueError('Le montage accepte de 0 à 200 morceaux.')
    last = -1.0
    for s in segments:
        if not isinstance(s, dict):
            raise ValueError('Morceau de montage invalide.')
        a, b = finite(s.get('start'), 'Début', 0), finite(s.get('end'), 'Fin', 0)
        if b <= a:
            raise ValueError('Bornes du montage invalides.')
        if source_duration and b > source_duration + 0.05:
            raise ValueError('Le montage dépasse la durée du fichier.')
        if a < last - 0.001:
            raise ValueError('Les morceaux du montage doivent être ordonnés et sans recouvrement.')
        last = b


def _validate_blanks(blanks, source_duration):
    """Les blancs trouvés et la décision prise sur chacun : gardé ou coupé."""
    if not isinstance(blanks, list) or len(blanks) > 400:
        raise ValueError('Le montage accepte de 0 à 400 blancs.')
    last = -1.0
    for b in blanks:
        if not isinstance(b, dict):
            raise ValueError('Blanc invalide.')
        a, z = finite(b.get('start'), 'Début du blanc', 0), finite(b.get('end'), 'Fin du blanc', 0)
        if z <= a:
            raise ValueError('Bornes de blanc invalides.')
        if source_duration and z > source_duration + 0.05:
            raise ValueError('Un blanc dépasse la durée du fichier.')
        if a < last - 0.001:
            raise ValueError('Les blancs doivent être ordonnés et sans recouvrement.')
        if not isinstance(b.get('cut', True), bool):
            raise ValueError('Décision de blanc invalide.')
        last = z


def validate_project(p):
    if p.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Version de projet non prise en charge.')
    if not isinstance(p.get('name'), str) or not p['name'].strip() or len(p['name']) > 150:
        raise ValueError('Le projet doit avoir un nom de 1 à 150 caractères.')
    sources = p.get('sources', [])
    if not isinstance(sources, list) or len(sources) > 1:
        raise ValueError('Un projet tient sur un seul fichier vidéo, déjà découpé.')
    duration = float(sources[0].get('duration') or 0) if sources else 0.0
    montage = p.get('montage')
    if not isinstance(montage, dict):
        raise ValueError('Montage absent.')
    _validate_segments(montage.get('segments', []), duration)
    if montage.get('silence_backup') is not None:
        _validate_segments(montage['silence_backup'], duration)
    _validate_blanks(montage.get('blanks') or [], duration)
    for key, limit in (('title', 150), ('hook', 300)):
        value = montage.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'Le champ « {key} » doit tenir en {limit} caractères.')
        if key == 'title' and '\n' in value:
            raise ValueError(f'Le champ « {key} » tient sur une ligne.')
        if key == 'hook' and value.count('\n') > 3:
            raise ValueError('L’accroche tient sur quatre lignes au plus.')
    if p.get('montage_hash') is not None and not isinstance(p['montage_hash'], str):
        raise ValueError('Empreinte de montage invalide.')
    cues = p.get('source_transcript')
    if cues is not None and (not isinstance(cues, list) or len(cues) > 20000):
        raise ValueError('Transcript du fichier invalide.')
    if p.get('source_transcript_state') not in (None, 'pending', 'ready', 'failed'):
        raise ValueError('État de transcript du fichier inconnu.')
    for key in ('export', 'production'):
        if p.get(key) is not None and not isinstance(p[key], dict):
            raise ValueError(f'Champ « {key} » invalide.')
    versions = p.get('versions', [])
    if not isinstance(versions, list) or len(versions) > 50:
        raise ValueError('Un projet accepte au plus 50 versions.')
    seen = set()
    for index, version in enumerate(versions, 1):
        if not isinstance(version, dict) or not isinstance(version.get('id'), str) or version['id'] in seen:
            raise ValueError('Identifiant de version absent ou dupliqué.')
        seen.add(version['id'])
        if version.get('index') != index:
            raise ValueError('Les versions sont numérotées dans l’ordre de dépôt.')
        if not isinstance(version.get('path'), str) or not version['path']:
            raise ValueError('Chemin de version invalide.')
        finite(version.get('duration', 0), 'Durée de la version', 0)
        words = version.get('transcript')
        if words is not None and (not isinstance(words, list) or len(words) > 20000):
            raise ValueError('Transcript de version invalide.')
        if version.get('transcript_state') not in (None, 'pending', 'ready', 'failed'):
            raise ValueError('État de transcript de version inconnu.')
        if not isinstance(version.get('final', False), bool):
            raise ValueError('Marque de version finale invalide.')
        frozen = version.get('montage')
        if frozen is not None:
            if not isinstance(frozen, dict):
                raise ValueError('Montage de version invalide.')
            _validate_segments(frozen.get('segments', []), duration)
        if version.get('montage_hash') is not None and not isinstance(version['montage_hash'], str):
            raise ValueError('Empreinte de montage de version invalide.')
    active = p.get('active_version')
    if active is not None and active not in seen:
        raise ValueError('Version affichée inconnue.')
    return p


def migrate(p):
    """Un projet v1/v2 garde son fichier, ses bornes, son titre et son accroche ; le reste était du cadrage."""
    if p.get('schema_version') == SCHEMA_VERSION:
        p.setdefault('versions', [])
        p.setdefault('active_version', None)
        p.setdefault('montage', default_montage((p.get('sources') or [None])[0]))
        return p
    sources = [s for s in (p.get('sources') or [])][:1]
    clip = next((c for c in p.get('clips') or [] if c.get('validated')), None) or (p.get('clips') or [None])[0] or {}
    montage = default_montage(sources[0] if sources else None)
    if clip.get('segments'):
        montage['segments'] = [dict(start=float(s['start']), end=float(s['end'])) for s in clip['segments']]
    montage['title'] = (clip.get('title') or '')[:150].replace('\n', ' ')
    montage['hook'] = (clip.get('hook') or '')[:300].replace('\n', ' ')
    kept = {k: p[k] for k in ('id', 'name', 'revision', 'created_at', 'updated_at') if k in p}
    migrated = dict(kept, schema_version=SCHEMA_VERSION, sources=sources,
                    montage=montage, versions=[], active_version=None)
    for key in ('folder_id', 'favorite', 'validated_at', 'ecarte_le', 'proxy_path', 'proxy_format', 'demo'):
        if p.get(key) is not None:
            migrated[key] = p[key]
    return migrated


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def directory(self, project_id):
        if not re.fullmatch(r'[a-f0-9]{16}', project_id):
            raise ValueError('Identifiant de projet invalide.')
        return self.root / 'projects' / project_id

    def get(self, project_id):
        with self.lock:
            path = self.directory(project_id) / 'project.json'
            if not path.exists():
                raise FileNotFoundError('Projet introuvable.')
            return migrate(json.loads(path.read_text()))

    def list(self):
        with self.lock:
            folders = {f['id'] for f in self.folders()}
            out = []
            for path in (self.root / 'projects').glob('*/project.json'):
                try:
                    out.append(summary(migrate(json.loads(path.read_text())), folders))
                except (ValueError, KeyError):
                    continue
            return sorted(out, key=lambda x: x['updated_at'], reverse=True)

    def recherche(self, requete, limite=40):
        """Les paroles dites, cherchees dans les transcripts deja la.

        Rien n'est indexe. A quelques dizaines de projets sur cette machine, relire les
        fichiers coute moins cher qu'un index a tenir a jour, et ne peut pas mentir.
        """
        requete = sans_accent(requete).strip()
        if len(requete) < 3:
            return dict(extraits=[], total=0, tronque=False)
        with self.lock:
            fichiers = sorted((self.root / 'projects').glob('*/project.json'))
        trouves, total = [], 0
        for chemin in fichiers:
            try:
                p = migrate(json.loads(chemin.read_text()))
            except (ValueError, KeyError, OSError):
                continue
            for piste, cues in _pistes(p):
                extraits = _extraits(cues, requete, 3)
                total += len(extraits)
                for extrait in extraits:
                    trouves.append(dict(extrait, project_id=p['id'], project_name=p.get('name', ''), piste=piste))
        trouves.sort(key=lambda e: (e['project_name'], e['start']))
        return dict(extraits=trouves[:limite], total=total, tronque=total > limite)

    def folders(self):
        path = self.root / 'folders.json'
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return data.get('folders', []) if isinstance(data, dict) else []

    def _write_folders(self, folders):
        atomic_json(self.root / 'folders.json', dict(folders=folders))

    def create_folder(self, name):
        with self.lock:
            name = _folder_name(name)
            folders = self.folders()
            if any(f['name'].casefold() == name.casefold() for f in folders):
                raise ValueError('Un dossier porte déjà ce nom.')
            folder = dict(id=uid(), name=name, created_at=now())
            self._write_folders(folders + [folder])
            return folder

    def rename_folder(self, folder_id, name):
        with self.lock:
            name = _folder_name(name)
            folders = self.folders()
            folder = next((f for f in folders if f['id'] == folder_id), None)
            if not folder:
                raise FileNotFoundError('Dossier introuvable.')
            if any(f['id'] != folder_id and f['name'].casefold() == name.casefold() for f in folders):
                raise ValueError('Un dossier porte déjà ce nom.')
            folder['name'] = name
            self._write_folders(folders)
            return folder

    def delete_folder(self, folder_id):
        """Deleting a folder never deletes projects: they go back to the library root."""
        with self.lock:
            folders = self.folders()
            if not any(f['id'] == folder_id for f in folders):
                raise FileNotFoundError('Dossier introuvable.')
            moved = 0
            for item in self.list():
                if item.get('folder_id') == folder_id:
                    self.mutate(item['id'], lambda p: p.update(folder_id=None))
                    moved += 1
            self._write_folders([f for f in folders if f['id'] != folder_id])
            return moved

    def move(self, project_id, folder_id):
        with self.lock:
            if folder_id is not None and not any(f['id'] == folder_id for f in self.folders()):
                raise FileNotFoundError('Dossier introuvable.')
            return self.mutate(project_id, lambda p: p.update(folder_id=folder_id))

    def set_favorite(self, project_id, favorite):
        if not isinstance(favorite, bool):
            raise ValueError('Valeur de favori invalide.')
        return self.mutate(project_id, lambda p: p.update(favorite=favorite))

    def set_ecarte(self, project_id, ecarte):
        """Ne pas garder : le projet sort de la boucle (ni relecture, ni validation) sans être supprimé.

        Le même appel avec ``False`` le remet en jeu. Une ligne part dans le journal des validations
        pour que la session Claude qui écoute l'Atelier sache qu'il ne faut rien produire.
        """
        if not isinstance(ecarte, bool):
            raise ValueError('Valeur invalide pour « Ne pas garder ».')

        def mark(p):
            if ecarte:
                p['ecarte_le'] = now()
            else:
                p.pop('ecarte_le', None)

        updated = self.mutate(project_id, mark)
        event = dict(at=now(), validated=False, ecarte=ecarte, step='ecarter', project_id=project_id,
                     name=updated.get('name'), project_dir=str(self.directory(project_id)),
                     source=((updated.get('sources') or [{}])[0]).get('path'))
        with open(self.root / 'validations.jsonl', 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + '\n')
        return updated

    def ensure_garde(self, project_id):
        if self.get(project_id).get('ecarte_le'):
            raise ValueError('Ce projet est écarté. Clique sur « Garder finalement » pour le remettre en jeu.')

    def set_validated(self, project_id, validated, step='review', version_id=None):
        """Valider un short : il passe en « Validé », et la version affichée devient la finale.

        On ne valide plus qu'en Relecture, devant la vidéo rendue. ``step`` reste dans le journal :
        les lignes écrites avant ce changement disent « montage », et on veut pouvoir les relire.
        """
        if not isinstance(validated, bool):
            raise ValueError('Valeur de validation invalide.')
        if step != 'review':
            raise ValueError('Étape de validation inconnue.')
        if validated:
            self.ensure_garde(project_id)

        def mark(p):
            p.update(validated_at=now() if validated else None)
            versions = p.get('versions') or []
            target = next((v for v in versions if v['id'] == version_id), None) if version_id else self.active_version(p)
            if version_id and target is None:
                raise FileNotFoundError('Version introuvable.')
            for v in versions:
                final = bool(validated and target and v['id'] == target['id'])
                v['final'] = final
                if final:
                    v['validated_at'] = now()
                else:
                    v.pop('validated_at', None)
            if validated:
                # La demande de production part avec le montage déjà exporté : « Envoyer en relecture »
                # l'a écrit dans « Montages validés » avant que l’utilisateur ne valide quoi que ce soit.
                exported = (p.get('export') or {}).get('path')
                p['production'] = self.write_production_request(p, exported, 'fait' if exported else 'en-attente')
            else:
                p.pop('production', None)
                (self.directory(p['id']) / 'a-produire' / (p['id'] + '.json')).unlink(missing_ok=True)

        updated = self.mutate(project_id, mark)
        # Journal lu par la session Claude qui pilote l'Atelier : une ligne par validation, rien d'autre.
        version = self.active_version(updated) if updated.get('versions') else None
        event = dict(at=now(), validated=validated, step=step, project_id=project_id, name=updated.get('name'),
                     project_dir=str(self.directory(project_id)),
                     source=((updated.get('sources') or [{}])[0]).get('path'),
                     version=(version or {}).get('path'),
                     title=(updated.get('montage') or {}).get('title', ''),
                     hook=(updated.get('montage') or {}).get('hook', ''),
                     a_produire=(updated.get('production') or {}).get('path'),
                     consigne=(updated.get('production') or {}).get('consigne'))
        with open(self.root / 'validations.jsonl', 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + '\n')
        return updated

    def production_consigne(self, project_id):
        """Ce qu'on donne à Claude pour produire le reel. Le même texte que le bouton copie."""
        return f'/montage-reels produis la V1 de {self.directory(project_id)}'

    def write_production_request(self, p, export=None, state='en-attente'):
        """La demande de production, lisible telle quelle par Claude, dans le dossier du projet."""
        source = (p.get('sources') or [None])[0] or {}
        montage = p.get('montage') or {}
        directory = self.directory(p['id'])
        path = directory / 'a-produire' / (p['id'] + '.json')
        consigne = self.production_consigne(p['id'])
        atomic_json(path, dict(
            projet=p['name'], projet_id=p['id'], dossier_projet=str(directory),
            fichier_source=source.get('path'), duree_source=source.get('duration'),
            montage_valide=str(export) if export else None, export=state,
            titre=montage.get('title', ''), accroche=montage.get('hook', ''),
            duree_titre_secondes=TITLE_SECONDS, duree_reel=montage_duration(montage),
            morceaux_gardes=montage.get('segments') or [],
            blancs_coupes=[b for b in (montage.get('blanks') or []) if b.get('cut', True)],
            valide_le=p.get('validated_at'), consigne=consigne, mis_a_jour=now()))
        return dict(path=str(path), consigne=consigne, at=now(), export=state,
                    montage_valide=str(export) if export else None)

    def create(self, name):
        with self.lock:
            p = dict(schema_version=SCHEMA_VERSION, id=uid(), name=name.strip(), revision=1, created_at=now(),
                     updated_at=now(), sources=[], montage=default_montage(), versions=[], active_version=None)
            p['montage_hash'] = montage_hash(p['montage'])
            validate_project(p)
            atomic_json(self.directory(p['id']) / 'project.json', p)
            return p

    def save(self, project_id, value, expected=None, internal=False):
        with self.lock:
            old = self.get(project_id)
            expected = value.get('revision') if expected is None else expected
            if old['revision'] != expected:
                raise Conflict('Ce projet a évolué. Recharge-le avant de sauvegarder pour conserver les changements récents.')
            p = migrate(copy.deepcopy(value))
            p.update(id=old['id'], created_at=old['created_at'], revision=old['revision'] + 1, updated_at=now())
            if not internal:
                # Le serveur fait autorité sur ce qu'il produit : l'éditeur n'enregistre que le montage.
                for key in ('sources', 'versions', 'active_version', 'proxy_path', 'proxy_format',
                            'demo', 'folder_id', 'favorite', 'validated_at', 'ecarte_le',
                            'source_transcript', 'source_transcript_state', 'export', 'production'):
                    if key in old:
                        p[key] = old[key]
                    else:
                        p.pop(key, None)
            # L'empreinte suit le montage enregistré : le navigateur ne peut pas la fabriquer.
            p['montage_hash'] = montage_hash(p.get('montage'))
            validate_project(p)
            atomic_json(self.directory(project_id) / 'project.json', p)
            self.write_montage_file(p)
            return p

    def write_montage_file(self, p):
        """Le montage, lisible tel quel par Claude, à côté du projet."""
        source = (p.get('sources') or [None])[0] or {}
        montage = p.get('montage') or {}
        atomic_json(self.directory(p['id']) / 'montage.json', dict(
            projet=p['name'], fichier=source.get('path'), duree_source=source.get('duration'),
            titre=montage.get('title', ''), accroche=montage.get('hook', ''),
            duree_titre_secondes=TITLE_SECONDS, duree_reel=montage_duration(montage),
            morceaux_gardes=montage.get('segments') or [], blancs_coupes=bool(montage.get('silence_backup')),
            blancs=montage.get('blanks') or [], mis_a_jour=p['updated_at']))

    def mutate(self, project_id, fn):
        with self.lock:
            p = self.get(project_id)
            fn(p)
            return self.save(project_id, p, internal=True)

    def rename(self, project_id, name):
        if not isinstance(name, str):
            raise ValueError('Nom de projet invalide.')
        return self.mutate(project_id, lambda p: p.update(name=name.strip()))

    def duplicate(self, project_id):
        """Copies the montage; deposited versions and their feedback stay with the original."""
        with self.lock:
            old = self.get(project_id)
            old_dir = self.directory(project_id)
            p = copy.deepcopy(old)
            p.update(id=uid(), revision=1, created_at=now(), updated_at=now(), versions=[], active_version=None)
            p['name'] = (old['name'][:140] + ' (copie)')
            for key in ('demo', 'demo_notice', 'favorite', 'validated_at', 'ecarte_le', 'export', 'production'):
                p.pop(key, None)
            new_dir = self.directory(p['id'])
            new_dir.mkdir(parents=True)
            try:
                if (old_dir / 'assets').is_dir():
                    shutil.copytree(old_dir / 'assets', new_dir / 'assets')
                proxy = p.get('proxy_path')
                if proxy and Path(proxy).is_relative_to(old_dir):
                    target = new_dir / 'assets' / ('proxy' + Path(proxy).suffix)
                    if Path(proxy).is_file():
                        target.parent.mkdir(exist_ok=True)
                        shutil.copy2(proxy, target)
                        p['proxy_path'] = str(target)
                    else:
                        p.pop('proxy_path', None)
                        p.pop('proxy_format', None)
                p = _rebase_paths(p, str(old_dir / 'assets'), str(new_dir / 'assets'))
                validate_project(p)
                atomic_json(new_dir / 'project.json', p)
                self.write_montage_file(p)
            except BaseException:
                shutil.rmtree(new_dir, ignore_errors=True)
                raise
            return p

    def trash(self, project_id):
        """Moves the project folder to the Trash, or to a studio trash folder when it is not writable."""
        with self.lock:
            p = self.get(project_id)
            source = self.directory(project_id)
            label = re.sub(r'[^\w .()-]+', '-', p['name']).strip() or 'Projet'
            for base in (Path.home() / '.Trash', self.root / 'corbeille'):
                target = base / f'Studio - {label} - {project_id}'
                n = 2
                while target.exists():
                    target = base / f'Studio - {label} - {project_id} ({n})'
                    n += 1
                try:
                    base.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                    return target
                except OSError:
                    if not source.exists():
                        raise
            raise OSError('Impossible de déplacer le projet vers la corbeille.')

    def add_version(self, project_id, path, info):
        """Un rendu déposé devient V1, V2… et prend la main dans la relecture."""
        version = dict(id=uid(), path=str(path), duration=round(float(info.get('duration') or 0), 3),
                       width=info.get('width'), height=info.get('height'), has_audio=bool(info.get('has_audio')),
                       added_at=now(), transcript=[], transcript_state='pending')

        def add(p):
            if len(p.get('versions') or []) >= 50:
                raise ValueError('Un projet accepte au plus 50 versions.')
            version['index'] = len(p['versions']) + 1
            # Le montage du jour part avec le rendu : c'est lui, et pas celui d'après, qui dit
            # à quelle seconde du fichier d'origine correspond chaque seconde de cette vidéo.
            version['montage'] = montage_empreinte(p.get('montage'))
            # L'empreinte gelée ici répond à une seule question en relecture : est-ce encore le
            # montage d'aujourd'hui ? Si elle diffère, la vidéo montrée date d'avant la retouche.
            version['montage_hash'] = montage_hash(p.get('montage'))
            p['versions'].append(version)
            p['active_version'] = version['id']
        p = self.mutate(project_id, add)
        return p, next(v for v in p['versions'] if v['id'] == version['id'])

    def set_active_version(self, project_id, version_id):
        def choose(p):
            if not any(v['id'] == version_id for v in p.get('versions') or []):
                raise FileNotFoundError('Version introuvable.')
            p['active_version'] = version_id
        return self.mutate(project_id, choose)

    def active_version(self, p):
        versions = p.get('versions') or []
        return next((v for v in versions if v['id'] == p.get('active_version')), versions[-1] if versions else None)

    def repointer(self, project_id, chemin):
        """Rend sa source a un projet dont le fichier a bouge.

        L’utilisateur range ses dossiers, le projet perd son rush et la relecture affiche du noir
        (arrive le 21/10/2026). Il redonne le nouveau chemin, et tout ce qui vivait dans
        l'ancien dossier suit : la source, les versions deposees, l'export.

        Le fichier est verifie avant d'etre ecrit : un chemin qui n'existe pas est refuse.
        """
        if not isinstance(chemin, str) or not chemin.strip():
            raise ValueError('Donner le nouveau chemin du fichier.')
        nouveau = Path(chemin.strip()).expanduser()
        if not nouveau.is_file():
            raise FileNotFoundError(f'Aucun fichier a cet endroit : {nouveau}')
        nouveau = nouveau.resolve()

        def repointe(p):
            sources = p.get('sources') or []
            if not sources:
                raise FileNotFoundError('Ce projet n’a pas de source a repointer.')
            ancien = Path(sources[0].get('path') or '')
            sources[0]['path'] = str(nouveau)
            if not ancien.name:
                return
            ancien_dossier, nouveau_dossier = ancien.parent, nouveau.parent
            if ancien_dossier == nouveau_dossier:
                return

            def suivre(valeur):
                """Un chemin de l'ancien dossier, et lui seul, repart du nouveau."""
                if not valeur:
                    return valeur
                chemin = Path(valeur)
                if chemin.is_file() or chemin.parent != ancien_dossier:
                    return valeur
                candidat = nouveau_dossier / chemin.name
                return str(candidat) if candidat.is_file() else valeur

            for version in p.get('versions') or []:
                version['path'] = suivre(version.get('path'))
            for cle in ('export', 'production'):
                bloc = p.get(cle)
                if isinstance(bloc, dict) and bloc.get('path'):
                    bloc['path'] = suivre(bloc['path'])
            if p.get('proxy_path'):
                p['proxy_path'] = suivre(p['proxy_path'])

        return self.mutate(project_id, repointe)

    def remove_source(self, project_id):
        def remove(p):
            if not p['sources']:
                raise FileNotFoundError('Aucun fichier à retirer.')
            p['sources'] = []
            p['montage'] = default_montage()
            p.pop('proxy_path', None)
            p.pop('proxy_format', None)
        return self.mutate(project_id, remove)


def sans_accent(valeur):
    """La meme normalisation que `normalizeText` cote navigateur : NFD, accents retires, minuscules."""
    plie = unicodedata.normalize('NFD', str(valeur or ''))
    return ''.join(c for c in plie if not unicodedata.combining(c)).lower()


def _pistes(p):
    """Ce qui porte des paroles dans un projet : le rush, puis chaque version deposee."""
    if p.get('source_transcript'):
        yield 'le rush', p['source_transcript']
    for version in p.get('versions') or []:
        if version.get('transcript'):
            yield version.get('label') or f"V{version.get('index')}", version['transcript']


def _extraits(cues, requete, limite):
    """Les passages d'une piste qui contiennent la requete, avec de quoi les relire.

    Whisper rend un mot par repere. On recolle donc la piste en une phrase unique pour
    chercher dedans, en gardant ou commence chaque mot : une requete de trois mots se
    retrouve meme si elle enjambe trois reperes.
    """
    mots = [c for c in cues if isinstance(c, dict) and isinstance(c.get('text'), str)]
    plein, bornes = '', []
    for cue in mots:
        if plein:
            plein += ' '
        bornes.append(len(plein))
        plein += sans_accent(cue['text'])
    extraits, depart, dernier = [], 0, -99
    while len(extraits) < limite:
        at = plein.find(requete, depart)
        if at < 0:
            break
        depart = at + max(1, len(requete))
        index = max(0, bisect.bisect_right(bornes, at) - 1)
        # Deux occurrences dans la meme phrase ne font qu'un extrait : on ne repete pas la citation.
        if index - dernier < 8:
            continue
        dernier = index
        autour = mots[max(0, index - 6):index + 10]
        extraits.append(dict(start=round(float(mots[index].get('start') or 0), 3),
                             texte=' '.join(c['text'].strip() for c in autour if c['text'].strip())))
    return extraits


def summary(p, folders=None):
    source = (p.get('sources') or [None])[0] or {}
    folder_id = p.get('folder_id')
    if folders is not None and folder_id not in folders:
        folder_id = None
    montage = p.get('montage') or {}
    versions = p.get('versions') or []
    trimmed = bool(montage.get('silence_backup')) or bool(montage.get('title'))
    if p.get('ecarte_le'):
        status = 'ecarte'
    elif p.get('validated_at'):
        status = 'done'
    elif versions:
        status = 'review'
    elif trimmed:
        status = 'montage'
    elif p.get('sources'):
        status = 'imported'
    else:
        status = 'empty'
    return {k: p[k] for k in ('id', 'name', 'revision', 'created_at', 'updated_at')} | dict(
        status=status, duration=source.get('duration'), reel_duration=montage_duration(montage),
        version_count=len(versions), title=montage.get('title', ''), trimmed=trimmed,
        has_media=bool(p.get('proxy_path') or source.get('path')), folder_id=folder_id,
        media_missing=bool(source.get('path')) and not Path(source['path']).is_file(),
        media_path=source.get('path'),
        favorite=bool(p.get('favorite')), validated_at=p.get('validated_at'), ecarte_le=p.get('ecarte_le'),
        demo=bool(p.get('demo')),
        export_path=(p.get('export') or {}).get('path'), export_state=(p.get('export') or {}).get('state'),
        width=source.get('width'), height=source.get('height'),
        active_version=p.get('active_version'),
        # Le menu d'entrée déplie les versions sans ouvrir le projet : index, date et rien d'autre.
        versions=[dict(id=v.get('id'), index=v.get('index'), created_at=v.get('created_at'),
                       label=v.get('label') or f"V{v.get('index')}")
                  for v in versions])


def _folder_name(name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        raise ValueError('Le nom du dossier doit faire de 1 à 60 caractères.')
    return name.strip()


def _rebase_paths(value, old_prefix, new_prefix):
    if isinstance(value, dict):
        return {k: _rebase_paths(v, old_prefix, new_prefix) for k, v in value.items()}
    if isinstance(value, list):
        return [_rebase_paths(v, old_prefix, new_prefix) for v in value]
    if isinstance(value, str) and (value == old_prefix or value.startswith(old_prefix + os.sep)):
        return new_prefix + value[len(old_prefix):]
    return value

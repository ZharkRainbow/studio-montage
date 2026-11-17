"""Persistent single-worker queue. Processes remain local and inputs are snapshots."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import queue
import shutil
import threading
import time
from . import reglages
from .store import atomic_json, now, uid

KINDS = ('proxy', 'transcript', 'words', 'relecture')
# La production par Claude tourne hors file : un export ne doit pas attendre qu'elle finisse.
ASIDE = ('production',)


class Cancelled(Exception):
    pass


def _same_sources(a, b):
    key = lambda sources: [(s.get('id'), s.get('path'), s.get('duration')) for s in sources or []]
    return key(a) == key(b)


class Jobs:
    def __init__(self, store):
        self.store = store
        self.root = store.root / 'jobs'
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.queue = queue.Queue()
        self.records = {}
        self.cancelled = set()
        for path in self.root.glob('*.json'):
            try:
                j = json.loads(path.read_text())
                if j['state'] in ('queued','running'):
                    j.update(state='failed', error='Application arrêtée pendant le traitement. Relancez : les caches de transcription seront réutilisés.', updated_at=now())
                    atomic_json(path,j)
                self.records[j['id']] = j
            except (ValueError,KeyError):
                pass
        threading.Thread(target=self.worker, daemon=True, name='studio-media-worker').start()

    def persist(self, j):
        j['updated_at'] = now()
        atomic_json(self.root/(j['id']+'.json'), j)

    def get(self, jid):
        with self.lock:
            if jid not in self.records:
                raise FileNotFoundError('Traitement introuvable.')
            return copy.deepcopy(self.records[jid])

    def list(self, pid=None):
        with self.lock:
            return [copy.deepcopy(j) for j in sorted(self.records.values(),key=lambda x:x['created_at'], reverse=True) if not pid or j['project_id']==pid][:100]

    def submit(self, pid, request):
        kind = request.get('type')
        if kind not in KINDS:
            raise ValueError('Type de traitement inconnu.')
        p = self.store.get(pid)
        if kind == 'relecture':
            self.store.ensure_garde(pid)
        if kind in ('proxy', 'words', 'relecture') and not p['sources']:
            raise ValueError('Importer une vidéo avant de lancer ce traitement.')
        if kind == 'relecture' and not ((p.get('montage') or {}).get('segments') or []):
            raise ValueError('Le montage ne garde aucun morceau : rien à envoyer en relecture.')
        vid = request.get('version_id')
        if kind == 'transcript':
            version = next((v for v in p['versions'] if v['id'] == vid), None) if vid else self.store.active_version(p)
            if not version:
                raise ValueError('Déposer une version rendue avant de la transcrire.')
            vid = version['id']
        with self.lock:
            for j in self.records.values():
                if j['project_id']==pid and j.get('version_id')==vid and j['type']==kind and j['state'] in ('running','queued') and j['id'] not in self.cancelled:
                    return copy.deepcopy(j)
            j = dict(id=uid(),project_id=pid,version_id=vid,type=kind,state='queued',progress=0,message='En attente',created_at=now(),updated_at=now(),result={},error=None,revision=p['revision'],auto=bool(request.get('auto')))
            self.records[j['id']] = j
            self.persist(j)
            self.queue.put((j['id'],p,request|dict(version_id=vid)))
            return copy.deepcopy(j)

    def cancel(self, jid):
        with self.lock:
            j = self.records.get(jid)
            if not j:
                raise FileNotFoundError('Traitement introuvable.')
            if j['state'] in ('queued','running'):
                self.cancelled.add(jid)
                j['message'] = 'Annulation demandée'
                self.persist(j)
            return copy.deepcopy(j)

    def cancel_kinds(self, pid, kinds, message='Remplacé : les sources ont changé'):
        """Stop work made obsolete by a newer request; its results would be refused anyway."""
        with self.lock:
            for j in self.records.values():
                if j['project_id']==pid and j['type'] in kinds and j['state'] in ('queued','running') and j['id'] not in self.cancelled:
                    self.cancelled.add(j['id'])
                    j['message'] = message
                    self.persist(j)

    def prepare(self, pid):
        """Queue the local preparation a project still lacks: proxy first, then the transcript of the version under review."""
        current = self.store.get(pid)
        if current['sources'] and (not current.get('proxy_path') or self._proxy_outdated(current)):
            return self.submit(pid, {'type': 'proxy', 'auto': True})
        if current['sources'] and not current.get('source_transcript') and current.get('source_transcript_state') != 'failed':
            if any(s.get('has_audio', True) for s in current['sources']):
                return self.submit(pid, {'type': 'words', 'auto': True})
        version = self.store.active_version(current)
        if version and not version.get('transcript') and version.get('transcript_state') != 'failed':
            return self.submit(pid, {'type': 'transcript', 'version_id': version['id'], 'auto': True})
        return None

    def _proxy_outdated(self, project):
        """A proxy made by an older pipeline is rebuilt once; the old file stays on screen meanwhile."""
        from .media import PROXY_FORMAT
        if project.get('demo') or project.get('proxy_format') == PROXY_FORMAT:
            return False
        if not all(Path(source.get('path', '')).is_file() for source in project['sources']):
            return False
        with self.lock:
            proxies = sorted((j for j in self.records.values() if j['project_id'] == project['id'] and j['type'] == 'proxy'), key=lambda j: j['created_at'])
        # An automatic rebuild that already failed is not retried on every opening.
        return not (proxies and proxies[-1]['state'] == 'failed' and proxies[-1].get('auto'))

    def worker(self):
        while True:
            jid,p,req = self.queue.get()
            try:
                self.run(jid,p,req)
            finally:
                self.queue.task_done()

    def run(self, jid, p, req):
        from . import media, speech
        def check():
            if jid in self.cancelled:
                raise Cancelled('Traitement annulé. Aucun résultat de ce travail n’a été publié.')
        stamp = [0]
        def progress(n, msg):
            check()
            with self.lock:
                j = self.records[jid]
                j.update(progress=max(0,min(99,round(n,1))),message=str(msg))
                if time.monotonic()-stamp[0] > .5:
                    self.persist(j)
                    stamp[0] = time.monotonic()
        j = self.records[jid]
        directory = self.store.directory(p['id'])
        out = directory/'artifacts'/jid
        out.mkdir(parents=True,exist_ok=True)
        atomic_json(out/'input.json',p)
        def url(path):
            return '/api/artifacts/'+p['id']+'/'+Path(path).resolve().relative_to(directory.resolve()).as_posix()
        try:
            check()
            with self.lock:
                j.update(state='running',message='Préparation du traitement')
                self.persist(j)
            kind = req['type']
            if kind == 'proxy':
                made = media.make_proxy(p['sources'][0],out,progress,check)
                check()
                def save_proxy(current):
                    if not _same_sources(current['sources'], p['sources']):
                        raise ValueError('Le fichier du projet a changé pendant le traitement. Relancer sur la nouvelle version.')
                    current['proxy_path'] = str(made['path'])
                    current['proxy_format'] = media.PROXY_FORMAT
                self.store.mutate(p['id'], save_proxy)
                result = dict(path=str(made['path']),url=url(made['path']))
            elif kind == 'words':
                source = p['sources'][0]
                cues = speech.transcribe_media(Path(source['path']), float(source['duration'] or 0),
                                               directory/'cache'/'transcription', progress, check, words=True)
                check()
                def save_source_words(current):
                    if not _same_sources(current['sources'], p['sources']):
                        raise ValueError('Le fichier du projet a changé pendant la transcription. Relancer sur le nouveau fichier.')
                    current['source_transcript'] = cues
                    current['source_transcript_state'] = 'ready'
                self.store.mutate(p['id'], save_source_words)
                result = dict(words=len(cues))
            elif kind == 'relecture':
                result = self._relecture(p, out, progress, check)
            else:
                version = next(v for v in p['versions'] if v['id'] == req['version_id'])
                cues = speech.transcribe_media(Path(version['path']), float(version['duration']),
                                               directory/'cache'/'transcription', progress, check, words=True)
                check()
                def save_words(current):
                    target = next((v for v in current['versions'] if v['id'] == version['id']), None)
                    if target is None:
                        raise ValueError('La version relue a été retirée pendant la transcription.')
                    target['transcript'] = cues
                    target['transcript_state'] = 'ready'
                self.store.mutate(p['id'], save_words)
                result = dict(version_id=version['id'], words=len(cues))
            with self.lock:
                j.update(state='succeeded',progress=100,message='Terminé et vérifié',result=result)
                self.persist(j)
            if kind in ('proxy', 'words', 'relecture'):
                # La version qui vient d'arriver se fait transcrire : la relecture a ses mots tout de suite.
                try:
                    self.prepare(p['id'])
                except (FileNotFoundError, ValueError):
                    pass
        except Exception as exc:
            if req['type'] == 'transcript' and not isinstance(exc, Cancelled):
                self._mark_failed_transcript(p['id'], req.get('version_id'))
            if req['type'] == 'words' and not isinstance(exc, Cancelled):
                self._mark_failed_words(p['id'])
            with self.lock:
                j.update(state='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc),message=str(exc))
                self.persist(j)

    def _relecture(self, p, out, progress, check):
        """Envoyer en relecture : l'export du montage, l'encadré d'accroche posé dessus, puis la version.

        Tout se fait ici, dans la file locale, avec la progression visible : pas de session Claude,
        et le short n'est pas validé pour autant.
        """
        from . import encadre, media
        montage = p.get('montage') or {}
        source = p['sources'][0]
        info = media.probe(source['path'])
        progress(2, 'Lecture du rush')
        overlay, encoder = None, None
        annonce, _ = encadre.split_hook(montage.get('hook'))
        if annonce:
            progress(3, 'Dessin de l’encadré d’accroche')
            carte = encadre.card_for_montage(montage, out, (info['width'], info['height']),
                                             polices_dir=reglages.load(self.store.root).get('polices_dir'),
                                             check=check)
            overlay = encadre.overlay_spec(carte)
            encoder = encadre.encoder_args(encadre.video_encoder(), info.get('rate') or info['fps'] or 25.0)
        target = self._export_dir(p) / (media.export_name(p['name']) + '.mp4')
        made = media.export_montage(source['path'], montage.get('segments') or [], target, progress, check,
                                    overlay=overlay, encoder=encoder)
        check()
        # Le MP4 qui part en relecture est celui qui vit dans « Montages validés » : un seul fichier,
        # celui qu'on publiera, et c'est lui qu'on relit.
        rendu = media.probe(made['path'])

        def save_export(current):
            current['export'] = dict(path=made['path'], at=now(), seconds=made['expected'],
                                     remux=made['remux'], bytes=made['bytes'],
                                     encadre=made['encadre'], state='fait')
        # Écarté pendant l'export : le MP4 reste dans « Montages validés », mais aucune version n'est déposée.
        self.store.ensure_garde(p['id'])
        self.store.mutate(p['id'], save_export)
        _, version = self.store.add_version(p['id'], made['path'], rendu)
        progress(99, 'Version déposée en relecture')
        return dict(path=made['path'], remux=made['remux'], seconds=made['expected'], bytes=made['bytes'],
                    encadre=made['encadre'], version_id=version['id'], version_index=version['index'])

    def _export_dir(self, p):
        """« Montages validés », à côté du rush. Si le dossier n'est pas accessible, dans le projet."""
        source = Path(p['sources'][0].get('path', '')).expanduser()
        for base in (source.parent / 'Montages validés', self.store.directory(p['id']) / 'montages-valides'):
            try:
                base.mkdir(parents=True, exist_ok=True)
                probe = base / '.ecriture'
                probe.write_text('', encoding='utf-8')
                probe.unlink()
                return base
            except OSError:
                continue
        raise ValueError('Impossible d’écrire le dossier « Montages validés ».')

    def start_production(self, pid, auto=False):
        """Claude produit la V1 en tâche de fond, hors file, avec son journal lisible dans les tâches."""
        p = self.store.get(pid)
        request = (p.get('production') or {}).get('path')
        if not request or not Path(request).is_file():
            raise ValueError('Aucune demande de production : valider le short d’abord.')
        if not shutil.which('claude'):
            raise ValueError('La commande « claude » est introuvable sur cette machine.')
        with self.lock:
            for j in self.records.values():
                if j['project_id'] == pid and j['type'] == 'production' and j['state'] in ('running', 'queued') and j['id'] not in self.cancelled:
                    return copy.deepcopy(j)
            j = dict(id=uid(), project_id=pid, version_id=None, type='production', state='running', progress=3,
                     message='Claude produit la V1', created_at=now(), updated_at=now(), result={}, error=None,
                     revision=p['revision'], auto=bool(auto))
            self.records[j['id']] = j
            self.persist(j)
        threading.Thread(target=self._produce, args=(j['id'], p), daemon=True, name='studio-production').start()
        return copy.deepcopy(j)

    def _produce(self, jid, p):
        from . import proc
        directory = self.store.directory(p['id'])
        out = directory / 'artifacts' / jid
        out.mkdir(parents=True, exist_ok=True)
        log = out / 'production.log'
        consigne = self.store.production_consigne(p['id'])
        cwd = Path(p['sources'][0].get('path', '')).expanduser().parent
        log.write_text(f'$ claude -p "{consigne}"\n(dans {cwd})\n', encoding='utf-8')
        seen = [0]

        def check():
            if jid in self.cancelled:
                raise Cancelled('Production annulée. Le journal s’arrête ici.')

        def on_line(line):
            seen[0] += 1
            with log.open('a', encoding='utf-8') as fh:
                fh.write(line + '\n')
            with self.lock:
                j = self.records[jid]
                j.update(progress=min(95, 3 + seen[0]), message=line[:160])
                self.persist(j)
        try:
            proc.stream([shutil.which('claude'), '-p', consigne], check, on_line,
                        error=RuntimeError, label='La production par Claude', process_group=True,
                        cwd=cwd if cwd.is_dir() else None)
            with self.lock:
                j = self.records[jid]
                j.update(state='succeeded', progress=100, message='Production terminée',
                         result=dict(log=str(log), lines=seen[0]))
                self.persist(j)
        except Exception as exc:
            with log.open('a', encoding='utf-8') as fh:
                fh.write(str(exc) + '\n')
            with self.lock:
                j = self.records[jid]
                j.update(state='cancelled' if isinstance(exc, Cancelled) else 'failed',
                         error=str(exc), message=str(exc)[:160], result=dict(log=str(log), lines=seen[0]))
                self.persist(j)

    def _mark_failed_words(self, pid):
        """Une transcription du fichier qui échoue est retenue : pas de whisper en boucle à chaque ouverture."""
        def mark(p):
            if not p.get('source_transcript'):
                p['source_transcript_state'] = 'failed'
        try:
            self.store.mutate(pid, mark)
        except (FileNotFoundError, ValueError):
            pass

    def _mark_failed_transcript(self, pid, version_id):
        """A failed transcript is remembered, so opening the project again does not relaunch whisper in a loop."""
        def mark(p):
            target = next((v for v in p.get('versions') or [] if v['id'] == version_id), None)
            if target is not None and not target.get('transcript'):
                target['transcript_state'] = 'failed'
        try:
            self.store.mutate(pid, mark)
        except (FileNotFoundError, ValueError):
            pass

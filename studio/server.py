"""Loopback-only HTTP application; no media upload and no remote file serving."""
from __future__ import annotations
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import parse_qs, unquote, urlsplit
from . import __version__
from . import retours as retours_module
from .store import Store, Conflict, default_montage, uid
from .jobs import Jobs

STATIC = Path(__file__).parent/'static'


def create_demo(store):
    """Explicit synthetic fixture. Never presented as Claude output or a real rush."""
    from .media import probe
    for item in store.list():
        if item.get('demo'):
            return store.get(item['id'])
    p = store.create('Mon premier montage · démo')
    directory = store.directory(p['id'])/'assets'
    directory.mkdir(parents=True,exist_ok=True)
    video = directory/'demo.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=720x1280:rate=25',
                    '-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','18','-af','volume=0.15',
                    '-c:v','libx264','-preset','ultrafast','-crf','26','-g','10','-keyint_min','10','-sc_threshold','0',
                    '-c:a','aac','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True,capture_output=True,timeout=120)
    source = dict(probe(video),id=uid(),path=str(video),name='Mire vidéo de démonstration',offset=0)
    p.update(demo=True,sources=[source],proxy_path=str(video),montage=default_montage(source))
    p['montage'].update(title='Un bon montage commence par une idée claire',hook='Montre la mire, explique, conclus.')
    p['demo_notice'] = 'Mire et son synthétiques, fabriqués sur cette machine. Aucun contenu réel, aucune analyse Claude.'
    return store.save(p['id'],p,internal=True)


def project_thumbnail(store,pid):
    """One still per media version, cached in the project folder.

    Ordre : la miniature du projet (champ `miniature`,
    une image, la couverture du reel), sinon la version active (ce que l'Atelier relit), sinon le proxy ou la source."""
    p=store.get(pid)
    active=[v.get('path') for v in p.get('versions',[]) if v.get('id')==p.get('active_version')]
    candidates=[p.get('miniature')]+active+[p.get('proxy_path')]+[s.get('path') for s in p.get('sources',[])[:1]]
    media=next((Path(c) for c in candidates if c and Path(c).is_file()),None)
    if not media:raise FileNotFoundError('Aucune image disponible pour ce projet.')
    stat=media.stat()
    key=hashlib.sha1(f'{media}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()[:16]
    target=store.directory(pid)/'thumbs'/f'{key}.jpg'
    if target.is_file():return target
    target.parent.mkdir(parents=True,exist_ok=True)
    image=media.suffix.lower() in ('.jpg','.jpeg','.png','.webp')
    duration=next((s.get('duration') for s in p.get('sources',[]) if s.get('duration')),0) or 0
    at=0 if image else (min(max(duration*0.2,0),30) if duration else 1)
    tmp=target.with_name(f'.{key}.{os.getpid()}.jpg')
    for offset in ((None,) if image else (at,0)):   # une image fixe : pas de -ss (ffmpeg n'en sortirait aucune image)
        seek=[] if offset is None else ['-ss',f'{offset:.2f}']
        result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',*seek,'-i',str(media),'-frames:v','1','-vf','scale=640:-2','-q:v','4',str(tmp)],capture_output=True,timeout=40)
        if result.returncode==0 and tmp.is_file() and tmp.stat().st_size:
            os.replace(tmp,target)
            for old in target.parent.glob('*.jpg'):
                if old!=target:old.unlink(missing_ok=True)
            return target
    tmp.unlink(missing_ok=True)
    raise FileNotFoundError('Vignette impossible à extraire.')


def brand_font(name):
    """ZT Nature is licensed, so it is read from the machine's installed fonts, never shipped in the repo."""
    from .media import _font_dirs
    if not re.fullmatch(r'[\w .-]+\.(?:otf|ttf)',name):
        raise FileNotFoundError('Police introuvable.')
    for directory in _font_dirs():
        candidate=directory/name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError('Police non installée sur cette machine.')


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,data_dir):
        self.store=Store(data_dir)
        self.jobs=Jobs(self.store)
        super().__init__(address,Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='AtelierStudio'

    def log_message(self,fmt,*args):
        if len(args)>1 and str(args[1]).startswith('5'):
            super().log_message(fmt,*args)

    def handle_one_request(self):
        # The browser drops kept-alive connections whenever it seeks a video: that is normal, not a server error.
        try:
            super().handle_one_request()
        except (BrokenPipeError,ConnectionResetError):
            self.close_connection=True

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        super().end_headers()

    def json(self,value,status=200):
        payload=json.dumps(value,ensure_ascii=False,allow_nan=False,default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(payload)

    def text(self,value,status=200):
        payload=str(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','text/plain; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(payload)

    def body(self):
        if not self.headers.get('Content-Type','').startswith('application/json'):
            raise ValueError('Content-Type application/json requis.')
        length=int(self.headers.get('Content-Length',0))
        if length<0 or length>16*1024*1024:
            raise ValueError('Requête trop volumineuse (16 Mo maximum).')
        self._body_read=True
        d=json.loads(self.rfile.read(length) or b'{}',parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nombre JSON invalide')))
        if not isinstance(d,dict):raise ValueError('Objet JSON requis.')
        return d

    def origin_ok(self):
        port=self.server.server_port
        hosts={f'localhost:{port}',f'127.0.0.1:{port}'}
        if self.headers.get('Host') not in hosts:
            return False
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://{h}' for h in hosts}:
            return False
        return self.headers.get('Sec-Fetch-Site') not in ('cross-site','same-site')

    def do_HEAD(self):self.dispatch()
    def do_GET(self):self.dispatch()
    def do_POST(self):self.dispatch()
    def do_PUT(self):self.dispatch()
    def do_DELETE(self):self.dispatch()

    def ensure_idle(self,pid):
        if any(j['state'] in ('queued','running') for j in self.server.jobs.list(pid)):
            raise ValueError('Une tâche tourne encore sur ce projet. Attendez la fin ou annulez-la depuis l’historique des tâches.')

    def dispatch(self):
        self._body_read=False
        try:
            self.route()
        finally:
            self.drain_body()

    def drain_body(self):
        # Keep-alive connection: a body a route never read would be parsed as the start of the next request.
        if self._body_read:return
        try:length=int(self.headers.get('Content-Length',0) or 0)
        except ValueError:length=0
        if 0<length<=16*1024*1024:
            try:self.rfile.read(length)
            except OSError:self.close_connection=True
        elif length:self.close_connection=True

    def route(self):
        try:
            if not self.origin_ok():
                return self.json({'error':'Accès réservé à cette application locale.'},403)
            u=urlsplit(self.path); path=unquote(u.path); query=parse_qs(u.query)
            method='GET' if self.command=='HEAD' else self.command
            if path.startswith('/api/'):
                return self.api(method,path,query)
            if method!='GET':return self.json({'error':'Méthode non permise.'},405)
            if path.startswith('/fonts/'):
                return self.file(brand_font(path.removeprefix('/fonts/')))
            relative = path.removeprefix('/static/') if path.startswith('/static/') else path.lstrip('/')
            asset=(STATIC/('index.html' if path=='/' else relative)).resolve()
            if not asset.is_relative_to(STATIC.resolve()):raise FileNotFoundError('Fichier introuvable.')
            return self.file(asset)
        except Conflict as exc:self.json({'error':str(exc)},409)
        except FileNotFoundError as exc:self.json({'error':str(exc)},404)
        except (ValueError,KeyError,TypeError) as exc:self.json({'error':str(exc)},400)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.json({'error':str(exc)},500)

    def api(self,method,path,q):
        from . import media, reglages, speech
        store=self.server.store
        bits=path.strip('/').split('/')
        if method=='GET' and path=='/api/health':return self.json(dict(ok=True,version=__version__))
        if method=='GET' and path=='/api/setup':
            from . import setup
            return self.json(setup.report(store.root)|dict(data_dir=str(store.root)))
        if method=='GET' and path=='/api/diagnostics':
            return self.json(media.diagnostics() | dict(speech=speech.status(),data_dir=str(store.root)))
        if method=='GET' and path=='/api/fonts':
            from .media import _font_dirs
            return self.json(dict(fonts=sorted(path.name for directory in _font_dirs() for path in directory.glob('*') if path.is_file() and re.fullmatch(r'[\w .-]+\.(?:otf|ttf)',path.name))))
        if path=='/api/projects':
            if method=='GET':return self.json(dict(projects=store.list(),folders=store.folders()))
            if method=='POST':
                data=self.body();created=store.create(data.get('name','Nouveau projet'))
                if data.get('folder_id'):created=store.move(created['id'],data['folder_id'])
                return self.json(created,201)
        if path=='/api/folders':
            if method=='GET':return self.json(dict(folders=store.folders()))
            if method=='POST':return self.json(store.create_folder(self.body().get('name')),201)
        if len(bits)>=3 and bits[1]=='folders':
            if len(bits)==3 and method=='DELETE':return self.json(dict(ok=True,moved=store.delete_folder(bits[2])))
            if len(bits)==4 and bits[3]=='rename' and method=='POST':return self.json(store.rename_folder(bits[2],self.body().get('name')))
        if method=='GET' and path=='/api/bibliotheque/animations':
            from . import bibliotheque
            return self.json(dict(animations=bibliotheque.animations(),
                                  categories=list(bibliotheque.CATEGORIES),
                                  collections=list(bibliotheque.COLLECTIONS),
                                  etats=list(bibliotheque.ETATS)))
        if method=='GET' and path=='/api/bibliotheque/presets':
            from . import bibliotheque
            return self.json(dict(presets=bibliotheque.presets(),defaut=(bibliotheque.preset_defaut() or {}).get('id')))
        if method=='GET' and path=='/api/bibliotheque/apercu':
            from . import bibliotheque
            # Même protection que les médias : le chemin est résolu puis jugé, et seuls deux noms sortent.
            return self.file(bibliotheque.fichier_apercu(q.get('id',[''])[0],q.get('fichier',['apercu.mp4'])[0]))
        if method=='GET' and len(bits)==4 and bits[1]=='bibliotheque' and bits[2]=='animations':
            from . import bibliotheque
            return self.json(bibliotheque.animation(bits[3]))
        if method=='POST' and path=='/api/bibliotheque/presets':
            from . import bibliotheque
            data=self.body()
            return self.json(bibliotheque.creer_preset(data.get('nom',''),data.get('depuis') or None),201)
        if method=='POST' and path=='/api/bibliotheque/presets/defaut':
            from . import bibliotheque
            ident=bibliotheque.definir_defaut(self.body().get('preset_id',''))
            return self.json(dict(defaut=ident))
        if len(bits)>=4 and bits[1]=='bibliotheque' and bits[2]=='presets':
            from . import bibliotheque
            ident=bits[3]
            if len(bits)==4 and method=='POST':
                data=self.body()
                return self.json(bibliotheque.modifier_preset(ident,data.get('bloc',''),data.get('cle',''),data.get('valeur')))
            if len(bits)==4 and method=='DELETE':
                bibliotheque.supprimer_preset(ident);return self.json(dict(ok=True))
            if len(bits)==5 and bits[4]=='animations' and method=='POST':
                data=self.body()
                return self.json(bibliotheque.animations_du_preset(ident,data.get('animation_id',''),bool(data.get('retirer'))))
        if method=='GET' and path=='/api/skills':
            from . import skills as skills_module
            return self.json(dict(skills=skills_module.liste()))
        if method=='GET' and len(bits)==3 and bits[1]=='skills' and bits[2].endswith('.zip'):
            from . import skills as skills_module
            nom,octets=skills_module.archive(bits[2][:-4])
            self.send_response(200)
            self.send_header('Content-Type','application/zip')
            self.send_header('Content-Length',str(len(octets)))
            self.send_header('Content-Disposition',f'attachment; filename="{nom}"')
            self.end_headers()
            if self.command!='HEAD':self.wfile.write(octets)
            return
        if path=='/api/reglages':
            if method=='GET':return self.json(reglages.load(store.root))
            if method=='PUT':return self.json(reglages.save(store.root,self.body()))
        if method=='POST' and path=='/api/demo':
            self.body();return self.json(create_demo(store))
        # Les paroles dites, tous projets confondus. La palette appelle cette route a la frappe.
        if method=='GET' and path=='/api/recherche':
            return self.json(store.recherche(q.get('q',[''])[0]))
        if path=='/api/jobs' and method=='GET':return self.json(dict(jobs=self.server.jobs.list(q.get('project_id',[None])[0])))
        if len(bits)>=3 and bits[1]=='jobs':
            if method=='GET' and len(bits)==3:return self.json(self.server.jobs.get(bits[2]))
            if method=='POST' and len(bits)==4 and bits[3]=='cancel':
                self.body();return self.json(self.server.jobs.cancel(bits[2]))
        if path=='/api/pick-file':
            from . import picker
            if method=='GET':return self.json(picker.describe(store.root,q.get('kind',['video'])[0]))
            if method=='POST':return self.json(picker.pick(store.root,self.body().get('kind','video')))
        if method=='GET' and len(bits)>=4 and bits[1]=='artifacts':
            directory=store.directory(bits[2]).resolve()
            asset=(directory/Path(*bits[3:])).resolve()
            # Le chemin est résolu avant d'être jugé : « retours/../project.json » n'est pas un retour.
            if not any(asset.is_relative_to(directory/name) for name in ('artifacts','assets','retours')):
                raise ValueError('Artefact inaccessible.')
            return self.file(asset)
        if method=='GET' and path=='/api/media':
            p=store.get(q.get('project_id',[''])[0])
            requested=q.get('version_id',[''])[0]
            if requested:
                version=next((v for v in p['versions'] if v['id']==requested),None)
                if not version:raise FileNotFoundError('Version introuvable.')
                return self.file(Path(version['path']))
            if q.get('proxy')==['1'] and p.get('proxy_path'):
                return self.file(Path(p['proxy_path']))
            src=next((s for s in p['sources'] if s['id']==q.get('source_id',[''])[0]),None)
            if not src:raise FileNotFoundError('Source introuvable.')
            return self.file(Path(src['path']))
        if len(bits)>=3 and bits[1]=='projects':
            pid=bits[2]
            if len(bits)==3:
                if method=='GET':return self.json(store.get(pid))
                if method=='PUT':return self.json(store.save(pid,self.body()))
                if method=='DELETE':
                    self.ensure_idle(pid)
                    target=store.trash(pid)
                    in_trash=target.parent==Path.home()/'.Trash'
                    return self.json(dict(ok=True,location='Corbeille' if in_trash else str(target)))
            if len(bits)==4 and bits[3]=='waveform' and method=='GET':
                from . import timeline
                try:
                    return self.json(timeline.waveform(store.get(pid),float(q.get('start',['0'])[0]),float(q.get('end',['0'])[0]),int(q.get('buckets',['600'])[0])))
                except timeline.TimelineError as exc:
                    raise ValueError(str(exc)) from exc
            if len(bits)==4 and bits[3]=='silences' and method=='POST':
                from . import timeline
                data=self.body();p=store.get(pid)
                segments=data.get('segments')
                if not isinstance(segments,list) or not segments or len(segments)>200:raise ValueError('Segments invalides.')
                for s in segments:
                    if not all(isinstance(s.get(k),(int,float)) and not isinstance(s.get(k),bool) for k in ('start','end')) or s['end']<=s['start'] or s['start']<0:
                        raise ValueError('Segments invalides.')
                min_duration=data.get('min_silence',0.35)
                if not isinstance(min_duration,(int,float)) or not 0.15<=min_duration<=2:raise ValueError('Durée minimale de blanc invalide.')
                try:
                    return self.json(timeline.analyse_montage(p,sorted(segments,key=lambda s:s['start']),float(min_duration)))
                except timeline.TimelineError as exc:
                    raise ValueError(str(exc)) from exc
            if len(bits)==4 and bits[3]=='prepare' and method=='POST':
                self.body()
                return self.json(dict(job=self.server.jobs.prepare(pid)))
            if bits[3]=='versions':
                return self.versions(method,pid,bits,q)
            if bits[3]=='retours':
                return self.retours(method,pid,bits,q)
            if len(bits)==4 and bits[3]=='reveal' and method=='POST':
                self.body()
                folder=store.directory(pid)
                if not folder.is_dir():raise FileNotFoundError('Dossier du projet introuvable.')
                opener=next((tool for tool in ('open','xdg-open') if shutil.which(tool)),None)
                if not opener:raise ValueError('Aucun gestionnaire de fichiers disponible sur cette machine.')
                subprocess.run([opener,str(folder)],check=True,timeout=10)
                return self.json(dict(ok=True,path=str(folder)))
            if len(bits)==4 and bits[3]=='thumbnail' and method=='GET':
                return self.file(project_thumbnail(store,pid))
            if len(bits)==4 and bits[3]=='sources' and method=='DELETE':
                self.ensure_idle(pid)
                updated=store.remove_source(pid)
                self.server.jobs.cancel_kinds(pid,('proxy',))
                return self.json(updated)
            if len(bits)==4 and bits[3]=='repointer' and method=='POST':
                self.ensure_idle(pid)
                return self.json(store.repointer(pid,self.body().get('path','')))
            if len(bits)==4 and method=='POST' and bits[3] in ('move','favorite','validate','ecarter'):
                data=self.body()
                if bits[3]=='move':return self.json(store.move(pid,data.get('folder_id') or None))
                if bits[3]=='ecarter':
                    updated=store.set_ecarte(pid,data.get('ecarte'))
                    if updated.get('ecarte_le'):self.server.jobs.cancel_kinds(pid,('relecture',),'Annulé : projet écarté')
                    return self.json(updated)
                if bits[3]=='validate':
                    step=data.get('step','review')
                    updated=store.set_validated(pid,data.get('validated'),step=step,version_id=data.get('version_id') or None)
                    # Le montage est déjà exporté depuis « Envoyer en relecture » : valider ne réencode rien.
                    # Il reste à lancer Claude, si l’utilisateur a demandé qu'il produise la V1 tout seul.
                    job=None
                    if updated.get('validated_at') and reglages.load(store.root).get('production_claude'):
                        try:job=self.server.jobs.start_production(pid,auto=True)
                        except (ValueError,FileNotFoundError) as exc:job=dict(error=str(exc))
                    return self.json(dict(updated,job=job))
                return self.json(store.set_favorite(pid,data.get('favorite')))
            if len(bits)==4 and method=='POST' and bits[3] in ('rename','duplicate'):
                data=self.body()
                if bits[3]=='rename':return self.json(store.rename(pid,data.get('name')))
                return self.json(store.duplicate(pid),201)
            if len(bits)==4 and method=='POST':
                action=bits[3];data=self.body()
                if action=='sources':
                    path=Path(data.get('path','')).expanduser().resolve()
                    if not path.is_file():raise ValueError('Fichier local introuvable. Collez son chemin absolu.')
                    meta=media.probe(path)
                    if not meta.get('width'):raise ValueError('Choisir une source vidéo.')
                    source=dict(meta,id=uid(),path=str(path),name=path.name,offset=0)
                    def add(p):
                        if p['sources']:raise ValueError('Un projet tient sur un seul fichier. Créez un projet pour un autre reel.')
                        p['sources'].append(source)
                        p['montage']=default_montage(source)
                        p.pop('proxy_path',None)
                        p.pop('proxy_format',None)
                    updated=store.mutate(pid,add)
                    self.server.jobs.cancel_kinds(pid,('proxy',))
                    self.server.jobs.prepare(pid)
                    return self.json(updated)
                if action=='relecture':
                    store.ensure_garde(pid)
                    return self.json(self.server.jobs.submit(pid,{'type':'relecture'}),202)
                if action=='production':return self.json(self.server.jobs.start_production(pid),202)
                if action=='jobs':return self.json(self.server.jobs.submit(pid,data),202)
        raise FileNotFoundError('Route introuvable.')

    def versions(self,method,pid,bits,q):
        """Deposited renders: V1, V2… The newest one takes over the review."""
        from . import media
        store=self.server.store
        if len(bits)==4 and method=='GET':
            p=store.get(pid)
            return self.json(dict(versions=[{k:v for k,v in item.items() if k!='transcript'} for item in p['versions']],
                                  active_version=p.get('active_version')))
        if len(bits)==4 and method=='POST':
            data=self.body()
            path=Path(data.get('path','')).expanduser().resolve()
            if not path.is_file():raise ValueError('Rendu introuvable. Collez le chemin absolu du MP4.')
            info=media.probe(path)
            if not info.get('width'):raise ValueError('Choisir un fichier vidéo rendu.')
            p,version=store.add_version(pid,path,info)
            self.server.jobs.submit(pid,{'type':'transcript','version_id':version['id'],'auto':True})
            return self.json(dict(project=p,version={k:v for k,v in version.items() if k!='transcript'}),201)
        if len(bits)==5 and method=='GET' and bits[4]!='':
            version=next((v for v in store.get(pid)['versions'] if v['id']==bits[4]),None)
            if not version:raise FileNotFoundError('Version introuvable.')
            return self.json(version)
        if len(bits)==6 and bits[5]=='select' and method=='POST':
            self.body()
            updated=store.set_active_version(pid,bits[4])
            self.server.jobs.prepare(pid)
            return self.json(updated)
        if len(bits)==6 and bits[5]=='transcript' and method=='POST':
            self.body()
            return self.json(self.server.jobs.submit(pid,{'type':'transcript','version_id':bits[4]}),202)
        raise FileNotFoundError('Route introuvable.')

    def _version(self,pid,q):
        store=self.server.store
        p=store.get(pid)
        wanted=q.get('version_id',[''])[0]
        version=next((v for v in p['versions'] if v['id']==wanted),None) if wanted else store.active_version(p)
        if not version:raise FileNotFoundError('Aucune version déposée pour ce projet.')
        return p,version

    def retours(self,method,pid,bits,q):
        """Timestamped feedback on the version under review, stored in retours/v<N>.json."""
        store=self.server.store
        if len(bits)==5 and bits[4]=='consigne' and method=='GET':
            p,version=self._version(pid,q)
            items=[r for r in retours_module.load(store,pid,version['index'])['retours'] if not r.get('resolved')]
            text=retours_module.consigne(p,version,items,store.directory(pid))
            return self.json(dict(text=text,count=len(items),version=version['index'],
                                  source_notice=retours_module.source_notice(p,version)))
        if len(bits)==5 and bits[4]=='resolve' and method=='POST':
            data=self.body();p,version=self._version(pid,q)
            ids=data.get('ids')
            if not isinstance(ids,list) or not all(isinstance(i,str) for i in ids):raise ValueError('Liste de retours invalide.')
            items=retours_module.load(store,pid,version['index'])['retours']
            for item in items:
                if item['id'] in ids:item.update(resolved=True,updated_at=retours_module.now())
            return self.json(retours_module.save(store,pid,version['index'],items))
        if len(bits)==4 and method=='GET':
            p,version=self._version(pid,q)
            return self.json(retours_module.load(store,pid,version['index'])|dict(counts=retours_module.counts(store,pid,version['index'])))
        if len(bits)==4 and method=='POST':
            data=self.body();p,version=self._version(pid,q)
            items=retours_module.load(store,pid,version['index'])['retours']
            entry=retours_module.validate_entry(store,pid,data,float(version['duration'] or 0))
            items.append(entry)
            items.sort(key=lambda item:item['start'])
            retours_module.save(store,pid,version['index'],items)
            return self.json(entry,201)
        if len(bits)==5 and method in ('PUT','DELETE'):
            p,version=self._version(pid,q)
            items=retours_module.load(store,pid,version['index'])['retours']
            existing=next((item for item in items if item['id']==bits[4]),None)
            if not existing:raise FileNotFoundError('Retour introuvable.')
            if method=='DELETE':
                retours_module.save(store,pid,version['index'],[item for item in items if item['id']!=bits[4]])
                return self.json(dict(ok=True))
            data=self.body()
            entry=retours_module.validate_entry(store,pid,data,float(version['duration'] or 0),existing=existing)
            items=[entry if item['id']==bits[4] else item for item in items]
            items.sort(key=lambda item:item['start'])
            retours_module.save(store,pid,version['index'],items)
            return self.json(entry)
        raise FileNotFoundError('Route introuvable.')

    def file(self,path):
        if not path.is_file():raise FileNotFoundError('Fichier indisponible.')
        size=path.stat().st_size
        start,end=0,size-1
        range_header=self.headers.get('Range')
        status=200
        if range_header:
            m=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
            if not m or not any(m.groups()):
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
            a,b=m.groups()
            if a:
                start=int(a);end=min(int(b) if b else size-1,size-1)
            else:
                start=max(0,size-int(b));end=size-1
            if start>end or start>=size:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
            status=206
        self.send_response(status)
        mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if path.suffix=='.js':mime='text/javascript'
        if path.suffix=='.otf':mime='font/otf'
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(max(0,end-start+1)))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-cache')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command=='HEAD':return
        with path.open('rb') as f:
            f.seek(start);remaining=end-start+1
            while remaining>0:
                chunk=f.read(min(1024*1024,remaining))
                if not chunk:break
                self.wfile.write(chunk);remaining-=len(chunk)

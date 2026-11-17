import base64
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from studio.server import Server
from studio.store import default_montage

PNG=base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')


def petit_mp4(path,seconds=2):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi',
                    '-i',f'testsrc2=size=160x284:rate=10','-t',str(seconds),'-pix_fmt','yuv420p',
                    '-c:v','libx264','-preset','ultrafast',str(path)],check=True,timeout=120)
    return path


class Base(unittest.TestCase):
    def request(self,path,method='GET',data=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        h={'Content-Type':'application/json'};h.update(headers or {})
        conn.request(method,path,body=json.dumps(data) if data is not None else None,headers=h)
        r=conn.getresponse();out=(r.status,dict(r.getheaders()),r.read());conn.close();return out


class ServerTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=Server(('127.0.0.1',0),cls.temp.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port
        cls.p=cls.server.store.create('Test HTTP')
        f=cls.server.store.directory(cls.p['id'])/'assets'/'range.mp4';f.parent.mkdir(parents=True);f.write_bytes(bytes(range(256))*4)
        cls.asset='/api/artifacts/'+cls.p['id']+'/assets/range.mp4'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def test_health(self):
        code,_,body=self.request('/api/health')
        self.assertEqual(code,200);self.assertTrue(json.loads(body)['ok'])

    def test_diagnostics_names_the_tools_the_two_steps_need(self):
        code,_,body=self.request('/api/diagnostics')
        data=json.loads(body)
        self.assertEqual(code,200)
        names=[tool['name'] for tool in data['tools']]
        self.assertEqual(names,['ffmpeg','ffprobe','whisper-cli','modèle Whisper'])
        self.assertIn('whisper_cli',data['speech'])

    def test_font_listing_only_names_font_files(self):
        code,_,body=self.request('/api/fonts')
        self.assertEqual(code,200)
        self.assertTrue(all(name.endswith(('.otf','.ttf')) for name in json.loads(body)['fonts']))

    def test_unread_body_does_not_poison_the_next_request_on_the_same_connection(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request('POST','/api/inconnue',body='{}',headers={'Content-Type':'application/json'})
        r=conn.getresponse();r.read();self.assertEqual(r.status,404)
        conn.request('GET','/api/health')
        r=conn.getresponse();body=r.read();conn.close()
        self.assertEqual(r.status,200);self.assertTrue(json.loads(body)['ok'])

    def test_range_is_partial_and_exact(self):
        status,headers,body=self.request(self.asset,headers={'Range':'bytes=100-199'})
        self.assertEqual(status,206);self.assertEqual(headers['Content-Range'],'bytes 100-199/1024')
        self.assertEqual(body,bytes(range(100,200)))

    def test_suffix_range(self):
        status,headers,body=self.request(self.asset,headers={'Range':'bytes=-10'})
        self.assertEqual(status,206);self.assertEqual(body,bytes(range(246,256)))

    def test_invalid_range(self):
        status,headers,body=self.request(self.asset,headers={'Range':'bytes=1024-'})
        self.assertEqual(status,416);self.assertEqual(headers['Content-Range'],'bytes */1024')

    def test_head(self):
        status,headers,body=self.request(self.asset,method='HEAD')
        self.assertEqual(status,200);self.assertEqual(body,b'');self.assertEqual(headers['Content-Length'],'1024')

    def test_only_three_folders_are_served(self):
        for forbidden in ('montage.json','project.json','retours/../project.json'):
            status,_,body=self.request('/api/artifacts/'+self.p['id']+'/'+forbidden)
            self.assertEqual(status,400,forbidden)
            self.assertIn('inaccessible',json.loads(body)['error'])

    def test_cross_origin_write_forbidden(self):
        status,_,_=self.request('/api/projects','POST',{'name':'Intrusion'},headers={'Origin':'https://evil.example'})
        self.assertEqual(status,403)

    def test_rebinding_host_forbidden(self):
        status,_,_=self.request('/api/health',headers={'Host':'evil.example'})
        self.assertEqual(status,403)

    def test_directory_traversal_forbidden(self):
        status,_,_=self.request('/api/artifacts/'+self.p['id']+'/assets/../../../../secret')
        self.assertEqual(status,400)

    def test_optimistic_revision_api(self):
        status,_,body=self.request('/api/projects','POST',{'name':'Version test'})
        self.assertEqual(status,201);p=json.loads(body)
        first,_,_=self.request('/api/projects/'+p['id'],'PUT',p)
        second,_,_=self.request('/api/projects/'+p['id'],'PUT',p)
        self.assertEqual(first,200);self.assertEqual(second,409)

    def test_a_project_holds_one_file_and_it_must_be_a_video(self):
        if not shutil.which('ffmpeg'):self.skipTest('ffmpeg absent')
        p=json.loads(self.request('/api/projects','POST',{'name':'Un seul fichier'})[2])
        rush=petit_mp4(Path(self.temp.name)/'rush.mp4')
        with mock.patch.object(self.server.jobs,'prepare',return_value=None):
            status,_,body=self.request('/api/projects/'+p['id']+'/sources','POST',{'path':str(rush)})
            self.assertEqual(status,200,body)
            saved=json.loads(body)
            self.assertEqual(len(saved['sources']),1)
            self.assertEqual(saved['montage']['segments'][0]['start'],0.0)
            status,_,body=self.request('/api/projects/'+p['id']+'/sources','POST',{'path':str(rush)})
        self.assertEqual(status,400);self.assertIn('un seul fichier',json.loads(body)['error'])
        status,_,body=self.request('/api/projects/'+p['id']+'/sources','POST',{'path':'/nulle/part.mp4'})
        self.assertEqual(status,400);self.assertIn('introuvable',json.loads(body)['error'])

    def test_rename_duplicate_and_delete_project(self):
        p=self.server.store.create('À gérer')
        status,_,body=self.request('/api/projects/'+p['id']+'/rename','POST',{'name':'Renommé'})
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['name'],'Renommé')
        status,_,body=self.request('/api/projects/'+p['id']+'/duplicate','POST',{})
        self.assertEqual(status,201);copy_id=json.loads(body)['id']
        home=Path(self.temp.name)/'home';(home/'.Trash').mkdir(parents=True,exist_ok=True)
        with mock.patch.object(Path,'home',return_value=home):
            status,_,body=self.request('/api/projects/'+p['id'],'DELETE',headers={'Content-Type':'text/plain'})
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['location'],'Corbeille')
        self.assertEqual(self.request('/api/projects/'+p['id'])[0],404)
        self.assertEqual(self.request('/api/projects/'+copy_id)[0],200)

    def test_delete_refused_while_job_runs(self):
        p=self.server.store.create('Occupé')
        self.server.jobs.records['busy']=dict(id='busy',project_id=p['id'],state='running',created_at='2026-01-01')
        self.addCleanup(self.server.jobs.records.pop,'busy',None)
        status,_,body=self.request('/api/projects/'+p['id'],'DELETE')
        self.assertEqual(status,400);self.assertIn('tâche',json.loads(body)['error'])
        self.assertEqual(self.request('/api/projects/'+p['id'])[0],200)

    def test_cross_origin_delete_forbidden(self):
        p=self.server.store.create('Protégé')
        status,_,_=self.request('/api/projects/'+p['id'],'DELETE',headers={'Origin':'https://evil.example'})
        self.assertEqual(status,403)
        self.assertEqual(self.request('/api/projects/'+p['id'])[0],200)

    def test_ne_pas_garder_bloque_la_relecture(self):
        p=self.server.store.create('Écartable')
        status,_,body=self.request('/api/projects/'+p['id']+'/ecarter','POST',{'ecarte':True})
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['ecarte_le'])
        status,_,body=self.request('/api/projects/'+p['id']+'/relecture','POST',{})
        self.assertEqual(status,400);self.assertIn('écarté',json.loads(body)['error'])
        # Le chemin générique des tâches ne contourne pas la garde.
        status,_,body=self.request('/api/projects/'+p['id']+'/jobs','POST',{'type':'relecture'})
        self.assertEqual(status,400);self.assertIn('écarté',json.loads(body)['error'])
        listing=json.loads(self.request('/api/projects')[2])
        self.assertEqual([x['status'] for x in listing['projects'] if x['id']==p['id']],['ecarte'])
        status,_,body=self.request('/api/projects/'+p['id']+'/ecarter','POST',{'ecarte':False})
        self.assertEqual(status,200);self.assertNotIn('ecarte_le',json.loads(body))

    def test_folders_move_favorite_and_thumbnail(self):
        if not shutil.which('ffmpeg'):self.skipTest('ffmpeg absent')
        status,_,body=self.request('/api/folders','POST',{'name':'Shorts'})
        self.assertEqual(status,201);folder=json.loads(body)
        status,_,body=self.request('/api/projects','POST',{'name':'Dans un dossier','folder_id':folder['id']})
        self.assertEqual(status,201);p=json.loads(body);self.assertEqual(p['folder_id'],folder['id'])
        status,_,body=self.request('/api/projects/'+p['id']+'/favorite','POST',{'favorite':True})
        self.assertTrue(json.loads(body)['favorite'])
        status,_,body=self.request('/api/projects/'+p['id']+'/move','POST',{'folder_id':None})
        self.assertIsNone(json.loads(body)['folder_id'])
        listing=json.loads(self.request('/api/projects')[2])
        self.assertIn(folder['id'],[f['id'] for f in listing['folders']])
        self.assertEqual(self.request('/api/projects/'+p['id']+'/thumbnail')[0],404)
        video=self.server.store.directory(p['id'])/'assets'/'clip.mp4'
        video.parent.mkdir(parents=True,exist_ok=True);petit_mp4(video)
        stored=self.server.store.get(p['id']);stored['proxy_path']=str(video)
        self.server.store.save(p['id'],stored,internal=True)
        status,headers,body=self.request('/api/projects/'+p['id']+'/thumbnail')
        self.assertEqual(status,200);self.assertEqual(headers['Content-Type'],'image/jpeg');self.assertTrue(body.startswith(b'\xff\xd8'))
        status,_,body=self.request('/api/folders/'+folder['id'],'DELETE')
        self.assertEqual(status,200)


@unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg absent')
class ReviewRouteTests(Base):
    """Le dépôt d'une version, les retours et la consigne, de bout en bout en HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=Server(('127.0.0.1',0),cls.temp.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port
        cls.rendu=petit_mp4(Path(cls.temp.name)/'v1.mp4',32)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def setUp(self):
        store=self.server.store
        p=store.create('Relecture HTTP')
        source=dict(id='s',path=str(self.rendu),name='rush.mp4',width=1080,height=1920,duration=60,fps=25,has_audio=True)
        p['sources']=[source]
        # Deux blancs coupés : 10→18 s et 30→40 s dans le fichier d'origine.
        p['montage']=default_montage(source)|dict(segments=[dict(start=0,end=10),dict(start=18,end=30),dict(start=40,end=50)])
        self.p=store.save(p['id'],p,internal=True)
        self.pid=self.p['id']

    def deposit(self):
        with mock.patch.object(self.server.jobs,'submit',return_value=dict(id='job',type='transcript')) as submit:
            status,_,body=self.request(f'/api/projects/{self.pid}/versions','POST',{'path':str(self.rendu)})
        self.assertEqual(status,201,body)
        return json.loads(body),submit

    def test_a_deposited_render_becomes_v1_and_asks_for_its_transcript(self):
        payload,submit=self.deposit()
        version=payload['version']
        self.assertEqual(version['index'],1)
        self.assertEqual(payload['project']['active_version'],version['id'])
        self.assertNotIn('transcript',version)
        self.assertEqual(submit.call_args.args[1]['type'],'transcript')
        self.assertTrue(submit.call_args.args[1]['auto'])
        code,_,body=self.request(f'/api/projects/{self.pid}/versions')
        listing=json.loads(body)
        self.assertEqual(code,200)
        self.assertEqual(listing['active_version'],version['id'])
        self.assertNotIn('transcript',listing['versions'][0])
        code,_,body=self.request(f"/api/projects/{self.pid}/versions/{version['id']}")
        self.assertEqual((code,json.loads(body)['transcript']),(200,[]))
        self.assertEqual(self.request(f'/api/projects/{self.pid}/versions/inconnue')[0],404)

    def test_a_deposit_refuses_anything_that_is_not_a_rendered_video(self):
        status,_,body=self.request(f'/api/projects/{self.pid}/versions','POST',{'path':'/nulle/part.mp4'})
        self.assertEqual(status,400);self.assertIn('Rendu introuvable',json.loads(body)['error'])

    def test_the_version_file_is_streamed_with_ranges(self):
        payload,_=self.deposit()
        url=f"/api/media?project_id={self.pid}&version_id={payload['version']['id']}"
        status,headers,body=self.request(url,headers={'Range':'bytes=0-15'})
        self.assertEqual(status,206);self.assertEqual(len(body),16)
        self.assertEqual(self.request(f'/api/media?project_id={self.pid}&version_id=inconnue')[0],404)

    def test_an_older_version_can_take_the_stage_again(self):
        first,_=self.deposit()
        second,_=self.deposit()
        self.assertEqual(second['version']['index'],2)
        with mock.patch.object(self.server.jobs,'prepare',return_value=None):
            code,_,body=self.request(f"/api/projects/{self.pid}/versions/{first['version']['id']}/select",'POST',{})
        self.assertEqual(code,200);self.assertEqual(json.loads(body)['active_version'],first['version']['id'])

    def test_feedback_lives_in_the_version_file_and_can_be_edited(self):
        payload,_=self.deposit()
        code,_,body=self.request(f'/api/projects/{self.pid}/retours','POST',
                                 {'type':'comment','start':12.0,'text':'Coupe ce silence','quote':'alors euh'})
        self.assertEqual(code,201,body);first=json.loads(body)
        self.assertEqual((first['start'],first['end'],first['resolved']),(12.0,None,False))
        code,_,body=self.request(f'/api/projects/{self.pid}/retours','POST',
                                 {'type':'cut','start':2.0,'end':5.5,'text':'Enlève cette phrase'})
        self.assertEqual(code,201,body);second=json.loads(body)
        code,_,body=self.request(f'/api/projects/{self.pid}/retours')
        data=json.loads(body)
        self.assertEqual([r['id'] for r in data['retours']],[second['id'],first['id']])
        self.assertEqual(data['counts'],dict(total=2,open=2,resolved=0))
        self.assertEqual(data['version'],1)
        stored=json.loads((self.server.store.directory(self.pid)/'retours'/'v1.json').read_text())
        self.assertEqual(stored['version'],1);self.assertEqual(len(stored['retours']),2)
        code,_,body=self.request(f"/api/projects/{self.pid}/retours/{first['id']}",'PUT',{'text':'Raccourcis plutôt'})
        self.assertEqual((code,json.loads(body)['text']),(200,'Raccourcis plutôt'))
        self.assertEqual(json.loads(body)['quote'],'alors euh')
        code,_,_=self.request(f"/api/projects/{self.pid}/retours/{second['id']}",'DELETE')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(self.request(f'/api/projects/{self.pid}/retours')[2])['counts']['total'],1)
        self.assertEqual(self.request(f'/api/projects/{self.pid}/retours/inconnu','DELETE')[0],404)
        self.assertEqual(payload['version']['index'],1)

    def test_an_empty_feedback_is_refused(self):
        self.deposit()
        status,_,body=self.request(f'/api/projects/{self.pid}/retours','POST',{'start':1.0,'text':'   '})
        self.assertEqual(status,400);self.assertIn('obligatoire',json.loads(body)['error'])
        status,_,body=self.request(f'/api/projects/{self.pid}/retours','POST',{'start':1.0,'text':'x','type':'autre'})
        self.assertEqual(status,400)

    def test_feedback_needs_a_deposited_version(self):
        status,_,body=self.request(f'/api/projects/{self.pid}/retours')
        self.assertEqual(status,404);self.assertIn('Aucune version',json.loads(body)['error'])

    def test_an_attached_capture_is_stored_as_png_and_served_back(self):
        self.deposit()
        data_url='data:image/png;base64,'+base64.b64encode(PNG).decode()
        code,_,body=self.request(f'/api/projects/{self.pid}/retours','POST',
                                 {'start':1.0,'text':'Vois le dessin','images':[data_url]})
        self.assertEqual(code,201,body);entry=json.loads(body)
        self.assertRegex(entry['images'][0],r'^images/[a-f0-9]{16}\.png$')
        status,headers,served=self.request(f"/api/artifacts/{self.pid}/retours/{entry['images'][0]}")
        self.assertEqual(status,200);self.assertEqual(served,PNG);self.assertEqual(headers['Content-Type'],'image/png')
        # Une image déjà enregistrée n'est pas réécrite à la modification.
        code,_,body=self.request(f"/api/projects/{self.pid}/retours/{entry['id']}",'PUT',
                                 {'text':'Vois le dessin','images':entry['images']})
        self.assertEqual(json.loads(body)['images'],entry['images'])
        status,_,body=self.request(f'/api/projects/{self.pid}/retours','POST',
                                  {'start':1.0,'text':'Faux PNG','images':['data:image/png;base64,bm9uIQ==']})
        self.assertEqual(status,400);self.assertIn('PNG',json.loads(body)['error'])

    def test_the_instruction_recomputes_source_times_and_resolve_empties_it(self):
        self.deposit()
        plage=json.loads(self.request(f'/api/projects/{self.pid}/retours','POST',
                                      {'type':'comment','start':10.5,'end':14.31,'text':'Trop lent ici',
                                       'quote':'et donc voilà'})[2])
        ponctuel=json.loads(self.request(f'/api/projects/{self.pid}/retours','POST',
                                         {'type':'cut','start':22.0,'text':'Enlève l’hésitation'})[2])
        code,_,body=self.request(f'/api/projects/{self.pid}/retours/consigne')
        data=json.loads(body)
        self.assertEqual((code,data['count'],data['version']),(200,2,1))
        text=data['text']
        self.assertTrue(text.startswith(f'/montage-reels applique ces retours au reel Relecture HTTP '
                                        f'({self.server.store.directory(self.pid)})\n'))
        self.assertIn('2 changements à appliquer :',text)
        # Le reel 10.50 s est déjà de l'autre côté du blanc 10→18 : il vaut 18.50 s dans le fichier d'origine.
        self.assertIn(f'1. COMMENTAIRE de 00:10.50 à 00:14.31 (REEL 10.50 s → 14.31 s, 3.81 s)'
                      f' · SOURCE 18.50 s → 22.31 s [id {plage["id"]}]',text)
        self.assertIn('   Mots : "et donc voilà"',text)
        self.assertIn('   Demande : Trop lent ici',text)
        self.assertIn(f'2. COUPE à 00:22.00 (REEL 22.00 s) · SOURCE 30.00 s [id {ponctuel["id"]}]',text)
        self.assertTrue(text.endswith('\n'))
        code,_,body=self.request(f'/api/projects/{self.pid}/retours/resolve','POST',{'ids':[plage['id']]})
        self.assertEqual(code,200)
        self.assertEqual([r['resolved'] for r in json.loads(body)['retours']],[True,False])
        data=json.loads(self.request(f'/api/projects/{self.pid}/retours/consigne')[2])
        self.assertEqual(data['count'],1)
        self.assertIn('1 changement à appliquer :',data['text'])
        self.assertNotIn(plage['id'],data['text'])
        status,_,_=self.request(f'/api/projects/{self.pid}/retours/resolve','POST',{'ids':'tout'})
        self.assertEqual(status,400)

    def test_every_version_keeps_its_own_feedback(self):
        first,_=self.deposit()
        self.request(f'/api/projects/{self.pid}/retours','POST',{'start':1.0,'text':'Sur la V1'})
        second,_=self.deposit()
        self.assertEqual(json.loads(self.request(f'/api/projects/{self.pid}/retours')[2])['counts']['total'],0)
        url=f"/api/projects/{self.pid}/retours?version_id={first['version']['id']}"
        data=json.loads(self.request(url)[2])
        self.assertEqual((data['version'],data['retours'][0]['text']),(1,'Sur la V1'))
        self.assertEqual(json.loads(self.request(f'/api/projects/{self.pid}/retours')[2])['version'],2)
        self.assertEqual(second['version']['index'],2)


class ValidateRouteTests(Base):
    """« Valider » en HTTP : l'état du short, la demande de production, et les réglages."""

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=Server(('127.0.0.1',0),cls.temp.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def setUp(self):
        store=self.server.store
        p=store.create('Short à valider')
        source=dict(id='s',path=str(Path(self.temp.name)/'rush.mp4'),name='rush.mp4',
                    width=1080,height=1920,duration=60,fps=25,has_audio=True)
        p['sources']=[source]
        p['montage']=default_montage(source)|dict(segments=[dict(start=0,end=12),dict(start=20,end=30)],title='Titre')
        self.p=store.save(p['id'],p,internal=True);self.pid=self.p['id']

    def produire_tout_seul(self,on=True):
        """Allume le réglage « Claude produit la V1 » le temps d'un test, et le rééteint après."""
        self.request('/api/reglages','PUT',{'production_claude':on})
        self.addCleanup(self.request,'/api/reglages','PUT',{'production_claude':False})

    def test_validating_hands_the_v1_to_claude_when_asked(self):
        # Le montage est déjà exporté par « Envoyer en relecture » : valider ne réencode rien.
        self.produire_tout_seul()
        faux=dict(id='job',type='production',state='running')
        with mock.patch.object(self.server.jobs,'start_production',return_value=faux) as start, \
             mock.patch.object(self.server.jobs,'submit') as submit:
            status,_,body=self.request(f'/api/projects/{self.pid}/validate','POST',{'validated':True})
        self.assertEqual(status,200,body);payload=json.loads(body)
        self.assertTrue(payload['validated_at'])
        self.assertEqual(payload['job'],faux)
        self.assertEqual(start.call_args.kwargs,{'auto':True})
        submit.assert_not_called()
        self.assertEqual(payload['production']['consigne'].split(' ')[0],'/montage-reels')
        self.assertEqual(json.loads(self.request('/api/projects')[2])['projects'][0]['status'],'done')

    def test_going_back_cancels_the_production_request(self):
        self.request(f'/api/projects/{self.pid}/validate','POST',{'validated':True})
        with mock.patch.object(self.server.jobs,'submit') as submit:
            status,_,body=self.request(f'/api/projects/{self.pid}/validate','POST',{'validated':False})
        self.assertEqual(status,200,body);payload=json.loads(body)
        self.assertIsNone(payload['validated_at']);self.assertIsNone(payload['job'])
        self.assertNotIn('production',payload)
        submit.assert_not_called()
        # Le montage reste intact : revenir en arrière ne coûte rien.
        self.assertEqual(payload['montage']['segments'],[dict(start=0.0,end=12.0),dict(start=20.0,end=30.0)])

    def test_a_production_that_cannot_start_says_so_without_losing_the_validation(self):
        self.produire_tout_seul()
        boom=ValueError('La commande « claude » est introuvable sur cette machine.')
        with mock.patch.object(self.server.jobs,'start_production',side_effect=boom):
            status,_,body=self.request(f'/api/projects/{self.pid}/validate','POST',{'validated':True})
        self.assertEqual(status,200,body);payload=json.loads(body)
        self.assertTrue(payload['validated_at'])
        self.assertIn('introuvable',payload['job']['error'])

    def test_validating_a_reread_starts_nothing_by_itself(self):
        store=self.server.store
        p,version=store.add_version(self.pid,str(Path(self.temp.name)/'v1.mp4'),
                                    dict(path=str(Path(self.temp.name)/'v1.mp4'),duration=42.0,
                                         width=1080,height=1920,has_audio=True))
        with mock.patch.object(self.server.jobs,'submit') as submit:
            status,_,body=self.request(f'/api/projects/{self.pid}/validate','POST',
                                       {'validated':True,'step':'review','version_id':version['id']})
        self.assertEqual(status,200,body);payload=json.loads(body)
        self.assertTrue(payload['validated_at']);self.assertIsNone(payload['job'])
        submit.assert_not_called()
        self.assertEqual([v['id'] for v in payload['versions'] if v.get('final')],[version['id']])
        status,_,body=self.request(f'/api/projects/{self.pid}/validate','POST',
                                   {'validated':True,'step':'review','version_id':'inconnue'})
        self.assertEqual(status,404)
        for etape in ('montage','ailleurs'):
            status,_,body=self.request(f'/api/projects/{self.pid}/validate','POST',{'validated':True,'step':etape})
            self.assertEqual(status,400);self.assertIn('inconnue',json.loads(body)['error'])

    def test_production_setting_is_off_until_asked(self):
        status,_,body=self.request('/api/reglages')
        self.assertEqual(status,200);self.assertEqual(json.loads(body),{'production_claude':False,'polices_dir':''})
        status,_,body=self.request('/api/reglages','PUT',{'production_claude':True})
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['production_claude'])
        self.assertTrue(json.loads(self.request('/api/reglages')[2])['production_claude'])
        status,_,body=self.request('/api/reglages','PUT',{'production_claude':'oui'})
        self.assertEqual(status,400);self.assertIn('vrai ou faux',json.loads(body)['error'])
        status,_,body=self.request('/api/reglages','PUT',{'autre_chose':True})
        self.assertEqual(status,400);self.assertIn('inconnu',json.loads(body)['error'])
        status,_,_=self.request('/api/reglages','PUT',{'production_claude':False},
                                headers={'Origin':'https://evil.example'})
        self.assertEqual(status,403)
        self.assertTrue(json.loads(self.request('/api/reglages')[2])['production_claude'])
        self.request('/api/reglages','PUT',{'production_claude':False})


class SendToReviewRouteTests(Base):
    """« Envoyer en relecture » : une tâche locale, et les refus qui s'expliquent."""

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=Server(('127.0.0.1',0),cls.temp.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def short(self,segments=((0,12),(20,30))):
        store=self.server.store
        p=store.create('À envoyer')
        source=dict(id='s',path=str(Path(self.temp.name)/'rush.mp4'),name='rush.mp4',
                    width=1080,height=1920,duration=60,fps=25,has_audio=True)
        p['sources']=[source]
        p['montage']=default_montage(source)|dict(segments=[dict(start=a,end=b) for a,b in segments],
                                                  hook='Il a fait 40 000 € / sans publicité')
        return store.save(p['id'],p,internal=True)

    def test_sending_queues_one_local_task(self):
        pid=self.short()['id']
        faux=dict(id='job',type='relecture',state='queued')
        with mock.patch.object(self.server.jobs,'submit',return_value=faux) as submit:
            status,_,body=self.request(f'/api/projects/{pid}/relecture','POST',{})
        self.assertEqual(status,202,body)
        self.assertEqual(json.loads(body),faux)
        self.assertEqual(submit.call_args.args[1],{'type':'relecture'})

    def test_a_short_without_a_file_says_why_nothing_was_sent(self):
        pid=self.server.store.create('Sans fichier')['id']
        status,_,body=self.request(f'/api/projects/{pid}/relecture','POST',{})
        self.assertEqual(status,400);self.assertIn('Importer une vidéo',json.loads(body)['error'])

    def test_a_montage_that_keeps_nothing_is_refused(self):
        pid=self.short(segments=())['id']
        status,_,body=self.request(f'/api/projects/{pid}/relecture','POST',{})
        self.assertEqual(status,400);self.assertIn('aucun morceau',json.loads(body)['error'])

    def test_asking_twice_rides_the_task_already_running(self):
        pid=self.short()['id']
        with mock.patch.object(self.server.jobs,'run',return_value=None):
            first=json.loads(self.request(f'/api/projects/{pid}/relecture','POST',{})[2])
            second=json.loads(self.request(f'/api/projects/{pid}/relecture','POST',{})[2])
        self.assertEqual(first['id'],second['id'])
        self.addCleanup(self.server.jobs.cancel_kinds,pid,('relecture',))


class PolicesSettingTests(Base):
    """Le dossier des polices ZT Nature se règle dans l'Atelier, pour les Mac qui les rangent ailleurs."""

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=Server(('127.0.0.1',0),cls.temp.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def test_the_folder_is_kept_as_written_and_checked_as_text(self):
        status,_,body=self.request('/api/reglages','PUT',{'polices_dir':'  ~/Library/Fonts  '})
        self.assertEqual(status,200,body)
        self.assertEqual(json.loads(body)['polices_dir'],'~/Library/Fonts')
        self.assertEqual(json.loads(self.request('/api/reglages')[2])['polices_dir'],'~/Library/Fonts')
        status,_,body=self.request('/api/reglages','PUT',{'polices_dir':True})
        self.assertEqual(status,400);self.assertIn('texte',json.loads(body)['error'])
        # Vidé, le réglage rend la main aux dossiers de polices de la machine.
        self.assertEqual(json.loads(self.request('/api/reglages','PUT',{'polices_dir':''})[2])['polices_dir'],'')

    def test_the_checklist_looks_for_the_fonts_where_the_setting_says(self):
        folder=Path(self.temp.name)/'mes polices'
        folder.mkdir()
        for name in ('ZTNature-Bold.otf','ZTNature-MediumItalic.otf'):
            (folder/name).write_bytes(b'otf')
        self.request('/api/reglages','PUT',{'polices_dir':str(folder)})
        self.addCleanup(self.request,'/api/reglages','PUT',{'polices_dir':''})
        items={item['id']:item for item in json.loads(self.request('/api/setup')[2])['requirements']}
        self.assertEqual(items['fonts']['path'],str(folder))
        self.assertTrue(items['fonts']['available'])


class BibliothequeRoutesTests(Base):
    """Les routes d'écriture des presets, sur une bibliothèque jetable."""

    @classmethod
    def setUpClass(cls):
        from studio import bibliotheque
        cls.temp=tempfile.TemporaryDirectory()
        cls.racine=Path(cls.temp.name)/'bibliotheque'
        (cls.racine/'presets').mkdir(parents=True)
        anim=cls.racine/'animations'/'une-anim'
        anim.mkdir(parents=True)
        (anim/'meta.json').write_text(json.dumps(dict(
            id='une-anim',nom='Une anim',categorie='Textes',collection='Mes styles',niveau='Simple',
            etat='Prototype',description='',quand_l_utiliser='',parametres={},duree_s=1.0,reference='')),
            encoding='utf-8')
        (cls.racine/'presets'/'depart.json').write_text(json.dumps(dict(
            schema=1,nom='Départ',description='',polices={},couleurs={},titre={},son={},image={},
            sous_titres={},encadre=dict(taille_px=64),animations_par_defaut=[])),encoding='utf-8')
        cls.patch=mock.patch.object(bibliotheque,'RACINE',cls.racine)
        cls.patch.start()
        cls.data=tempfile.TemporaryDirectory()
        cls.server=Server(('127.0.0.1',0),cls.data.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        cls.patch.stop();cls.data.cleanup();cls.temp.cleanup()

    def test_le_parcours_complet_d_un_preset(self):
        code,_,body=self.request('/api/bibliotheque/presets','POST',{'nom':'Mon style','depuis':'depart'})
        self.assertEqual(code,201)
        neuf=json.loads(body)
        self.assertEqual(neuf['id'],'mon-style')
        self.assertEqual(neuf['encadre']['taille_px'],64)

        code,_,body=self.request('/api/bibliotheque/presets/defaut','POST',{'preset_id':'mon-style'})
        self.assertEqual((code,json.loads(body)['defaut']),(200,'mon-style'))
        self.assertEqual(json.loads(self.request('/api/bibliotheque/presets')[2])['defaut'],'mon-style')

        code,_,body=self.request('/api/bibliotheque/presets/mon-style','POST',
                                 {'bloc':'encadre','cle':'taille_px','valeur':'60'})
        self.assertEqual((code,json.loads(body)['encadre']['taille_px']),(200,60))

        code,_,body=self.request('/api/bibliotheque/presets/mon-style/animations','POST',
                                 {'animation_id':'une-anim'})
        self.assertEqual((code,json.loads(body)['animations_par_defaut']),(200,['une-anim']))
        code,_,body=self.request('/api/bibliotheque/presets/mon-style/animations','POST',
                                 {'animation_id':'une-anim','retirer':True})
        self.assertEqual(json.loads(body)['animations_par_defaut'],[])

        code,_,_=self.request('/api/bibliotheque/presets/mon-style','DELETE')
        self.assertEqual(code,200)
        self.assertEqual([p['id'] for p in json.loads(self.request('/api/bibliotheque/presets')[2])['presets']],
                         ['depart'])

    def test_les_ecritures_refusent_ce_qui_sort_du_dossier(self):
        for chemin,corps in (('/api/bibliotheque/presets',{'nom':''}),
                             ('/api/bibliotheque/presets/defaut',{'preset_id':'../animations'}),
                             ('/api/bibliotheque/presets/depart',{'bloc':'encadre','cle':'inventee','valeur':1}),
                             ('/api/bibliotheque/presets/depart/animations',{'animation_id':'../une-anim'})):
            code,_,_=self.request(chemin,'POST',corps)
            self.assertIn(code,(400,404),chemin)
        # Le dernier preset ne se supprime pas : il resterait une bibliothèque sans style.
        self.assertEqual(self.request('/api/bibliotheque/presets/depart','DELETE')[0],400)


if __name__=='__main__':unittest.main()

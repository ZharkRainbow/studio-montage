import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from studio.store import (Store,Conflict,default_montage,montage_duration,montage_empreinte,montage_hash,
                          reel_to_source,source_table,source_to_reel,migrate,validate_project,summary)

SRC=dict(id='src',path='/local/rush.mp4',width=1080,height=1920,duration=60,fps=25,has_audio=True)


def rendu(path='/local/v1.mp4',duration=42.0):
    return dict(path=path,duration=duration,width=1080,height=1920,has_audio=True)


class MontageTimeTests(unittest.TestCase):
    def test_a_new_montage_keeps_the_whole_file(self):
        montage=default_montage(SRC)
        self.assertEqual(montage['segments'],[dict(start=0.0,end=60.0)])
        self.assertEqual((montage['title'],montage['hook'],montage['silence_backup']),('','',None))
        self.assertEqual(default_montage()['segments'],[])
        self.assertEqual(montage_duration(montage),60.0)

    def test_reel_time_points_at_the_right_second_of_the_source(self):
        # Deux blancs coupés : 0→10 gardé, 18→30 gardé, 40→50 gardé.
        montage=dict(segments=[dict(start=0,end=10),dict(start=18,end=30),dict(start=40,end=50)])
        self.assertEqual(montage_duration(montage),32.0)
        self.assertEqual(reel_to_source(montage,0),0.0)
        self.assertEqual(reel_to_source(montage,9.5),9.5)
        self.assertEqual(reel_to_source(montage,12.0),20.0)
        self.assertEqual(reel_to_source(montage,22.0),30.0)
        self.assertEqual(reel_to_source(montage,25.0),43.0)
        self.assertEqual(reel_to_source(montage,32.0),50.0)
        # Au-delà du montage, il n'y a pas de correspondance : mieux vaut rien qu'un temps faux.
        self.assertIsNone(reel_to_source(montage,32.5))
        self.assertIsNone(reel_to_source(montage,99.0))
        self.assertIsNone(reel_to_source(dict(segments=[]),5))

    def test_a_render_that_lasts_something_else_gets_no_source_table(self):
        montage=dict(segments=[dict(start=0,end=10),dict(start=18,end=30),dict(start=40,end=50)])
        # Le rendu dure ce que durent les morceaux gardés : la table vaut pour lui.
        self.assertEqual(source_table(dict(duration=32.0),montage),montage)
        self.assertEqual(source_table(dict(duration=32.4),montage),montage)
        # Un rendu plus long que le montage ne vient pas de ce montage.
        self.assertIsNone(source_table(dict(duration=62.5),montage))
        self.assertIsNone(source_table(dict(duration=32.0),dict(segments=[])))
        # Les morceaux figés au dépôt passent avant le montage d'aujourd'hui.
        frozen=dict(segments=[dict(start=0,end=62.5)])
        self.assertEqual(source_table(dict(duration=62.5,montage=frozen),montage),frozen)

    def test_source_time_comes_back_to_reel_time(self):
        montage=dict(segments=[dict(start=0,end=10),dict(start=18,end=30)])
        for reel in (0.0,4.25,10.0,11.5,21.9):
            self.assertAlmostEqual(source_to_reel(montage,reel_to_source(montage,reel)),reel,places=3)
        self.assertEqual(source_to_reel(montage,100),22.0)


class EmpreinteTests(unittest.TestCase):
    """L'empreinte du montage : elle dit si la vidéo relue montre encore le montage d'aujourd'hui."""

    def test_only_what_changes_the_picture_counts(self):
        montage=dict(segments=[dict(start=0,end=12)],hook='Accroche / étiquette',title='Titre',
                     blanks=[dict(start=12,end=20,cut=True)],silence_backup=[dict(start=0,end=60)])
        self.assertEqual(montage_empreinte(montage),
                         dict(segments=[dict(start=0.0,end=12.0)],hook='Accroche / étiquette'))
        # Un titre, un blanc repéré ou une sauvegarde d'avant-coupe ne changent pas l'image rendue.
        for autre in (dict(title='Autre titre'),dict(blanks=[]),dict(silence_backup=None)):
            self.assertEqual(montage_hash(montage|autre),montage_hash(montage))

    def test_recutting_the_beginning_changes_the_fingerprint(self):
        montage=dict(segments=[dict(start=0,end=12)],hook='Accroche')
        recoupe=dict(segments=[dict(start=1.5,end=12)],hook='Accroche')
        self.assertNotEqual(montage_hash(recoupe),montage_hash(montage))
        # Changer l'accroche change l'encadré, donc l'image : c'est un autre montage.
        self.assertNotEqual(montage_hash(montage|dict(hook='Autre')),montage_hash(montage))
        # Les mêmes bornes écrites autrement donnent la même empreinte.
        self.assertEqual(montage_hash(dict(segments=[dict(start=0,end=12.0)],hook=' Accroche ')),
                         montage_hash(montage))

    def test_an_empty_montage_still_has_one(self):
        self.assertEqual(montage_empreinte(None),dict(segments=[],hook=''))
        self.assertEqual(len(montage_hash(None)),16)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)
        self.p=self.store.create('Essai')
        self.p['sources']=[dict(SRC)]
        self.p['montage']=default_montage(SRC)
        self.p=self.store.save(self.p['id'],self.p,internal=True)

    def test_stale_save_preserves_newer_revision(self):
        old=copy.deepcopy(self.p)
        self.p['name']='Version récente'
        self.store.save(self.p['id'],self.p)
        old['name']='Ancienne version'
        with self.assertRaises(Conflict):self.store.save(old['id'],old)
        self.assertEqual(self.store.get(old['id'])['name'],'Version récente')

    def test_invalid_save_is_atomic(self):
        path=self.store.directory(self.p['id'])/'project.json'
        before=path.read_bytes()
        self.p['montage']['segments'][0]['end']=80
        with self.assertRaisesRegex(ValueError,'dépasse la durée'):self.store.save(self.p['id'],self.p)
        self.assertEqual(path.read_bytes(),before)

    def test_montage_is_what_the_editor_saves(self):
        self.p['montage'].update(segments=[dict(start=0,end=12),dict(start=20,end=40)],
                                 silence_backup=[dict(start=0,end=60)],title='Mon titre',hook='Reste jusqu’au bout')
        saved=self.store.save(self.p['id'],self.p)
        self.assertEqual(montage_duration(saved['montage']),32.0)
        self.assertEqual(saved['montage']['title'],'Mon titre')
        self.assertTrue(saved['montage']['silence_backup'])

    def test_a_title_stays_on_one_short_line(self):
        self.p['montage']['title']='Deux\nlignes'
        with self.assertRaisesRegex(ValueError,'une ligne'):self.store.save(self.p['id'],self.p)
        self.p=self.store.get(self.p['id'])
        self.p['montage']['hook']='x'*301
        with self.assertRaisesRegex(ValueError,'300 caractères'):self.store.save(self.p['id'],self.p)

    def test_unordered_segments_rejected(self):
        self.p['montage']['segments']=[dict(start=10,end=20),dict(start=5,end=15)]
        with self.assertRaisesRegex(ValueError,'ordonnés'):self.store.save(self.p['id'],self.p)

    def test_a_project_holds_one_file_only(self):
        self.p['sources']=[dict(SRC),dict(SRC,id='deux')]
        with self.assertRaisesRegex(ValueError,'un seul fichier'):validate_project(self.p)

    def test_source_paths_cannot_be_replaced_by_ui_save(self):
        self.p['sources'][0]['path']='/private/another.mp4'
        saved=self.store.save(self.p['id'],self.p)
        self.assertEqual(saved['sources'][0]['path'],'/local/rush.mp4')

    def test_nonfinite_numbers_rejected(self):
        self.p['montage']['segments'][0]['end']=float('nan')
        with self.assertRaises(ValueError):validate_project(self.p)

    def test_montage_file_sits_next_to_the_project(self):
        self.p['montage'].update(segments=[dict(start=0,end=12)],title='Titre',hook='Accroche',
                                 silence_backup=[dict(start=0,end=60)])
        self.store.save(self.p['id'],self.p)
        data=json.loads((self.store.directory(self.p['id'])/'montage.json').read_text())
        self.assertEqual(data['projet'],'Essai')
        self.assertEqual(data['fichier'],'/local/rush.mp4')
        self.assertEqual((data['titre'],data['accroche']),('Titre','Accroche'))
        self.assertEqual((data['duree_source'],data['duree_reel']),(60,12.0))
        self.assertEqual(data['duree_titre_secondes'],3.5)
        self.assertEqual(data['morceaux_gardes'],[dict(start=0,end=12)])
        self.assertTrue(data['blancs_coupes'])

    def test_project_id_cannot_escape_data_directory(self):
        with self.assertRaises(ValueError):self.store.get('../../escape')

    def test_removing_the_file_empties_the_montage(self):
        self.p['proxy_path']='/x/proxy.mp4'
        self.store.save(self.p['id'],self.p,internal=True)
        after=self.store.remove_source(self.p['id'])
        self.assertEqual((after['sources'],after['montage']['segments']),([],[]))
        self.assertNotIn('proxy_path',after)
        with self.assertRaises(FileNotFoundError):self.store.remove_source(self.p['id'])


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)
        self.p=self.store.create('Relecture')
        self.p['sources']=[dict(SRC)];self.p['montage']=default_montage(SRC)
        self.p=self.store.save(self.p['id'],self.p,internal=True)

    def test_versions_are_numbered_in_deposit_order_and_the_last_takes_over(self):
        p,v1=self.store.add_version(self.p['id'],'/local/v1.mp4',rendu())
        p,v2=self.store.add_version(p['id'],'/local/v2.mp4',rendu('/local/v2.mp4',40.5))
        self.assertEqual([v['index'] for v in p['versions']],[1,2])
        self.assertEqual(v1['transcript_state'],'pending')
        self.assertEqual(v1['transcript'],[])
        self.assertEqual((v2['duration'],p['active_version']),(40.5,v2['id']))
        self.assertEqual(self.store.active_version(p)['id'],v2['id'])
        self.assertEqual(self.store.set_active_version(p['id'],v1['id'])['active_version'],v1['id'])
        with self.assertRaises(FileNotFoundError):self.store.set_active_version(p['id'],'inconnue')

    def test_a_deposited_render_carries_the_fingerprint_of_its_montage(self):
        p,v1=self.store.add_version(self.p['id'],'/local/v1.mp4',rendu(duration=60.0))
        self.assertEqual(v1['montage_hash'],p['montage_hash'])
        # Recouper le début laisse la version derrière : c'est ce décalage que la relecture signale.
        p['montage']['segments']=[dict(start=2.0,end=60.0)]
        saved=self.store.save(p['id'],p,internal=True)
        self.assertNotEqual(saved['montage_hash'],saved['versions'][0]['montage_hash'])
        p,v2=self.store.add_version(saved['id'],'/local/v2.mp4',rendu('/local/v2.mp4',58.0))
        self.assertEqual(v2['montage_hash'],p['montage_hash'])

    def test_a_deposited_render_keeps_the_montage_that_made_it(self):
        p,v1=self.store.add_version(self.p['id'],'/local/v1.mp4',rendu(duration=60.0))
        self.assertEqual(v1['montage']['segments'],[dict(start=0.0,end=60.0)])
        # Couper encore des blancs ne réécrit pas la table du rendu déjà déposé.
        p['montage']['segments']=[dict(start=0.0,end=20.0),dict(start=30.0,end=60.0)]
        saved=self.store.save(p['id'],p,internal=True)
        self.assertEqual(saved['versions'][0]['montage']['segments'],[dict(start=0.0,end=60.0)])
        p,v2=self.store.add_version(p['id'],'/local/v2.mp4',rendu('/local/v2.mp4',50.0))
        self.assertEqual(v2['montage']['segments'],[dict(start=0.0,end=20.0),dict(start=30.0,end=60.0)])

    def test_an_unknown_displayed_version_falls_back_to_the_last_one(self):
        p,_=self.store.add_version(self.p['id'],'/local/v1.mp4',rendu())
        p['active_version']=None
        self.assertEqual(self.store.active_version(p)['index'],1)
        self.assertIsNone(self.store.active_version(dict(versions=[],active_version=None)))

    def test_fifty_versions_at_most(self):
        p=self.p
        for n in range(50):
            p,_=self.store.add_version(p['id'],f'/local/v{n}.mp4',rendu(f'/local/v{n}.mp4'))
        with self.assertRaisesRegex(ValueError,'50 versions'):self.store.add_version(p['id'],'/local/trop.mp4',rendu())

    def test_the_editor_cannot_invent_a_version(self):
        p,_=self.store.add_version(self.p['id'],'/local/v1.mp4',rendu())
        p['versions']=[]
        saved=self.store.save(p['id'],p)
        self.assertEqual(len(saved['versions']),1)

    def test_duplicate_copies_the_montage_not_the_versions(self):
        d=self.store.directory(self.p['id'])
        (d/'assets').mkdir(parents=True);(d/'assets'/'demo.mp4').write_bytes(b'video')
        (d/'artifacts'/'job').mkdir(parents=True);(d/'artifacts'/'job'/'proxy.mp4').write_bytes(b'proxy')
        p=self.store.get(self.p['id'])
        p['sources']=[dict(SRC,path=str(d/'assets'/'demo.mp4'))]
        p.update(proxy_path=str(d/'artifacts'/'job'/'proxy.mp4'),proxy_format='h264-720p-natif-gop10',demo=True)
        p['montage']['title']='Garde ça'
        p=self.store.save(p['id'],p,internal=True)
        p,_=self.store.add_version(p['id'],'/local/v1.mp4',rendu())
        copy_=self.store.duplicate(p['id'])
        nd=self.store.directory(copy_['id'])
        self.assertEqual(copy_['name'],'Relecture (copie)')
        self.assertEqual(copy_['montage']['title'],'Garde ça')
        self.assertEqual(copy_['versions'],[]);self.assertIsNone(copy_['active_version'])
        self.assertEqual(copy_['sources'][0]['path'],str(nd/'assets'/'demo.mp4'))
        self.assertTrue(Path(copy_['proxy_path']).is_file())
        self.assertNotIn('demo',copy_)
        self.assertTrue(json.loads((nd/'montage.json').read_text())['titre']=='Garde ça')
        self.assertEqual(len(self.store.get(p['id'])['versions']),1)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)
        self.p=self.store.create('Consulting')

    def test_rename_validates_name(self):
        self.assertEqual(self.store.rename(self.p['id'],'  Nouveau nom ')['name'],'Nouveau nom')
        with self.assertRaises(ValueError):self.store.rename(self.p['id'],'   ')

    def test_folder_lifecycle_never_deletes_projects(self):
        folder=self.store.create_folder('  Clients ')
        self.assertEqual(folder['name'],'Clients')
        with self.assertRaisesRegex(ValueError,'déjà'):self.store.create_folder('clients')
        self.store.move(self.p['id'],folder['id'])
        self.assertEqual(self.store.list()[0]['folder_id'],folder['id'])
        self.assertEqual(self.store.rename_folder(folder['id'],'Clients 2026')['name'],'Clients 2026')
        self.assertEqual(self.store.delete_folder(folder['id']),1)
        self.assertEqual(self.store.folders(),[])
        self.assertIsNone(self.store.list()[0]['folder_id'])
        self.assertEqual(len(self.store.list()),1)

    def test_move_to_unknown_folder_rejected(self):
        with self.assertRaises(FileNotFoundError):self.store.move(self.p['id'],'nope')

    def test_folder_and_favorite_survive_stale_editor_save(self):
        folder=self.store.create_folder('Masterclass')
        stale=self.store.get(self.p['id'])
        self.store.move(self.p['id'],folder['id']);self.store.set_favorite(self.p['id'],True)
        fresh=self.store.get(self.p['id'])
        stale['revision']=fresh['revision'];stale['name']='Renommé depuis l’éditeur'
        saved=self.store.save(self.p['id'],stale)
        self.assertEqual(saved['folder_id'],folder['id']);self.assertTrue(saved['favorite'])

    def test_ne_pas_garder_sort_le_projet_de_la_boucle_sans_le_supprimer(self):
        self.store.set_ecarte(self.p['id'],True)
        item=self.store.list()[0]
        self.assertEqual(item['status'],'ecarte');self.assertTrue(item['ecarte_le'])
        with self.assertRaisesRegex(ValueError,'écarté'):self.store.set_validated(self.p['id'],True)
        with self.assertRaisesRegex(ValueError,'écarté'):self.store.ensure_garde(self.p['id'])
        # Une sauvegarde de l'éditeur ne le remet pas en jeu par accident.
        stale=self.store.get(self.p['id']);stale.pop('ecarte_le',None)
        self.assertTrue(self.store.save(self.p['id'],stale).get('ecarte_le'))
        lignes=[json.loads(l) for l in (self.store.root/'validations.jsonl').read_text().splitlines()]
        self.assertEqual((lignes[-1]['ecarte'],lignes[-1]['validated'],lignes[-1]['project_id']),(True,False,self.p['id']))
        self.store.set_ecarte(self.p['id'],False)
        self.assertNotEqual(self.store.list()[0]['status'],'ecarte');self.assertIsNone(self.store.list()[0]['ecarte_le'])
        self.store.ensure_garde(self.p['id'])
        with self.assertRaises(ValueError):self.store.set_ecarte(self.p['id'],'oui')

    def test_summary_status_progression(self):
        self.assertEqual(self.store.list()[0]['status'],'empty')
        p=self.store.get(self.p['id'])
        p['sources']=[dict(SRC)];p['montage']=default_montage(SRC)
        p=self.store.save(p['id'],p,internal=True)
        item=self.store.list()[0]
        self.assertEqual((item['status'],item['duration'],item['reel_duration']),('imported',60,60.0))
        p['montage'].update(segments=[dict(start=0,end=12)],silence_backup=[dict(start=0,end=60)],title='Titre')
        p=self.store.save(p['id'],p,internal=True)
        item=self.store.list()[0]
        self.assertEqual((item['status'],item['reel_duration'],item['trimmed'],item['title']),('montage',12.0,True,'Titre'))
        p,_=self.store.add_version(p['id'],'/local/v1.mp4',rendu())
        item=self.store.list()[0]
        self.assertEqual((item['status'],item['version_count']),('review',1))

    def test_trash_moves_folder_without_touching_sources(self):
        home=Path(self.tmp.name)/'home';(home/'.Trash').mkdir(parents=True)
        rush=Path(self.tmp.name)/'rush.mp4';rush.write_bytes(b'rush')
        p=self.store.get(self.p['id'])
        p['sources']=[dict(SRC,path=str(rush))];self.store.save(p['id'],p,internal=True)
        with mock.patch.object(Path,'home',return_value=home):
            target=self.store.trash(self.p['id'])
        self.assertTrue((target/'project.json').is_file());self.assertEqual(target.parent,home/'.Trash')
        self.assertTrue(rush.is_file())
        with self.assertRaises(FileNotFoundError):self.store.get(self.p['id'])
        self.assertEqual(self.store.list(),[])

    def test_trash_falls_back_to_studio_folder(self):
        home=Path(self.tmp.name)/'no-home-trash';home.mkdir()
        (home/'.Trash').write_text('not a directory')
        with mock.patch.object(Path,'home',return_value=home):
            target=self.store.trash(self.p['id'])
        self.assertEqual(target.parent,self.store.root/'corbeille')


class ValidationTests(unittest.TestCase):
    """Valider un short : l'état « Validé », la demande de production, le journal, et le retour en arrière."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)
        self.p=self.store.create('Short 1')
        self.p['sources']=[dict(SRC)]
        self.p['montage']=default_montage(SRC)
        self.p['montage'].update(segments=[dict(start=0,end=12),dict(start=20,end=30)],title='Titre',
                                 hook='Accroche',blanks=[dict(start=12,end=20,cut=True),dict(start=40,end=41,cut=False)])
        self.p=self.store.save(self.p['id'],self.p,internal=True)

    def journal(self):
        path=Path(self.tmp.name)/'validations.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def demande(self):
        return self.store.directory(self.p['id'])/'a-produire'/(self.p['id']+'.json')

    def test_validating_writes_the_production_request(self):
        updated=self.store.set_validated(self.p['id'],True)
        self.assertTrue(updated['validated_at'])
        self.assertEqual(self.store.list()[0]['status'],'done')
        data=json.loads(self.demande().read_text())
        self.assertEqual(data['projet'],'Short 1')
        self.assertEqual(data['consigne'],f'/montage-reels produis la V1 de {self.store.directory(self.p["id"])}')
        self.assertEqual(data['morceaux_gardes'],[dict(start=0.0,end=12.0),dict(start=20.0,end=30.0)])
        # Seuls les blancs vraiment coupés partent en production : ceux laissés à l'œil ne comptent pas.
        self.assertEqual(data['blancs_coupes'],[dict(start=12.0,end=20.0,cut=True)])
        self.assertEqual((data['titre'],data['accroche'],data['export']),('Titre','Accroche','en-attente'))
        self.assertEqual(updated['production']['consigne'],data['consigne'])
        self.assertEqual(updated['production']['path'],str(self.demande()))
        # Le montage part en relecture avant d'être validé : l'export est déjà là, la demande le dit.
        self.store.mutate(self.p['id'],lambda p:p.update(export=dict(path='/local/Montages validés/Short 1.mp4',
                                                                     remux=False,bytes=1234,state='fait')))
        self.store.set_validated(self.p['id'],True)
        self.assertEqual(json.loads(self.demande().read_text())['export'],'fait')

    def test_the_journal_keeps_one_line_per_validation(self):
        self.store.set_validated(self.p['id'],True)
        self.store.set_validated(self.p['id'],False)
        lines=self.journal()
        self.assertEqual([line['validated'] for line in lines],[True,False])
        self.assertEqual(lines[0]['name'],'Short 1')
        self.assertEqual(lines[0]['step'],'review')
        self.assertEqual(lines[0]['source'],'/local/rush.mp4')
        self.assertEqual(lines[0]['title'],'Titre')
        self.assertTrue(lines[0]['a_produire'].endswith(self.p['id']+'.json'))
        self.assertIsNone(lines[1]['a_produire'])

    def test_going_back_loses_nothing_of_the_montage(self):
        self.store.set_validated(self.p['id'],True)
        self.store.mutate(self.p['id'],lambda p:p.update(export=dict(path='/local/Montages validés/Short 1.mp4',
                                                                     remux=True,bytes=1234,state='fait')))
        back=self.store.set_validated(self.p['id'],False)
        self.assertIsNone(back['validated_at'])
        self.assertNotIn('production',back)
        self.assertFalse(self.demande().exists())
        # Le montage et le fichier déjà exporté restent : revenir en arrière n'efface pas le travail.
        self.assertEqual(back['montage']['segments'],[dict(start=0.0,end=12.0),dict(start=20.0,end=30.0)])
        self.assertEqual((back['montage']['title'],back['montage']['hook']),('Titre','Accroche'))
        self.assertEqual(len(back['montage']['blanks']),2)
        self.assertEqual(back['export']['path'],'/local/Montages validés/Short 1.mp4')
        self.assertEqual(self.store.list()[0]['status'],'montage')
        again=self.store.set_validated(self.p['id'],True)
        self.assertTrue(again['validated_at'])
        self.assertTrue(self.demande().exists())

    def test_validating_a_reread_marks_the_shown_version_as_final(self):
        p,v1=self.store.add_version(self.p['id'],'/local/v1.mp4',rendu())
        p,v2=self.store.add_version(self.p['id'],'/local/v2.mp4',rendu('/local/v2.mp4'))
        updated=self.store.set_validated(self.p['id'],True,step='review',version_id=v1['id'])
        finals=[v['id'] for v in updated['versions'] if v.get('final')]
        self.assertEqual(finals,[v1['id']])
        self.assertTrue(next(v for v in updated['versions'] if v['id']==v1['id'])['validated_at'])
        self.assertNotIn('validated_at',next(v for v in updated['versions'] if v['id']==v2['id']))
        # Valider en relecture, c'est valider le short : la demande de production part de là.
        self.assertTrue(updated['production']['path'])
        self.assertEqual(self.journal()[0]['step'],'review')
        back=self.store.set_validated(self.p['id'],False,step='review')
        self.assertFalse([v['id'] for v in back['versions'] if v.get('final')])

    def test_validation_refuses_what_it_cannot_do(self):
        with self.assertRaisesRegex(ValueError,'validation invalide'):self.store.set_validated(self.p['id'],'oui')
        # On ne valide plus qu'en relecture : le montage n'est plus une étape de validation.
        for etape in ('montage','export'):
            with self.assertRaisesRegex(ValueError,'inconnue'):self.store.set_validated(self.p['id'],True,step=etape)
        with self.assertRaises(FileNotFoundError):
            self.store.set_validated(self.p['id'],True,step='review',version_id='nope')
        self.assertIsNone(self.store.get(self.p['id']).get('validated_at'))


class MigrationTests(unittest.TestCase):
    def test_an_old_project_keeps_its_file_its_bounds_its_title_and_its_hook(self):
        old=dict(schema_version=2,id='a'*16,name='Ancien',revision=7,created_at='2026-01-01T00:00:00+00:00',
                 updated_at='2026-01-02T00:00:00+00:00',sources=[dict(SRC)],folder_id='f1',favorite=True,
                 clips=[dict(validated=True,segments=[dict(start=2,end=12),dict(start=20,end=30)],
                             title='Titre d’avant',hook='Accroche d’avant',points=[dict(label='Jordy')],
                             composition=dict(kind='split'),captions=[dict(start=0,end=1,text='x')],
                             render_path='/vieux/rendu.mp4')])
        p=migrate(old)
        validate_project(p)
        self.assertEqual(p['schema_version'],3)
        self.assertEqual(p['montage']['segments'],[dict(start=2.0,end=12.0),dict(start=20.0,end=30.0)])
        self.assertEqual((p['montage']['title'],p['montage']['hook']),('Titre d’avant','Accroche d’avant'))
        self.assertEqual((p['versions'],p['active_version']),([],None))
        self.assertEqual((p['revision'],p['folder_id'],p['favorite']),(7,'f1',True))
        for gone in ('clips','captions','points','composition'):
            self.assertNotIn(gone,p)

    def test_a_v3_project_without_versions_is_completed_not_rewritten(self):
        p=migrate(dict(schema_version=3,id='b'*16,name='Neuf',revision=1,created_at='x',updated_at='y',
                       sources=[dict(SRC)]))
        self.assertEqual(p['montage']['segments'],[dict(start=0.0,end=60.0)])
        self.assertEqual((p['versions'],p['active_version']),([],None))


def _cues(phrase, depart=0.0):
    """Whisper rend un mot par repère : on imite la forme exacte de ce qu'il écrit."""
    return [dict(id=f'c{i}', start=round(depart + i * 0.5, 3), end=round(depart + i * 0.5 + 0.4, 3), text=mot)
            for i, mot in enumerate(phrase.split())]


def _projet_parlant(store, nom, phrase, version=None):
    p = store.create(nom)
    p['sources'] = [dict(id='s1', path='/local/rush.mp4', duration=120.0)]
    p['source_transcript'] = _cues(phrase)
    p['source_transcript_state'] = 'ready'
    if version:
        p['versions'] = [dict(id='v1', index=1, path='/local/v1.mp4', duration=30.0,
                              created_at='2026-10-21T10:00:00Z', transcript=_cues(version, 4.0),
                              transcript_state='ready')]
        p['active_version'] = 'v1'
    store.save(p['id'], p, internal=True)
    return p


# --- Repointer un média déplacé (A6) ---
class RepointerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name).resolve()  # macOS : /var est un lien vers /private/var
        self.addCleanup(self._tmp.cleanup)

    def test_repointer_suit_le_fichier_et_ce_qui_vivait_a_cote(self):
        """L'utilisateur range ses dossiers : le projet retrouve sa source, ses versions et son export."""
        tmp_path = self.tmp_path
        ancien, nouveau = tmp_path / 'avant', tmp_path / 'apres'
        ancien.mkdir(); nouveau.mkdir()
        rush = ancien / 'entretien.mp4'; rush.write_bytes(b'rush')
        v1 = ancien / 'v1.mp4'; v1.write_bytes(b'v1')
        export = ancien / 'export.mp4'; export.write_bytes(b'export')

        store = Store(tmp_path / 'data')
        p = store.create('Entretien')
        p['sources'] = [dict(id='s1', path=str(rush), duration=12.0)]
        p['versions'] = [dict(id='v1', index=1, path=str(v1), created_at='2026-10-21T10:00:00Z')]
        p['export'] = dict(path=str(export), state='fait')
        store.save(p['id'], p, internal=True)

        for fichier in (rush, v1, export):
            fichier.rename(nouveau / fichier.name)

        assert summary(store.get(p['id']))['media_missing'] is True

        repointe = store.repointer(p['id'], str(nouveau / 'entretien.mp4'))
        assert repointe['sources'][0]['path'] == str(nouveau / 'entretien.mp4')
        assert repointe['versions'][0]['path'] == str(nouveau / 'v1.mp4')
        assert repointe['export']['path'] == str(nouveau / 'export.mp4')
        assert summary(store.get(p['id']))['media_missing'] is False

    def test_repointer_refuse_un_chemin_qui_n_existe_pas(self):
        tmp_path = self.tmp_path
        store = Store(tmp_path / 'data')
        rush = tmp_path / 'entretien.mp4'; rush.write_bytes(b'rush')
        p = store.create('Entretien')
        p['sources'] = [dict(id='s1', path=str(rush), duration=12.0)]
        store.save(p['id'], p, internal=True)
        with self.assertRaises(FileNotFoundError):
            store.repointer(p['id'], str(tmp_path / 'nulle-part.mp4'))
        assert store.get(p['id'])['sources'][0]['path'] == str(rush)

    def test_repointer_laisse_en_place_ce_qui_vivait_ailleurs(self):
        """Une version rangée dans un autre dossier n'est pas déplacée par erreur."""
        tmp_path = self.tmp_path
        ancien, nouveau, ailleurs = tmp_path / 'avant', tmp_path / 'apres', tmp_path / 'ailleurs'
        for d in (ancien, nouveau, ailleurs):
            d.mkdir()
        rush = ancien / 'entretien.mp4'; rush.write_bytes(b'rush')
        v1 = ailleurs / 'v1.mp4'; v1.write_bytes(b'v1')
        store = Store(tmp_path / 'data')
        p = store.create('Entretien')
        p['sources'] = [dict(id='s1', path=str(rush), duration=12.0)]
        p['versions'] = [dict(id='v1', index=1, path=str(v1), created_at='2026-10-21T10:00:00Z')]
        store.save(p['id'], p, internal=True)
        rush.rename(nouveau / rush.name)
        repointe = store.repointer(p['id'], str(nouveau / 'entretien.mp4'))
        assert repointe['versions'][0]['path'] == str(v1)


# --- Chercher une phrase dite (A6) ---
class RechercheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name).resolve()  # macOS : /var est un lien vers /private/var
        self.addCleanup(self._tmp.cleanup)

    def test_la_recherche_traverse_les_mots_et_ignore_les_accents(self):
        tmp_path = self.tmp_path
        store = Store(tmp_path / 'data')
        _projet_parlant(store, 'Entretien', "on a change de methode l an dernier et ca a tout change")

        trouve = store.recherche('CHANGÉ DE MÉTHODE')
        assert len(trouve['extraits']) == 1
        extrait = trouve['extraits'][0]
        assert extrait['project_name'] == 'Entretien'
        assert extrait['piste'] == 'le rush'
        assert extrait['start'] == 1.0
        # L'extrait se relit : les mots d'avant et d'après sont là, tels qu'ils ont été dits.
        assert 'on a change de methode l an dernier' in extrait['texte']

    def test_la_recherche_dit_dans_quelle_piste_elle_a_trouve(self):
        tmp_path = self.tmp_path
        store = Store(tmp_path / 'data')
        _projet_parlant(store, 'Entretien', "le rush parle de budget", version="la version parle de budget aussi")
        pistes = {e['piste']: e['start'] for e in store.recherche('budget')['extraits']}
        assert pistes == {'le rush': 2.0, 'V1': 6.0}

    def test_une_requete_trop_courte_ne_cherche_rien(self):
        tmp_path = self.tmp_path
        store = Store(tmp_path / 'data')
        _projet_parlant(store, 'Entretien', "ab ab ab ab")
        assert store.recherche('ab') == dict(extraits=[], total=0, tronque=False)
        assert store.recherche('  ') == dict(extraits=[], total=0, tronque=False)

    def test_la_recherche_ne_repete_pas_le_meme_passage(self):
        """Trois projets, trois passages au plus par piste, et le compte dit ce qui est caché."""
        tmp_path = self.tmp_path
        store = Store(tmp_path / 'data')
        mot = ' '.join(['budget'] * 60)
        for nom in ('Un', 'Deux', 'Trois'):
            _projet_parlant(store, nom, mot)
        trouve = store.recherche('budget', limite=4)
        assert len(trouve['extraits']) == 4
        assert trouve['total'] == 9 and trouve['tronque'] is True
        # Deux extraits de la même piste ne citent pas le même instant.
        for nom in ('Un', 'Deux', 'Trois'):
            departs = [e['start'] for e in trouve['extraits'] if e['project_name'] == nom]
            assert len(departs) == len(set(departs))

    def test_un_projet_sans_transcript_ne_gene_pas_la_recherche(self):
        tmp_path = self.tmp_path
        store = Store(tmp_path / 'data')
        muet = store.create('Muet')
        store.save(muet['id'], muet, internal=True)
        _projet_parlant(store, 'Parlant', "il reste du budget pour octobre")
        trouve = store.recherche('budget')
        assert [e['project_name'] for e in trouve['extraits']] == ['Parlant']


if __name__=='__main__':unittest.main()

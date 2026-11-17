"""Les retours d'une version : horodatage, captures, et la consigne copiée pour Claude."""
import base64
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
import zlib

from studio import retours
from studio.store import Store

MONTAGE = dict(segments=[dict(start=0, end=10), dict(start=18, end=30), dict(start=40, end=50)],
               title='Titre', hook='Accroche', silence_backup=None)


def png(width=4, height=4):
    def chunk(kind, payload):
        raw = kind + payload
        return struct.pack('>I', len(payload)) + raw + struct.pack('>I', zlib.crc32(raw))
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    rows = b''.join(b'\x00' + b'\x00\x00\x00' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def data_url(payload=None):
    return 'data:image/png;base64,' + base64.b64encode(payload or png()).decode('ascii')


class TimecodeTests(unittest.TestCase):
    def test_a_timecode_shows_minutes_seconds_and_hundredths(self):
        self.assertEqual(retours.timecode(0), '00:00.00')
        self.assertEqual(retours.timecode(10.5), '00:10.50')
        self.assertEqual(retours.timecode(9.999), '00:10.00')
        self.assertEqual(retours.timecode(65.25), '01:05.25')
        self.assertEqual(retours.timecode(3600), '60:00.00')
        # Un temps négatif n'existe pas dans une vidéo : il est ramené à zéro.
        self.assertEqual(retours.timecode(-4), '00:00.00')

    def test_the_feedback_list_drops_the_hundredths(self):
        self.assertEqual(retours.short_timecode(0), '0:00')
        self.assertEqual(retours.short_timecode(36.9), '0:36')
        self.assertEqual(retours.short_timecode(125), '2:05')

    def test_a_date_is_said_in_french_and_a_broken_one_is_admitted(self):
        self.assertRegex(retours.french_datetime('2026-03-07T14:05:00+01:00'), r'^7 mars à \d{2}:\d{2}$')
        self.assertEqual(retours.french_datetime('pas une date'), 'date inconnue')
        self.assertEqual(retours.french_datetime(None), 'date inconnue')


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.project = self.store.create('Reel')
        self.pid = self.project['id']

    def entry(self, **data):
        return retours.validate_entry(self.store, self.pid, data, 32.0)

    def test_a_feedback_keeps_its_time_its_words_and_its_request(self):
        item = self.entry(start=10.504, end=14.313, text='  Coupe ce passage  ', quote='et donc voilà')
        self.assertEqual((item['start'], item['end']), (10.5, 14.31))
        self.assertEqual((item['text'], item['quote']), ('Coupe ce passage', 'et donc voilà'))
        self.assertEqual((item['type'], item['resolved'], item['images']), ('comment', False, []))
        self.assertEqual(len(item['id']), 16)
        self.assertTrue(item['created_at'] and item['updated_at'])

    def test_a_feedback_without_a_request_is_refused(self):
        with self.assertRaisesRegex(retours.RetourError, 'obligatoire'):
            self.entry(start=1, text='   ')
        with self.assertRaisesRegex(retours.RetourError, 'dépasse 2000'):
            self.entry(start=1, text='x' * 2001)
        with self.assertRaisesRegex(retours.RetourError, 'texte attendu'):
            self.entry(start=1, text=12)

    def test_a_range_that_ends_where_it_starts_becomes_a_single_point(self):
        self.assertIsNone(self.entry(start=5, end=5.005, text='ici')['end'])
        self.assertIsNone(self.entry(start=5, end=2, text='ici')['end'])
        self.assertEqual(self.entry(start=5, end=6, text='ici')['end'], 6.0)

    def test_a_feedback_outside_the_version_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Début du retour'):
            self.entry(start=99, text='hors limites')
        with self.assertRaisesRegex(ValueError, 'Début du retour'):
            self.entry(start=float('nan'), text='pas un nombre')

    def test_only_a_comment_or_a_cut_is_accepted(self):
        self.assertEqual(self.entry(start=1, type='cut', text='coupe')['type'], 'cut')
        with self.assertRaisesRegex(retours.RetourError, 'Type de retour inconnu'):
            self.entry(start=1, type='musique', text='non')

    def test_editing_a_feedback_keeps_its_id_and_its_creation_date(self):
        first = self.entry(start=4, text='première idée')
        second = retours.validate_entry(self.store, self.pid, dict(text='idée revue'), 32.0, existing=first)
        self.assertEqual(second['id'], first['id'])
        self.assertEqual(second['created_at'], first['created_at'])
        self.assertEqual((second['start'], second['text']), (4.0, 'idée revue'))

    def test_a_drawing_lands_beside_the_feedback_as_a_png(self):
        item = self.entry(start=2, text='vois le dessin', images=[data_url()])
        self.assertRegex(item['images'][0], r'^images/[a-f0-9]{16}\.png$')
        stored = retours.directory(self.store, self.pid) / item['images'][0]
        self.assertEqual(stored.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        # Une capture déjà enregistrée n'est pas réécrite au prochain enregistrement.
        again = retours.validate_entry(self.store, self.pid, dict(images=item['images']), 32.0, existing=item)
        self.assertEqual(again['images'], item['images'])
        self.assertEqual(len(list((retours.directory(self.store, self.pid) / 'images').iterdir())), 1)

    def test_anything_that_is_not_a_png_is_refused(self):
        for bad in ('data:image/jpeg;base64,' + base64.b64encode(b'x').decode(),
                    'data:image/png;base64,' + base64.b64encode(b'pas un png').decode(),
                    'data:image/png;base64,###',
                    'https://exemple.test/capture.png', 42):
            with self.assertRaises(retours.RetourError, msg=repr(bad)[:40]):
                self.entry(start=1, text='capture', images=[bad])
        with self.assertRaisesRegex(retours.RetourError, 'Au plus 6 captures'):
            self.entry(start=1, text='trop', images=[data_url()] * 7)

    def test_a_capture_heavier_than_four_megabytes_is_refused(self):
        heavy = 'data:image/png;base64,' + 'A' * (retours.MAX_IMAGE_BYTES * 4 // 3 + 64)
        with self.assertRaisesRegex(retours.RetourError, 'trop lourde'):
            self.entry(start=1, text='énorme', images=[heavy])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.pid = self.store.create('Reel')['id']

    def test_feedback_lives_in_one_file_per_version(self):
        retours.save(self.store, self.pid, 2, [dict(id='a', text='un', resolved=False)])
        path = retours.directory(self.store, self.pid) / 'v2.json'
        saved = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(saved['version'], 2)
        self.assertEqual(len(saved['retours']), 1)
        self.assertTrue(saved['updated_at'])
        self.assertEqual(retours.load(self.store, self.pid, 2)['retours'], saved['retours'])

    def test_a_version_without_feedback_reads_as_empty_not_as_an_error(self):
        empty = retours.load(self.store, self.pid, 1)
        self.assertEqual((empty['version'], empty['retours'], empty['updated_at']), (1, [], None))
        self.assertEqual(retours.counts(self.store, self.pid, 1), dict(total=0, open=0, resolved=0))

    def test_an_impossible_version_number_is_refused(self):
        for bad in (0, 51, -1, 1.5, '1', None):
            with self.assertRaises(retours.RetourError, msg=repr(bad)):
                retours.path_for(self.store, self.pid, bad)

    def test_a_broken_feedback_file_is_reported_not_silently_emptied(self):
        path = retours.directory(self.store, self.pid) / 'v1.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{ pas du json', encoding='utf-8')
        with self.assertRaisesRegex(retours.RetourError, 'illisible'):
            retours.load(self.store, self.pid, 1)

    def test_a_file_that_lost_its_shape_reads_as_empty(self):
        path = retours.directory(self.store, self.pid) / 'v1.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[]', encoding='utf-8')
        self.assertEqual(retours.load(self.store, self.pid, 1)['retours'], [])

    def test_open_and_resolved_feedback_are_counted_apart(self):
        retours.save(self.store, self.pid, 1, [dict(id='a', resolved=True), dict(id='b'), dict(id='c', resolved=False)])
        self.assertEqual(retours.counts(self.store, self.pid, 1), dict(total=3, open=2, resolved=1))

    def test_a_version_never_holds_more_than_four_hundred_feedback(self):
        with self.assertRaisesRegex(retours.RetourError, 'Au plus 400 retours'):
            retours.save(self.store, self.pid, 1, [dict(id=str(i)) for i in range(401)])


class ConsigneTests(unittest.TestCase):
    """Le format du brief, au caractère près, avec les temps SOURCE recalculés."""

    def setUp(self):
        self.project = dict(id='p', name='Reel 42', montage=MONTAGE)
        self.version = dict(index=1, path='/local/renders/v1.mp4', duration=32.0,
                            added_at='2026-03-07T14:05:00+01:00')
        self.dir = Path('/local/projets/p')

    def text(self, items):
        return retours.consigne(self.project, self.version, items, self.dir)

    def test_the_header_names_the_reel_the_file_and_the_number_of_changes(self):
        lines = self.text([]).splitlines()
        self.assertEqual(lines[0], '/montage-reels applique ces retours au reel Reel 42 (/local/projets/p)')
        self.assertEqual(lines[1], '')
        self.assertIn('Vidéo relue : /local/renders/v1.mp4, version du 7 mars à ', lines[2])
        self.assertTrue(lines[2].endswith('durée 00:32.00 (32.00 s).'))
        self.assertEqual(lines[3], '0 changement à appliquer :')

    def test_one_change_is_said_in_the_singular(self):
        text = self.text([dict(id='a1', type='comment', start=1.0, end=None, text='garde ça')])
        self.assertIn('1 changement à appliquer :', text)
        self.assertNotIn('changements', text)

    def test_a_point_feedback_gives_the_reel_time_and_the_source_time(self):
        text = self.text([dict(id='abc123', type='cut', start=22.0, end=None, text='coupe cette phrase')])
        self.assertIn('1. COUPE à 00:22.00 (REEL 22.00 s) · SOURCE 30.00 s [id abc123]', text)
        self.assertIn('   Demande : coupe cette phrase', text)

    def test_a_range_feedback_gives_both_ends_its_length_and_the_source_window(self):
        text = self.text([dict(id='plage1', type='comment', start=10.5, end=14.31,
                               text='reprends cette partie', quote='et donc voilà')])
        self.assertIn('1. COMMENTAIRE de 00:10.50 à 00:14.31 (REEL 10.50 s → 14.31 s, 3.81 s)'
                      ' · SOURCE 18.50 s → 22.31 s [id plage1]', text)
        self.assertIn('   Mots : "et donc voilà"', text)

    def test_the_captures_are_given_as_full_local_paths(self):
        text = self.text([dict(id='dessin', type='comment', start=2.0, end=None, text='vois le dessin',
                               images=['images/0123456789abcdef.png', 'images/fedcba9876543210.png'])])
        self.assertIn('   Captures : /local/projets/p/retours/images/0123456789abcdef.png, '
                      '/local/projets/p/retours/images/fedcba9876543210.png', text)

    def test_the_changes_are_numbered_in_order_and_the_text_ends_with_one_newline(self):
        text = self.text([dict(id='a', type='comment', start=1.0, end=None, text='un'),
                          dict(id='b', type='cut', start=5.0, end=None, text='deux'),
                          dict(id='c', type='comment', start=9.0, end=None, text='trois')])
        self.assertIn('3 changements à appliquer :', text)
        heads = [line.split('.')[0] for line in text.splitlines() if re.match(r'^\d+\. ', line)]
        self.assertEqual(heads, ['1', '2', '3'])
        self.assertTrue(text.endswith('   Demande : trois\n'))
        self.assertFalse(text.endswith('\n\n'))

    def test_the_very_last_kept_frame_still_has_a_source_time(self):
        text = self.text([dict(id='fin', type='comment', start=32.0, end=None, text='la toute fin')])
        self.assertIn('1. COMMENTAIRE à 00:32.00 (REEL 32.00 s) · SOURCE 50.00 s [id fin]', text)


class SourceTimeTests(unittest.TestCase):
    """Un temps SOURCE faux enverrait Claude au mauvais endroit : mieux vaut dire qu'il manque."""

    def setUp(self):
        self.project = dict(id='p', name='Reel 42', montage=MONTAGE)
        self.dir = Path('/local/projets/p')

    def text(self, version, items):
        return retours.consigne(self.project, version, items, self.dir)

    def version(self, duration, **extra):
        return dict(index=1, path='/local/renders/v1.mp4', duration=duration,
                    added_at='2026-03-07T14:05:00+01:00', **extra)

    def test_a_render_longer_than_the_montage_gets_no_source_time_at_all(self):
        # Le cas de l'audit : 32 s de morceaux gardés, un MP4 de 62,5 s.
        text = self.text(self.version(62.5), [dict(id='fin', type='comment', start=60.0, end=61.0,
                                                   text='tout près de la fin')])
        self.assertIn('Temps SOURCE indisponibles : les morceaux gardés durent 32.00 s, '
                      'la vidéo relue 62.50 s.', text)
        self.assertIn('(REEL 60.00 s → 61.00 s, 1.00 s) · SOURCE indisponible [id fin]', text)
        self.assertNotIn('SOURCE 50.00', text)

    def test_the_montage_frozen_at_deposit_wins_over_the_one_of_the_day(self):
        frozen = dict(segments=[dict(start=0, end=20), dict(start=30, end=42.5)])
        text = self.text(self.version(32.5, montage=frozen),
                         [dict(id='a', type='comment', start=25.0, end=None, text='ici')])
        self.assertNotIn('Temps SOURCE indisponibles', text)
        # 25 s de reel : 20 s dans le premier morceau, puis 5 s après 30 s.
        self.assertIn('· SOURCE 35.00 s [id a]', text)

    def test_a_feedback_past_the_kept_pieces_says_so_instead_of_inventing(self):
        text = self.text(self.version(32.0), [dict(id='trop', type='comment', start=32.4, end=None,
                                                   text='après le dernier morceau')])
        self.assertNotIn('Temps SOURCE indisponibles', text)
        self.assertIn('(REEL 32.40 s) · SOURCE hors des morceaux gardés [id trop]', text)

    def test_a_project_without_a_montage_says_why_the_source_times_are_missing(self):
        self.project = dict(id='p', name='Reel 42', montage=dict(segments=[]))
        text = self.text(self.version(32.0), [dict(id='a', type='comment', start=1.0, end=None, text='ici')])
        self.assertIn('aucun montage n’est enregistré', text)
        self.assertIn('· SOURCE indisponible [id a]', text)

    def test_nothing_is_said_when_the_render_matches_the_montage(self):
        self.assertIsNone(retours.source_notice(self.project, self.version(32.0)))
        self.assertIsNotNone(retours.source_notice(self.project, self.version(62.5)))


if __name__ == '__main__':
    unittest.main()

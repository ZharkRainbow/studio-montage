"""La transcription locale : lecture des sorties Whisper, recollage des blocs, tri des hallucinations."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from studio import speech

SRT = """1
00:00:00,000 --> 00:00:02,500
Bonjour à tous

2
00:00:02,500 --> 00:00:05,000
on attaque le montage
"""

VTT = """WEBVTT
X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0

NOTE une remarque
sur deux lignes

00:00.000 --> 00:01.200
Première phrase

cue-2
00:01.200 --> 00:02.400
Deuxième phrase
"""

WORDS = """1
00:00:00,000 --> 00:00:00,000


2
00:00:00,120 --> 00:00:00,340
Bonjour

3
00:00:00,340 --> 00:00:00,340
à

4
00:00:00,360 --> 00:00:00,700
tous
"""


class TimestampTests(unittest.TestCase):
    def test_a_timestamp_is_read_in_seconds(self):
        self.assertAlmostEqual(speech._parse_timestamp('00:00:02,500'), 2.5)
        self.assertAlmostEqual(speech._parse_timestamp('01:02:03.250'), 3723.25)
        self.assertAlmostEqual(speech._parse_timestamp('02:30'), 150.0)

    def test_an_impossible_timestamp_is_refused(self):
        for bad in ('00:60:00,000', '00:00:61,000', '2.5', 'début', ''):
            with self.assertRaises(speech.SpeechError, msg=repr(bad)):
                speech._parse_timestamp(bad)


class ParseTests(unittest.TestCase):
    def test_an_srt_file_becomes_timed_cues(self):
        cues = speech.parse_transcript(SRT)
        self.assertEqual([c['text'] for c in cues], ['Bonjour à tous', 'on attaque le montage'])
        self.assertEqual((cues[0]['start'], cues[0]['end']), (0.0, 2.5))
        self.assertTrue(all(c['id'] for c in cues))
        self.assertEqual(len({c['id'] for c in cues}), 2)

    def test_a_vtt_file_ignores_its_headers_notes_and_identifiers(self):
        cues = speech.parse_transcript(VTT)
        self.assertEqual([c['text'] for c in cues], ['Première phrase', 'Deuxième phrase'])
        self.assertEqual((cues[1]['start'], cues[1]['end']), (1.2, 2.4))

    def test_timed_json_is_accepted_and_keeps_the_ids_it_carries(self):
        cues = speech.parse_transcript('{"segments": [{"id": "mien", "start": 1, "end": 2, "text": " voilà "}]}')
        self.assertEqual(cues, [dict(id='mien', start=1.0, end=2.0, text='voilà')])

    def test_plain_text_is_refused_rather_than_given_invented_times(self):
        with self.assertRaisesRegex(speech.SpeechError, "n'a pas d'horodatage"):
            speech.parse_transcript('Bonjour à tous, on attaque le montage.')
        with self.assertRaisesRegex(speech.SpeechError, 'vide'):
            speech.parse_transcript('   ')

    def test_broken_json_says_where_it_breaks(self):
        with self.assertRaisesRegex(speech.SpeechError, 'ligne 1'):
            speech.parse_transcript('[{"start": 0,}]')
        with self.assertRaisesRegex(speech.SpeechError, 'aucun segment'):
            speech.parse_transcript('[]')
        with self.assertRaisesRegex(speech.SpeechError, 'liste de segments'):
            speech.parse_transcript('{"transcript": "du texte"}')

    def test_a_segment_without_times_or_text_is_refused(self):
        for bad in ('[{"start": 0, "end": 1}]', '[{"start": 0, "end": 1, "text": "  "}]',
                    '[{"start": 2, "end": 1, "text": "a"}]', '[{"start": -1, "end": 1, "text": "a"}]',
                    '[{"start": "0", "end": 1, "text": "a"}]', '[{"start": 0, "end": 1, "text": "a"}, 4]'):
            with self.assertRaises(speech.SpeechError, msg=bad):
                speech.parse_transcript(bad)

    def test_two_segments_cannot_share_one_id(self):
        with self.assertRaisesRegex(speech.SpeechError, 'dupliqué'):
            speech.parse_transcript('[{"id": "x", "start": 0, "end": 1, "text": "a"},'
                                    ' {"id": "x", "start": 1, "end": 2, "text": "b"}]')

    def test_word_mode_keeps_one_cue_per_word_including_the_instant_ones(self):
        cues = speech._parse_subtitles(WORDS, words=True)
        self.assertEqual([c['text'] for c in cues], ['Bonjour', 'à', 'tous'])
        self.assertEqual((cues[1]['start'], cues[1]['end']), (0.34, 0.34))

    def test_in_sentence_mode_an_instant_word_joins_its_neighbour(self):
        cues = speech._parse_subtitles(WORDS)
        self.assertEqual([c['text'] for c in cues], ['Bonjour à', 'tous'])

    def test_an_instant_word_at_the_very_start_joins_the_first_sentence(self):
        kept = speech._absorb_instant_cues([
            dict(start=0.0, end=0.0, text='Et'),
            dict(start=0.1, end=1.0, text='donc voilà'),
        ])
        self.assertEqual(kept, [dict(start=0.0, end=1.0, text='Et donc voilà')])

    def test_subtitles_with_no_timing_line_are_refused(self):
        with self.assertRaisesRegex(speech.SpeechError, 'ligne de temps attendue'):
            speech._parse_subtitles('du texte\nsans temps\n\n00:00:00,000 --> 00:00:01,000\nphrase\n')
        with self.assertRaisesRegex(speech.SpeechError, 'fin antérieure'):
            speech._parse_subtitles('1\n00:00:02,000 --> 00:00:01,000\nphrase\n')


class MergeTests(unittest.TestCase):
    def test_a_second_block_is_shifted_and_the_overlap_is_shared(self):
        first = [dict(start=0.0, end=2.0, text='un'), dict(start=29.0, end=29.9, text='deux')]
        incoming = [dict(start=0.5, end=1.5, text='deux'), dict(start=5.0, end=6.0, text='trois')]
        chunk_start = speech.TRANSCRIBE_CHUNK_SECONDS - speech.TRANSCRIBE_OVERLAP_SECONDS
        merged = speech._merge_chunk_cues(first, incoming, chunk_start, is_first=False)
        self.assertEqual([c['text'] for c in merged], ['un', 'deux', 'trois'])
        # Le mot « deux » n'est pas compté deux fois, et les temps restent absolus.
        self.assertAlmostEqual(merged[1]['start'], 29.0)
        self.assertAlmostEqual(merged[2]['start'], chunk_start + 5.0)

    def test_the_first_block_keeps_its_own_times(self):
        incoming = [dict(start=1.0, end=2.0, text='un')]
        self.assertEqual(speech._merge_chunk_cues([], incoming, 0.0, is_first=True), incoming)


class HallucinationTests(unittest.TestCase):
    def test_subtitle_credits_whisper_invents_in_silences_are_dropped(self):
        cues = [dict(start=0.0, end=1.0, text='Bonjour à tous'),
                dict(start=1.0, end=3.0, text='Sous-titrage Société Radio-Canada'),
                dict(start=3.0, end=4.0, text="Sous-titres réalisés par la communauté d'Amara.org"),
                dict(start=4.0, end=5.0, text='Abonnez-vous !'),
                dict(start=5.0, end=6.0, text='on attaque')]
        kept = speech._drop_credit_hallucinations(cues)
        self.assertEqual([c['text'] for c in kept], ['Bonjour à tous', 'on attaque'])

    def test_a_sentence_that_merely_contains_the_words_is_kept(self):
        cues = [dict(start=0.0, end=1.0, text='Abonnez-vous à la chaîne si ça vous plaît')]
        self.assertEqual(speech._drop_credit_hallucinations(cues), cues)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.video = Path(self.tmp.name) / 'reel.mp4'
        self.video.write_bytes(b'\x00' * 32)

    def source(self, **over):
        return {**dict(id='s', path=str(self.video), duration=60.0, has_audio=True), **over}

    def test_the_project_video_is_the_one_that_gets_transcribed(self):
        source, path = speech._primary(dict(sources=[self.source()]))
        self.assertEqual(path, self.video.resolve())
        self.assertEqual(source['id'], 's')

    def test_a_project_that_cannot_be_transcribed_says_why(self):
        cases = {
            'Ajoutez': dict(sources=[]),
            'piste audio': dict(sources=[self.source(has_audio=False)]),
            'chemin local': dict(sources=[self.source(path='')]),
            'introuvable': dict(sources=[self.source(path=str(self.video) + '.absent')]),
            'Durée': dict(sources=[self.source(duration=0)]),
        }
        for message, project in cases.items():
            with self.assertRaisesRegex(speech.SpeechError, message, msg=message):
                speech._primary(project)

    def test_a_missing_file_stops_before_whisper_is_even_called(self):
        with self.assertRaisesRegex(speech.SpeechError, 'introuvable'):
            speech.transcribe_media(Path(self.tmp.name) / 'absent.mp4', 10.0, Path(self.tmp.name))

    def test_a_missing_whisper_model_is_named_in_the_error(self):
        with mock.patch.dict('os.environ', {'WHISPER_MODEL': str(Path(self.tmp.name) / 'absent.bin'),
                                            'WHISPER_CLI': '/bin/true'}):
            with self.assertRaisesRegex(speech.SpeechError, 'Modèle Whisper local introuvable'):
                speech._require_whisper()

    def test_status_reports_what_the_machine_can_do(self):
        with mock.patch.dict('os.environ', {'WHISPER_MODEL': str(self.video), 'WHISPER_CLI': '/bin/true',
                                            'WHISPER_LANGUAGE': 'fr'}):
            report = speech.status()
        self.assertEqual(report['whisper_cli'], '/bin/true')
        self.assertTrue(report['model_ready'])
        self.assertEqual(report['language'], 'fr')


if __name__ == '__main__':
    unittest.main()

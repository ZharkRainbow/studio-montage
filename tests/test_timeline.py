from array import array
import unittest

from studio import timeline


class SilenceTests(unittest.TestCase):
    def test_threshold_follows_the_room_noise(self):
        speech, pause = [-18.0] * 50, [-44.0] * 30
        levels = speech + pause + speech + [-44.0] * 10 + speech
        found, threshold = timeline.silences(levels, 10.0, 0.35)
        self.assertEqual(found, [{"start": 11.0, "end": 11.6}])
        self.assertTrue(-44 < threshold < -18)
        noisy = [value + 12 for value in levels]
        self.assertEqual(timeline.silences(noisy, 10.0, 0.35)[0], found)

    def test_cut_keeps_a_breath_around_words_and_drops_crumbs(self):
        segments = [{"start": 0.0, "end": 10.0}]
        pauses = [{"start": 3.0, "end": 4.0}, {"start": 9.9, "end": 10.3}]
        self.assertEqual(timeline.cut_silences(segments, pauses), [{"start": 0.0, "end": 3.12}, {"start": 3.88, "end": 10.0}])
        self.assertEqual(timeline.cut_silences(segments, [{"start": 5.0, "end": 5.2}]), segments)

    def test_a_cut_never_bites_on_a_word(self):
        words = [{"start": 1.0, "end": 1.4}, {"start": 3.9, "end": 4.3}]
        blanks = timeline.plan_blanks([{"start": 0.0, "end": 10.0}], [{"start": 1.2, "end": 4.1}], words)
        self.assertEqual(blanks, [{"start": 1.52, "end": 3.8, "cut": True}])
        self.assertEqual(timeline.bites(blanks, words), [])

    def test_a_word_inside_a_pause_splits_the_cut_in_two(self):
        words = [{"start": 0.2, "end": 0.6}, {"start": 2.0, "end": 2.3}, {"start": 4.0, "end": 4.4}]
        blanks = timeline.plan_blanks([{"start": 0.0, "end": 6.0}], [{"start": 0.6, "end": 4.0}], words)
        self.assertEqual(blanks, [{"start": 0.72, "end": 1.9, "cut": True}, {"start": 2.42, "end": 3.9, "cut": True}])
        self.assertEqual(timeline.bites(blanks, words), [])

    def test_breaths_between_words_are_found_when_the_envelope_misses_them(self):
        words = [{"start": 0.0, "end": 1.0}, {"start": 1.8, "end": 2.6}, {"start": 2.7, "end": 3.4}]
        found = timeline.word_pauses(words, 0.35)
        self.assertEqual(found, [{"start": 1.0, "end": 1.8}])

    def test_a_gap_as_loud_as_the_speech_is_a_forgotten_word_not_a_blank(self):
        words = [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}]
        levels = [-40.0] * 50 + [-18.0] * 50 + [-40.0] * 50
        self.assertEqual(timeline.word_pauses(words, 0.35, levels, 0.0, -24.0), [])
        quiet = [-18.0] * 50 + [-45.0] * 50 + [-18.0] * 50
        self.assertEqual(timeline.word_pauses(words, 0.35, quiet, 0.0, -24.0), [{"start": 1.0, "end": 2.0}])

    def test_a_blank_kept_by_hand_stays_in_the_montage(self):
        blanks = [{"start": 1.0, "end": 2.0, "cut": False}, {"start": 3.0, "end": 4.0, "cut": True}]
        self.assertEqual(timeline.cut_blanks([{"start": 0.0, "end": 5.0}], blanks),
                         [{"start": 0.0, "end": 3.0}, {"start": 4.0, "end": 5.0}])

    def test_remaining_blanks_are_counted_inside_the_kept_pieces(self):
        pauses = [{"start": 1.0, "end": 2.0}, {"start": 6.0, "end": 6.5}]
        kept = [{"start": 0.0, "end": 3.0}, {"start": 5.0, "end": 8.0}]
        self.assertEqual(timeline.residual_blanks(pauses, kept),
                         [{"start": 1.0, "end": 2.0}, {"start": 6.0, "end": 6.5}])
        self.assertEqual(timeline.residual_blanks(pauses, [{"start": 0.0, "end": 1.2}]), [])

    def test_source_words_follow_the_offset_of_the_file(self):
        project = {"sources": [{"offset": 2.0}], "source_transcript": [{"start": 3.0, "end": 3.4, "text": "bonjour"}]}
        self.assertEqual(timeline.source_words(project), [{"start": 1.0, "end": 1.4, "text": "bonjour"}])
        self.assertEqual(timeline.source_words({"sources": [{}]}), [])

    def test_a_word_stamp_that_swallows_a_pause_comes_back_to_the_voice(self):
        """whisper étire la fin d'un mot jusqu'au suivant : on la recale sur ce qui sonne."""
        words = [{"start": 1.0, "end": 3.0, "text": "l'erreur,"}]
        self.assertEqual(timeline.refine_words(words, [{"start": 1.3, "end": 2.6}]),
                         [{"start": 1.0, "end": 1.3, "text": "l'erreur,"},
                          {"start": 2.6, "end": 3.0, "text": "l'erreur,"}])

    def test_a_word_with_no_sound_left_disappears(self):
        self.assertEqual(timeline.refine_words([{"start": 1.0, "end": 1.4}], [{"start": 0.9, "end": 1.5}]), [])
        loud = [-18.0] * 100
        self.assertEqual(timeline.refine_words([{"start": 1.0, "end": 1.4}], [{"start": 0.9, "end": 1.5}], loud, 0.0, -24.0),
                         [{"start": 1.0, "end": 1.4, "text": ""}])

    def test_the_voice_is_hunted_lower_than_the_blanks(self):
        self.assertLess(timeline.voice_db(-60.0, -20.0), timeline.profile([-60.0] * 10 + [-20.0] * 10)[2])

    def test_a_blank_left_uncut_stays_clickable(self):
        blanks = [{"start": 1.0, "end": 1.2, "cut": True}]
        self.assertEqual(timeline.with_kept(blanks, [{"start": 0.9, "end": 2.0}], [{"start": 0.0, "end": 5.0}]),
                         [{"start": 1.0, "end": 1.2, "cut": True}, {"start": 1.2, "end": 2.0, "cut": False}])

    def test_peaks_are_normalised(self):
        samples = array("h", [0, 16384, -32768, 100] * 25)
        values = timeline.peaks(samples, 4)
        self.assertEqual(len(values), 4); self.assertEqual(max(values), 1.0)


if __name__ == "__main__":
    unittest.main()

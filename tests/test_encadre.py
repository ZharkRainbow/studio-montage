"""L'encadré d'accroche : ce qu'on lit dans l'accroche, où on trouve la police, et le dessin lui-même."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio import encadre
from studio.media import MediaError


def chrome_ok() -> bool:
    try:
        encadre.chrome_binary()
    except MediaError:
        return False
    return True


def font_ok() -> bool:
    try:
        encadre.font_path()
    except MediaError:
        return False
    return True


class SplitHookTests(unittest.TestCase):
    """L'accroche du montage se coupe sur « / » : avant l'annonce, après l'étiquette."""

    def test_a_two_tier_hook_gives_the_block_and_the_label(self):
        self.assertEqual(encadre.split_hook('Il a fait 40 000 € en 3 mois / sans publicité'),
                         ('Il a fait 40 000 € en 3 mois', '(sans publicité)'))

    def test_the_parentheses_are_not_doubled_when_the_user_writes_them(self):
        self.assertEqual(encadre.split_hook('Le vrai chiffre / (en 2026)')[1], '(en 2026)')

    def test_a_hook_without_a_slash_stays_on_one_tier(self):
        self.assertEqual(encadre.split_hook('Personne ne le dit'), ('Personne ne le dit', ''))

    def test_spaces_and_line_breaks_are_flattened(self):
        self.assertEqual(encadre.split_hook('  Deux   lignes\n d’accroche /  l’étiquette  '),
                         ('Deux lignes d’accroche', '(l’étiquette)'))

    def test_an_empty_hook_asks_for_no_card(self):
        for empty in (None, '', '   ', '\n', '/ étiquette seule'):
            self.assertEqual(encadre.split_hook(empty)[0], '', repr(empty))


class FontTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_the_settings_folder_comes_first(self):
        mine = self.folder / encadre.FONT_FILE
        mine.write_bytes(b'otf')
        self.assertEqual(encadre.font_path(self.folder), mine.resolve())

    def test_without_zt_nature_the_bundled_inter_tight_is_used(self):
        with mock.patch.object(encadre, '_font_dirs', return_value=[]):
            self.assertEqual(encadre.font_path(self.folder), encadre.FALLBACK_FONT.resolve())

    def test_an_absent_font_says_where_to_put_it(self):
        with mock.patch.object(encadre, '_font_dirs', return_value=[]), \
             mock.patch.object(encadre, 'FALLBACK_FONT', Path(self.folder) / 'absente.ttf'):
            with self.assertRaises(MediaError) as boom:
                encadre.font_path(self.folder)
        message = str(boom.exception)
        self.assertIn(encadre.FONT_FILE, message)
        self.assertIn(str(encadre.default_font_dir()), message)
        self.assertIn(str(self.folder), message)

    def test_the_default_folder_follows_the_machine(self):
        with mock.patch.object(encadre.platform, 'system', return_value='Darwin'):
            self.assertEqual(encadre.default_font_dir(), Path.home() / 'Library/Fonts')
        with mock.patch.object(encadre.platform, 'system', return_value='Linux'):
            self.assertEqual(encadre.default_font_dir(), Path.home() / '.local/share/fonts')


class EncoderTests(unittest.TestCase):
    """videotoolbox sur un Mac, libx264 sur le serveur : c'est la machine qui décide."""

    def test_a_mac_uses_videotoolbox_when_ffmpeg_offers_it(self):
        listing = subprocess.CompletedProcess([], 0, stdout=' V....D h264_videotoolbox  VideoToolbox H.264\n')
        with mock.patch.object(encadre.platform, 'system', return_value='Darwin'), \
             mock.patch.object(encadre.subprocess, 'run', return_value=listing):
            self.assertEqual(encadre.video_encoder(), 'h264_videotoolbox')

    def test_a_mac_without_videotoolbox_falls_back(self):
        listing = subprocess.CompletedProcess([], 0, stdout=' V....D libx264  H.264\n')
        with mock.patch.object(encadre.platform, 'system', return_value='Darwin'), \
             mock.patch.object(encadre.subprocess, 'run', return_value=listing):
            self.assertEqual(encadre.video_encoder(), 'libx264')

    def test_anywhere_else_it_is_libx264_without_even_asking(self):
        with mock.patch.object(encadre.platform, 'system', return_value='Linux'), \
             mock.patch.object(encadre.subprocess, 'run', side_effect=AssertionError('ffmpeg interrogé pour rien')):
            self.assertEqual(encadre.video_encoder(), 'libx264')

    def test_each_encoder_brings_its_own_settings_and_the_source_frame_rate(self):
        mac = encadre.encoder_args('h264_videotoolbox', 29.97)
        self.assertEqual(mac[:4], ['-c:v', 'h264_videotoolbox', '-b:v', '12M'])
        self.assertEqual(mac[-1], '29.970000')
        self.assertIn('-crf', encadre.encoder_args('libx264', 25.0))


class ChromeTests(unittest.TestCase):
    def test_the_environment_wins_over_the_known_places(self):
        with tempfile.NamedTemporaryFile(suffix='-chrome') as fake:
            with mock.patch.dict(encadre.os.environ, {'STUDIO_CHROME': fake.name}):
                self.assertEqual(encadre.chrome_binary(), fake.name)

    def test_no_chrome_at_all_is_said_plainly(self):
        with mock.patch.dict(encadre.os.environ, {'STUDIO_CHROME': '', 'CHROME': ''}), \
             mock.patch.object(encadre, 'CHROME_CANDIDATES', ()), \
             mock.patch.object(encadre.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(MediaError, 'Chrome est introuvable'):
                encadre.chrome_binary()


class OverlayTests(unittest.TestCase):
    def test_the_card_holds_four_seconds_and_fades_out_at_the_end(self):
        spec = encadre.overlay_spec('/local/encadre.png')
        self.assertEqual(spec['seconds'], 4.0)
        self.assertEqual(spec['fade_start'], 3.7)
        self.assertAlmostEqual(spec['fade_start'] + spec['fade_seconds'], spec['seconds'], places=6)


@unittest.skipUnless(chrome_ok() and font_ok() and shutil.which('ffmpeg'), 'Chrome, ZT Nature ou ffmpeg absents')
class RenderTests(unittest.TestCase):
    """Le vrai dessin : Chrome, la police sous licence, et un PNG qui n'est pas vide."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_a_two_tier_card_is_drawn_at_the_size_of_the_video(self):
        montage = dict(hook='Il a fait 40 000 € en 3 mois / sans publicité')
        card = encadre.card_for_montage(montage, self.root, (540, 960))
        self.assertEqual(card, self.root / 'encadre.png')
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                'stream=width,height', '-of', 'csv=p=0', str(card)],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(probe.stdout.strip(), '540,960')
        # Peinte, mais pas pleine : l'encadré laisse voir la vidéo autour de lui.
        painted = encadre.ink_fraction(card)
        self.assertGreater(painted, 0.01)
        self.assertLess(painted, 0.5)

    def test_an_empty_hook_draws_nothing_at_all(self):
        self.assertIsNone(encadre.card_for_montage(dict(hook='  '), self.root, (540, 960)))
        self.assertFalse((self.root / 'encadre.png').exists())

    def test_a_card_without_its_font_is_refused_rather_than_drawn_blank(self):
        with mock.patch.object(encadre, '_font_dirs', return_value=[]), \
             mock.patch.object(encadre, 'FALLBACK_FONT', self.root / 'absente.ttf'):
            with self.assertRaisesRegex(MediaError, 'introuvable'):
                encadre.render_card('Une accroche', '', self.root / 'encadre.png', (540, 960),
                                    polices_dir=str(self.root))


if __name__ == '__main__':
    unittest.main()

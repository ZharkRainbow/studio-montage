"""La tâche « Envoyer en relecture » : un export encadré dans « Montages validés », déposé en version."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from studio import encadre
from studio.jobs import Jobs
from studio.media import MediaError
from studio.store import Store, default_montage


def outils() -> bool:
    if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
        return False
    try:
        encadre.chrome_binary()
        encadre.font_path()
    except MediaError:
        return False
    return True


def rush(path: Path, seconds: int = 8) -> Path:
    """Un faux rush vert : aucun bleu dedans, donc le bloc bleu de l'encadré se compte tout seul."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', f'color=c=0x167F3C:s=360x640:rate=25:duration={seconds}',
                    '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={seconds}',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-shortest', str(path)], check=True, timeout=180)
    return path


@unittest.skipUnless(outils(), 'ffmpeg, Chrome ou ZT Nature absents')
class RelectureJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rush = rush(self.root / 'rushes' / 'plateau.mp4')
        self.store = Store(self.root / 'projets')
        self.jobs = Jobs(self.store)
        p = self.store.create('Short 1')
        p['sources'] = [{'id': 's', 'path': str(self.rush), 'name': 'plateau.mp4',
                         'width': 360, 'height': 640, 'duration': 8.0, 'fps': 25, 'has_audio': True}]
        p['montage'] = default_montage(p['sources'][0]) | dict(
            segments=[{'start': 0.0, 'end': 3.0}, {'start': 5.0, 'end': 8.0}],
            hook='Il a fait 40 000 € en 3 mois / sans publicité')
        self.p = self.store.save(p['id'], p, internal=True)

    def etapes(self):
        suivi = []
        return suivi, (lambda n, message: suivi.append((n, message)))

    def envoyer(self):
        out = self.store.directory(self.p['id']) / 'artifacts' / 'job'
        out.mkdir(parents=True, exist_ok=True)
        suivi, progress = self.etapes()
        return self.jobs._relecture(self.store.get(self.p['id']), out, progress, lambda: None), suivi

    def part_bleue(self, path: str, seconds: float) -> float:
        """La part de pixels franchement bleus : le bloc bleu de l'encadré, et lui seul."""
        raw = subprocess.run(['ffmpeg', '-hide_banner', '-v', 'error', '-ss', f'{seconds:.3f}', '-i', path,
                              '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True, timeout=120).stdout
        self.assertTrue(raw, f'aucune image à {seconds} s')
        pixels = [raw[i:i + 3] for i in range(0, len(raw), 3)]
        bleus = sum(1 for r, g, b in pixels if b > 150 and r < 110 and g < 110)
        return bleus / len(pixels)

    def mp4(self) -> Path:
        return self.rush.parent / 'Montages validés' / 'Short 1.mp4'

    def test_the_montage_lands_in_montages_valides_with_its_card_and_becomes_v1(self):
        result, suivi = self.envoyer()
        self.assertEqual(result['path'], str(self.mp4()))
        self.assertTrue(self.mp4().is_file())
        self.assertTrue(result['encadre'])
        self.assertFalse(result['remux'])
        self.assertAlmostEqual(result['seconds'], 6.0, places=3)
        self.assertEqual(result['version_index'], 1)
        self.assertIn('encadré', ' '.join(message for _, message in suivi))

        # L'encadré est là dès la première image : les miniatures sont prises sur la 1re frame.
        self.assertGreater(self.part_bleue(result['path'], 0.0), 0.02)
        self.assertLess(self.part_bleue(result['path'], 5.0), 0.005)

        # Le projet garde l'export et la version, avec l'empreinte du montage qui les a faits.
        updated = self.store.get(self.p['id'])
        self.assertEqual(updated['export'], dict(updated['export'], state='fait', encadre=True,
                                                 path=str(self.mp4())))
        version = updated['versions'][0]
        self.assertEqual(version['path'], str(self.mp4()))
        self.assertEqual(version['montage_hash'], updated['montage_hash'])
        self.assertEqual(updated['active_version'], version['id'])
        self.assertIsNone(updated.get('validated_at'), 'envoyer en relecture ne valide pas le short')

    def test_sending_again_after_a_recut_makes_v2_from_the_new_beginning(self):
        self.envoyer()
        p = self.store.get(self.p['id'])
        avant = p['montage_hash']
        p['montage']['segments'] = [{'start': 1.5, 'end': 3.0}, {'start': 5.0, 'end': 8.0}]
        p = self.store.save(p['id'], p, internal=True)
        # Le montage a bougé : la V1 montre un ancien montage, et c'est ce que la relecture signale.
        self.assertNotEqual(p['montage_hash'], avant)
        self.assertEqual(p['versions'][0]['montage_hash'], avant)

        result, _ = self.envoyer()
        self.assertEqual(result['version_index'], 2)
        # 1,50 s calé sur la grille à 25 i/s donne 1,52 s : (3 - 1,52) + (8 - 5) = 4,48 s, soit 112 images.
        self.assertAlmostEqual(result['seconds'], 4.48, places=3)
        # Le premier MP4 n'est pas écrasé : le nouveau prend le nom libre d'à côté.
        self.assertNotEqual(result['path'], str(self.mp4()))
        self.assertTrue(self.mp4().is_file())
        updated = self.store.get(self.p['id'])
        self.assertEqual(updated['versions'][1]['montage_hash'], updated['montage_hash'])

    def test_a_short_without_a_hook_is_sent_without_a_card(self):
        p = self.store.get(self.p['id'])
        p['montage']['hook'] = ''
        self.store.save(p['id'], p, internal=True)
        result, suivi = self.envoyer()
        self.assertFalse(result['encadre'])
        self.assertNotIn('encadré', ' '.join(message for _, message in suivi))
        self.assertLess(self.part_bleue(result['path'], 0.0), 0.005)


if __name__ == '__main__':
    unittest.main()

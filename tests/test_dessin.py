"""Le dessin de la Relecture : outils, épaisseurs, lissage, texte lisible, capture fidèle.

La logique de peinture vit dans `studio/static/editor/review/ink.js`, écrite sans DOM exprès :
elle se teste en Node, avec un contexte 2D factice. Ce fichier relaie `node --test`, puis vérifie
dans le module d'interface les cinq points demandés, qu'un test en Node ne peut pas voir.
"""
from pathlib import Path
import json
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / 'studio' / 'static'
INK = STATIC / 'editor' / 'review' / 'ink.js'
DRAW = STATIC / 'editor' / 'review' / 'draw.js'
SUITE = ROOT / 'tests' / 'js' / 'ink.test.mjs'
SCENARIO = ROOT / 'tests' / 'e2e' / 'scenarios' / 'dessin.json'


class InkTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node absent')
    def test_le_dessin_passe_ses_controles_en_node(self):
        result = subprocess.run(['node', '--test', str(SUITE)], capture_output=True, text=True, timeout=180, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])
        self.assertIn('fail 0', result.stdout, result.stdout[-2000:])

    def test_ink_reste_sans_dependance(self):
        """Un vrai import dans ink.js, et le test en Node ne le chargerait plus tel quel."""
        imports = [line for line in INK.read_text().splitlines() if line.startswith('import ')]
        self.assertEqual(imports, [], f'ink.js importe : {imports}')


class DrawToolsTests(unittest.TestCase):
    """Les cinq points demandés, lus dans le module qui construit la barre d'outils."""

    def setUp(self):
        self.draw = DRAW.read_text()

    def has(self, needle, note=''):
        self.assertTrue(needle in self.draw, f'draw.js ne contient pas « {needle} » {note}'.strip())

    def test_le_feutre_est_l_outil_d_ouverture(self):
        self.has('setTool(DEFAULT_TOOL);', '(l\'ouverture de Dessiner choisit l\'outil par défaut)')

    def test_la_barre_offre_les_outils_les_epaisseurs_et_les_couleurs(self):
        # Les deux groupes de boutons radio sont fabriqués par la même fonction, d'où le nom de groupe.
        self.has('data-draw-${group}')
        self.has("radioHtml('tool'")
        self.has("radioHtml('width'")
        for attribute in ('data-draw-color', 'data-draw-undo', 'data-draw-attach'):
            self.has(attribute)

    def test_aucun_tout_effacer_ne_subsiste(self):
        """Plus de bouton tout effacer : l'annulation se fait trait par trait."""
        for path in STATIC.rglob('*.js'):
            text = path.read_text()
            for forbidden in ('data-draw-clear', 'clearShapes', 'Tout effacer', 'Effacer tout'):
                self.assertNotIn(forbidden, text, f'{path.name} contient encore « {forbidden} »')

    def test_le_champ_texte_garde_son_propre_annuler(self):
        """Sans ce stopPropagation, ⌘Z pendant la saisie retirerait un trait au lieu d'un mot."""
        saisie = self.draw[self.draw.index('function textField'):self.draw.index('function openText')]
        self.assertIn("event.key === 'Enter'", saisie, 'Entrée ne valide pas la saisie')
        self.assertIn("event.key === 'Escape'", saisie, 'Échap n\'annule pas la saisie')
        marque = saisie.index("event.key.toLowerCase() === 'z'")
        self.assertIn('stopPropagation', saisie[marque:marque + 200], '⌘Z dans le champ n\'est pas isolé')

    def test_cmd_z_retire_un_trait_quand_le_crayon_est_en_main(self):
        app = (STATIC / 'app.js').read_text()
        self.assertIn('if (state.review.drawing && !event.shiftKey) undoStroke();', app)

    def test_la_capture_sort_a_la_resolution_de_la_video(self):
        capture = self.draw[self.draw.index('export function captureDrawing'):]
        for needle in ('out.width = video.videoWidth;', 'out.height = video.videoHeight;',
                       # Les tracés sont normalisés : la peinture prend la taille de sortie, sans facteur d'échelle.
                       'paintInk(ctx, state.review.strokes, out.width, out.height);',
                       # Un texte en cours de saisie part dans la capture au lieu d'être perdu.
                       'commitText();'):
            self.assertIn(needle, capture, f'captureDrawing ne contient pas « {needle} »')

    def test_les_traces_sont_ranges_en_coordonnees_normalisees(self):
        """C'est ce qui fait tenir la capture : aucune coordonnée en pixels d'écran n'est gardée."""
        self.has('(event.clientX - rect.left) / rect.width')
        self.has('(event.clientY - rect.top) / rect.height')

    def test_la_toile_et_le_retour_parlent_de_strokes(self):
        """Un reliquat « shapes » quelque part, et la toile ne se vide plus en ouvrant un projet."""
        for path in STATIC.rglob('*.js'):
            self.assertNotIn('review.shapes', path.read_text(), f'{path.name} parle encore de review.shapes')
        self.assertIn('strokes: [],', (STATIC / 'core' / 'router.js').read_text())


class ScenarioTests(unittest.TestCase):
    def test_le_scenario_navigateur_couvre_le_dessin_v2(self):
        steps = json.loads(SCENARIO.read_text())['steps']
        texte = json.dumps(steps, ensure_ascii=False)
        for needle in ('data-draw-tool=\\"free\\"', 'data-draw-tool=\\"text\\"', 'data-draw-width=\\"epais\\"',
                       'Meta+Z', 'Ctrl+Z', 'Escape', 'data-draw-attach'):
            self.assertIn(needle, texte, f'le scénario ne couvre pas « {needle} »')
        # Le PNG joint est écrit sur le disque : c'est ce qui permet de le regarder, pas seulement de le compter.
        self.assertTrue(any('save' in step for step in steps), 'le scénario n\'enregistre aucun PNG')

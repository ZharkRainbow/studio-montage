"""La bibliothèque d'animations et les presets : lecture, protections, preset actif."""
import json
import unittest
from pathlib import Path
import tempfile

from studio import bibliotheque


FICHE = dict(id='essai', nom='Essai', categorie='Textes', collection='Mes styles', niveau='Simple',
             etat='Prototype', description='Une ligne.', quand_l_utiliser='Jamais.',
             parametres={'texte': 'texte'}, duree_s=1.0, reference='nulle part')


def pose(racine: Path, ident: str, **surcharge) -> Path:
    directory = racine / 'animations' / ident
    directory.mkdir(parents=True)
    (directory / 'meta.json').write_text(json.dumps(dict(FICHE, id=ident, **surcharge), ensure_ascii=False),
                                         encoding='utf-8')
    return directory


class AnimationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.racine = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_une_fiche_dit_si_son_apercu_existe(self):
        directory = pose(self.racine, 'avec-apercu')
        fiche = bibliotheque.animation('avec-apercu', self.racine)
        self.assertFalse(fiche['apercu'])
        self.assertFalse(fiche['vignette'])
        (directory / 'apercu.mp4').write_bytes(b'x')
        (directory / 'apercu.jpg').write_bytes(b'x')
        fiche = bibliotheque.animation('avec-apercu', self.racine)
        self.assertTrue(fiche['apercu'])
        self.assertTrue(fiche['vignette'])

    def test_une_fiche_cassee_ne_cache_pas_les_autres(self):
        pose(self.racine, 'bonne')
        casse = self.racine / 'animations' / 'cassee'
        casse.mkdir()
        (casse / 'meta.json').write_text('{ pas du json', encoding='utf-8')
        fiches = bibliotheque.animations(self.racine)
        self.assertEqual({f['id'] for f in fiches}, {'bonne', 'cassee'})
        self.assertIn('erreur', next(f for f in fiches if f['id'] == 'cassee'))

    def test_un_identifiant_qui_remonte_les_dossiers_est_refuse(self):
        for mauvais in ('../presets', 'Majuscule', 'avec espace', '', 'a/b'):
            with self.assertRaises((bibliotheque.BibliothequeError, FileNotFoundError)):
                bibliotheque.animation(mauvais, self.racine)

    def test_seuls_les_deux_apercus_sortent_du_dossier(self):
        directory = pose(self.racine, 'servi')
        (directory / 'apercu.mp4').write_bytes(b'x')
        (directory / 'secret.txt').write_text('rien', encoding='utf-8')
        self.assertEqual(bibliotheque.fichier_apercu('servi', 'apercu.mp4', self.racine).name, 'apercu.mp4')
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.fichier_apercu('servi', 'secret.txt', self.racine)
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.fichier_apercu('servi', '../../meta.json', self.racine)

    def test_chaque_fiche_livree_est_complete(self):
        """Bibliothèque vidée le 30/10, refaite une fiche à la fois depuis le 04/11 : aucune
        fiche fantôme (dossier sans meta.json), chaque fiche lisible, rangée et rendue."""
        for fiche in bibliotheque.animations():
            with self.subTest(fiche['id']):
                self.assertNotIn('erreur', fiche, f"{fiche['id']} : {fiche.get('erreur')}")
                self.assertIn(fiche['categorie'], bibliotheque.CATEGORIES)
                self.assertIn(fiche['collection'], bibliotheque.COLLECTIONS)
                self.assertIn(fiche['niveau'], bibliotheque.NIVEAUX)
                self.assertIn(fiche['etat'], bibliotheque.ETATS)
                for champ in ('nom', 'description', 'quand_l_utiliser', 'reference'):
                    self.assertTrue(str(fiche.get(champ, '')).strip(), f'{champ} vide')
                self.assertGreater(fiche['duree_s'], 0)
                self.assertTrue(fiche['composition'], 'pas de composition HyperFrames')
                self.assertTrue(fiche['apercu'] and fiche['vignette'], 'aperçu non rendu')

    def test_une_entree_sans_apercu_ne_peut_pas_etre_validee(self):
        """Règle du brief : un aperçu qui ne rend pas ne passe jamais en Validé."""
        for fiche in bibliotheque.animations():
            if fiche['etat'] == 'Validé':
                self.assertTrue(fiche['apercu'], f"{fiche['id']} est Validé sans aperçu rendu")


class PresetsTests(unittest.TestCase):
    def test_aucun_preset_de_depart(self):
        """Presets vidés le 30/10 : la liste est vide et la page n'a pas de défaut."""
        self.assertEqual(bibliotheque.presets(), [])
        self.assertIsNone(bibliotheque.preset_defaut())

    def test_les_animations_par_defaut_existent_dans_la_bibliotheque(self):
        connues = {f['id'] for f in bibliotheque.animations()}
        for preset in bibliotheque.presets():
            for ident in preset['animations_par_defaut']:
                self.assertIn(ident, connues, f"{preset['id']} appelle {ident}")

    def test_une_valeur_absente_est_nulle_et_annotee(self):
        """Valeur absente de Style-Reels.md = null plus une note, jamais un chiffre inventé."""
        for preset in bibliotheque.presets():
            for bloc in ('sous_titres', 'titre'):
                for cle, valeur in preset[bloc].items():
                    if valeur is None:
                        self.assertIn(f'_note_{cle}', preset[bloc], f"{preset['id']}.{bloc}.{cle}")

class EcriturePresetsTests(unittest.TestCase):
    """Les écritures : création, duplication, défaut, édition d'une valeur, animations."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.racine = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.racine / 'presets').mkdir(parents=True)
        pose(self.racine, 'une-anim')
        self.depart = dict(schema=1, nom='Départ', description='',
                           polices={}, couleurs={}, titre={}, son={}, image={},
                           sous_titres=dict(taille_px=50, couleur='#FFFFFF'),
                           encadre=dict(taille_px=64, duree_s=4.0, _source='ici'),
                           animations_par_defaut=[])
        (self.racine / 'presets' / 'depart.json').write_text(json.dumps(self.depart), encoding='utf-8')

    def test_une_creation_ne_recopie_jamais_un_identifiant_existant(self):
        premier = bibliotheque.creer_preset('Mon style', racine=self.racine)
        second = bibliotheque.creer_preset('Mon style', racine=self.racine)
        self.assertEqual(premier['id'], 'mon-style')
        self.assertEqual(second['id'], 'mon-style-2')
        self.assertEqual(premier['schema'], bibliotheque.SCHEMA)

    def test_un_preset_neuf_n_invente_aucune_valeur(self):
        neuf = bibliotheque.creer_preset('Vierge', racine=self.racine)
        for bloc in bibliotheque.BLOCS:
            self.assertEqual(neuf[bloc], {}, bloc)
        self.assertEqual(neuf['animations_par_defaut'], [])

    def test_une_duplication_reprend_les_valeurs_sans_l_identifiant(self):
        copie = bibliotheque.creer_preset('Copie', depuis='depart', racine=self.racine)
        self.assertNotEqual(copie['id'], 'depart')
        self.assertEqual(copie['encadre']['taille_px'], 64)
        self.assertEqual(copie['nom'], 'Copie')
        relu = bibliotheque.preset(copie['id'], self.racine)
        self.assertEqual(relu['id'], copie['id'])

    def test_le_defaut_se_pose_et_se_relit(self):
        self.assertIsNone(bibliotheque.defaut_id(self.racine))
        bibliotheque.definir_defaut('depart', self.racine)
        self.assertEqual(bibliotheque.defaut_id(self.racine), 'depart')
        self.assertEqual(bibliotheque.preset_defaut(self.racine)['id'], 'depart')
        self.assertEqual({p['id'] for p in bibliotheque.presets(self.racine)}, {'depart'})

    def test_un_preset_inconnu_ne_devient_pas_le_defaut(self):
        for mauvais in ('fantome', '../animations', ''):
            with self.assertRaises((bibliotheque.BibliothequeError, FileNotFoundError)):
                bibliotheque.definir_defaut(mauvais, self.racine)

    def test_l_edition_garde_le_type_et_sait_vider(self):
        mis = bibliotheque.modifier_preset('depart', 'encadre', 'taille_px', '60', racine=self.racine)
        self.assertEqual(mis['encadre']['taille_px'], 60)
        self.assertIsInstance(mis['encadre']['taille_px'], int)
        mis = bibliotheque.modifier_preset('depart', 'encadre', 'duree_s', '4,5', racine=self.racine)
        self.assertEqual(mis['encadre']['duree_s'], 4.5)
        mis = bibliotheque.modifier_preset('depart', 'encadre', 'taille_px', None, racine=self.racine)
        self.assertIsNone(mis['encadre']['taille_px'])

    def test_l_edition_refuse_une_cle_absente_un_bloc_inconnu_et_les_cles_de_service(self):
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.modifier_preset('depart', 'encadre', 'inventee', 1, racine=self.racine)
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.modifier_preset('depart', 'inconnu', 'taille_px', 1, racine=self.racine)
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.modifier_preset('depart', 'encadre', '_source', 'ailleurs', racine=self.racine)
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.modifier_preset('depart', 'encadre', 'taille_px', 'grand', racine=self.racine)

    def test_une_animation_s_ajoute_une_fois_et_se_retire(self):
        mis = bibliotheque.animations_du_preset('depart', 'une-anim', racine=self.racine)
        self.assertEqual(mis['animations_par_defaut'], ['une-anim'])
        mis = bibliotheque.animations_du_preset('depart', 'une-anim', racine=self.racine)
        self.assertEqual(mis['animations_par_defaut'], ['une-anim'])
        mis = bibliotheque.animations_du_preset('depart', 'une-anim', retirer=True, racine=self.racine)
        self.assertEqual(mis['animations_par_defaut'], [])

    def test_une_animation_qui_n_existe_pas_ne_s_ajoute_pas(self):
        with self.assertRaises((bibliotheque.BibliothequeError, FileNotFoundError)):
            bibliotheque.animations_du_preset('depart', 'fantome', racine=self.racine)

    def test_le_dernier_preset_ne_se_supprime_pas(self):
        with self.assertRaises(bibliotheque.BibliothequeError):
            bibliotheque.supprimer_preset('depart', self.racine)
        bibliotheque.creer_preset('Deuxieme', racine=self.racine)
        bibliotheque.definir_defaut('depart', self.racine)
        bibliotheque.supprimer_preset('depart', self.racine)
        self.assertIsNone(bibliotheque.defaut_id(self.racine))
        self.assertEqual(len(bibliotheque.presets(self.racine)), 1)


if __name__ == '__main__':
    unittest.main()

# Écrire `plan.json` pour le style classique

Modèle de forme (jamais de contenu) : `../exemples/exemple-classique.json`, un plan validé. Les numéros de mots et les images viennent de `mots.txt` du projet. Tous les temps sont en images de la vidéo coupée.

## Champs
| Champ | Contenu | Règle validée |
|---|---|---|
| `style` | `"classique"` | |
| `habillage` | `"epure"` (quatre coins) ou `"complet"` (+ encadrés avec le nom de la marque du profil et timecode, + `hud`) | épuré par défaut |
| `corrections` | `{"mot transcrit": "mot affiché"}` | « postes » donne « posts », « six » donne « 6 », marques et noms propres corrigés |
| `fusion` | `{"206": "c'est", "207": ""}` | un mot coupé par une coupe : le recoller sur le premier, vider le second |
| `groupes` | listes de numéros de mots, 1 à 4 mots | sous-titres en ZT Nature SemiBold si elle est installée, sinon Inter Tight, mot à mot, flou vers net |
| `fin_forcee` | `{"dernier mot du groupe": image de fin}` | finir un sous-titre avant un bloc, un carton, une liste, un mot en profondeur |
| `blocs` | `id`, `lead` (petite ligne), `big` (grand mot italique), `fin`, `statique`, `fx` | l'accroche : `id: "hook"`, `statique: true`, `fx: true` (entière dès l'image 0, s'efface vers le bas, avance, brille) |
| `profondeur` | mot derrière la personne : `id`, `texte` (CAPITALES), `f0`, `f1`, `sommet`, `brille` (images où la brillance passe) | 2 ou 3 par 30 s ; `sommet` = sommet de la tête donné par `mesurer` (vidéo sans zoom) à l'image où le mot apparaît, une fois tout mouvement de caméra fini ; si la tête bouge de plus de 60 px pendant l'affichage, raccourcir `f1` |
| | chiffre en compteur : `chiffre` (0-9), `cx` (centre horizontal), `haut` (haut du chiffre) | le placer à côté de la tête, jamais centré dessus |
| `cartons` | `id`, `f0`, `f1`, `label` (« CE QU’ON ME DIT »), `num` (« N°01 »), `phrases` (`lignes`, `em`, `ponct`) | fond bleu ; objections et phrases fortes ; 2 phrases maximum (elles s'empilent) ; `em` = mots en italique bleu clair |
| `panneau` | `titre`, `chiffre`, `position: "bas"`, `lignes` (`f`, `n`, `txt`, `tag`, `ftag`, `accent`) | pour un chiffre décomposé (« 3 posts : 2 planifiés + 1 actualité ») ; toujours en bas, grand, opaque |
| `roues` | `items`, `pas` ([image, rang actif]…), `y`, `style: "blanc-glow"`, `tag` (`f`, `txt`, `item`) | énumérations, jours ; `y` choisi avec `mesurer` pour ne pas couvrir le visage |
| `traces` | `forme` (`rond` ou `trait`), `mots`, `f0`, `df`, `couleur` | au plus 2 ronds blancs et 1 trait bleu `#2f6bff` par 30 s |
| `punchs` | en classique : `[image, zoom de départ, zoom posé]`  | sur les mots en profondeur et les chiffres, 1,05 à 1,08 |
| `sfx` | `[image du pic, nom, niveau dB]` | voir ci-dessous |
| `musique` | `{"fichier": "ma-musique.mp3", "debut": 1.5}` | lit à -34 LUFS, fichier pris dans `musique_dir` du profil ; `{"fichier": null}` = sans musique (par défaut si le profil n'en donne pas) |

## Bruitages (noms permis et niveaux validés)
Les fichiers viennent de `sfx_dir` du profil, sous ces noms (ou la table `sfx` du profil). Sans bibliothèque de sons : ne pas mettre de `sfx` dans le plan.
- `whoosh-doux.mp3` -26 : entrée de carton. `whoosh-court.mp3` -31 : sortie de carton.
- `impact-moyen.wav` -29 à -31 : mot fort, mot en profondeur. `impact-boom.mp3` -23 : chiffre clé (une ou deux fois).
- `clic-num.wav` -28 à -31 : lignes de carton, crans de liste, crans du compteur. `clic.mp3` -32 : lignes du panneau.
- `whoosh-rapide.wav` -29 à -34 : arrivée d'un mot en profondeur, tracé à la main. `shine.wav` -28 à -32 : brillance, étiquette bleue.
- `clic-souris.wav` -31 : petit accent. Tous sous la voix.

## Interdits
Texte noir sur l'image. Dégradé ou néon sur les listes. Grain, noir et blanc ou désaturation de l'image (la colo reste naturelle, LUT choisie par `preparer`). Petites mentions en graisse fine. Texte sur la tête. Barre de progression.

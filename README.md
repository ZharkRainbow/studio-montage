# Studio de montage

Un studio de montage pour reels et shorts, qui tourne en local sur ton Mac, avec Claude Code.

- **L'Atelier de relecture** : tu coupes les blancs, tu fixes le début et la fin, tu écris le titre et l'accroche. Puis tu relis le rendu, tu poses des retours horodatés, et un bouton prépare la consigne pour Claude.
- **Des skills pour Claude Code** : trouver les bons passages d'une vidéo longue, écrire les accroches, monter un reel dans le style classique, appliquer tes retours, analyser le montage d'un concurrent.

Rien ne quitte ta machine : la transcription se fait en local.

## Installer en un copier-coller

Ouvre Claude Code et colle ce message :

```
Installe le studio de montage : https://github.com/ZharkRainbow/studio-montage — clone-le dans ~/Documents/studio-montage, lis le README et lance bash installer.sh.
```

Claude installe tout. Quand c'est fini, ferme Claude Code et rouvre-le.

## Installer à la main

Il faut un Mac (Apple Silicon conseillé), [Homebrew](https://brew.sh) et [Claude Code](https://claude.com/claude-code).

```bash
git clone https://github.com/ZharkRainbow/studio-montage.git ~/Documents/studio-montage
cd ~/Documents/studio-montage
bash installer.sh
```

Le script installe ffmpeg, whisper.cpp et son modèle (1,6 Go), Node, ImageMagick, Chrome, puis les skills dans `~/.claude/skills`. Il se relance sans risque. Ferme et rouvre Claude Code à la fin.

## Lancer l'Atelier

Double-clic sur **Ouvrir Studio.command**, ou :

```bash
cd ~/Documents/studio-montage && python3 -m studio --port 8768 --open
```

Il s'ouvre sur http://localhost:8768. Pour l'arrêter : `Ctrl+C`. Diagnostic : `python3 -m studio doctor` (la même liste que la page **Réglages**).

## Le parcours

| Étape | Ce que tu fais |
|---|---|
| Montage | La vidéo, la timeline dessous : blancs hachurés (Léger, Normal, Serré), « Supprimer les blancs », poignées DÉBUT et FIN, titre et accroche. « Envoyer en relecture » exporte le montage avec l'encadré d'accroche. |
| Relecture | Le MP4 rendu, en versions V1, V2… Transcript mot à mot, dessin sur l'image, retours en commentaire ou en coupe. « Copier la consigne » prépare le texte à coller dans Claude Code (`/montage-reels …`). |

### Les gestes du Montage

| Geste | Ce qu'il fait |
|---|---|
| Espace | Lecture, pause |
| `I` / `O` | Début, fin du reel sur la tête de lecture |
| Clic sur un blanc | Le garder ou le couper |
| Molette | Zoomer sous le pointeur |
| `+` / `−` · `Maj+Z` | Zoomer, dézoomer · tout voir |
| `Maj` + glisser | Sélectionner une zone ; `Suppr` la coupe, `Échap` l'efface |
| Pastille de vitesse | 1× → 1,2× → 1,5× → 2× |

Un projet = un fichier vidéo. Le montage et les retours sont écrits en JSON dans le dossier du projet (`.studio-data/`), lisibles par Claude.

## Les skills

| Skill | Ce qu'il fait | Comment le lancer |
|---|---|---|
| `hooks-shorts` | Trouve dans une vidéo longue les passages qui feront de bons shorts et écrit leurs accroches. Apprend de tes corrections. | « trouve les hooks de cette vidéo » |
| `viral-hooks` | Banque de 100 structures d'accroche, pour trouver un angle. | « donne-moi des angles d'accroche » |
| `classique` et `montage-styles` | Monte un reel face caméra dans le style classique : sous-titres mot à mot, mots en profondeur derrière la personne, cartons, listes, puis contrôle et dépôt dans l'Atelier. | `/classique /chemin/rush.mp4` |
| `montage-reels` | Produit la V1 d'un reel validé, ou applique tes retours de relecture, puis dépose la nouvelle version. | coller la consigne de l'Atelier |
| `analyze-editing-inspiration` | Analyse le montage d'un reel qui t'inspire (rythme, coupes, texte, motion, son) et en tire une fiche de règles réutilisables. Installé depuis le dépôt public d'AI Studio. | « analyse le montage de ce reel » + le fichier ou le lien |
| `hyperframes`, `media-use`, `embedded-captions` | Animation et motion design en HTML, musique et son, sous-titres incrustés. Installés depuis le dépôt officiel de HeyGen. | « fais une animation de titre », « sous-titre cette vidéo » |

## Tes réglages

`~/.config/studio-montage/profil.json` (créé par l'installation) :

| Champ | Rôle |
|---|---|
| `marque` | Le nom affiché dans l'habillage complet du style classique |
| `luts_dir`, `lut_log` | Si ta caméra filme en Log : le dossier de tes `.cube` et le nom de la LUT de conversion officielle du fabricant. Sinon, laisse `null` : aucune couleur n'est ajoutée. |
| `sfx_dir` | Ton dossier de bruitages, avec les noms listés dans `montage-styles/references/plan-classique.md` |
| `musique_dir`, `musique_defaut` | Ton dossier de musiques et la piste par défaut |
| `polices_dir` | Où chercher la police ZT Nature si tu l'as achetée |

Rien n'est obligatoire. Sans bruitages ni musique, le reel sort sans. Sans ZT Nature (police payante), le studio et le style classique utilisent Inter Tight, livrée avec le dépôt (licence OFL).

## Règles de base

- La voix ne se retouche pas : seulement le volume et un limiteur sur les pointes.
- Pas de colorimétrie ajoutée : une source déjà en Rec.709 reste telle quelle.
- Pour supprimer un projet, passe par l'Atelier (il va à la Corbeille). Ne touche jamais `.studio-data` à la main.
- Ne redémarre pas l'Atelier pendant qu'une tâche tourne (page Tâches).

## Licences

- Inter Tight, Instrument Serif, JetBrains Mono : SIL Open Font License 1.1.
- GSAP : licence indiquée dans l'en-tête du fichier.
- HyperFrames (HeyGen) et `analyze-editing-inspiration` (AI Studio) ne sont pas copiés ici : l'installation les récupère depuis leurs dépôts publics, sous leurs propres conditions.

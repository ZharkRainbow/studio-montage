---
name: montage-styles
description: Moteur du style classique. Utiliser quand /classique est lancé, ou quand il faut monter, recontrôler ou corriger une vidéo face caméra dans le style classique (découpe au mot, plan par vidéo, rendu HyperFrames, contrôle, dépôt dans l'Atelier de relecture).
---

# Moteur du style classique

Une vidéo face caméra passe par une chaîne fixe. Le style ne se règle QUE par `plan.json`. Le CSS et le JS du moteur ne se modifient jamais pour une vidéo. Les rendus se font l'un après l'autre, jamais en parallèle.

```
PY=~/.venv-studio-montage/bin/python ; M=~/.claude/skills/montage-styles/moteur/montage.py
RUSH=<nom du fichier sans extension> ; P=<dossier du rush>/$RUSH-classique
```

Réglages de la personne (marque, LUT, sons, musiques) : `~/.config/studio-montage/profil.json`, modèle dans `profil.exemple.json`. Tout est facultatif : sans LUT, sans sons et sans musique, le reel sort quand même.

## Étapes (dans l'ordre, pour chaque rush)
1. **Lire le rush avant de couper.** Un rush brut contient souvent plusieurs prises, des faux départs, une fin répétée. Transcrire d'abord sans rien garder de côté :
   `$PY -I $M decouper --projet $P --rush $RUSH --source /chemin/$RUSH.mp4`
   puis lire les mots dans `$P/job/montage/$RUSH-analysis-minimale.json` (temps = `startFrame` / fps). Choisir les bonnes prises (la dernière prise réussie d'une phrase, jamais une phrase coupée).
2. **Découper pour de bon** avec les plages gardées, en secondes :
   `$PY -I $M decouper --projet $P --rush $RUSH --source /chemin/$RUSH.mp4 --garder 3.2-41.0,55.5-80.2`
   Les blancs de plus de 0,35 s entre deux mots sont coupés (`--blanc` pour changer). Sortie : `$P/job/montage/$RUSH-cuts.json`.
3. `$PY -I $M preparer --projet $P --rush $RUSH --source /chemin/$RUSH.mp4 --style classique` : vidéo coupée, mots, image en Rec.709 (rush en Log : LUT `lut_log` du profil ; déjà en Rec.709 : aucune LUT, jamais de colorimétrie ajoutée), détourage de la personne (environ 3 min).
4. Lire `$P/mots.txt` EN ENTIER : numéro de chaque mot, image où il commence, coupes. Repérer l'accroche, les mots forts, les chiffres, les objections, les énumérations.
5. `$PY -I $M mesurer --projet $P --plages 66-144,690-718` (images de la vidéo coupée) : sommet et largeur de la tête toutes les 3 images (`--pas 1` pour chaque image), zones libres. Rien n'est écrit.
6. Écrire `$P/plan.json` selon `references/plan-classique.md` (modèle de forme : `exemples/exemple-classique.json`).
7. Versions : `v1`, puis `v2`, `v3`… à chaque correction ; `generer` refuse une version qui existe déjà.
   `$PY -I $M generer --projet $P --version v1`
   `$PY -I $M rendre --projet $P --version v1`
   `$PY -I $M controler --projet $P --version v1`
   Code 1 = défaut bloquant : corriger le plan et refaire la version suivante. Traiter chaque ligne « À REGARDER » en ouvrant la planche ou l'image indiquée. Ligne « INFO » d'un écartement automatique de plus de 20 px : corriger avec `dx`.
8. **Regarder `$P/vN/controle/planche.png`** avec `references/controle.md`, point par point. Un point raté : corriger le plan, version suivante.
9. `$PY -I $M controler --projet $P --version vN --vu` (atteste que la planche a été regardée), puis
   `$PY -I $M deposer --projet $P --version vN --dossier "Style classique"` (crée le dossier et un projet dans l'Atelier de relecture), ou `--projet-atelier ID` pour une nouvelle version d'un projet existant. Le dépôt refuse s'il reste un défaut, si `--vu` manque, si le fichier a changé ou si l'Atelier ne tourne pas (le lancer : `cd ~/Documents/studio-montage && python3 -m studio --port 8768`).
10. Dire à la personne : le projet dans l'Atelier, ce qui a été vérifié (contrôle, planche) et ce qui ne l'a pas été (pas d'écoute en temps réel : rythme, synchro, ressenti du son).

Retours de relecture sur une version : skill `montage-reels`, puis corriger `plan.json` et refaire la version suivante avec ce moteur.

## Le son
La voix reste celle du rush : seulement le volume (-14 LUFS), un passe-haut à 70 Hz et un limiteur sur les pointes. Musique à -34 LUFS sous la voix.

## Drapeaux rouges (s'arrêter)
- « Je corrige le CSS pour cette vidéo » : non, on corrige le plan. Si aucune option du plan ne convient, demander.
- « Le contrôle bloque mais c'est voulu » : non.
- « Je dépose sans regarder la planche », « --vu sans l'avoir ouverte » : interdit.
- Texte noir, néon, image désaturée, petit mot à plus de 20 px de son grand mot, texte sur la tête : refusés. Le contrôle bloque dès 10 % de la boîte sur la tête et signale dès 3 %.

## Fichiers
`moteur/` (code), `references/` (plan, contrôle), `exemples/` (plan validé : la forme seulement, jamais le contenu), `profil.exemple.json`.

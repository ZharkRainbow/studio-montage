---
name: montage-reels
description: Produire la V1 d'un reel validé dans l'Atelier de relecture (localhost:8768), ou appliquer les retours d'une relecture, puis déposer la nouvelle version. Déclencheurs - une consigne collée qui commence par « /montage-reels produis la V1 de ... » ou « /montage-reels applique ces retours au reel ... » (boutons « Copier la consigne » de l'Atelier). Aussi - « applique mes retours », « refais la V2 du reel », « corrige le reel d'après la relecture ».
---

# montage-reels : le lien entre l'Atelier de relecture et Claude

L'Atelier de relecture (`~/Documents/studio-montage`, http://localhost:8768) fait deux choses à la main : le **Montage** (début, fin, blancs coupés, titre, accroche) et la **Relecture** (le MP4 rendu, des retours horodatés). Ce skill fait le reste : produire la vidéo finie, puis appliquer les retours. Toute écriture dans l'Atelier passe par son API, jamais à la main dans `.studio-data`.

## 0. Le style de la personne
Avant la première production, lire `STYLE.md` dans ce dossier. S'il n'existe pas, demander une fois à la personne ce qu'elle veut sur ses reels (sous-titres ou non et lesquels, style classique ou autre, musique, carte de fin, couleurs, police), l'écrire dans `STYLE.md`, puis s'y tenir. Une règle qui ressort d'un retour (« je préfère l'accroche sur deux lignes ») s'y inscrit le jour même, en remplaçant celle qu'elle contredit.

## 1. « produis la V1 de <dossier du projet> »
1. Lire `<dossier>/a-produire/<id>.json` : `montage_valide` (le MP4 exporté par l'Atelier : blancs déjà coupés, encadré d'accroche déjà posé), `titre`, `accroche`, `morceaux_gardes` (temps dans la source), `fichier_source`.
2. Partir de `montage_valide`, jamais de la source : c'est ce que la personne a validé.
3. Appliquer le style de `STYLE.md` avec le bon outil : `embedded-captions` pour les sous-titres, `/classique` pour le style classique, `hyperframes` pour une animation ou un titre, `media-use` pour la musique et le son.
4. Écrire le rendu dans `V1/` à côté de `montage_valide`, puis le déposer (section 3).
5. Vérifier que le début est bien celui choisi au Montage :
   `python3 ~/.claude/skills/montage-reels/scripts/verifier-debut.py <dossier du projet> "<mp4 rendu>"`
   (`OK, meme debut` ou `DIFFERENT`, code 1). La référence est faite des `morceaux_gardes` collés, pas d'une fenêtre continue de la source.

## 2. « applique ces retours au reel ... »
La consigne donne le nom du reel, le dossier du projet, le MP4 relu et sa version, puis chaque retour : COMMENTAIRE ou COUPE, temps REEL et SOURCE, mots cités, demande, captures.
1. Lire `<dossier>/project.json` (sources, versions), `montage.json` (bornes, blancs, titre, accroche), `retours/v<N>.json` et `retours/images/` (dessins et captures : les REGARDER).
2. Retrouver la chaîne qui a produit le MP4 relu (le plan du style classique, la composition HyperFrames, le script) et la modifier. Ne pas réécrire ce qui existe.
3. Règles :
   - Un retour = une modification. Ne rien changer d'autre que ce qui est demandé.
   - REEL = temps dans la vidéo relue ; SOURCE = temps dans le fichier d'origine. Si la consigne dit « SOURCE indisponible », se fier aux mots cités.
   - Accroche ou texte à réécrire : proposer 2 ou 3 versions dans le chat AVANT d'incruster ; jamais de deux-points ni de tiret cadratin.
   - L'accroche incrustée est celle que la personne a choisie. Après son choix, l'écrire dans l'Atelier AVANT de rendre, pour que l'Atelier et le fichier disent la même chose :
     ```bash
     P=<id du projet>; A='<annonce> / (<finalité>)'
     curl -s localhost:8768/api/projects/$P | python3 -c 'import json,sys; p=json.load(sys.stdin); p["montage"]["hook"]=sys.argv[1]; print(json.dumps(p))' "$A" \
      | curl -s -X PUT localhost:8768/api/projects/$P -H 'Content-Type: application/json' --data-binary @- \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["montage"]["hook"])'
     ```
   - L'encadré d'accroche est visible dès la PREMIÈRE IMAGE du reel, sans animation d'entrée : la miniature est prise sur la première image. Vérifier la frame 0 (`ffmpeg -frames:v 1`) avant de déposer.
   - Une demande floue (« un truc plus stylé ») : faire 2 variantes courtes et laisser la personne choisir.
   - Le son de la voix ne se retouche pas (ni débruitage, ni égaliseur, ni compression) : seulement le volume et un limiteur sur les pointes, sauf demande explicite.
4. Rendre dans `V<N+1>/`, même nom de fichier, puis déposer (section 3).

## 3. Déposer et vérifier
- Déposer la version (elle devient la version relue, son transcript se lance seul) :
  `curl -s -X POST http://localhost:8768/api/projects/<id>/versions -H 'Content-Type: application/json' -d '{"path":"<chemin absolu du mp4>"}'`
- Exception : si la source du projet est elle-même un rendu de Claude (trailer, version longue), la V<N+1> va dans un **nouveau projet dont elle est la source** (`POST /api/projects {name, folder_id}`, puis `POST /api/projects/<id>/sources {path}` et `/versions {path}`), sinon le Montage reste sur l'ancienne version.
- **Un fichier rendu sur disque n'est pas une version déposée.** Comparer l'empreinte de la version active de l'Atelier avec le fichier livré :
  ```bash
  P=<id du projet>; F="<fichier livré>"
  V=$(curl -s localhost:8768/api/projects/$P | python3 -c 'import json,sys; p=json.load(sys.stdin); v=[x for x in p["versions"] if x["id"]==p.get("active_version")] or p["versions"][-1:]; print(v[0]["path"])')
  [ -f "$V" ] && [ "$(shasum -a 256 < "$V")" = "$(shasum -a 256 < "$F")" ] && echo "DÉPOSÉE" || echo "PAS DÉPOSÉE : l'Atelier lit $V"
  ```
- Vérifier sur une image extraite (ffmpeg) que chaque retour est bien appliqué, puis dire à la personne de recharger la Relecture.
- Le transcript de la Relecture est un whisper du fichier entier : pour juger un début, une reprise ou un mot coupé, retranscrire le passage seul plutôt que se fier à ses bornes de mots (whisper étire les mots sur les pauses et invente parfois du texte dans les longs silences).

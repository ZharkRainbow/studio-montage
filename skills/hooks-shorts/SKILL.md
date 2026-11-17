---
name: hooks-shorts
description: Trouver dans une vidéo longue (podcast, consulting, live, masterclass, témoignage) les moments qui feront de bons shorts, avec un hook qui démarre fort, et écrire leur accroche. Apprend des corrections de la personne à chaque série. Déclencheurs - « trouve les hooks », « sélectionne les shorts », « détecte les moments viraux », « fais la sélection du podcast », « quels passages on peut couper en reels », « les meilleurs moments de cette vidéo ». Ne PAS utiliser pour appliquer des retours de relecture (montage-reels).
---

# hooks-shorts : trouver les bons hooks, et apprendre de chaque correction

But : que la personne n'ait plus à refaire les débuts et les accroches à la main. Chaque série relue rend le skill meilleur.

## 0. Avant tout : relire la mémoire du skill
1. `LECONS.md` (dans ce dossier) : les règles tirées des corrections. Elles priment sur tout le reste.
2. Les règles de style de la personne, si elle en a un fichier (lui demander où il est la première fois).
3. Si une série précédente a été relue dans l'Atelier et pas encore apprise : lancer d'abord l'étape 5.

## 1. Le matériau
- Transcript mot à mot horodaté (whisper.cpp en `-ml 1 -sow`, ou WhisperX), jamais seulement le transcript d'un outil d'enregistrement (Riverside, Fathom, Zoom) : ses temps sont décalés de 1 à 4 s, parfois 15 s.
- Qui parle : seule la personne à l'image dit le hook.
- Consulting, live, podcast : chercher dans le transcript toute demande de ne pas diffuser un passage (« coupe ça », « ne le mets pas dans la vidéo ») et l'exclure.

## 2. Trouver les candidats
Un candidat est une phrase qui OUVRE une idée et frappe seule :
- une affirmation qui contredit une croyance (« le nombre d'abonnés ne sert à rien ») ;
- une erreur que tout le monde fait (« tout le monde essaie de vendre au 1er message ») ;
- un résultat concret et rare (un chiffre, une durée, un avant-après) ;
- une histoire qui démarre (« le jour où j'ai viré… ») ;
- une prédiction tranchée (« demain l'IA prospectera mieux que toi »).
Ratisser large d'abord : tous les débuts possibles de la vidéo, puis trier. Pour trouver un angle, la banque `viral-hooks` peut aider.

## 3. Trier : ce qui est éliminé d'office
- Début sur un mot de liaison ou une amorce (liste dans LECONS.md, règle 1).
- Première phrase qui renvoie à ce qui précède (« ça », « lui », « ce truc-là »).
- Hésitation, faux départ ou intonation plate dans les 4 premières secondes : le vérifier en retranscrivant les 4 premières secondes seules (`ffmpeg -ss <début> -t 4`, puis whisper) et en comparant au transcript complet.
- Fin qui coupe une phrase ou qui traîne après la chute.
- Passage qui exige un partage d'écran, ou qui dessert la personne.
- Doublon de sujet avec un autre short ou une série déjà publiée.
Durée : 30 à 90 s. Un passage plus long se découpe en plusieurs shorts, chacun avec son propre hook.

## 4. Livrer
Pour chaque short retenu :
- id (préfixe de la vidéo + numéro, ex. `POD-03`), début et fin au centième recalés au mot près, durée ;
- la première phrase (le hook) et la dernière, mot pour mot ;
- 2 accroches au format de LECONS.md (règles 4 à 7) : affirmation avec un mot en CAPITALES, puis la finalité entre parenthèses ; troisième personne ; jamais de deux-points ni de tiret cadratin ;
- une note de 1 à 10, une ligne qui la justifie, les risques ;
- un fichier `selection.json` (champs : id, debut, fin, duree_s, hook, derniere_phrase, titre, accroches, note, justification, risques) et un `SELECTION.md` lisible, trié par note.
Contrôle final par script : chaque début et chaque fin existent dans le transcript, aucune accroche ne contient « : » ni « — », aucun hook ne commence par un mot de la liste noire.
Toujours soumettre les accroches à la personne avant de les incruster.

Pour la relecture : déposer chaque short dans l'Atelier de relecture sous un nom qui commence par son id (`POD-03 - …`), c'est ce qui permet à l'étape 5 de retrouver les corrections.

## 5. Apprendre (après chaque série relue)
1. `python3 scripts/apprendre.py <chemin(s) des selection.json de la série>`
   Il compare la sélection proposée à ce que la personne a gardé dans l'Atelier (accroche réécrite, début et fin recoupés, short validé) et ajoute les écarts à `retours.jsonl`. Données de l'Atelier lues dans `$STUDIO_DATA_DIR` (par défaut `~/Documents/studio-montage/.studio-data`).
2. Lire les écarts affichés. Pour chaque motif qui revient (au moins 2 cas), écrire ou corriger une règle dans `LECONS.md` avec les ids en preuve. Un cas isolé reste dans `retours.jsonl` sans devenir une règle.
3. Dire à la personne en 3 lignes ce qui a été appris.
`LECONS.md` et `retours.jsonl` sont la mémoire du skill : les mettre à jour fait partie du travail, sans demander. Modifier ce SKILL.md (la méthode) reste soumis à l'accord de la personne.

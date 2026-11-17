---
name: classique
description: Utiliser quand la personne tape /classique, ou demande de monter des vidéos face caméra « en style classique », avec des fichiers ou un dossier de rushes.
---

# /classique : monter des rushes dans le style classique

Le style classique :
- image naturelle (Rec.709, LUT de conversion seulement si la caméra filme en Log), jamais de grain ni de noir et blanc ;
- accroche en grand italique dès l'image 0, effacée vers le bas, qui brille ;
- sous-titres mot à mot, flou vers net (ZT Nature si elle est installée, sinon Inter Tight) ;
- 2 ou 3 mots en profondeur derrière la personne (dégradé bleu, étirés, brillance) et un chiffre en compteur ;
- cartons sur fond bleu (« CE QU’ON ME DIT », N°01) ;
- panneau d'infos en bas, listes qui défilent en blanc avec lueur, au plus 2 ronds à la main et 1 soulignement bleu ;
- bruitages et musique calme à -34 LUFS si la personne en a configuré (profil) ;
- habillage épuré : les quatre coins.

**SOUS-SKILL OBLIGATOIRE : `montage-styles`.** Le suivre étape par étape, écrire le plan selon `~/.claude/skills/montage-styles/references/plan-classique.md`.

Entrée : fichiers ou dossier de rushes. Si rien n'est donné, demander les vidéos. Dossier de l'Atelier par défaut : celui que la personne nomme, sinon « Style classique ».

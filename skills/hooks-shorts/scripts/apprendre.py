#!/usr/bin/env python3
"""Apprendre des corrections : compare ce que le skill a proposé (selection.json) avec ce que
la personne a gardé dans l'Atelier (accroche réécrite, début et fin recoupés, short validé ou non).

usage : apprendre.py <selection.json> [<selection.json> ...]
Ajoute une ligne par short dans ../retours.jsonl (sans doublon) et affiche le bilan à reporter dans LECONS.md.
"""
import glob, json, os, re, sys
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
JOURNAL = ICI / 'retours.jsonl'
ATELIER = Path(os.environ.get('STUDIO_DATA_DIR', Path.home() / 'Documents/studio-montage/.studio-data')).expanduser() / 'projects'

proposes = {}
for f in sys.argv[1:]:
    data = json.load(open(f, encoding='utf-8'))
    for s in data.get('shorts', data if isinstance(data, list) else []):
        proposes[s['id']] = s

deja = set()
if JOURNAL.exists():
    for ligne in open(JOURNAL, encoding='utf-8'):
        r = json.loads(ligne); deja.add((r['id'], r.get('accroche_finale'), r.get('coupe_debut')))

nouveaux, bilan = [], dict(shorts=0, valides=0, accroche_reecrite=0, debut_recoupe=0, fin_recoupee=0)
for pj in glob.glob(str(ATELIER / '*/project.json')):
    p = json.load(open(pj, encoding='utf-8'))
    m = re.match(r'([A-Z]{2,5}-\d+)', p.get('name', ''))
    if not m or m.group(1) not in proposes:
        continue
    mt_path = Path(pj).with_name('montage.json')
    if not mt_path.exists():
        continue
    mt = json.load(open(mt_path, encoding='utf-8'))
    garde = mt.get('morceaux_gardes') or []
    if not garde:
        continue
    s = proposes[m.group(1)]
    r = dict(id=m.group(1), valide=bool(p.get('validated_at')),
             coupe_debut=round(garde[0]['start'], 2),
             coupe_fin=round(max(0.0, (mt.get('duree_source') or 0) - garde[-1]['end']), 2),
             hook_propose=s.get('hook'), accroches_proposees=s.get('accroches'),
             accroche_finale=mt.get('accroche'), titre_final=mt.get('titre'), note_proposee=s.get('note'))
    r['accroche_reecrite'] = bool(r['accroche_finale']) and r['accroche_finale'] not in (r['accroches_proposees'] or [])
    bilan['shorts'] += 1
    bilan['valides'] += r['valide']
    bilan['accroche_reecrite'] += r['accroche_reecrite']
    bilan['debut_recoupe'] += r['coupe_debut'] > 0.25
    bilan['fin_recoupee'] += r['coupe_fin'] > 0.25
    if (r['id'], r['accroche_finale'], r['coupe_debut']) not in deja:
        nouveaux.append(r)

with open(JOURNAL, 'a', encoding='utf-8') as fh:
    for r in nouveaux:
        fh.write(json.dumps(r, ensure_ascii=False) + '\n')
print(json.dumps(bilan, ensure_ascii=False))
for r in nouveaux:
    if r['accroche_reecrite'] or r['coupe_debut'] > 0.25:
        print(f"{r['id']} | début recoupé {r['coupe_debut']} s | hook proposé : {(r['hook_propose'] or '')[:70]!r}")
        if r['accroche_reecrite']:
            print(f"   proposé : {r['accroches_proposees']}\n   gardé   : {r['accroche_finale']!r}")
print(f"{len(nouveaux)} ligne(s) ajoutée(s) à {JOURNAL}")

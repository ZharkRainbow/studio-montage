// Ce qu'un dossier sait dire de lui-même : un point d'avancement, et la même liste en CSV.
//
// Un dossier se lit, il ne se transforme pas. Aucune de ces deux actions ne touche un projet :
// pas de preset appliqué, pas de rendu lancé, pas de validation en masse. On regarde l'état,
// on le copie dans un message, ou on l'emporte dans un tableur.
import { fmtDuration } from '../core/dom.js';
import { STATUS, findFolder, state } from '../core/state.js';
import { toast } from '../core/toast.js';
import { copyText } from '../settings.js';

function projetsDu(folderId) {
  return state.projects.filter(projet => projet.folder_id === folderId).sort((a, b) => a.name.localeCompare(b.name, 'fr'));
}

function etat(projet) {
  return STATUS[projet.status]?.label || projet.status || '';
}

function duree(secondes) {
  return secondes ? fmtDuration(secondes) : '';
}

function contenu(folderId) {
  const folder = findFolder(folderId);
  if (!folder) return null;
  const projets = projetsDu(folderId);
  if (!projets.length) {
    toast(`Le dossier « ${folder.name} » est vide : rien à lister.`, { kind: 'info' });
    return null;
  }
  return { folder, projets };
}

export function copierPoint(folderId) {
  const dossier = contenu(folderId);
  if (!dossier) return;
  const { folder, projets } = dossier,
    valides = projets.filter(projet => projet.status === 'done').length,
    gardes = projets.filter(projet => projet.status !== 'ecarte').length;
  const lignes = projets.map(projet => {
    const reel = duree(projet.reel_duration);
    return `- ${projet.name} : ${etat(projet)}${reel ? ` (${reel})` : ''}${projet.media_missing ? ' — fichier déplacé' : ''}`;
  });
  copyText(`${folder.name} — ${valides} validés sur ${gardes}\n${lignes.join('\n')}\n`, 'Point d’avancement');
}

function cellule(valeur) {
  const texte = String(valeur ?? '');
  return /[";\n]/.test(texte) ? `"${texte.replace(/"/g, '""')}"` : texte;
}

/* Le fichier part en téléchargement. Point-virgule et BOM : un tableur réglé en français
   ouvre le fichier en colonnes du premier coup, sans boîte de dialogue d'import. */
export function exporterListe(folderId) {
  const dossier = contenu(folderId);
  if (!dossier) return;
  const { folder, projets } = dossier;
  const entete = ['Nom', 'Durée', 'Version', 'Fichier final', 'Statut'];
  const lignes = projets.map(projet => [
    projet.name,
    duree(projet.reel_duration || projet.duration),
    projet.versions?.find(version => version.id === projet.active_version)?.label || '',
    projet.export_path || '',
    etat(projet),
  ]);
  const csv = '﻿' + [entete, ...lignes].map(ligne => ligne.map(cellule).join(';')).join('\r\n') + '\r\n';
  const lien = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })),
    download: `${folder.name.replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '') || 'dossier'}.csv`,
  });
  document.body.append(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 4000);
  toast(`Liste de « ${folder.name} » exportée : ${projets.length} projets.`, { kind: 'success' });
}

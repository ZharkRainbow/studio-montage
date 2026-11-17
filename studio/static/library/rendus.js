// La page Rendus : la file des tâches du studio, tous projets confondus.
//
// L'éditeur suit déjà les tâches du projet ouvert. Ici on regarde la machine : ce qui
// tourne, ce qui attend, ce qui a échoué, et on peut annuler ou ouvrir le projet concerné.
import { api } from '../core/api.js';
import { $, esc, relTime } from '../core/dom.js';
import { JOB_LABELS, JOB_STATES, state } from '../core/state.js';
import { go } from '../core/router.js';
import { toast } from '../core/toast.js';

const EN_COURS = ['queued', 'running'];
let minuterie = null;

function nomDuProjet(job) {
  const projet = state.projects.find(p => p.id === job.project_id);
  return projet ? projet.name : 'Projet supprimé';
}

function ligne(job) {
  const actif = EN_COURS.includes(job.state);
  const progression = Math.max(0, Math.min(100, Number(job.progress) || 0));
  return (
    `<article class="rendu-row r-${esc(job.state)}">` +
    `<div class="rendu-main">` +
    `<strong>${esc(nomDuProjet(job))}</strong>` +
    `<span class="rendu-type">${esc(JOB_LABELS[job.type] || job.type)}</span>` +
    `</div>` +
    `<div class="rendu-etat">` +
    `<span class="status s-job-${esc(job.state)}">${esc(JOB_STATES[job.state] || job.state)}</span>` +
    (actif ? `<div class="rendu-barre"><i style="width:${progression}%"></i></div>` : '') +
    `<small>${esc(job.error || job.message || '')}</small>` +
    `</div>` +
    `<div class="rendu-temps"><small>${esc(relTime(job.updated_at))}</small></div>` +
    `<div class="rendu-actions">` +
    (job.project_id
      ? `<button class="link-button" type="button" data-rendu-ouvrir="${esc(job.project_id)}">Ouvrir le projet</button>` +
        `<button class="link-button" type="button" data-rendu-dossier="${esc(job.project_id)}">Ouvrir le dossier</button>`
      : '') +
    (actif ? `<button class="link-button" type="button" data-rendu-annuler="${esc(job.id)}">Annuler</button>` : '') +
    `</div></article>`
  );
}

function groupe(titre, jobs, vide) {
  return (
    `<section class="rendu-groupe"><h2>${esc(titre)}</h2>` +
    (jobs.length ? jobs.map(ligne).join('') : `<p class="rendu-vide">${esc(vide)}</p>`) +
    `</section>`
  );
}

export function renderRendus() {
  const jobs = state.rendus || [];
  const enCours = jobs.filter(job => job.state === 'running');
  const enAttente = jobs.filter(job => job.state === 'queued');
  const finis = jobs.filter(job => job.state === 'succeeded').slice(0, 30);
  const echecs = jobs.filter(job => job.state === 'failed' || job.state === 'cancelled').slice(0, 30);
  $('#chantier-view').innerHTML =
    `<header class="lib-head"><div class="lib-title"><span class="eyebrow">Atelier</span>` +
    `<h1>Rendus</h1><p>Les tâches du studio : proxy, transcription, envoi en relecture, production. ` +
    `Elles tournent sur cette machine, une à la fois.</p></div></header>` +
    `<div class="rendu-liste">` +
    groupe('En cours', enCours, 'Rien ne tourne en ce moment.') +
    groupe('En attente', enAttente, 'Aucune tâche en attente.') +
    groupe('Terminées', finis, 'Aucune tâche terminée pour l’instant.') +
    groupe('Échecs et annulations', echecs, 'Aucun échec.') +
    `</div>`;
}

export async function chargerRendus() {
  try {
    const payload = await api('/api/jobs');
    state.rendus = payload.jobs || [];
  } catch (error) {
    state.rendus = [];
  }
  majBanniere();
}

// La file est commune à tous les projets : la bannière doit aussi se mettre à jour
// quand un travail démarre depuis une autre page du menu.
export function suivreRendus() {
  if (minuterie) return;
  minuterie = setInterval(async () => {
    await chargerRendus();
    if (state.route?.name === 'chantier' && state.route.section === 'rendus') renderRendus();
  }, 2000);
}

/* La bannière : un rendu en cours se voit depuis n'importe quelle page du menu. */
export function majBanniere() {
  const banniere = $('#rendu-banniere');
  if (!banniere) return;
  const actifs = (state.rendus || []).filter(job => EN_COURS.includes(job.state));
  const dansEditeur = Boolean(state.project);
  banniere.hidden = !actifs.length || dansEditeur;
  if (banniere.hidden) return;
  const job = actifs[0];
  banniere.innerHTML =
    `<span class="rendu-point" aria-hidden="true"></span>` +
    `<span>${actifs.length > 1 ? `${actifs.length} rendus en cours` : 'Un rendu est en cours'} · ` +
    `${esc(nomDuProjet(job))} · ${esc(JOB_LABELS[job.type] || job.type)}</span>` +
    `<button class="link-button" type="button" data-rendu-voir>Voir les rendus</button>`;
}

export async function ouvrirRendus() {
  await chargerRendus();
  renderRendus();
}

// La page et la bannière écoutent leur propre zone : le routeur des clics reste court.
let branche = false;
export function brancherRendus() {
  if (branche) return;
  branche = true;
  for (const zone of [$('#chantier-view'), $('#rendu-banniere')]) zone?.addEventListener('click', event => actionRendu(event.target));
}

function actionRendu(cible) {
  const dossier = cible.closest('[data-rendu-dossier]');
  if (dossier) {
    api(`/api/projects/${encodeURIComponent(dossier.dataset.renduDossier)}/reveal`, { method: 'POST', body: {} })
      .catch(error => toast(error.message, { kind: 'error' }));
    return true;
  }
  const ouvrir = cible.closest('[data-rendu-ouvrir]');
  if (ouvrir) {
    go(`#/projet/${encodeURIComponent(ouvrir.dataset.renduOuvrir)}`);
    return true;
  }
  if (cible.closest('[data-rendu-voir]')) {
    go('#/rendus');
    return true;
  }
  const annuler = cible.closest('[data-rendu-annuler]');
  if (annuler) {
    api(`/api/jobs/${encodeURIComponent(annuler.dataset.renduAnnuler)}/cancel`, { method: 'POST', body: {} })
      .then(ouvrirRendus)
      .catch(error => toast(error.message, { kind: 'error' }));
    return true;
  }
  return false;
}

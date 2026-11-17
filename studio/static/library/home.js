// Accueil.
import { $, esc, fmtDuration, ICONS, relTime, storage } from '../core/dom.js';
import { findFolder, findProject, state } from '../core/state.js';
import { projectCard, statusBadge, thumbHtml } from './sidebar.js';

export function renderHome() {
  const root = $('#home-continue');
  if (!state.projects.length) {
    root.innerHTML =
      `<div><div class="home-block-head"><div><span class="eyebrow">Premiers pas</span><h2>` +
      `Par où commencer</h2></div></div><div class="onboarding">
      ` +
      `<button class="onboard-card" type="button" data-action="new-project">` +
      `<span class="onboard-icon">${ICONS.plus}</span><strong>Créer un projet</strong><span>` +
      `Donne-lui un nom, choisis ta vidéo, le studio prépare le proxy de lecture.</span>` +
      `</button>
      ` +
      `<button class="onboard-card" type="button" data-action="new-folder">` +
      `<span class="onboard-icon">${ICONS.folder}</span><strong>Organiser en dossiers</strong>` +
      `<span>Un dossier par client, par série ou par format, et un glisser-déposer pour ranger.` +
      `</span></button>
    </div></div>`;
    return;
  }
  const gardes = state.projects.filter(project => project.status !== 'ecarte'),
    remembered = findProject(storage.get('atelier:lastProject')),
    last = (remembered?.status !== 'ecarte' && remembered) || gardes[0] || state.projects[0];
  const others = state.projects.filter(project => project.id !== last.id).slice(0, 4);
  const folder = findFolder(last.folder_id);
  const montageLabel = last.trimmed ? last.title || 'Blancs coupés' : last.has_media ? 'À monter' : 'À importer';
  const steps = [
    ['Montage', montageLabel, last.trimmed ? 100 : last.has_media ? 35 : 0, last.trimmed],
    ['Relecture', last.version_count ? `V${last.version_count} déposée` : 'En attente', last.version_count ? 100 : 0, last.version_count > 0],
  ];
  root.innerHTML =
    `<div>
    <div class="home-block-head"><div><span class="eyebrow">Reprendre</span><h2>` +
    `Là où tu t’es arrêté</h2></div></div>
    ` +
    `<article class="spotlight" data-project-card="${esc(last.id)}">
      ` +
    `<button class="p-thumb" type="button" data-open-project="${esc(last.id)}" ` +
    `aria-label="Ouvrir ${esc(last.name)}">${thumbHtml(last)}<span class="p-badges">` +
    `${statusBadge(last)}` +
    `</span>` +
    (last.duration ? `<span class="p-duration">${fmtDuration(last.duration)}</span>` : '') +
    `<` +
    `/button>
      <div class="spotlight-body">
        <h3>${esc(last.name)}</h3>
        ` +
    `<div class="spotlight-meta"><span>` +
    `${ICONS.folder}${folder ? esc(folder.name) : 'Sans dossier'}</span><span>` +
    `${ICONS.film}${last.reel_duration ? fmtDuration(last.reel_duration) : 'reel vide'}</span><span>` +
    `${ICONS.clock}${esc(relTime(last.updated_at))}</span></div>
        ` +
    `<div class="pipeline"` +
    `>` +
    steps
      .map(
        ([label, value, fill, done]) =>
          `<div class="pipeline-step ${done ? 'done' : ''}"><small>${label}</small><strong>` +
          `${esc(value)}</strong><i style="--fill:${fill}%"></i></div>`,
      )
      .join('') +
    `<` +
    `/div>
        <div class="spotlight-actions">` +
    `<button class="button primary" type="button" data-open-project="${esc(last.id)}">` +
    `${ICONS.play} Reprendre</button>` +
    `<button class="button outline" type="button" data-project-menu="${esc(last.id)}">` +
    `${ICONS.more} Actions</button></div>
      </div>
    </article>
  </div>` +
    `
  ` +
    (others.length
      ? `<div><div class="home-block-head"><div><span class="eyebrow">Récents</span><h2>` +
        `Tes derniers projets</h2></div><a class="link-button" href="#/projets">` +
        `Tout voir (${state.projects.length})</a></div>` +
        `<div class="p-grid">` +
        others.map((project, index) => projectCard(project, index)).join('') +
        `<` +
        `/div></div>`
      : '') +
    ``;
}

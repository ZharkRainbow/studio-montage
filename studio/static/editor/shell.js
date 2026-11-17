// Coquille de l’éditeur : rendu global, en-tête, les deux étapes, scène et inspecteur.
import { $, $$, esc, ICONS } from '../core/dom.js';
import { updateSaveState, updateUndoButtons } from '../core/history.js';
import { renderJobs } from '../core/jobs.js';
import { montage, versions } from '../core/montage.js';
import { findFolder, state } from '../core/state.js';
import { renderMain, renderSidebar } from '../library/sidebar.js';
import { renderMontageInspector, renderMontageStage } from './montage/view.js';
import { renderReviewInspector, renderReviewStage } from './review/view.js';

export const STEPS = [
  ['montage', 'Montage'],
  ['review', 'Relecture'],
];

export function renderStage() {
  state.stageToken += 1;
  if (state.step === 'review') renderReviewStage();
  else renderMontageStage();
}

export function stageToolbar(title, meta, right = '') {
  $('#stage-toolbar').innerHTML = `<div class="toolbar-title"><strong>${esc(title)}</strong><small>${esc(meta)}</small></div>${right}`;
}

export function emptyStage(title, copy, actions = '') {
  $('#stage-body').innerHTML =
    `<div class="empty-stage"><span class="empty-icon">${ICONS.film}</span><h2>${esc(title)}` +
    `</h2><p>${esc(copy)}</p><div class="empty-actions">${actions}</div></div>`;
  $('#transport').innerHTML = '';
}

export function renderInspector() {
  $('#inspector-actions').innerHTML = '';
  if (state.step === 'review') {
    renderReviewInspector();
    return;
  }
  $('#inspector-title').textContent = state.project?.sources?.length ? 'Titre et résultat' : 'Fichier source';
  renderMontageInspector();
}

export function refreshMontageChrome() {
  renderInspector();
  renderSteps();
}

export function setStep(step) {
  if (step === state.step) return;
  state.step = step;
  state.playing = false;
  state.playhead = 0;
  state.review.drawing = false;
  render();
}

export function render() {
  const inProject = Boolean(state.project);
  $('#shell').hidden = inProject;
  $('#editor').hidden = !inProject;
  renderSidebar();
  if (!inProject) {
    state.jobsOpen = false;
    renderMain();
    return;
  }
  renderHeader();
  renderSteps();
  renderJobs();
  renderStage();
  renderInspector();
  updateUndoButtons();
  updateSaveState();
}

export function renderHeader() {
  if (!state.project) return;
  $('#project-name').textContent = state.project.name;
  const folder = findFolder(state.project.folder_id),
    crumb = $('#crumb-folder');
  crumb.textContent = folder ? folder.name : 'Projets';
  crumb.href = folder ? `#/dossier/${encodeURIComponent(folder.id)}` : '#/projets';
  document.title = `${state.project.name} — Atelier`;
}

// Montage terminé dès qu’un geste a touché le reel ; Relecture dès qu’une version est déposée.
export function stepDone(step, project = state.project) {
  const cut = montage(project);
  if (step === 'montage') return Boolean((cut?.segments?.length || 0) > 1 || cut?.title);
  return versions(project).length > 0;
}

export function renderSteps() {
  $$('#steps button').forEach(button => {
    const step = button.dataset.step;
    button.classList.toggle('active', step === state.step);
    button.classList.toggle('complete', stepDone(step) && step !== state.step);
  });
  requestAnimationFrame(() => {
    const active = $('#steps button.active'),
      indicator = $('#steps-indicator');
    if (!active || !indicator) return;
    indicator.style.width = `${active.offsetWidth}px`;
    indicator.style.transform = `translateX(${active.offsetLeft}px)`;
  });
}

// File des tâches : création, suivi et menu Tâches.
import { api } from './api.js';
import { ensureMontage } from './montage.js';
import { $, clamp, esc, setBusy } from './dom.js';
import { saveProject } from './history.js';
import { JOB_LABELS, JOB_STATES, state } from './state.js';
import { showNotice } from './toast.js';
import { render, setStep } from '../editor/shell.js';
import { updatePrep } from '../editor/montage/view.js';

/* ---------- Rush preparation ---------- */
// The step already shows one percentage; a second one inside the message reads as a contradiction.
export function plainJobMessage(message) {
  return String(message || '').replace(/\s*·\s*\d+\s*%\s*$/, '');
}

export function latestJob(type) {
  return state.jobs.find(job => job.type === type) || null;
}

export async function createJob(type, options = {}, button = null) {
  if (!state.project) return;
  if (state.dirty) await saveProject();
  setBusy(button, true, 'Ajout…');
  try {
    const job = await api(`/api/projects/${encodeURIComponent(state.project.id)}/jobs`, { method: 'POST', body: { type, ...options } });
    state.jobs.unshift(job);
    renderJobs();
    showNotice(`${JOB_LABELS[type] || type} ajoutée à la file.`, 'success', 2600);
  } catch (error) {
    showNotice(error.message);
  } finally {
    setBusy(button, false);
  }
}

export async function pollJobs() {
  if (!state.project) return;
  try {
    const payload = await api(`/api/jobs?project_id=${encodeURIComponent(state.project.id)}`);
    const incoming = payload.jobs || [];
    let shouldReload = false,
      openReview = false;
    if (state.jobsPrimedFor !== state.project.id) {
      // Jobs finished before this page opened stay in the history but must not re-alert.
      state.jobsPrimedFor = state.project.id;
      for (const job of incoming) if (['succeeded', 'failed', 'cancelled'].includes(job.state)) state.seenJobs.add(job.id);
    }
    for (const job of incoming) {
      if (['succeeded', 'failed', 'cancelled'].includes(job.state) && !state.seenJobs.has(job.id)) {
        state.seenJobs.add(job.id);
        if (job.state === 'succeeded') shouldReload = true;
        // L'envoi en relecture finit sur une version déposée : c'est là qu'on emmène l'utilisateur.
        if (job.state === 'succeeded' && job.type === 'relecture') openReview = true;
        if (job.state === 'failed') showNotice(`${JOB_LABELS[job.type] || job.type} : ${job.error || job.message || 'échec'}`);
      }
    }
    state.jobs = incoming;
    renderJobs();
    document.dispatchEvent(new CustomEvent('atelier:jobs'));
    updatePrep();
    if (shouldReload && !state.dirty) {
      state.project = await api(`/api/projects/${encodeURIComponent(state.project.id)}`);
      ensureMontage();
      if (openReview) {
        // On relit la version qui vient d'arriver, pas celle d'avant : sans ça, un renvoi laisserait
        // la Relecture sur l'ancien montage, exactement le défaut qu'on corrige.
        state.review.versionId = state.project.active_version;
        setStep('review');
      }
      render();
    } else if (shouldReload && !state.project.proxy_path) {
      // Des modifications non enregistrées ne doivent pas bloquer le montage sur l'écran de préparation :
      // on ne reprend que le proxy, le reste du projet local est gardé.
      const fresh = await api(`/api/projects/${encodeURIComponent(state.project.id)}`);
      if (fresh.proxy_path) {
        state.project.proxy_path = fresh.proxy_path;
        state.project.proxy_format = fresh.proxy_format;
        render();
      }
    }
  } catch {
    /* A transient polling error must not cover the editor. */
  }
}

export let pollTimer = null;

export function startJobPolling() {
  clearInterval(pollTimer);
  pollJobs();
  pollTimer = window.setInterval(pollJobs, 2000);
}

export function renderJobs() {
  const menu = $('#jobs-menu'),
    list = $('#jobs-list'),
    label = $('#jobs-label'),
    toggle = $('#jobs-toggle');
  if (!menu || !state.project) return;
  const active = state.jobs.filter(j => ['queued', 'running'].includes(j.state)),
    running = active.find(j => j.state === 'running'),
    progress = running ? clamp(Math.round(running.progress || 0), 0, 100) : 0;
  menu.classList.toggle('running', active.length > 0);
  menu.classList.toggle('open', state.jobsOpen);
  list.hidden = !state.jobsOpen;
  toggle.setAttribute('aria-expanded', String(state.jobsOpen));
  menu.style.setProperty('--progress', progress);
  label.textContent = running
    ? `${JOB_LABELS[running.type] || running.type} · ${progress} %`
    : active.length
      ? `${active.length} en attente`
      : 'Tâches';
  list.innerHTML =
    `<div class="jobs-pop-head"><strong>Tâches</strong>` +
    `<small>` +
    (active.length ? `${active.length} en cours` : state.jobs.length ? 'terminées' : 'aucune') +
    `<` +
    `/small></div><div class="jobs-pop-list"` +
    `>` +
    (state.jobs.length
      ? state.jobs
          .slice(0, 12)
          .map(
            job =>
              `<div class="job ${esc(job.state)}"><div class="job-top"><strong>` +
              `${esc(JOB_LABELS[job.type] || job.type)}</strong>` +
              `<span>` +
              esc(job.state === 'running' ? `${Math.round(job.progress || 0)} %` : JOB_STATES[job.state] || job.state) +
              `<` +
              `/span></div><div class="job-bar">` +
              `<i style="--progress:${job.state === 'succeeded' ? 100 : clamp(job.progress || 0, 0, 100)}%"></i>` +
              `</div><div class="job-message"><span>` +
              `${esc(job.error || plainJobMessage(job.message) || 'En attente')}` +
              `</span>` +
              (['queued', 'running'].includes(job.state) ? `<button data-cancel-job="${esc(job.id)}">annuler</button>` : '') +
              `<` +
              `/div></div>`,
          )
          .join('')
      : '<div class="rail-empty">Les proxies et les transcriptions apparaîtront ici.</div>') +
    `</div>`;
}

export function setJobsOpen(open) {
  if (state.jobsOpen === open) return;
  state.jobsOpen = open;
  renderJobs();
}

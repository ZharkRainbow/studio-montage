// Étape Relecture : en-tête de la version, lecteur, transcript et colonne Retours.
import { api } from '../../core/api.js';
import { $, esc, fmtDuration, ICONS, setBusy } from '../../core/dom.js';
import { openMenu } from '../../core/menu.js';
import { staleMontage, versions } from '../../core/montage.js';
import { state } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { emptyStage, render, stageToolbar } from '../shell.js';
import { frenchDate, loadRetours, ratioLabel, reviewVersion } from './data.js';
import { paintSelection, transcriptHtml, wireTranscript } from './transcript.js';
import { playerHtml, renderMarks, reviewController, setMuted, setSpeed, setupPlayer } from './player.js';
import { renderRetours, retoursHead, retoursHtml } from './retours.js';

export function reviewSubtitle(version) {
  if (!version) return 'Aucune version déposée';
  const parts = [];
  const ratio = ratioLabel(version);
  if (ratio) parts.push(`Format ${ratio}`);
  if (version.duration) parts.push(fmtDuration(version.duration));
  parts.push(`Rendu le ${frenchDate(version.added_at)}`);
  parts.push(`Retours v${version.index}`);
  return parts.join(' · ');
}

function headerHtml(version) {
  const open = state.review.counts?.open || 0;
  return (
    `<div class="review-head"><span class="review-icon">${ICONS.film}</span>` +
    `<div class="review-id"><strong>${esc(state.project.name)}</strong><small>${esc(reviewSubtitle(version))}</small></div>` +
    `<div class="review-head-acts">` +
    `<button class="icon-button" type="button" data-version-menu title="Versions" aria-label="Versions">${ICONS.more}</button>` +
    `<button class="button light compact" type="button" data-copy-consigne${open ? '' : ' disabled'}>` +
    `${ICONS.copy} Copier la consigne${open ? `<b class="pill-count">${open}</b>` : ''}</button></div></div>`
  );
}

function staleBanner(version) {
  if (!staleMontage(version)) return '';
  return (
    `<div class="stale-banner" data-stale-banner>${ICONS.alert}` +
    `<div><strong>La relecture montre un ancien montage</strong>` +
    `<small>Le montage a changé depuis la V${version.index}. Renvoie-le pour relire ce qui sera publié.</small></div>` +
    `<button class="button primary compact" type="button" data-send-review>Renvoyer en relecture</button></div>`
  );
}

export function renderReviewStage() {
  const version = reviewVersion();
  if (!version) {
    stageToolbar('Relecture', 'Dépose le rendu pour le relire');
    emptyStage(
      'Aucune version à relire',
      'Dépose le MP4 rendu : le studio le lit tel quel, le transcrit mot à mot et accueille tes retours.',
      `<button class="button primary" type="button" data-open-version>${ICONS.plus} Déposer une version</button>`,
    );
    return;
  }
  state.review.versionId = version.id;
  $('#stage-toolbar').innerHTML = headerHtml(version);
  $('#stage-body').innerHTML = staleBanner(version) + playerHtml();
  $('#transport').innerHTML = transcriptHtml();
  const token = state.stageToken;
  setupPlayer(token);
  setSpeed(state.speed);
  setMuted(state.review.muted);
  wireTranscript(token, time => reviewController()?.seek(time));
  paintSelection();
  ensureReview();
}

export function renderReviewInspector() {
  $('#inspector-title').textContent = 'Retours';
  $('#inspector-actions').innerHTML = retoursHead();
  $('#inspector-content').innerHTML = retoursHtml();
}

// Les retours vivent dans retours/v<N>.json : on les charge dès que la version affichée change.
export async function ensureReview() {
  const version = reviewVersion();
  if (!state.project || !version) return;
  const key = `${state.project.id}:${version.id}`;
  if (state.review.loadedFor === key || state.review.loading === key) return;
  state.review.loading = key;
  try {
    await loadRetours();
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    state.review.loading = null;
  }
  if (state.step !== 'review' || !state.project) return;
  renderRetours();
  refreshReviewHeader();
}

export function refreshReviewHeader() {
  const toolbar = $('#stage-toolbar');
  if (toolbar && state.step === 'review' && reviewVersion()) toolbar.innerHTML = headerHtml(reviewVersion());
}

export function openVersionMenu(anchor) {
  const list = versions();
  const items = list
    .slice()
    .reverse()
    .map(version => ({
      label: `V${version.index} · ${frenchDate(version.added_at)}`,
      checked: version.id === state.review.versionId,
      action: () => selectVersion(version.id),
    }));
  if (items.length) items.push({ separator: true });
  items.push({ label: 'Déposer une nouvelle version', icon: 'plus', action: () => openVersionDialog() });
  openMenu(items, anchor);
}

export async function selectVersion(id) {
  if (!state.project || id === state.review.versionId) return;
  try {
    await api(`/api/projects/${encodeURIComponent(state.project.id)}/versions/${encodeURIComponent(id)}/select`, { method: 'POST', body: {} });
  } catch (error) {
    return toast(error.message, { kind: 'error' });
  }
  const full = await api(`/api/projects/${encodeURIComponent(state.project.id)}/versions/${encodeURIComponent(id)}`).catch(() => null);
  if (full) {
    const target = (state.project.versions || []).find(version => version.id === id);
    if (target) Object.assign(target, full.version || full);
  }
  state.project.active_version = id;
  Object.assign(state.review, { versionId: id, retours: [], loadedFor: null, selection: null, images: [], editing: null, time: 0 });
  render();
}

export async function openVersionDialog() {
  $('#version-path').value = '';
  $('#version-picked').hidden = true;
  $('#version-pick').hidden = false;
  $('#version-dialog').showModal();
  $('#version-pick').focus();
  try {
    const info = await api('/api/pick-file?kind=video');
    const hint = $('#version-pick-hint');
    if (info?.available) hint.textContent = `S’ouvre dans ${info.label}`;
    else $('#version-pick').hidden = true;
  } catch {
    /* le raccourci Finder n’est qu’un confort */
  }
}

export async function submitVersion(button) {
  const path = $('#version-path').value.trim();
  if (!path) return;
  setBusy(button, true, 'Dépôt');
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(state.project.id)}/versions`, { method: 'POST', body: { path } });
    state.project = payload.project;
    Object.assign(state.review, {
      versionId: payload.version?.id || null,
      retours: [],
      counts: { total: 0, open: 0, resolved: 0 },
      loadedFor: null,
      selection: null,
      images: [],
      editing: null,
      time: 0,
    });
    state.step = 'review';
    $('#version-dialog').close();
    render();
    toast(`Version V${payload.version?.index || ''} déposée. La transcription démarre.`, { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    setBusy(button, false, 'Déposer la version');
  }
}

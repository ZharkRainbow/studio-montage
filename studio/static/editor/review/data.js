// Données de la relecture : version affichée, retours, consigne.
import { api } from '../../core/api.js';
import { activeVersion } from '../../core/montage.js';
import { state } from '../../core/state.js';

export const MONTHS = ['janv.', 'févr.', 'mars', 'avril', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

// 00:10.50 — minutes, secondes et centièmes, comme dans le studio de référence.
export function tc(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${(total % 60).toFixed(2).padStart(5, '0')}`;
}

// 0:36 — ce qu’affiche la liste des retours.
export function shortTc(seconds) {
  const total = Math.floor(Math.max(0, Number(seconds) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export function frenchDate(iso) {
  const moment = new Date(iso || '');
  if (Number.isNaN(moment.getTime())) return 'date inconnue';
  const hh = String(moment.getHours()).padStart(2, '0'),
    mm = String(moment.getMinutes()).padStart(2, '0');
  return `${moment.getDate()} ${MONTHS[moment.getMonth()]}, ${hh}:${mm}`;
}

export function reviewVersion() {
  const list = state.project?.versions || [];
  return list.find(version => version.id === state.review.versionId) || activeVersion() || null;
}

export function reviewWords() {
  return reviewVersion()?.transcript || [];
}

export function ratioLabel(version) {
  if (!version?.width || !version?.height) return '';
  const divisor = (a, b) => (b ? divisor(b, a % b) : a);
  const d = divisor(version.width, version.height) || 1;
  return `${Math.round(version.width / d)}:${Math.round(version.height / d)}`;
}

export function visibleRetours() {
  const items = state.review.retours;
  if (state.review.filter === 'open') return items.filter(item => !item.resolved);
  if (state.review.filter === 'resolved') return items.filter(item => item.resolved);
  return items;
}

function retoursPath(suffix = '') {
  const version = reviewVersion();
  return `/api/projects/${encodeURIComponent(state.project.id)}/retours${suffix}?version_id=${encodeURIComponent(version?.id || '')}`;
}

export async function loadRetours() {
  const version = reviewVersion();
  if (!state.project || !version) {
    Object.assign(state.review, { retours: [], counts: { total: 0, open: 0, resolved: 0 }, loadedFor: null });
    return;
  }
  const payload = await api(retoursPath());
  state.review.retours = payload.retours || [];
  state.review.counts = payload.counts || { total: 0, open: 0, resolved: 0 };
  state.review.loadedFor = `${state.project.id}:${version.id}`;
}

export async function createRetour(body) {
  const entry = await api(retoursPath(), { method: 'POST', body });
  await loadRetours();
  return entry;
}

export async function updateRetour(id, body) {
  const entry = await api(retoursPath(`/${encodeURIComponent(id)}`), { method: 'PUT', body });
  await loadRetours();
  return entry;
}

export async function deleteRetour(id) {
  await api(retoursPath(`/${encodeURIComponent(id)}`), { method: 'DELETE' });
  await loadRetours();
}

export async function resolveRetours(ids) {
  await api(retoursPath('/resolve'), { method: 'POST', body: { ids } });
  await loadRetours();
}

export async function fetchConsigne() {
  return api(retoursPath('/consigne'));
}

export function imageUrl(relative) {
  return `/api/artifacts/${encodeURIComponent(state.project.id)}/retours/${relative}`;
}

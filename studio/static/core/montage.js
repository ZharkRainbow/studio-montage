// Modèle du montage : un fichier, des morceaux gardés, le temps REEL et le temps SOURCE.
import { state } from './state.js';

export const TITLE_SECONDS = 3.5;

export function montage(project = state.project) {
  return project?.montage || null;
}

export function segments(project = state.project) {
  return montage(project)?.segments || [];
}

export function montageDuration(project = state.project) {
  return segments(project).reduce((sum, piece) => sum + Math.max(0, Number(piece.end) - Number(piece.start)), 0);
}

// Un temps du reel vers le temps du fichier d’origine : c’est ce que la consigne appelle SOURCE.
export function reelToSource(reelTime, project = state.project) {
  let left = Math.max(0, Number(reelTime) || 0);
  for (const piece of segments(project)) {
    const length = piece.end - piece.start;
    if (left <= length) return piece.start + left;
    left -= length;
  }
  return segments(project).at(-1)?.end || 0;
}

export function sourceToReel(sourceTime, project = state.project) {
  let total = 0;
  for (const piece of segments(project)) {
    if (sourceTime >= piece.start && sourceTime <= piece.end) return total + sourceTime - piece.start;
    total += piece.end - piece.start;
  }
  return 0;
}

export function activeSource(project = state.project) {
  return project?.sources?.[0] || null;
}

export function isDemoProject(project = state.project) {
  if (!project) return false;
  return Boolean(project.demo || project.sources?.some(source => /demo|synthetic|synthétique/i.test(`${source.path} ${source.name}`)));
}

export function proxyUrl() {
  return activeSource() && state.project ? `/api/media?project_id=${encodeURIComponent(state.project.id)}&proxy=1` : '';
}

export function versions(project = state.project) {
  return project?.versions || [];
}

export function activeVersion(project = state.project) {
  const list = versions(project);
  return list.find(version => version.id === project?.active_version) || list.at(-1) || null;
}

// Chaque version emporte l'empreinte du montage dont elle sort. Si le montage a bougé depuis, la
// vidéo relue n'est plus celle qui sera publiée : c'est le défaut vécu sur IKE-11, et ça se voit.
export function staleMontage(version = activeVersion(), project = state.project) {
  const current = project?.montage_hash,
    frozen = version?.montage_hash;
  return Boolean(current && frozen && current !== frozen);
}

export function versionUrl(version) {
  if (!version || !state.project) return '';
  return `/api/media?project_id=${encodeURIComponent(state.project.id)}&version_id=${encodeURIComponent(version.id)}`;
}

// Le serveur répare et migre le montage ; l’éditeur ne complète que ce qu’un geste a pu laisser incomplet.
export function ensureMontage(project = state.project) {
  if (!project) return;
  project.montage ||= { segments: [], silence_backup: null, blanks: [], title: '', hook: '' };
  project.montage.segments ||= [];
  project.montage.blanks ||= [];
  if (typeof project.montage.title !== 'string') project.montage.title = '';
  if (typeof project.montage.hook !== 'string') project.montage.hook = '';
}

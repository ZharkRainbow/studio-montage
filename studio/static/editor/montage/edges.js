// Bornes du reel : fenêtre, poignées, flèches et suppression des blancs.
import { api } from '../../core/api.js';
import { activeSource, ensureMontage, montage } from '../../core/montage.js';
import { $, clamp, clone, ICONS, setBusy } from '../../core/dom.js';
import { checkpoint, markDirty, undo } from '../../core/history.js';
import { state } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { renderInspector } from '../shell.js';
import { trimController, updateTrimDom, updateTrimPlayhead } from './stage.js';
import { loadWaveform } from './wave.js';
import { applyView, zoomBarHtml } from './zoombar.js';
import { isZoomed } from '../../core/zoom.js';
import { addBlank, currentBlanks, reelBounds, segmentsFromBlanks, toggleBlank } from '../../core/blancs.js';

export const SILENCE_LEVELS = [
  ['light', 'Léger', 0.5],
  ['normal', 'Normal', 0.35],
  ['tight', 'Serré', 0.25],
];

export const TRIM_MIN = 0.3;

export function rushDuration() {
  return Number(activeSource()?.duration) || Infinity;
}

// Tout le fichier source : la borne commune du zoom, de la règle et de la mini-barre.
export function viewBounds() {
  const cut = montage(),
    rush = rushDuration();
  return { start: 0, end: Number.isFinite(rush) ? rush : Number(cut?.segments?.at(-1)?.end) || 1 };
}

export function trimWindowFor(cut) {
  const start = cut.segments[0].start,
    end = cut.segments.at(-1).end,
    pad = clamp((end - start) * 0.25, 4, 20);
  return { key: state.project?.id || '', start: Math.max(0, start - pad), end: Math.min(rushDuration(), end + pad), peaks: null };
}

// Un zoom voulu, sur ce projet : la fenêtre ne se recadre pas toute seule derrière le dos de l'utilisateur.
export function zoomHeld() {
  return state.trim?.key === (state.project?.id || '') && isZoomed(state.trim, viewBounds());
}

export function trimFits(cut) {
  const w = state.trim;
  if (!w || w.key !== (state.project?.id || '')) return false;
  const span = w.end - w.start,
    margin = span * 0.03;
  return cut.segments[0].start >= w.start + (w.start > 0 ? margin : 0) && cut.segments.at(-1).end <= w.end - (w.end < rushDuration() ? margin : 0);
}

// Déplacer une borne au-delà d’une coupe abandonne les morceaux restés dehors ; les morceaux d’origine servent de référence pendant le glisser.
export function trimSegments(pieces, edge, time) {
  let kept = pieces.map(piece => ({ ...piece }));
  if (edge === 'start') {
    time = clamp(time, 0, kept.at(-1).end - TRIM_MIN);
    kept = kept.filter(piece => piece.end - TRIM_MIN > time);
    kept[0].start = +time.toFixed(2);
  } else {
    time = clamp(time, kept[0].start + TRIM_MIN, rushDuration());
    kept = kept.filter(piece => piece.start + TRIM_MIN < time);
    kept.at(-1).end = +time.toFixed(2);
  }
  return kept;
}

export function nudgeButtons(edge) {
  const icons = { '-0.5': ICONS.chevronsLeft, '-0.1': ICONS.chevronLeft, 0.1: ICONS.chevronRightSm, 0.5: ICONS.chevronsRight };
  return ['-0.5', '-0.1', '0.1', '0.5'].map(
    step =>
      `<button class="nudge" type="button" data-trim-nudge="${edge}:${step}" ` +
      `title="${step.startsWith('-') ? '−' : '+'}${step.replace('-', '').replace('.', ',')} s" ` +
      `aria-label="${edge === 'start' ? 'Début' : 'Fin'} ` +
      `${step.startsWith('-') ? 'plus tôt' : 'plus tard'} de ` +
      `${step.replace('-', '').replace('.', ',')} seconde">${icons[step]}</button>`,
  );
}

// La barre d’outils des blancs : l’intensité de la détection, la coupe automatique, la coupe à la
// main et le dézoom. « Couper ici » se fait en deux clics, comme dans l’outil Reels.
export function silenceToolHtml(cut) {
  return (
    `<div class="silence-tool">` +
    `<div class="segmented tiny" role="radiogroup" ` +
    `aria-label="Intensité"` +
    `>` +
    SILENCE_LEVELS.map(
      ([id, label]) =>
        `<button type="button" class="${state.silenceLevel === id ? 'active' : ''}" ` +
        `data-silence-level="${id}" role="radio" aria-checked="${state.silenceLevel === id}">` +
        `${label}</button>`,
    ).join('') +
    `<` +
    `/div><button class="button secondary compact" type="button" data-remove-silences>` +
    `${ICONS.scissors} Supprimer les blancs` +
    `</button>` +
    (cut.silence_backup ? '<button class="link-button" type="button" data-restore-silences>Rétablir</button>' : '') +
    `<button class="button secondary compact${state.cutFrom === null ? '' : ' armed'}" type="button" data-cut-here ` +
    `title="Deux clics : la tête de lecture donne le début, puis la fin">` +
    `${ICONS.scissors} ${state.cutFrom === null ? 'Couper ici' : 'Fin de la coupe'}</button>` +
    (state.trimSelection
      ? `<button class="button secondary compact" type="button" data-cut-selection ` +
        `title="Couper la zone sélectionnée (Suppr)">${ICONS.scissors} Couper la sélection</button>`
      : '') +
    zoomBarHtml() +
    `</div>`
  );
}

export function commitTrim(cut) {
  ensureMontage();
  markDirty();
  renderInspector();
  // Une coupe ne vole pas le zoom : tant que l'utilisateur regarde de près, la fenêtre reste où elle est.
  if (!trimFits(cut) && !zoomHeld()) {
    state.trim = trimWindowFor(cut);
    updateTrimDom(cut);
    loadWaveform();
  }
  const controller = trimController();
  if (controller) updateTrimPlayhead(cut, controller.video.currentTime);
}

export function editTrimEdge(edge, time) {
  const cut = montage();
  if (!cut?.segments?.length) return;
  checkpoint();
  cut.segments = trimSegments(cut.segments, edge, time);
  updateTrimDom(cut);
  commitTrim(cut);
  trimController()?.seek(edge === 'start' ? cut.segments[0].start : Math.max(cut.segments[0].start, cut.segments.at(-1).end - 1.5));
}

export async function removeSilences(button) {
  const cut = montage();
  if (!cut?.segments?.length || !state.project) return;
  const projectId = state.project.id;
  const [, label, minimum] = SILENCE_LEVELS.find(([id]) => id === state.silenceLevel) || SILENCE_LEVELS[1];
  setBusy(button, true, 'Analyse…');
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/silences`, {
      method: 'POST',
      body: { segments: cut.segments, min_silence: minimum },
    });
    if (state.project?.id !== projectId) return;
    if (result.saved_seconds < 0.2) {
      toast(`Aucun blanc à couper en réglage ${label.toLowerCase()}. Essaie « Serré » pour les pauses ` + `plus courtes.`, {
        kind: 'info',
        timeout: 4200,
      });
      return;
    }
    checkpoint();
    const backup = cut.silence_backup || clone(cut.segments);
    cut.segments = result.segments;
    cut.blanks = result.blanks || [];
    cut.silence_backup = backup;
    if (Array.isArray(result.words)) state.words = result.words;
    commitTrim(cut);
    updateTrimDom(cut);
    $('#trim-silence').innerHTML = silenceToolHtml(cut);
    trimController()?.seek(cut.segments[0].start);
    const count = result.count || 1,
      kept = (result.blanks || []).filter(blank => blank.cut === false).length;
    toast(
      `${count} blanc${count > 1 ? 's' : ''} supprimé${count > 1 ? 's' : ''} · ` +
        `−${String(result.saved_seconds.toFixed(1)).replace('.', ',')} s` +
        (kept ? ` · ${kept} laissé${kept > 1 ? 's' : ''} : un clic les coupe` : ''),
      { kind: 'success', action: { label: 'Annuler', run: () => undo() } },
    );
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    if (document.body.contains(button)) setBusy(button, false);
  }
}

export function restoreSilences() {
  const cut = montage();
  if (!cut?.silence_backup) return;
  checkpoint();
  cut.segments = cut.silence_backup;
  cut.silence_backup = null;
  // Les blancs trouvés restent visibles, tous gardés : la détection n’est pas à refaire.
  cut.blanks = currentBlanks(cut).map(blank => ({ ...blank, cut: false }));
  commitTrim(cut);
  updateTrimDom(cut);
  $('#trim-silence').innerHTML = silenceToolHtml(cut);
  toast('Les blancs sont rétablis.', { kind: 'success', timeout: 2200 });
}

// Une décision prise sur un blanc : on recalcule les morceaux gardés avec la même règle que le
// serveur, bornes d’abord, pour qu’un aller-retour ne change rien au montage.
export function applyBlanks(cut, list, bounds = null) {
  if (!list) return;
  const span = bounds || reelBounds(cut);
  if (!span) return;
  cut.blanks = list;
  cut.segments = segmentsFromBlanks(span, list);
  updateTrimDom(cut);
  commitTrim(cut);
}

export function toggleBlankAt(index) {
  const cut = montage();
  if (!cut?.segments?.length) return;
  const list = currentBlanks(cut);
  if (!list[index]) return;
  const bounds = reelBounds(cut);
  checkpoint();
  applyBlanks(cut, toggleBlank(list, index), bounds);
  trimController()?.seek(Math.max(0, Number(list[index].start) - 0.6));
}

// « Couper ici » : premier clic, le début de la coupe ; deuxième clic, sa fin. Les deux bords
// s’aimantent aux mots. Recliquer sans avoir bougé annule.
export function cutHere() {
  const cut = montage(),
    controller = trimController();
  if (!cut?.segments?.length || !controller) return;
  const time = controller.video.currentTime;
  if (state.cutFrom === null) {
    state.cutFrom = time;
    $('#trim-silence').innerHTML = silenceToolHtml(cut);
    toast('Place la tête de lecture à la fin de la coupe, puis reclique.', { kind: 'info', timeout: 3600 });
    return;
  }
  const from = state.cutFrom;
  state.cutFrom = null;
  const list = addBlank(currentBlanks(cut), from, time, state.words);
  $('#trim-silence').innerHTML = silenceToolHtml(cut);
  if (!list) {
    toast('Coupe annulée : trop courte pour s’entendre.', { kind: 'info', timeout: 2400 });
    return;
  }
  const bounds = reelBounds(cut);
  checkpoint();
  applyBlanks(cut, list, bounds);
  toast('Coupe ajoutée à la main.', { kind: 'success', timeout: 2600, action: { label: 'Annuler', run: () => undo() } });
}

// « Tout voir » : la timeline montre le fichier en entier.
export function fitAll() {
  applyView(viewBounds());
}

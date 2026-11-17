// Couper par sélection : Maj + glisser sur la piste dessine une zone ambre, Suppr la coupe.
// La coupe passe par addBlank, comme « Couper ici » : même aimant aux mots, même checkpoint.
import { $, clamp } from '../../core/dom.js';
import { state } from '../../core/state.js';
import { montage } from '../../core/montage.js';
import { checkpoint, undo } from '../../core/history.js';
import { toast } from '../../core/toast.js';
import { addBlank, currentBlanks, HAND_CUT_MIN, reelBounds } from '../../core/blancs.js';
import { orderSelection } from '../../core/zoom.js';
import { applyBlanks, silenceToolHtml } from './edges.js';

let anchor = null;

export function selectionHtml() {
  return `<div class="trim-select" id="trim-select" hidden><b></b></div>`;
}

export function hasSelection() {
  return Boolean(state.trimSelection);
}

export function selecting() {
  return anchor !== null;
}

// La barre reprend le bouton « Couper la sélection » : il n’existe que tant qu’une zone est tracée.
function refreshTool() {
  const cut = montage(),
    slot = $('#trim-silence');
  if (slot && cut) slot.innerHTML = silenceToolHtml(cut);
}

export function startSelection(time) {
  anchor = Number(time);
  state.trimSelection = orderSelection(anchor, anchor);
  updateSelectionDom();
}

export function dragSelection(time) {
  if (anchor === null) return;
  state.trimSelection = orderSelection(anchor, time);
  updateSelectionDom();
}

// Au lâcher : une zone trop courte pour s’entendre ne reste pas affichée.
export function endSelection() {
  if (anchor === null) return;
  anchor = null;
  const span = state.trimSelection;
  if (span && span.end - span.start < HAND_CUT_MIN) {
    clearSelection();
    return;
  }
  refreshTool();
}

export function clearSelection() {
  anchor = null;
  if (!state.trimSelection) return;
  state.trimSelection = null;
  updateSelectionDom();
  refreshTool();
}

// La zone se place en pourcentage de la fenêtre visible : elle suit le zoom et le défilement.
export function updateSelectionDom() {
  const box = $('#trim-select'),
    view = state.trim,
    span = state.trimSelection;
  if (!box || !view) return;
  box.hidden = !span;
  if (!span) return;
  const width = view.end - view.start,
    pct = time => clamp(((time - view.start) / width) * 100, 0, 100);
  box.style.left = `${pct(span.start)}%`;
  box.style.width = `${Math.max(0, pct(span.end) - pct(span.start))}%`;
  $('b', box).textContent = `${(span.end - span.start).toFixed(1).replace('.', ',')} s`;
}

// Suppr, Retour arrière ou le bouton de la barre : la sélection devient une coupe.
export function cutSelection() {
  const cut = montage(),
    span = state.trimSelection;
  if (!cut?.segments?.length || !span) return;
  const list = addBlank(currentBlanks(cut), span.start, span.end, state.words);
  if (!list) {
    clearSelection();
    toast('Coupe annulée : trop courte pour s’entendre.', { kind: 'info', timeout: 2400 });
    return;
  }
  const bounds = reelBounds(cut);
  checkpoint();
  state.trimSelection = null;
  anchor = null;
  applyBlanks(cut, list, bounds);
  updateSelectionDom();
  refreshTool();
  toast('Coupe ajoutée.', { kind: 'success', timeout: 2600, action: { label: 'Annuler', run: () => undo() } });
}

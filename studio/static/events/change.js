// Délégation des changements de champs.
import { markDirty, mutateMontage } from '../core/history.js';
import { state } from '../core/state.js';
import { ensureMontage } from '../core/montage.js';
import { refreshMontageChrome } from '../editor/shell.js';
import { refreshTitleMarker } from '../editor/montage/stage.js';
import { endZoomSlide, slideZoom } from '../editor/montage/zoombar.js';
import { attachComposerImage, toggleRetour } from '../editor/review/retours.js';
import { setReglage } from '../settings.js';
import { addAnimationToPreset } from '../library/animations.js';
import { moveProject } from '../library/projects.js';

export function handleChange(event) {
  const target = event.target;
  // Le curseur de zoom : la forme d’onde ne se recharge qu’au lâcher, pas à chaque millième.
  if (target.hasAttribute?.('data-zoom-slider')) {
    endZoomSlide();
    return;
  }
  if (target.id === 'composer-file') {
    const file = target.files?.[0];
    target.value = '';
    if (file) attachComposerImage(file);
    return;
  }
  const reglage = target.closest?.('[data-reglage]');
  if (reglage) {
    setReglage(reglage.dataset.reglage, reglage.type === 'checkbox' ? reglage.checked : reglage.value.trim(), reglage);
    return;
  }
  const versPreset = target.closest?.('[data-animation-preset]');
  if (versPreset) {
    addAnimationToPreset(versPreset.dataset.animationPreset, target.value, target);
    return;
  }
  const rangement = target.closest?.('[data-card-folder]');
  if (rangement) {
    moveProject(rangement.dataset.cardFolder, target.value || null);
    return;
  }
  const resolve = target.closest?.('[data-retour-toggle]');
  if (resolve) {
    toggleRetour(resolve.dataset.retourToggle, target.checked);
    return;
  }
  if (!state.project) return;
  const field = target.closest?.('[data-montage-field]');
  if (field) {
    const key = field.dataset.montageField,
      value = key === 'title' ? field.value.replace(/\s+/g, ' ').trim() : field.value.trim();
    ensureMontage();
    if (state.project.montage[key] === value) return;
    mutateMontage(cut => {
      cut[key] = value;
    }, { rerender: false });
    refreshMontageChrome();
    refreshTitleMarker();
  }
}

export function handleInput(event) {
  if (event.target.hasAttribute?.('data-zoom-slider')) {
    slideZoom(event.target.value);
    return;
  }
  const field = event.target.closest?.('[data-montage-field]');
  if (!field || !state.project) return;
  // La frappe met le titre et l’accroche à jour sans attendre la sortie du champ, sans toucher à l’historique.
  ensureMontage();
  state.project.montage[field.dataset.montageField] = field.value;
  markDirty();
  refreshTitleMarker();
}

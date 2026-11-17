// Délégation des clics et actions nommées.
import { copyText, copyValue, loadSetup, renderSettings } from '../settings.js';
import { api } from '../core/api.js';
import { $, $$, storage } from '../core/dom.js';
import { createJob, pollJobs, setJobsOpen } from '../core/jobs.js';
import { go } from '../core/router.js';
import { currentFolderId, state } from '../core/state.js';
import { toast } from '../core/toast.js';
import { openSourceDialog, pickFile, removeSource } from '../editor/sources.js';
import { renderLibrary } from '../library/library.js';
import { renderMain } from '../library/sidebar.js';
import { openPalette } from '../library/palette.js';
import { copyProductionConsigne, createFolder, openNewProjectDialog, sendToReview } from '../library/projects.js';
import { showFolderMenu, showProjectMenu, startProduction, toggleFavorite } from '../library/projects.js';
import { cutHere, editTrimEdge, fitAll, removeSilences, restoreSilences } from '../editor/montage/edges.js';
import { zoomBy } from '../editor/montage/zoombar.js';
import { cutSelection } from '../editor/montage/select.js';
import { nextSpeed } from '../core/speed.js';
import { ZOOM_FACTOR } from '../core/zoom.js';
import { montage } from '../core/montage.js';
import { captureDrawing, setColor, setDrawing, setTool, setWidth, undoStroke } from '../editor/review/draw.js';
import { reviewController, setMuted, setSpeed } from '../editor/review/player.js';
import { setSelection } from '../editor/review/transcript.js';
import { copyConsigne, openConsigne } from '../editor/review/consigne.js';
import {
  addDrawing,
  attachComposerImage,
  cancelEdit,
  dropComposerImage,
  insertIdea,
  removeRetour,
  renderRetours,
  selectRetour,
  setComposerTab,
  setFilter,
  startEdit,
  submitComposer,
} from '../editor/review/retours.js';
import { openVersionDialog, openVersionMenu } from '../editor/review/view.js';
import { copyAnimationConsigne, copyAnimationNom, renderAnimations, selectAnimation } from '../library/animations.js';
import { editPresetValue, removePresetAnimation, showPresetMenu, togglePreset } from '../library/presets.js';

export async function runAction(name, element) {
  if (name === 'new-project') openNewProjectDialog(currentFolderId());
  else if (name === 'new-folder') await createFolder();
  else if (name === 'reset-filters') {
    state.libSearch = '';
    state.libFilter = 'all';
    renderLibrary();
  } else if (name === 'refresh-setup') await loadSetup({ announce: true, button: element });
  else if (name === 'copy-consigne-production') await copyProductionConsigne(element);
  else if (name === 'start-production') await startProduction(element);
  else if (name === 'install-tab') {
    state.installTab = element.dataset.tab;
    renderSettings();
  }
}

export async function handleClick(event) {
  const t = event.target;
  if (state.jobsOpen && !t.closest('#jobs-menu')) setJobsOpen(false);
  const closer = t.closest('[data-dialog-close]');
  if (closer) {
    closer.closest('dialog')?.close('cancel');
    return;
  }
  if (t.closest('[data-open-palette]')) {
    openPalette();
    return;
  }
  const pickButton = t.closest('[data-pick-file]');
  if (pickButton) {
    await pickFile(pickButton.dataset.pickFile, pickButton);
    return;
  }
  const copyButton = t.closest('[data-copy]');
  if (copyButton) {
    const [text, label] = copyValue(copyButton.dataset.copy);
    copyText(text, label, copyButton);
    return;
  }
  const action = t.closest('[data-action]');
  if (action) {
    await runAction(action.dataset.action, action);
    return;
  }
  const favorite = t.closest('[data-favorite]');
  if (favorite) {
    event.preventDefault();
    toggleFavorite(favorite.dataset.favorite, favorite);
    return;
  }
  const projectMenu = t.closest('[data-project-menu]');
  if (projectMenu) {
    showProjectMenu(projectMenu.dataset.projectMenu, projectMenu, projectMenu.closest('[data-project-card]'));
    return;
  }
  const folderMenu = t.closest('[data-folder-menu]');
  if (folderMenu) {
    event.preventDefault();
    showFolderMenu(folderMenu.dataset.folderMenu, folderMenu);
    return;
  }
  const chip = t.closest('[data-lib-filter]');
  if (chip) {
    state.libFilter = chip.dataset.libFilter;
    renderLibrary();
    return;
  }
  const viewMode = t.closest('[data-view-mode]');
  if (viewMode) {
    state.viewMode = viewMode.dataset.viewMode;
    storage.set('atelier:viewMode', state.viewMode);
    renderLibrary();
    return;
  }
  const openButton = t.closest('[data-open-project]');
  if (openButton) {
    go(`#/projet/${encodeURIComponent(openButton.dataset.openProject)}`);
    return;
  }
  const zone = t.closest('[data-card-versions]');
  if (zone) {
    const id = zone.dataset.cardVersions;
    state.cardVersions = state.cardVersions === id ? null : id;
    // Les cartes se dessinent aussi sur l'Accueil : on redemande la vue courante, pas la bibliothèque.
    renderMain();
    return;
  }
  const versionCard = t.closest('[data-card-version]');
  if (versionCard) {
    state.pendingVersion = versionCard.dataset.cardVersion;
    go(`#/projet/${encodeURIComponent(versionCard.dataset.project)}`);
    return;
  }
  if (await bibliothequeClick(t)) return;
  if (!state.project) return;
  if (await reviewClick(t)) return;
  if (montageClick(t)) return;
  const removeSourceButton = t.closest('[data-remove-source]');
  if (removeSourceButton) {
    removeSource(removeSourceButton.dataset.removeSource);
    return;
  }
  if (t.closest('[data-open-source]')) {
    openSourceDialog();
    return;
  }
  const jobButton = t.closest('[data-job]');
  if (jobButton) {
    await createJob(jobButton.dataset.job, {}, jobButton);
    return;
  }
  const cancel = t.closest('[data-cancel-job]');
  if (cancel) {
    try {
      await api(`/api/jobs/${encodeURIComponent(cancel.dataset.cancelJob)}/cancel`, { method: 'POST', body: {} });
      await pollJobs();
    } catch (error) {
      toast(error.message, { kind: 'error' });
    }
    return;
  }
}

// La bibliothèque : grille d'animations, panneau de détail, cartes de presets.
async function bibliothequeClick(t) {
  if (t.closest('[data-animation-close]')) {
    selectAnimation(null);
    return true;
  }
  const nom = t.closest('[data-animation-nom]');
  if (nom) {
    await copyAnimationNom(nom.dataset.animationNom, nom);
    return true;
  }
  const consigne = t.closest('[data-animation-consigne]');
  if (consigne) {
    await copyAnimationConsigne(consigne.dataset.animationConsigne, consigne);
    return true;
  }
  const categorie = t.closest('[data-anim-category]');
  if (categorie) {
    state.animCategory = categorie.dataset.animCategory;
    renderAnimations();
    return true;
  }
  const editionPreset = t.closest('[data-preset-edit]');
  if (editionPreset) {
    await editPresetValue(editionPreset.dataset.presetEdit, editionPreset.dataset.bloc);
    return true;
  }
  const retirer = t.closest('[data-preset-remove-anim]');
  if (retirer) {
    await removePresetAnimation(retirer.dataset.presetRemoveAnim, retirer.dataset.animationId);
    return true;
  }
  const presetMenu = t.closest('[data-preset-menu]');
  if (presetMenu) {
    showPresetMenu(presetMenu.dataset.presetMenu, presetMenu);
    return true;
  }
  const bascule = t.closest('[data-preset-toggle]');
  if (bascule) {
    await togglePreset(bascule.dataset.presetToggle);
    return true;
  }
  const carte = t.closest('[data-animation]');
  if (carte && !t.closest('button,select,a')) {
    selectAnimation(carte.dataset.animation);
    return true;
  }
  return false;
}

// Étape Montage : niveaux de blancs, suppression, rétablissement, pas fins sur les bornes.
function montageClick(t) {
  const level = t.closest('[data-silence-level]');
  if (level) {
    state.silenceLevel = level.dataset.silenceLevel;
    $$('[data-silence-level]').forEach(button => {
      button.classList.toggle('active', button === level);
      button.setAttribute('aria-checked', String(button === level));
    });
    return true;
  }
  if (t.closest('[data-remove-silences]')) {
    removeSilences(t.closest('[data-remove-silences]'));
    return true;
  }
  if (t.closest('[data-restore-silences]')) {
    restoreSilences();
    return true;
  }
  if (t.closest('[data-cut-here]')) {
    cutHere();
    return true;
  }
  if (t.closest('[data-fit-view]')) {
    fitAll();
    return true;
  }
  const step = t.closest('[data-zoom-step]');
  if (step) {
    zoomBy(step.dataset.zoomStep === 'in' ? ZOOM_FACTOR : 1 / ZOOM_FACTOR);
    return true;
  }
  if (t.closest('[data-cut-selection]')) {
    cutSelection();
    return true;
  }
  if (t.closest('[data-trim-speed]')) {
    setSpeed(nextSpeed(state.speed));
    return true;
  }
  const nudge = t.closest('[data-trim-nudge]');
  if (nudge) {
    const [edge, step] = nudge.dataset.trimNudge.split(':'),
      cut = montage();
    if (cut?.segments?.length)
      editTrimEdge(edge, (edge === 'start' ? cut.segments[0].start : cut.segments.at(-1).end) + Number(step));
    return true;
  }
  return false;
}

// Étape Relecture : transport, dessin, cartes de retours, saisie, consigne et versions.
async function reviewClick(t) {
  const filter = t.closest('[data-review-filter]');
  if (filter) {
    setFilter(filter.dataset.reviewFilter);
    return true;
  }
  if (t.closest('[data-review-draw]')) {
    setDrawing(!state.review.drawing);
    return true;
  }
  const skip = t.closest('[data-review-skip]');
  if (skip) {
    const controller = reviewController();
    if (controller) controller.seek(state.review.time + Number(skip.dataset.reviewSkip));
    return true;
  }
  if (t.closest('[data-review-speed]')) {
    setSpeed(nextSpeed(state.speed));
    return true;
  }
  if (t.closest('[data-review-mute]')) {
    setMuted(!state.review.muted);
    return true;
  }
  if (await drawClick(t)) return true;
  if (await composerClick(t)) return true;
  if (await cardClick(t)) return true;
  if (t.closest('[data-copy-consigne]')) {
    await openConsigne(t.closest('[data-copy-consigne]'));
    return true;
  }
  if (t.closest('[data-consigne-copy]')) {
    await copyConsigne(t.closest('[data-consigne-copy]'));
    return true;
  }
  const resend = t.closest('[data-send-review]');
  if (resend) {
    await sendToReview(resend);
    return true;
  }
  const versionMenu = t.closest('[data-version-menu]');
  if (versionMenu) {
    openVersionMenu(versionMenu);
    return true;
  }
  if (t.closest('[data-open-version]')) {
    await openVersionDialog();
    return true;
  }
  return false;
}

async function drawClick(t) {
  const tool = t.closest('[data-draw-tool]');
  if (tool) {
    setTool(tool.dataset.drawTool);
    return true;
  }
  const width = t.closest('[data-draw-width]');
  if (width) {
    setWidth(width.dataset.drawWidth);
    return true;
  }
  const color = t.closest('[data-draw-color]');
  if (color) {
    setColor(color.dataset.drawColor);
    return true;
  }
  if (t.closest('[data-draw-undo]')) {
    undoStroke();
    return true;
  }
  if (t.closest('[data-draw-attach]')) {
    const png = captureDrawing();
    if (png) {
      addDrawing(png);
      setDrawing(false);
    }
    return true;
  }
  return false;
}

async function composerClick(t) {
  const tab = t.closest('[data-composer-tab]');
  if (tab) {
    setComposerTab(tab.dataset.composerTab);
    return true;
  }
  if (t.closest('[data-composer-ideas]')) {
    insertIdea();
    return true;
  }
  if (t.closest('[data-composer-attach]')) {
    $('#composer-file').click();
    return true;
  }
  const drop = t.closest('[data-composer-drop]');
  if (drop) {
    dropComposerImage(drop.dataset.composerDrop);
    return true;
  }
  if (t.closest('[data-composer-clear]')) {
    setSelection(null);
    renderRetours();
    return true;
  }
  if (t.closest('[data-composer-cancel]')) {
    cancelEdit();
    return true;
  }
  if (t.closest('[data-composer-add]')) {
    await submitComposer(t.closest('[data-composer-add]'));
    return true;
  }
  return false;
}

async function cardClick(t) {
  const goTo = t.closest('[data-goto-retour]');
  if (goTo) {
    const item = state.review.retours.find(entry => entry.id === goTo.dataset.gotoRetour);
    if (item) {
      reviewController()?.seek(item.start);
      state.review.selected = item.id;
      renderRetours();
    }
    return true;
  }
  const edit = t.closest('[data-retour-edit]');
  if (edit) {
    startEdit(edit.dataset.retourEdit);
    return true;
  }
  const remove = t.closest('[data-retour-delete]');
  if (remove) {
    await removeRetour(remove.dataset.retourDelete);
    return true;
  }
  const card = t.closest('[data-retour-id]');
  if (card && !t.closest('input,button,textarea')) {
    selectRetour(card.dataset.retourId);
    return true;
  }
  return false;
}

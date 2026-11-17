import { loadSetup } from './settings.js';
import { api } from './core/api.js';
import { $, $$, setBusy, storage } from './core/dom.js';
import { redo, saveProject, undo } from './core/history.js';
import { setJobsOpen } from './core/jobs.js';
import { closeMenu, onMenuClick, onMenuKey } from './core/menu.js';
import * as model from './core/montage.js';
import { applyRoute, go, parseRoute } from './core/router.js';
import { refreshProjects, state } from './core/state.js';
import { sendToReview, validateProject } from './library/projects.js';
import { toggleEcarte } from './library/ecarter.js';
import { toast } from './core/toast.js';
import { render, renderSteps, setStep } from './editor/shell.js';
import { handleChange, handleInput } from './events/change.js';
import { handleClick } from './events/click.js';
import { onCardKey, renderLibrary, wireLibraryInteractions } from './library/library.js';
import { filterPalette, openPalette, paletteState, runPalette, setPaletteActive } from './library/palette.js';
import { createFolder, openNewProjectDialog, showProjectMenu } from './library/projects.js';
import { renderSidebar } from './library/sidebar.js';
import { brancherRendus, chargerRendus } from './library/rendus.js';
import { animationHover } from './library/animations.js';
import { editTrimEdge, fitAll } from './editor/montage/edges.js';
import { zoomBy } from './editor/montage/zoombar.js';
import { clearSelection, cutSelection } from './editor/montage/select.js';
import { ZOOM_FACTOR } from './core/zoom.js';
import { trimController } from './editor/montage/stage.js';
import { copyConsigne } from './editor/review/consigne.js';
import { setDrawing, undoStroke } from './editor/review/draw.js';
import { reviewController } from './editor/review/player.js';
import { focusComposer, submitComposer } from './editor/review/retours.js';
import { submitVersion } from './editor/review/view.js';

// Raccourcis de la Relecture : Espace lit, P prend le crayon, C écrit un retour, les flèches déplacent la tête.
function reviewKey(event) {
  const key = event.key.toLowerCase(),
    player = reviewController();
  if (key === 'p') {
    setDrawing(!state.review.drawing);
    return true;
  }
  if (key === 'c') {
    focusComposer();
    return true;
  }
  if (!player) return false;
  if (event.code === 'Space') {
    player.toggle();
    return true;
  }
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    player.seek(player.video.currentTime + (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 0.1 : 1));
    return true;
  }
  return false;
}

function wireGlobalEvents() {
  $('#home-button').addEventListener('click', () => go('#/'));
  $('#new-project-button').addEventListener('click', () => openNewProjectDialog(null));
  $('#new-folder-button').addEventListener('click', () => createFolder());
  $('#back-button').addEventListener('click', () => go(state.returnHash || '#/projets'));
  $('#project-button').addEventListener('click', event => state.project && showProjectMenu(state.project.id, event.currentTarget));
  $('#lib-search').addEventListener('input', event => {
    state.libSearch = event.target.value;
    renderLibrary();
  });
  $('#lib-search').addEventListener('keydown', event => {
    if (event.key === 'Escape' && event.target.value) {
      event.preventDefault();
      state.libSearch = '';
      renderLibrary();
    }
  });
  $('#lib-sort').addEventListener('change', event => {
    state.libSort = event.target.value;
    storage.set('atelier:sort', state.libSort);
    renderLibrary();
  });
  $('#menu').addEventListener('click', onMenuClick);
  $('#menu').addEventListener('keydown', onMenuKey);
  $('#palette-input').addEventListener('input', filterPalette);
  $('#palette-input').addEventListener('keydown', event => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setPaletteActive(paletteState.active + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setPaletteActive(paletteState.active - 1);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      runPalette();
    }
  });
  $('#palette-list').addEventListener('pointermove', event => {
    const item = event.target.closest('[data-palette-index]');
    if (item && +item.dataset.paletteIndex !== paletteState.active) setPaletteActive(+item.dataset.paletteIndex, false);
  });
  $('#palette-list').addEventListener('click', event => {
    const item = event.target.closest('[data-palette-index]');
    if (item) runPalette(+item.dataset.paletteIndex);
  });
  $('#palette').addEventListener('click', event => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  $$('dialog.dialog').forEach(dialog =>
    dialog.addEventListener('click', event => {
      if (event.target === dialog) dialog.close('cancel');
    }),
  );

  $('#project-form').addEventListener('submit', async event => {
    event.preventDefault();
    const input = $('#new-project-name'),
      button = $('#create-project-submit'),
      name = input.value.trim();
    if (!name) return;
    setBusy(button, true, 'Création…');
    try {
      const project = await api('/api/projects', { method: 'POST', body: { name, folder_id: $('#new-project-folder').value || null } });
      $('#project-dialog').close();
      input.value = '';
      await refreshProjects();
      go(`#/projet/${encodeURIComponent(project.id)}`);
    } catch (error) {
      toast(error.message, { kind: 'error' });
    } finally {
      setBusy(button, false, 'Créer le projet');
    }
  });
  $('#source-form').addEventListener('submit', async event => {
    event.preventDefault();
    const path = $('#source-path').value.trim(),
      button = $('#source-submit');
    if (!path) return;
    setBusy(button, true, 'Analyse…');
    try {
      state.project = await api(`/api/projects/${encodeURIComponent(state.project.id)}/sources`, { method: 'POST', body: { path } });
      model.ensureMontage();
      $('#source-dialog').close();
      state.step = 'montage';
      render();
      toast('Vidéo ajoutée. Le proxy de lecture se prépare.', { kind: 'success' });
    } catch (error) {
      toast(error.message, { kind: 'error' });
    } finally {
      setBusy(button, false, 'Analyser la source');
    }
  });
  $('#source-path').addEventListener('input', event => {
    if (!$('#source-picked').hidden && event.target.value.trim() !== '') {
      $('#source-picked').hidden = true;
      $('#source-pick').hidden = false;
    }
  });
  $('#version-form').addEventListener('submit', event => {
    event.preventDefault();
    submitVersion($('#version-submit'));
  });
  $('#version-path').addEventListener('input', event => {
    if (!$('#version-picked').hidden && event.target.value.trim() !== '') {
      $('#version-picked').hidden = true;
      $('#version-pick').hidden = false;
    }
  });
  // Entrée ajoute le retour, Maj+Entrée passe à la ligne : la saisie du studio de référence.
  document.addEventListener('keydown', event => {
    if (event.target.id === 'composer-text' && event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submitComposer($('[data-composer-add]'));
      return;
    }
    // ⌘↩ copie la consigne sans quitter le clavier.
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && $('#consigne-dialog').open) {
      event.preventDefault();
      copyConsigne($('[data-consigne-copy]'));
    }
  });

  $('#steps').addEventListener('click', event => {
    const button = event.target.closest('[data-step]');
    if (button) setStep(button.dataset.step);
  });
  $('#validate-button').addEventListener('click', validateProject);
  $('#send-review-button').addEventListener('click', event => sendToReview(event.currentTarget));
  $('#ecarter-button').addEventListener('click', () => state.project && toggleEcarte(state.project.id));
  $('#undo-button').addEventListener('click', undo);
  $('#redo-button').addEventListener('click', redo);
  $('#jobs-toggle').addEventListener('click', () => setJobsOpen(!state.jobsOpen));

  // Les aperçus de la bibliothèque ne tournent qu'au survol : trente-sept vidéos d'un coup, non.
  $('#main').addEventListener('pointerover', event => {
    const card = event.target.closest?.('.an-card');
    if (card && !card.contains(event.relatedTarget)) animationHover(card, true);
  });
  $('#main').addEventListener('pointerout', event => {
    const card = event.target.closest?.('.an-card');
    if (card && !card.contains(event.relatedTarget)) animationHover(card, false);
  });

  document.addEventListener('click', handleClick);
  document.addEventListener('change', handleChange);
  document.addEventListener('input', handleInput);
  document.addEventListener('keydown', event => {
    const meta = event.metaKey || event.ctrlKey;
    if (meta && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openPalette();
      return;
    }
    if (!$('#menu').hidden) {
      if (!event.target.closest?.('#menu')) onMenuKey(event);
      return;
    }
    // A ticked checkbox or a moved slider keeps the shortcuts; only fields that take typing swallow the keys.
    const typing = event.target.tagName === 'INPUT' && !['checkbox', 'radio', 'range', 'button', 'color'].includes(event.target.type);
    const editing = typing || ['TEXTAREA', 'SELECT'].includes(event.target.tagName) || Boolean(event.target.isContentEditable);
    if (editing || document.querySelector('dialog[open]')) return;
    if (!state.project) {
      if (event.key === '/' && state.route?.name === 'library') {
        event.preventDefault();
        $('#lib-search').focus();
        return;
      }
      onCardKey(event);
      return;
    }
    if (meta && event.key === 'Enter') {
      // ⌘↵ fait le geste de l'étape : envoyer en relecture au Montage, valider en Relecture.
      event.preventDefault();
      if (state.step === 'review') validateProject();
      else sendToReview($('#send-review-button'));
    } else if (meta && event.key.toLowerCase() === 's') {
      event.preventDefault();
      saveProject();
    } else if (meta && event.key.toLowerCase() === 'z') {
      event.preventDefault();
      // Le crayon à la main, ⌘Z retire le dernier trait ; ailleurs, il annule le montage.
      if (state.review.drawing && !event.shiftKey) undoStroke();
      else event.shiftKey ? redo() : undo();
    } else if (event.key === 'Escape' && state.jobsOpen) {
      setJobsOpen(false);
    } else if (state.step === 'montage' && trimController() && !meta) {
      const trim = trimController(),
        key = event.key.toLowerCase();
      if (event.code === 'Space') {
        event.preventDefault();
        trim.toggle();
      } else if (key === 'i') {
        event.preventDefault();
        editTrimEdge('start', trim.video.currentTime);
      } else if (key === 'o') {
        event.preventDefault();
        editTrimEdge('end', trim.video.currentTime);
      } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        trim.seek(trim.video.currentTime + (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 0.1 : 1));
      } else if (event.key === '+' || event.key === '=') {
        event.preventDefault();
        zoomBy(ZOOM_FACTOR);
      } else if (event.key === '-' || event.key === '−') {
        event.preventDefault();
        zoomBy(1 / ZOOM_FACTOR);
      } else if (key === 'z' && event.shiftKey) {
        event.preventDefault();
        fitAll();
      } else if ((event.key === 'Delete' || event.key === 'Backspace') && state.trimSelection) {
        event.preventDefault();
        cutSelection();
      } else if (event.key === 'Escape') {
        clearSelection();
      }
    } else if (state.step === 'review' && !meta && reviewKey(event)) {
      event.preventDefault();
    }
  });
  window.addEventListener('resize', () => {
    closeMenu();
    renderSidebar();
    if (state.project) renderSteps();
  });
  window.addEventListener('hashchange', applyRoute);
  window.addEventListener('beforeunload', event => {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  wireLibraryInteractions();
}

async function bootstrap() {
  wireGlobalEvents();
  try {
    const [health, projects, diagnostics, reglages] = await Promise.all([
      api('/api/health'), api('/api/projects'), api('/api/diagnostics').catch(() => null),
      api('/api/reglages').catch(() => null),
    ]);
    state.projects = projects.projects || [];
    state.folders = projects.folders || [];
    state.diagnostics = diagnostics;
    state.reglages = reglages;
    $('.app').setAttribute('aria-busy', 'false');
    await applyRoute();
    loadSetup();
    brancherRendus();
    chargerRendus();
    if (!health.ok) toast('Le serveur a répondu, mais son diagnostic est négatif.', { kind: 'error' });
  } catch (error) {
    $('.app').setAttribute('aria-busy', 'false');
    state.route = parseRoute();
    render();
    toast(error.message, { kind: 'error' });
  }
}

// Read-only handle for the headless QA driver; the page never reads it.
if (new URLSearchParams(location.search).has('qa')) {
  window.__atelier = { state, model, reviewController, trimController };
}

bootstrap();

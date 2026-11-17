// Routage par hash, ouverture et fermeture d’un projet.
import { api } from './api.js';
import { activeVersion, ensureMontage } from './montage.js';
import { $, storage } from './dom.js';
import { flushSave } from './history.js';
import { pollJobs, pollTimer, startJobPolling } from './jobs.js';
import { closeMenu } from './menu.js';
import { findFolder, refreshProjects, state } from './state.js';
import { toast } from './toast.js';
import { render } from '../editor/shell.js';

/* ---------- Routing ---------- */
export function parseRoute() {
  const [head, arg] = location.hash.replace(/^#\/?/, '').split('/');
  if (head === 'projets') return { name: 'library', filter: 'all' };
  if (head === 'favoris') return { name: 'library', filter: 'favorites' };
  if (head === 'dossier' && arg) return { name: 'library', filter: 'folder', folderId: decodeURIComponent(arg) };
  if (head === 'projet' && arg) return { name: 'project', id: decodeURIComponent(arg) };
  if (head === 'animations') return { name: 'animations' };
  if (head === 'presets') return { name: 'presets' };
  // Deux sections annoncées au menu que d'autres étapes du chantier remplissent.
  if (head === 'skills') return { name: 'chantier', section: 'skills' };
  if (head === 'rendus') return { name: 'chantier', section: 'rendus' };
  if (head === 'reglages') return { name: 'settings' };
  return { name: 'home' };
}

export function go(hash, { replace = false } = {}) {
  if (location.hash === hash || (!location.hash && hash === '#/')) {
    applyRoute();
    return;
  }
  if (replace) {
    history.replaceState(null, '', hash);
    applyRoute();
  } else location.hash = hash;
}

export let routing = Promise.resolve();

export function applyRoute() {
  routing = routing.then(applyRouteNow, applyRouteNow);
  return routing;
}

export async function applyRouteNow() {
  const route = parseRoute();
  if (route.name === 'project') {
    if (state.project?.id === route.id) {
      render();
      return;
    }
    if (state.route?.name !== 'project') state.returnHash = state.route?.name === 'library' ? state.lastLibraryHash || '#/projets' : '#/';
    if (await openProject(route.id)) {
      state.route = route;
      return;
    }
    if (state.project) {
      history.replaceState(null, '', `#/projet/${encodeURIComponent(state.project.id)}`);
      return;
    }
    history.replaceState(null, '', state.returnHash || '#/projets');
    state.route = parseRoute();
    render();
    return;
  }
  if (state.project) {
    if (!(await closeProject())) {
      history.replaceState(null, '', `#/projet/${encodeURIComponent(state.project.id)}`);
      return;
    }
    await refreshProjects().catch(() => {});
  }
  if (route.name === 'library' && route.filter === 'folder' && !findFolder(route.folderId)) {
    history.replaceState(null, '', '#/projets');
    route.filter = 'all';
    delete route.folderId;
  }
  if (route.name === 'library') state.lastLibraryHash = location.hash || '#/projets';
  if (state.route?.name !== route.name || state.route?.filter !== route.filter || state.route?.folderId !== route.folderId) {
    state.libFilter = 'all';
    state.libSearch = '';
  }
  state.route = route;
  document.title = 'Atelier — Studio vidéo local';
  render();
  $('#main').scrollTop = 0;
}

export async function closeProject({ discard = false } = {}) {
  if (!discard && !(await flushSave())) return false;
  clearTimeout(state.saveTimer);
  clearInterval(pollTimer);
  state.project = null;
  state.dirty = false;
  state.history = [];
  state.future = [];
  state.playing = false;
  closeMenu();
  render();
  return true;
}

export async function openProject(id) {
  if (state.project && state.project.id !== id && !(await flushSave())) return false;
  try {
    const project = await api(`/api/projects/${encodeURIComponent(id)}`);
    state.project = project;
    ensureMontage();
    state.history = [];
    state.future = [];
    state.dirty = false;
    state.changeVersion = 0;
    state.playhead = 0;
    // Un projet déjà relu rouvre sur la Relecture ; sinon on reste sur le Montage.
    state.step = project.versions?.length ? 'review' : 'montage';
    state.jobs = [];
    state.jobsOpen = false;
    state.playing = false;
    Object.assign(state.review, {
      versionId: activeVersion()?.id || null,
      retours: [],
      counts: { total: 0, open: 0, resolved: 0 },
      filter: 'open',
      composer: 'comment',
      selection: null,
      images: [],
      draft: '',
      drawing: false,
      strokes: [],
      selected: null,
      editing: null,
      time: 0,
      wordIndex: -1,
      loadedFor: null,
      loading: null,
    });
    // Une version choisie depuis une carte de la bibliothèque : la Relecture s'ouvre dessus.
    const voulue = state.pendingVersion;
    state.pendingVersion = null;
    if (voulue && (project.versions || []).some(version => version.id === voulue)) {
      state.step = 'review';
      state.review.versionId = voulue;
    }
    storage.set('atelier:lastProject', project.id);
    closeMenu();
    render();
    startJobPolling();
    api(`/api/projects/${encodeURIComponent(project.id)}/prepare`, { method: 'POST', body: {} })
      .then(result => {
        if (result.job) pollJobs();
      })
      .catch(() => {});
    if (project.demo_notice) toast(project.demo_notice, { kind: 'info', timeout: 7000 });
    return true;
  } catch (error) {
    toast(error.message, { kind: 'error' });
    return false;
  }
}

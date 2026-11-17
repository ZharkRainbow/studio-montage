// État partagé de l’application et accès à la bibliothèque.
import { api } from './api.js';
import { safeSpeed } from './speed.js';
import { renderHeader } from '../editor/shell.js';
import { renderMain, renderSidebar } from '../library/sidebar.js';

export const JOB_STATES = { queued: 'En attente', running: 'En cours', succeeded: 'Terminé', failed: 'Échec', cancelled: 'Annulé' };

export const JOB_LABELS = {
  proxy: 'Création du proxy',
  transcript: 'Transcription mot à mot',
  words: 'Mots du fichier',
  relecture: 'Envoi en relecture',
  production: 'Production par Claude',
};

export const state = {
  projects: [],
  project: null,
  diagnostics: null,
  reglages: null,
  jobs: [],
  // La file du studio entier, pour la page Rendus et la bannière. `jobs` reste le projet ouvert.
  rendus: [],
  // Les skills du dépôt, lus une fois : ils ne bougent pas pendant une session.
  skills: null,
  step: 'montage',
  playhead: 0,
  playing: false,
  dirty: false,
  saving: false,
  changeVersion: 0,
  saveTimer: null,
  history: [],
  future: [],
  seenJobs: new Set(),
  stageToken: 0,
  jobsOpen: false,
  prepCorrect: true,
  silenceLevel: 'normal',
  trim: null,
  words: [],
  cutFrom: null,
  // Maj + glisser sur la piste : la zone à couper, en temps du fichier.
  trimSelection: null,
  // La vitesse de lecture, la même au Montage et en Relecture, gardée d’un projet à l’autre.
  speed: (() => {
    try {
      return safeSpeed(localStorage.getItem('atelier:speed'));
    } catch {
      return 1;
    }
  })(),
  waveCache: new Map(),
  folders: [],
  route: null,
  returnHash: '#/projets',
  lastLibraryHash: '#/projets',
  libSearch: '',
  libFilter: 'all',
  libSort: (() => {
    try {
      return localStorage.getItem('atelier:sort') || 'updated';
    } catch {
      return 'updated';
    }
  })(),
  viewMode: (() => {
    try {
      return localStorage.getItem('atelier:viewMode') || 'grid';
    } catch {
      return 'grid';
    }
  })(),
  fonts: null,
  // La bibliothèque est lue une fois, à la première visite de la page.
  animations: null,
  animCategories: [],
  animCollections: [],
  animCategory: 'all',
  animCollection: 'all',
  animSearch: '',
  animSelected: null,
  presets: null,
  presetDefaut: null,
  presetOpen: null,
  // La zone « Versions » dépliée sur une carte de projet, et la version demandée à l'ouverture.
  cardVersions: null,
  pendingVersion: null,
  // Tout ce que l’étape Relecture garde en mémoire : version lue, retours, saisie, dessin.
  review: {
    versionId: null,
    retours: [],
    counts: { total: 0, open: 0, resolved: 0 },
    filter: 'open',
    composer: 'comment',
    selection: null,
    images: [],
    draft: '',
    muted: false,
    drawing: false,
    tool: 'free',
    width: 'moyen',
    color: '#e9a84b',
    strokes: [],
    selected: null,
    editing: null,
    time: 0,
    wordIndex: -1,
    loadedFor: null,
    loading: null,
    consigneIds: [],
  },
};

export const STATUS = {
  empty: { label: 'Vide', filter: 'todo' },
  imported: { label: 'À monter', filter: 'todo' },
  montage: { label: 'En montage', filter: 'montage' },
  review: { label: 'En relecture', filter: 'review' },
  done: { label: 'Validé', filter: 'done' },
  ecarte: { label: 'Écartée', filter: 'ecarte' },
};

export const FILTERS = [
  ['all', 'Tous'],
  ['todo', 'À monter'],
  ['montage', 'En montage'],
  ['review', 'En relecture'],
  ['done', 'Validés'],
  ['ecarte', 'Écartées'],
];

/* ---------- Data ---------- */
export async function refreshProjects() {
  const payload = await api('/api/projects');
  state.projects = payload.projects || [];
  state.folders = payload.folders || [];
  renderSidebar();
  if (!state.project) renderMain();
  else renderHeader();
}

export const findProject = id => state.projects.find(project => project.id === id);

export const findFolder = id => state.folders.find(folder => folder.id === id);

export function currentFolderId() {
  if (state.project) return state.project.folder_id || null;
  return state.route?.filter === 'folder' ? state.route.folderId : null;
}

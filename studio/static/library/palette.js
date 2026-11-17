// Palette de commandes.
import { api } from '../core/api.js';
import { copyText, loadSetup } from '../settings.js';
import { versions } from '../core/montage.js';
import { $, $$, esc, fmtDuration, ICONS, normalizeText, plural } from '../core/dom.js';
import { saveProject } from '../core/history.js';
import { closeMenu } from '../core/menu.js';
import { toast } from '../core/toast.js';
import { go } from '../core/router.js';
import { currentFolderId, findFolder, state, STATUS } from '../core/state.js';
import { setStep } from '../editor/shell.js';
import { createFolder, openNewProjectDialog, renameProject } from './projects.js';
import { openConsigne } from '../editor/review/consigne.js';
import { openVersionDialog } from '../editor/review/view.js';

/* ---------- Command palette ---------- */
export const paletteState = { items: [], results: [], active: 0 };

export function scoreText(text, query) {
  const t = normalizeText(text);
  let cursor = 0,
    total = 0,
    streak = 0;
  for (let i = 0; i < query.length; i++) {
    const at = t.indexOf(query[i], cursor);
    if (at < 0) return -1;
    streak = at === cursor && i > 0 ? streak + 1 : 0;
    total += 2 + streak * 4;
    if (at === 0) total += 12;
    else if (/[\s\-_/.:·]/.test(t[at - 1])) total += 8;
    cursor = at + 1;
  }
  return total;
}

export function buildPaletteItems() {
  const items = [],
    add = (group, label, icon, run, hint = '', keywords = '') => items.push({ group, label, icon, run, hint, keywords });
  if (state.project) {
    add('Projet ouvert', 'Étape 1 · Montage', 'layers', () => setStep('montage'), '', 'montage blancs timeline titre accroche');
    add('Projet ouvert', 'Étape 2 · Relecture', 'captions', () => setStep('review'), '', 'relecture retours transcript consigne');
    if (versions().length) add('Projet ouvert', 'Copier la consigne', 'copy', () => openConsigne(null), '', 'claude retours consigne');
    add('Projet ouvert', 'Déposer une version', 'plus', () => openVersionDialog(), '', 'rendu version mp4');
    add('Projet ouvert', 'Enregistrer', 'check', () => saveProject(), '⌘S', 'sauvegarder');
    add('Projet ouvert', 'Renommer ce projet', 'pencil', () => renameProject(state.project.id));
    add('Projet ouvert', 'Retour à la bibliothèque', 'back', () => go(state.returnHash || '#/projets'), '', 'fermer quitter');
  }
  add('Actions', 'Nouveau projet', 'plus', () => openNewProjectDialog(currentFolderId()), '', 'creer ajouter');
  add('Actions', 'Nouveau dossier', 'folder', () => createFolder(), '', 'creer organiser ranger');
  for (const project of state.projects)
    add(
      'Projets',
      project.name,
      'film',
      () => go(`#/projet/${encodeURIComponent(project.id)}`),
      [findFolder(project.folder_id)?.name, STATUS[project.status]?.label].filter(Boolean).join(' · '),
      STATUS[project.status]?.label,
    );
  for (const folder of state.folders)
    add(
      'Dossiers',
      folder.name,
      'folder',
      () => go(`#/dossier/${encodeURIComponent(folder.id)}`),
      plural(state.projects.filter(project => project.folder_id === folder.id).length, 'projet'),
    );
  add('Navigation', 'Accueil', 'home', () => go('#/'));
  add('Navigation', 'Tous les projets', 'grid', () => go('#/projets'), '', 'bibliotheque');
  add('Navigation', 'Favoris', 'star', () => go('#/favoris'));
  add('Navigation', 'Réglages', 'gear', () => go('#/reglages'), '', 'installation outils diagnostic parametres settings');
  add(
    'Actions',
    'Copier le prompt d’installation',
    'copy',
    async () => {
      if (!state.setup) await loadSetup();
      if (state.setup) copyText(state.setup.prompt, 'Prompt d’installation');
    },
    '',
    'installer nouvelle machine claude code',
  );
  return items;
}

/* Les paroles dites. Elles ne sont pas en memoire : le serveur relit les transcripts a
   chaque demande. On attend donc que la frappe se pose, et on ne redemande jamais deux
   fois la meme chose. Trois lettres au moins, sinon tout le disque repond. */
const paroles = { query: '', extraits: [], total: 0, tronque: false };
let attente = null;

function demanderParoles(query) {
  clearTimeout(attente);
  if (query.length < 3) {
    Object.assign(paroles, { query: '', extraits: [], total: 0, tronque: false });
    return;
  }
  if (paroles.query === query) return;
  attente = setTimeout(async () => {
    let trouve = { extraits: [], total: 0, tronque: false };
    try {
      trouve = await api(`/api/recherche?q=${encodeURIComponent(query)}`);
    } catch (error) {
      trouve = { extraits: [], total: 0, tronque: false };
    }
    Object.assign(paroles, { query, extraits: trouve.extraits || [], total: trouve.total || 0, tronque: Boolean(trouve.tronque) });
    if (normalizeText($('#palette-input').value.trim()) === query) filterPalette();
  }, 180);
}

/* On ouvre le projet et on dit le temps. Ouvrir l'editeur pile a cet instant demanderait
   de toucher Montage, et Montage ne bouge pas cette nuit. */
function itemsParoles() {
  const groupe = paroles.tronque ? `Paroles · ${paroles.extraits.length} passages sur ${paroles.total}` : 'Paroles';
  return paroles.extraits.map(extrait => ({
    group: groupe,
    label: extrait.texte,
    icon: 'captions',
    hint: `${extrait.project_name} · ${extrait.piste} · ${fmtDuration(extrait.start)}`,
    keywords: '',
    run: () => {
      go(`#/projet/${encodeURIComponent(extrait.project_id)}`);
      toast(`Passage à ${fmtDuration(extrait.start)} dans ${extrait.piste}.`);
    },
  }));
}

export function openPalette() {
  closeMenu();
  const dialog = $('#palette');
  if (dialog.open) {
    dialog.close();
    return;
  }
  paletteState.items = buildPaletteItems();
  $('#palette-input').value = '';
  filterPalette();
  dialog.showModal();
  $('#palette-input').focus();
}

export function filterPalette() {
  const query = normalizeText($('#palette-input').value.trim()),
    order = ['Projet ouvert', 'Actions', 'Projets', 'Dossiers', 'Navigation'];
  let results;
  if (!query) {
    let projectCount = 0;
    results = [...paletteState.items]
      .sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group))
      .filter(item => item.group !== 'Projets' || projectCount++ < 8);
  } else {
    const scored = paletteState.items
      .map((item, i) => ({
        item,
        i,
        score: Math.max(
          scoreText(item.label, query),
          item.keywords ? scoreText(item.keywords, query) - 3 : -1,
          item.hint ? scoreText(item.hint, query) - 6 : -1,
        ),
      }))
      .filter(entry => entry.score >= 0);
    for (const entry of scored) if (normalizeText(entry.item.label).includes(query)) entry.score += 40;
    const top = Math.max(0, ...scored.map(entry => entry.score));
    scored.splice(0, scored.length, ...scored.filter(entry => entry.score >= top * 0.4));
    const best = {};
    for (const entry of scored) best[entry.item.group] = Math.max(best[entry.item.group] ?? -1, entry.score);
    results = scored
      .sort((a, b) => best[b.item.group] - best[a.item.group] || a.item.group.localeCompare(b.item.group) || b.score - a.score || a.i - b.i)
      .map(entry => entry.item);
  }
  demanderParoles(query);
  paletteState.results = query && paroles.query === query ? [...results, ...itemsParoles()] : results;
  paletteState.active = 0;
  renderPalette();
}

export function renderPalette() {
  const list = $('#palette-list');
  let group = '';
  $('#palette-count').textContent = paletteState.results.length || '';
  if (!paletteState.results.length) {
    list.innerHTML = '<li class="palette-empty">Aucun résultat. Essaie un autre mot.</li>';
    return;
  }
  list.innerHTML = paletteState.results
    .map((item, index) => {
      const head = item.group !== group ? `<li class="palette-group" role="presentation">${esc(item.group)}</li>` : '';
      group = item.group;
      return (
        `${head}<li class="palette-item ${index === paletteState.active ? 'active' : ''}" ` +
        `role="option" aria-selected="${index === paletteState.active}" ` +
        `data-palette-index="${index}"><span class="palette-item-icon">${ICONS[item.icon] || ''}` +
        `</span><span class="palette-item-label">${esc(item.label)}` +
        `</span>` +
        (item.hint ? `<span class="palette-item-hint">${esc(item.hint)}</span>` : '') +
        `</li>`
      );
    })
    .join('');
}

export function setPaletteActive(index, reveal = true) {
  if (!paletteState.results.length) return;
  paletteState.active = (index + paletteState.results.length) % paletteState.results.length;
  $$('#palette-list .palette-item').forEach(el => {
    const on = +el.dataset.paletteIndex === paletteState.active;
    el.classList.toggle('active', on);
    el.setAttribute('aria-selected', String(on));
    if (on && reveal) el.scrollIntoView({ block: 'nearest' });
  });
}

export function runPalette(index = paletteState.active) {
  const item = paletteState.results[index];
  if (!item) return;
  $('#palette').close();
  item.run();
}

// Liste des projets, glisser-déposer et clavier.
import { $, $$, clamp, esc, fmtDuration, ICONS, normalizeText, plural } from '../core/dom.js';
import { go } from '../core/router.js';
import { FILTERS, findFolder, findProject, state, STATUS } from '../core/state.js';
import { deleteProject, moveProject, renameProject, showFolderMenu, showProjectMenu } from './projects.js';
import { projectCard, projectRowHtml } from './sidebar.js';

export function renderLibrary() {
  const route = state.route || { name: 'library', filter: 'all' };
  let scoped = state.projects,
    heading = 'Tous les projets',
    kicker = 'Bibliothèque',
    folder = null;
  if (route.filter === 'favorites') {
    scoped = scoped.filter(project => project.favorite);
    heading = 'Favoris';
  }
  if (route.filter === 'folder') {
    folder = findFolder(route.folderId);
    scoped = folder ? scoped.filter(project => project.folder_id === folder.id) : [];
    heading = folder?.name || 'Dossier';
    kicker = 'Dossier';
  }
  $('#lib-kicker').textContent = kicker;
  $('#lib-heading').innerHTML = `` + (folder ? ICONS.folder : route.filter === 'favorites' ? ICONS.star : '') + `${esc(heading)}`;
  const totalDuration = scoped.reduce((sum, project) => sum + (Number(project.duration) || 0), 0);
  const gardes = scoped.filter(project => project.status !== 'ecarte'),
    valides = gardes.filter(project => project.status === 'done').length;
  $('#lib-sub').textContent = scoped.length
    ? `${plural(scoped.length, 'projet')}` +
      ` · ${valides} / ${gardes.length} validés` +
      (totalDuration ? ` · ${fmtDuration(totalDuration)} de rushes` : '')
    : 'Aucun projet ici pour l’instant';
  $('#lib-head-actions').innerHTML = folder
    ? `<button class="button outline" type="button" data-folder-menu="${esc(folder.id)}">` +
      `${ICONS.more} Dossier</button>` +
      `<button class="button primary" type="button" data-action="new-project">` +
      `${ICONS.plus} Nouveau projet</button>`
    : `<button class="button outline" type="button" data-action="new-folder">` +
      `${ICONS.folder} Nouveau dossier</button>` +
      `<button class="button primary" type="button" data-action="new-project">` +
      `${ICONS.plus} Nouveau projet</button>`;
  const counts = Object.fromEntries(
    FILTERS.map(([key]) => [key, key === 'all' ? scoped.length : scoped.filter(project => STATUS[project.status]?.filter === key).length]),
  );
  $('#lib-filters').innerHTML = FILTERS.map(
    ([key, label]) =>
      `<button class="chip ${state.libFilter === key ? 'active' : ''}" type="button" role="tab" ` +
      `aria-selected="${state.libFilter === key}" data-lib-filter="${key}">${label}<b>` +
      `${counts[key]}</b></button>`,
  ).join('');
  const search = $('#lib-search');
  if (search.value !== state.libSearch) search.value = state.libSearch;
  $('#lib-sort').value = state.libSort;
  $$('[data-view-mode]').forEach(button => button.classList.toggle('active', button.dataset.viewMode === state.viewMode));
  const query = normalizeText(state.libSearch.trim());
  let list = scoped.filter(project => state.libFilter === 'all' || STATUS[project.status]?.filter === state.libFilter);
  if (query) list = list.filter(project => normalizeText(`${project.name} ${findFolder(project.folder_id)?.name || ''}`).includes(query));
  const sorters = {
    updated: (a, b) => b.updated_at.localeCompare(a.updated_at),
    created: (a, b) => b.created_at.localeCompare(a.created_at),
    name: (a, b) => a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' }),
  };
  list = [...list].sort(sorters[state.libSort] || sorters.updated);
  const content = $('#lib-content');
  if (!scoped.length) {
    const copy = folder
      ? ['Ce dossier est vide', 'Glisse un projet sur le dossier dans la barre latérale, ou crée un projet directement ici.']
      : route.filter === 'favorites'
        ? ['Aucun favori', 'Clique sur l’étoile d’un projet pour le retrouver ici en un coup d’œil.']
        : ['Aucun projet', 'Crée ton premier projet : donne-lui un nom et choisis ta vidéo.'];
    content.innerHTML =
      `<div class="empty-state">` +
      `<span class="empty-icon"` +
      `>` +
      (folder ? ICONS.folder : route.filter === 'favorites' ? ICONS.star : ICONS.film) +
      `</span>` +
      `<h3>${copy[0]}</h3><p>${copy[1]}</p>` +
      `<div class="empty-actions"` +
      `>` +
      (route.filter === 'favorites'
        ? '<a class="button outline" href="#/projets">Voir tous les projets</a>'
        : `<button class="button primary" type="button" data-action="new-project">` +
          `${ICONS.plus} Nouveau projet` +
          `</button>` +
          ``) +
      `<` +
      `/div></div>`;
    return;
  }
  if (!list.length) {
    content.innerHTML =
      `<div class="empty-state"><span class="empty-icon">${ICONS.search}</span><h3>Aucun résultat` +
      `</h3><p>Aucun projet ne correspond à ` +
      `${query ? `« ${esc(state.libSearch.trim())} »` : 'ce filtre'}.</p>` +
      `<div class="empty-actions">` +
      `<button class="button outline" type="button" data-action="reset-filters">` +
      `Réinitialiser les filtres</button></div></div>`;
    return;
  }
  content.innerHTML =
    state.viewMode === 'list'
      ? `<div class="p-list" role="list"><div class="p-list-head"><span></span><span>Nom</span>` +
        `<span>Statut</span><span>Versions</span><span>Durée</span><span>Modifié</span><span>` +
        `</span></div>${list.map(projectRowHtml).join('')}</div>`
      : `<div class="p-grid" ` +
        `role="list">` +
        list.map((project, index) => projectCard(project, index, { showFolder: !folder })).join('') +
        `</div>`;
}

/* ---------- Drag & drop ---------- */
export const DRAG_TYPE = 'application/x-atelier-project';

export function wireLibraryInteractions() {
  document.addEventListener('dragstart', event => {
    const card = event.target.closest?.('[data-project-card]');
    if (!card || state.project) return;
    event.dataTransfer.setData(DRAG_TYPE, card.dataset.projectCard);
    event.dataTransfer.setData('text/plain', findProject(card.dataset.projectCard)?.name || '');
    event.dataTransfer.effectAllowed = 'move';
    card.classList.add('dragging');
  });
  document.addEventListener('dragend', event => {
    event.target.closest?.('[data-project-card]')?.classList.remove('dragging');
    $$('.drop-target').forEach(el => el.classList.remove('drop-target'));
  });
  const dropTarget = event => event.target.closest?.('[data-drop-folder], [data-route="all"]');
  document.addEventListener('dragover', event => {
    const target = dropTarget(event);
    if (!target || !event.dataTransfer.types.includes(DRAG_TYPE)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const row = target.closest('.folder-row') || target;
    if (!row.classList.contains('drop-target')) {
      $$('.drop-target').forEach(el => el.classList.remove('drop-target'));
      row.classList.add('drop-target');
    }
  });
  document.addEventListener('dragleave', event => {
    const target = dropTarget(event);
    if (target && !target.contains(event.relatedTarget)) (target.closest('.folder-row') || target).classList.remove('drop-target');
  });
  document.addEventListener('drop', event => {
    const target = dropTarget(event);
    const id = event.dataTransfer.getData(DRAG_TYPE);
    if (!target || !id) return;
    event.preventDefault();
    $$('.drop-target').forEach(el => el.classList.remove('drop-target'));
    moveProject(id, target.dataset.dropFolder || null);
  });
  document.addEventListener('contextmenu', event => {
    const card = event.target.closest('[data-project-card]'),
      folderRow = event.target.closest('[data-folder-row]');
    if (card && !state.project) {
      event.preventDefault();
      showProjectMenu(card.dataset.projectCard, { x: event.clientX, y: event.clientY }, card);
    } else if (folderRow) {
      event.preventDefault();
      showFolderMenu(folderRow.dataset.folderRow, { x: event.clientX, y: event.clientY });
    }
  });
  document.addEventListener(
    'load',
    event => {
      if (event.target.matches?.('.p-thumb img')) event.target.classList.remove('loading');
    },
    true,
  );
  document.addEventListener(
    'error',
    event => {
      if (event.target.matches?.('.p-thumb img')) event.target.remove();
    },
    true,
  );
  $('#main').addEventListener('scroll', () => $('.lib-toolbar')?.classList.toggle('stuck', $('#main').scrollTop > 90), { passive: true });
}

export function onCardKey(event) {
  const card = event.target.closest?.('[data-project-card]');
  if (!card || event.target !== card) return false;
  const id = card.dataset.projectCard;
  if (event.key === 'Enter') {
    event.preventDefault();
    go(`#/projet/${encodeURIComponent(id)}`);
    return true;
  }
  if (event.key === 'F2') {
    event.preventDefault();
    renameProject(id);
    return true;
  }
  if ((event.key === 'Backspace' && (event.metaKey || event.ctrlKey)) || event.key === 'Delete') {
    event.preventDefault();
    deleteProject(id);
    return true;
  }
  if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
    event.preventDefault();
    showProjectMenu(id, card.querySelector('[data-project-menu]') || card, card);
    return true;
  }
  if (event.key.startsWith('Arrow')) {
    const cards = $$('[data-project-card][tabindex="0"]', card.parentElement),
      index = cards.indexOf(card);
    const columns = Math.max(1, cards.filter(el => el.offsetTop === cards[0].offsetTop).length);
    const delta = {
      ArrowRight: 1,
      ArrowLeft: -1,
      ArrowDown: card.classList.contains('p-row') ? 1 : columns,
      ArrowUp: card.classList.contains('p-row') ? -1 : -columns,
    }[event.key];
    const next = cards[clamp(index + delta, 0, cards.length - 1)];
    if (next) {
      event.preventDefault();
      next.focus();
    }
    return true;
  }
  return false;
}

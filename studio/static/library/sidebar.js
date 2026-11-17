// Barre latérale et cartes de projet.
import { renderSettings } from '../settings.js';
import { $, $$, esc, fmtDuration, ICONS, plural, relTime } from '../core/dom.js';
import { findFolder, state, STATUS } from '../core/state.js';
import { renderHome } from './home.js';
import { renderLibrary } from './library.js';
import { renderAnimations } from './animations.js';
import { renderPresets } from './presets.js';
import { ouvrirRendus, renderRendus, suivreRendus } from './rendus.js';
import { ouvrirSkills } from './skills.js';

/* ---------- Sidebar ---------- */
export function renderSidebar() {
  const route = state.project ? null : state.route;
  $('#count-all').textContent = state.projects.length || '';
  $('#count-favorites').textContent = state.projects.filter(project => project.favorite).length || '';
  $('#count-animations').textContent = state.animations?.length || '';
  $('#count-presets').textContent = state.presets?.length || '';
  const activeKey = !route
    ? ''
    : route.name === 'home'
      ? 'home'
      : route.name === 'animations' || route.name === 'presets'
        ? route.name
        : route.name === 'chantier'
          ? route.section
          : route.filter;
  $$('#side-nav .side-link').forEach(link => link.classList.toggle('active', link.dataset.route === activeKey));
  const folders = [...state.folders].sort((a, b) => a.name.localeCompare(b.name, 'fr'));
  $('#folder-list').innerHTML = folders.length
    ? folders
        .map(folder => {
          const inside = state.projects.filter(project => project.folder_id === folder.id && project.status !== 'ecarte'),
            count = inside.length,
            done = inside.filter(project => project.validated_at).length;
          const active = route?.filter === 'folder' && route.folderId === folder.id;
          return (
            `<div class="folder-row" data-drop-folder="${esc(folder.id)}" ` +
            `data-folder-row="${esc(folder.id)}">` +
            `<a class="side-link ${active ? 'active' : ''}" ` +
            `href="#/dossier/${encodeURIComponent(folder.id)}" ` +
            `title="${esc(folder.name)}${count ? ` · ${done} / ${count} validés` : ''}">` +
            `${ICONS.folder}<span>${esc(folder.name)}</span>` +
            `<b class="side-count${done && done === count ? ' done' : ''}">${count ? (done ? `${done}/${count}` : count) : ''}</b>` +
            `</a><button class="icon-button tiny folder-more" type="button" ` +
            `data-folder-menu="${esc(folder.id)}" aria-label="Actions du dossier ${esc(folder.name)}" ` +
            `aria-haspopup="menu">${ICONS.more}</button></div>`
          );
        })
        .join('')
    : `<p class="folder-empty">Range tes projets par client ou par format.` +
      `<button class="link-button" type="button" data-action="new-folder">Créer un dossier` +
      `</button></p>`;
  const indicator = $('#side-indicator'),
    active = $('#side-nav .side-link.active');
  if (active) {
    indicator.style.opacity = '1';
    indicator.style.transform = `translateY(${active.offsetTop}px)`;
    indicator.style.height = `${active.offsetHeight}px`;
  } else indicator.style.opacity = '0';
  const tools = state.diagnostics?.tools || [],
    missing = state.setup ? state.setup.required - state.setup.ready : tools.filter(tool => !tool.available).length;
  const settingsActive = route?.name === 'settings';
  const rendusActive = route?.name === 'chantier' && route.section === 'rendus';
  $('#sidebar-foot').innerHTML =
    `<a class="side-link ${rendusActive ? 'active' : ''}" href="#/rendus" data-route="rendus" ` +
    `title="La file des tâches de rendu">` +
    `<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 15.5h12M6.5 12V5M10 12V8M13.5 12V3.5"/></svg>` +
    `<span>Rendus</span></a>` +
    `<a class="side-link ${settingsActive ? 'active' : ''}" href="#/reglages" ` +
    `data-route="settings" ` +
    `title="` +
    (missing ? `${plural(missing, 'élément')} à installer` : 'Machine prête') +
    `">` +
    `${ICONS.gear}<span>Réglages</span>` +
    `<i class="side-dot ${missing ? 'warn' : ''}" ` +
    `aria-label="${missing ? 'À vérifier' : 'Prêt'}"></i></a>`;
}

/* ---------- Home & library ---------- */
export function renderMain() {
  const route = state.route || { name: 'home' };
  $('#home-view').hidden = route.name !== 'home';
  $('#library-view').hidden = route.name !== 'library';
  $('#animations-view').hidden = route.name !== 'animations';
  $('#presets-view').hidden = route.name !== 'presets';
  $('#chantier-view').hidden = route.name !== 'chantier';
  $('#settings-view').hidden = route.name !== 'settings';
  // Le suivi des rendus tourne partout : la bannière doit s'allumer même hors de la page.
  suivreRendus();
  if (route.name === 'home') renderHome();
  else if (route.name === 'settings') renderSettings();
  else if (route.name === 'animations') renderAnimations();
  else if (route.name === 'presets') renderPresets();
  else if (route.name === 'chantier') renderChantier(route.section);
  else renderLibrary();
}

function renderChantier(section) {
  if (section === 'skills') {
    ouvrirSkills();
    return;
  }
  renderRendus();
  ouvrirRendus();
}

export function statusBadge(project) {
  return `<span class="status s-${esc(project.status)}">` + `${esc(STATUS[project.status]?.label || project.status)}</span>`;
}

export function thumbHtml(project) {
  const img = project.has_media
    ? `<img class="loading" ` +
      `src="/api/projects/${encodeURIComponent(project.id)}/thumbnail?v=` +
      `${encodeURIComponent(project.updated_at)}" alt="" loading="lazy" draggable="false">`
    : '';
  return `<span class="p-placeholder">${ICONS.film}<span>${project.has_media ? '' : 'Aucun média'}` + `</span></span>${img}`;
}

// Deux pastilles, une par étape : Montage puis Relecture.
export function progressClasses(project) {
  return [project.trimmed ? 'done' : project.has_media ? 'on' : '', project.version_count ? 'done' : project.trimmed ? 'on' : ''];
}

export function favButton(project) {
  const on = Boolean(project.favorite);
  return (
    `<button class="p-fav ${on ? 'on' : ''}" type="button" data-favorite="${esc(project.id)}" ` +
    `aria-pressed="${on}" title="${on ? 'Retirer des favoris' : 'Ajouter aux favoris'}" ` +
    `aria-label="${on ? 'Retirer des favoris' : 'Ajouter aux favoris'}">${ICONS.star}</button>`
  );
}

// La version active, telle qu'elle s'affiche sur la carte : V3.
export function versionActive(project) {
  const versions = project.versions || [];
  if (!versions.length) return null;
  return versions.find(version => version.id === project.active_version) || versions[versions.length - 1];
}

function dateCourte(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: '2-digit' });
}

// La zone « Versions » : dépliée, elle liste V1..Vn avec leur date. Un clic ouvre le projet sur cette version.
function versionsZone(project) {
  const versions = project.versions || [];
  if (!versions.length) return '';
  const id = esc(project.id);
  const ouvert = state.cardVersions === project.id;
  return (
    `<div class="p-versions${ouvert ? ' open' : ''}">` +
    `<button class="link-button p-versions-toggle" type="button" data-card-versions="${id}" ` +
    `aria-expanded="${ouvert}">Versions${ouvert ? '' : ` (${versions.length})`}</button>` +
    (ouvert
      ? `<ul>` +
        versions
          .map(
            version =>
              `<li><button type="button" data-card-version="${esc(version.id)}" data-project="${id}">` +
              `<b>${esc(version.label)}</b><span>${esc(dateCourte(version.created_at))}</span>` +
              (version.id === project.active_version ? `<i class="p-version-on" title="Version active"></i>` : '') +
              `</button></li>`,
          )
          .join('') +
        `</ul>`
      : '') +
    `</div>`
  );
}

// « Ranger dans » : le même déplacement que le menu, à portée de clic sur la carte.
function rangement(project) {
  const dossiers = [...state.folders].sort((a, b) => a.name.localeCompare(b.name, 'fr'));
  if (!dossiers.length) return '';
  return (
    `<label class="select-field p-ranger"><span class="p-ranger-lab">Ranger dans</span>` +
    `<select data-card-folder="${esc(project.id)}" aria-label="Ranger ${esc(project.name)} dans un dossier">` +
    `<option value=""${project.folder_id ? '' : ' selected'}>Aucun dossier</option>` +
    dossiers
      .map(
        folder =>
          `<option value="${esc(folder.id)}"${project.folder_id === folder.id ? ' selected' : ''}>` +
          `${esc(folder.name)}</option>`,
      )
      .join('') +
    `</select></label>`
  );
}

export function projectCard(project, index, { showFolder = true } = {}) {
  const id = esc(project.id),
    name = esc(project.name),
    folder = showFolder ? findFolder(project.folder_id) : null;
  const [a, b] = progressClasses(project);
  const active = versionActive(project);
  return (
    `<article class="p-card" style="--i:${index}" tabindex="0" draggable="true" ` +
    `data-project-card="${id}" aria-label="${name}">
    ` +
    `<button class="p-thumb" type="button" data-open-project="${id}" tabindex="-1" ` +
    `aria-label="Ouvrir ${name}">${thumbHtml(project)}<span class="p-badges">` +
    `${statusBadge(project)}` +
    (active ? `<span class="status s-version">${esc(active.label)}</span>` : '') +
    (project.demo ? '<span class="status s-demo">Démo</span>' : '') +
    // Le fichier source a bouge : on le dit sur la carte, le menu propose de le repointer.
    (project.media_missing ? '<span class="status s-perdu">Fichier déplacé</span>' : '') +
    `</s` +
    `pan>` +
    (project.duration ? `<span class="p-duration">${fmtDuration(project.duration)}</span>` : '') +
    `<` +
    `/button>
    ${favButton(project)}
    <div class="p-body"><div class="p-title">` +
    `<strong title="${name}">${name}</strong>` +
    `<button class="icon-button" type="button" data-project-menu="${id}" aria-label="Actions ` +
    `pour ${name}" aria-haspopup="menu">${ICONS.more}</button></div>
    ` +
    `<div class="p-meta">` +
    (folder ? `<span class="p-folder">${ICONS.folder}${esc(folder.name)}</span> · ` : '') +
    `${project.version_count ? plural(project.version_count, 'version') : 'aucune version'}` +
    ` · ${esc(relTime(project.updated_at))}</div>
    ` +
    `<div class="p-progress" aria-hidden="true" title="Montage · Relecture">` +
    `<i class="${a}"></i><i class="${b}"></i></div>` +
    versionsZone(project) +
    rangement(project) +
    `</div>
  </article>`
  );
}

export function projectRowHtml(project, index) {
  const id = esc(project.id),
    name = esc(project.name),
    folder = findFolder(project.folder_id);
  return (
    `<div class="p-row" style="--i:${index}" tabindex="0" draggable="true" ` +
    `data-project-card="${id}" aria-label="${name}">
    ` +
    `<button class="p-thumb" type="button" data-open-project="${id}" tabindex="-1" ` +
    `aria-label="Ouvrir ${name}">${thumbHtml(project)}</button>
    <div class="p-row-name">` +
    `<button type="button" data-open-project="${id}" tabindex="-1">${name}</button><small>` +
    `${folder ? esc(folder.name) : 'Sans dossier'}${project.demo ? ' · démo' : ''}` +
    `${project.media_missing ? ' · fichier déplacé' : ''}</small>` +
    `</div>
    <span>${statusBadge(project)}</span>
    <span class="p-cell">` +
    `${project.version_count ? plural(project.version_count, 'version') : '—'}</span>
    <span class="p-cell">` +
    `${project.duration ? fmtDuration(project.duration) : '—'}</span>
    <span class="p-cell">` +
    `${esc(relTime(project.updated_at))}</span>
    <div class="p-row-actions">` +
    `${favButton(project)}` +
    `<button class="icon-button" type="button" data-project-menu="${id}" aria-label="Actions ` +
    `pour ${name}" aria-haspopup="menu">${ICONS.more}</button></div>
  </div>`
  );
}

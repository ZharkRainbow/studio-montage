// Actions sur les projets et les dossiers.
import { api } from '../core/api.js';
import { $, esc, plural, setBusy, storage } from '../core/dom.js';
import { checkpoint, flushSave, markDirty, updateSaveState } from '../core/history.js';
import { openMenu } from '../core/menu.js';
import { closeProject, go, parseRoute } from '../core/router.js';
import { currentFolderId, findFolder, findProject, refreshProjects, state } from '../core/state.js';
import { confirmAction, promptDialog, toast } from '../core/toast.js';
import { pollJobs } from '../core/jobs.js';
import { copyText } from '../settings.js';
import { copierPoint, exporterListe } from './dossier.js';
import { render, renderHeader } from '../editor/shell.js';
import { renderLibrary } from './library.js';
import { renderMain, renderSidebar } from './sidebar.js';
import { toggleEcarte } from './ecarter.js';

export function openNewProjectDialog(folderId = currentFolderId()) {
  const select = $('#new-project-folder');
  select.innerHTML =
    `<option value="">Aucun dossier` +
    `</option>` +
    state.folders.map(folder => `<option value="${esc(folder.id)}">${esc(folder.name)}</option>`).join('') +
    ``;
  select.value = folderId && findFolder(folderId) ? folderId : '';
  $('#new-project-name').value = '';
  $('#project-dialog').showModal();
  setTimeout(() => $('#new-project-name').focus(), 30);
}

export async function renameProject(id) {
  const project = state.project?.id === id ? state.project : findProject(id);
  if (!project) return;
  const name = await promptDialog({ kicker: 'Projet', title: 'Renommer le projet', label: 'Nom du projet', value: project.name, submit: 'Renommer' });
  if (!name || name === project.name) return;
  try {
    if (state.project?.id === id) {
      checkpoint();
      state.project.name = name;
      markDirty();
      renderHeader();
      if (!(await flushSave())) return;
    } else {
      await api(`/api/projects/${encodeURIComponent(id)}/rename`, { method: 'POST', body: { name } });
    }
    await refreshProjects();
    toast('Projet renommé.', { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export async function duplicateProject(id) {
  if (state.project?.id === id && !(await flushSave())) return;
  try {
    const copy = await api(`/api/projects/${encodeURIComponent(id)}/duplicate`, { method: 'POST', body: {} });
    await refreshProjects();
    toast(`Copie créée : ${copy.name}`, { kind: 'success', action: { label: 'Ouvrir', run: () => go(`#/projet/${encodeURIComponent(copy.id)}`) } });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export function deleteProject(id) {
  const project = findProject(id) || (state.project?.id === id ? state.project : null);
  if (!project) return;
  confirmAction(
    `Supprimer « ${project.name} » ?`,
    'Le dossier du projet (réglages, proxy et rendus) part dans la Corbeille. Tes rushes et ta ' + 'musique d’origine ne sont pas touchés.',
    async () => {
      const open = state.project?.id === id,
        wasDirty = open && state.dirty;
      if (open) clearTimeout(state.saveTimer);
      try {
        const result = await api(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (storage.get('atelier:lastProject') === id) storage.remove('atelier:lastProject');
        if (open) {
          await closeProject({ discard: true });
          history.replaceState(null, '', state.returnHash || '#/projets');
          state.route = parseRoute();
        }
        await refreshProjects();
        render();
        toast(`Projet supprimé. Il se trouve dans : ${result.location}.`, { kind: 'success', timeout: 5000 });
      } catch (error) {
        if (wasDirty) markDirty();
        toast(error.message, { kind: 'error' });
      }
    },
    { label: 'Supprimer', danger: true },
  );
}

export async function toggleFavorite(id, button) {
  const project = findProject(id);
  if (!project) return;
  const next = !project.favorite;
  project.favorite = next;
  if (button) {
    button.classList.toggle('on', next);
    button.classList.add('pop');
    button.setAttribute('aria-pressed', String(next));
    setTimeout(() => button.classList.remove('pop'), 460);
  }
  renderSidebar();
  if (state.route?.filter === 'favorites' && !state.project) renderLibrary();
  try {
    await api(`/api/projects/${encodeURIComponent(id)}/favorite`, { method: 'POST', body: { favorite: next } });
    if (state.project?.id === id) state.project.favorite = next;
  } catch (error) {
    project.favorite = !next;
    renderSidebar();
    renderMain();
    toast(error.message, { kind: 'error' });
  }
}

export async function moveProject(id, folderId, { undoable = true } = {}) {
  const project = findProject(id);
  const previous = project ? project.folder_id || null : null;
  if (project && previous === (folderId || null)) return;
  try {
    await api(`/api/projects/${encodeURIComponent(id)}/move`, { method: 'POST', body: { folder_id: folderId || null } });
    if (state.project?.id === id) state.project.folder_id = folderId || null;
    await refreshProjects();
    const folder = findFolder(folderId);
    toast(folder ? `« ${project?.name || 'Projet'} » déplacé dans ${folder.name}.` : `« ${project?.name || 'Projet'} » replacé à la racine.`, {
      kind: 'success',
      action: undoable ? { label: 'Annuler', run: () => moveProject(id, previous, { undoable: false }) } : undefined,
    });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export async function createFolder({ moveProjectId = null } = {}) {
  const name = await promptDialog({
    kicker: 'Organisation',
    title: 'Nouveau dossier',
    label: 'Nom du dossier',
    submit: 'Créer le dossier',
    maxLength: 60,
  });
  if (!name) return;
  try {
    const folder = await api('/api/folders', { method: 'POST', body: { name } });
    if (moveProjectId) await api(`/api/projects/${encodeURIComponent(moveProjectId)}/move`, { method: 'POST', body: { folder_id: folder.id } });
    await refreshProjects();
    toast(moveProjectId ? `Dossier « ${folder.name} » créé et projet déplacé.` : `Dossier « ${folder.name} » créé.`, { kind: 'success' });
    if (!moveProjectId && !state.project) go(`#/dossier/${encodeURIComponent(folder.id)}`);
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export async function renameFolder(id) {
  const folder = findFolder(id);
  if (!folder) return;
  const name = await promptDialog({
    kicker: 'Dossier',
    title: 'Renommer le dossier',
    label: 'Nom du dossier',
    value: folder.name,
    submit: 'Renommer',
    maxLength: 60,
  });
  if (!name || name === folder.name) return;
  try {
    await api(`/api/folders/${encodeURIComponent(id)}/rename`, { method: 'POST', body: { name } });
    await refreshProjects();
    toast('Dossier renommé.', { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export function deleteFolder(id) {
  const folder = findFolder(id);
  if (!folder) return;
  const count = state.projects.filter(project => project.folder_id === id).length;
  confirmAction(
    `Supprimer le dossier « ${folder.name} » ?`,
    count
      ? `Les ${plural(count, 'projet')} qu’il contient ne sont pas supprimés : ils retournent dans ` + `« Tous les projets ».`
      : 'Le dossier est vide. Aucun projet n’est touché.',
    async () => {
      try {
        await api(`/api/folders/${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (state.route?.folderId === id) history.replaceState(null, '', '#/projets');
        state.route = state.project ? state.route : parseRoute();
        await refreshProjects();
        if (!state.project) render();
        toast('Dossier supprimé.', { kind: 'success' });
      } catch (error) {
        toast(error.message, { kind: 'error' });
      }
    },
    { label: 'Supprimer le dossier', danger: true },
  );
}

/* Un rush range ailleurs ne doit pas couter le projet. On redonne le chemin, et ce qui
   vivait dans le meme dossier (versions, export) suit, a condition d'y etre vraiment. */
export async function repointerProjet(id) {
  const project = state.project?.id === id ? state.project : findProject(id);
  if (!project) return;
  const chemin = await promptDialog({
    kicker: 'Média',
    title: 'Repointer le fichier source',
    label: 'Nouveau chemin du fichier',
    hint: 'Colle le chemin du fichier à son nouvel emplacement. Les versions et l’export rangés ' +
      'dans l’ancien dossier suivent, si le même nom s’y trouve.',
    value: project.media_path || '',
    submit: 'Repointer',
  });
  if (!chemin) return;
  try {
    await api(`/api/projects/${encodeURIComponent(id)}/repointer`, { method: 'POST', body: { path: chemin } });
    await refreshProjects();
    toast('Source repointée.');
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export function projectMenuItems(project) {
  const inEditor = state.project?.id === project.id;
  const folders = [...state.folders].sort((a, b) => a.name.localeCompare(b.name, 'fr'));
  return [
    ...(inEditor
      ? [{ label: 'Retour à la bibliothèque', icon: 'back', action: () => go(state.returnHash || '#/projets') }]
      : [{ label: 'Ouvrir', icon: 'open', shortcut: '↵', action: () => go(`#/projet/${encodeURIComponent(project.id)}`) }]),
    { separator: true },
    { label: 'Renommer', icon: 'pencil', shortcut: 'F2', action: () => renameProject(project.id) },
    { label: 'Dupliquer', icon: 'copy', action: () => duplicateProject(project.id) },
    {
      label: 'Afficher dans le Finder',
      icon: 'open',
      action: () =>
        api(`/api/projects/${encodeURIComponent(project.id)}/reveal`, { method: 'POST', body: {} }).catch(error =>
          toast(error.message, { kind: 'error' }),
        ),
    },
    { label: project.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris', icon: 'star', action: () => toggleFavorite(project.id) },
    { label: project.ecarte_le ? 'Garder finalement' : 'Ne pas garder', icon: 'pencil', danger: !project.ecarte_le, action: () => toggleEcarte(project.id) },
    ...(project.media_missing
      ? [{ label: 'Repointer le fichier source', icon: 'open', action: () => repointerProjet(project.id) }]
      : []),
    {
      label: 'Dupliquer le preset mis en avant',
      icon: 'copy',
      action: async () => {
        const { loadPresets, savePresetFromProject } = await import('./presets.js');
        await loadPresets().catch(() => {});
        await savePresetFromProject(project);
      },
    },
    {
      label: 'Déplacer vers',
      icon: 'folder',
      children: [
        { label: 'Aucun dossier', icon: 'grid', checked: !project.folder_id, action: () => moveProject(project.id, null) },
        ...(folders.length ? [{ separator: true }] : []),
        ...folders.map(folder => ({
          label: folder.name,
          icon: 'folder',
          checked: project.folder_id === folder.id,
          action: () => moveProject(project.id, folder.id),
        })),
        { separator: true },
        { label: 'Nouveau dossier…', icon: 'plus', action: () => createFolder({ moveProjectId: project.id }) },
      ],
    },
    { separator: true },
    { label: 'Supprimer', icon: 'trash', danger: true, shortcut: '⌫', action: () => deleteProject(project.id) },
  ];
}

export function showProjectMenu(id, anchor, card) {
  const project = findProject(id) || (state.project?.id === id ? { ...state.project, favorite: state.project.favorite } : null);
  if (!project) return;
  card?.classList.add('menu-open');
  openMenu(projectMenuItems(project), anchor, { onClose: () => card?.classList.remove('menu-open') });
}

export function showFolderMenu(id, anchor) {
  const folder = findFolder(id);
  if (!folder) return;
  openMenu(
    [
      { label: 'Ouvrir le dossier', icon: 'open', action: () => go(`#/dossier/${encodeURIComponent(id)}`) },
      { label: 'Nouveau projet ici', icon: 'plus', action: () => openNewProjectDialog(id) },
      { separator: true },
      // Lire le dossier, pas le transformer : rien ici ne touche un projet.
      { label: 'Copier le point d’avancement', icon: 'copy', action: () => copierPoint(id) },
      { label: 'Exporter la liste (.csv)', icon: 'download', action: () => exporterListe(id) },
      { separator: true },
      { label: 'Renommer', icon: 'pencil', action: () => renameFolder(id) },
      { separator: true },
      { label: 'Supprimer le dossier', icon: 'trash', danger: true, action: () => deleteFolder(id) },
    ],
    anchor,
  );
}

// Envoyer en relecture : l'Atelier enregistre, exporte le montage dans « Montages validés »,
// y pose l'encadré d'accroche et dépose le résultat en version. Le short n'est pas validé pour
// autant : la validation, c'est le bouton d'en face, en Relecture.
export async function sendToReview(button = null) {
  const project = state.project;
  if (!project) return;
  if (project.ecarte_le) return toast('Projet écarté : « Garder finalement » pour le renvoyer en relecture.', { kind: 'info' });
  if (!(await flushSave())) return;
  setBusy(button, true, 'Envoi…');
  try {
    await api(`/api/projects/${encodeURIComponent(project.id)}/relecture`, { method: 'POST', body: {} });
    await pollJobs();
    toast('Envoi en relecture : export du montage, encadré d’accroche, puis la version s’ouvre.', {
      kind: 'info',
      timeout: 4200,
    });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    setBusy(button, false);
    updateSaveState();
  }
}

// Valider : la validation finale, en Relecture. Le short passe en « Validé », la demande de
// production attend dans a-produire, et le short suivant non validé du dossier s'ouvre.
// Un second clic sur un short déjà validé le repasse en cours.
export async function validateProject() {
  const project = state.project;
  if (!project) return;
  if (project.ecarte_le) return toast('Projet écarté : « Garder finalement » pour le valider.', { kind: 'info' });
  if (!(await flushSave())) return;
  const next = !project.validated_at,
    step = 'review';
  try {
    const updated = await api(`/api/projects/${encodeURIComponent(project.id)}/validate`, {
      method: 'POST',
      body: { validated: next, step, version_id: project.active_version || null },
    });
    for (const key of ['validated_at', 'revision', 'versions', 'export', 'production', 'status']) {
      if (key in updated) project[key] = updated[key];
      else delete project[key];
    }
    updateSaveState();
    await refreshProjects();
    render();
    if (!next) return toast('Short repassé en cours. La version relue et son export restent où ils sont.', { kind: 'info' });
    pollJobs();
    announceValidation(project, step, updated.job);
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

// Ce que l'utilisateur lit après avoir validé : où il en est dans le dossier, ce que la machine fait
// maintenant, et le short suivant qui s'ouvre tout seul.
function announceValidation(project, step, job) {
  const siblings = folderSiblings(project.folder_id).filter(item => item.status !== 'ecarte'),
    done = siblings.filter(item => item.status === 'done').length;
  const suite = !job ? '' : job.error ? ` · Claude n’a pas démarré : ${job.error}` : ' · Claude produit la V1';
  toast(`Validé. ${done} / ${siblings.length} validés dans ce dossier${suite}.`, { kind: job?.error ? 'info' : 'success' });
  const after = siblings.slice(siblings.findIndex(item => item.id === project.id) + 1).concat(siblings);
  const following = after.find(item => !['done', 'ecarte'].includes(item.status) && item.id !== project.id);
  if (following) go(`#/projet/${encodeURIComponent(following.id)}`);
  else toast('Tous les shorts du dossier sont validés.', { kind: 'success' });
}

// Les shorts du même dossier, dans l'ordre où ils s'ouvrent : par nom, 2 avant 10.
export function folderSiblings(folderId) {
  return state.projects
    .filter(item => (item.folder_id || null) === (folderId || null))
    .sort((x, y) => x.name.localeCompare(y.name, 'fr', { numeric: true }));
}

// Si la production par Claude est éteinte, la demande attend dans « a-produire » : ce bouton
// donne la consigne à coller dans une session Claude.
export async function copyProductionConsigne(button) {
  const consigne = state.project?.production?.consigne;
  if (!consigne) return toast('Valide le short en relecture pour obtenir la consigne de production.', { kind: 'info' });
  await copyText(consigne, 'Consigne de production', button);
}

// Lancer la production à la main, quand le réglage automatique est éteint.
export async function startProduction(button) {
  if (!state.project) return;
  setBusy(button, true, 'Lancement…');
  try {
    await api(`/api/projects/${encodeURIComponent(state.project.id)}/production`, { method: 'POST', body: {} });
    pollJobs();
    toast('Claude produit la V1. Son journal est dans les tâches.', { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    setBusy(button, false, 'Lancer la production');
  }
}

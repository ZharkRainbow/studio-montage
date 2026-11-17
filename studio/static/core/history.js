// Sauvegarde automatique, annuler et rétablir.
import { api } from './api.js';
import { activeVersion, ensureMontage, staleMontage, versions } from './montage.js';
import { $, clone, pause } from './dom.js';
import { state } from './state.js';
import { showNotice, toast } from './toast.js';
import { render, renderHeader } from '../editor/shell.js';

// L’annulation ne couvre que ce que l’éditeur change, c’est-à-dire le montage. Les versions déposées, leurs
// transcripts et tout ce que le serveur possède ne sont ni copiés à chaque geste ni annulés, et la révision
// courante est conservée pour qu’une sauvegarde après annulation ne soit pas refusée comme un conflit.
const LIVE_KEYS = [
  'revision', 'updated_at', 'name', 'sources', 'versions', 'active_version', 'proxy_path', 'proxy_format',
  'demo', 'demo_notice', 'folder_id', 'favorite', 'validated_at', 'ecarte_le', 'source_transcript', 'source_transcript_state',
  'export', 'production', 'status',
];

function snapshot(project) {
  return Object.fromEntries(Object.entries(project).filter(([key]) => !LIVE_KEYS.includes(key)).map(([key, value]) => [key, clone(value)]));
}

function restore(saved) {
  const live = Object.fromEntries(LIVE_KEYS.filter(key => key in state.project).map(key => [key, state.project[key]]));
  return { ...saved, ...live };
}

export function checkpoint() {
  if (!state.project) return;
  state.history.push(snapshot(state.project));
  if (state.history.length > 40) state.history.shift();
  state.future = [];
  updateUndoButtons();
}

export function undo() {
  if (!state.history.length || !state.project) return;
  state.future.push(snapshot(state.project));
  state.project = restore(state.history.pop());
  markDirty();
  render();
}

export function redo() {
  if (!state.future.length || !state.project) return;
  state.history.push(snapshot(state.project));
  state.project = restore(state.future.pop());
  markDirty();
  render();
}

export function updateUndoButtons() {
  $('#undo-button').disabled = !state.history.length;
  $('#redo-button').disabled = !state.future.length;
}

export function markDirty(renderNow = false) {
  state.dirty = true;
  state.changeVersion += 1;
  updateSaveState();
  clearTimeout(state.saveTimer);
  state.saveTimer = window.setTimeout(saveProject, 850);
  if (renderNow) render();
}

export function updateSaveState(error = '') {
  const el = $('#save-state');
  el.className = `save-state${error ? ' error' : state.saving ? ' saving' : ''}`;
  $('span', el).textContent = error || (state.saving ? 'Enregistrement…' : state.dirty ? 'Modifications' : 'À jour');
  // Un bouton par étape, à la même place : on envoie en relecture au Montage, on valide en Relecture.
  const review = state.step === 'review',
    v = $('#validate-button'),
    s = $('#send-review-button'),
    e = $('#ecarter-button'),
    ecarte = Boolean(state.project?.ecarte_le),
    busy = state.jobs.some(job => job.type === 'relecture' && ['queued', 'running'].includes(job.state));
  // Ne pas garder : le projet reste dans la base, mais il sort de la boucle tant qu'on ne le remet pas en jeu.
  if (e) {
    e.disabled = !state.project || state.saving;
    e.textContent = ecarte ? 'Garder finalement' : 'Ne pas garder';
    e.classList.toggle('is-ecarte', ecarte);
    e.title = ecarte
      ? 'Remettre ce projet en jeu : il repasse en montage et en relecture'
      : 'Sortir ce projet de la boucle sans le supprimer : ni relecture, ni validation';
  }
  if (v) {
    v.hidden = !review;
    v.disabled = !state.project || state.saving || ecarte;
    v.textContent = state.project?.validated_at ? 'Validé' : 'Valider';
    v.classList.toggle('is-validated', Boolean(state.project?.validated_at));
  }
  if (s) {
    // Un montage retouché après coup se voit déjà en Relecture ; au Montage, c'est le bouton qui s'allume.
    const stale = staleMontage(activeVersion(state.project), state.project);
    s.hidden = review;
    s.disabled = !state.project || state.saving || busy || ecarte || !(state.project?.montage?.segments || []).length;
    s.textContent = busy ? 'Envoi…' : versions(state.project).length ? 'Renvoyer en relecture' : 'Envoyer en relecture';
    s.classList.toggle('is-stale', stale && !busy);
    s.title = stale && !busy
      ? 'La relecture montre un ancien montage : renvoie-le pour relire ce qui sera publié (⌘↩)'
      : 'Exporter ce montage avec son encadré et ouvrir la relecture dessus (⌘↩)';
  }
}

// La timeline garde l’objet montage avec lequel elle a été construite : une sauvegarde met cet objet à jour
// sur place plutôt que de remplacer le projet, sinon toute édition faite après une sauvegarde automatique
// atterrit sur une copie détachée.
export function adoptSaved(updated) {
  for (const [key, value] of Object.entries(updated)) if (key !== 'montage') state.project[key] = value;
}

// Un changement venu du serveur (proxy, transcript, version déposée) ne touche que des clés que l’éditeur
// ne modifie jamais : on les adopte sur place. L’historique reste valide, car les instantanés ne les gardent pas.
export function adoptServerProject(updated) {
  for (const key of LIVE_KEYS) {
    if (key in updated) state.project[key] = updated[key];
    else delete state.project[key];
  }
  ensureMontage();
}

// Une tâche (proxy, transcription) peut enregistrer le projet alors que des éditions attendent encore :
// on reprend la copie du serveur, on remet le montage de l’éditeur par-dessus, puis on ré-enregistre.
async function rebaseOnServer(projectId) {
  const server = await api(`/api/projects/${encodeURIComponent(projectId)}`);
  if (state.project?.id !== projectId) return false;
  for (const key of LIVE_KEYS) {
    if (key in server) state.project[key] = server[key];
    else delete state.project[key];
  }
  return true;
}

export async function saveProject(retried = false) {
  if (!state.project || !state.dirty || (state.saving && !retried)) return;
  clearTimeout(state.saveTimer);
  state.saving = true;
  updateSaveState();
  const outgoing = clone(state.project);
  const outgoingVersion = state.changeVersion;
  try {
    const updated = await api(`/api/projects/${encodeURIComponent(outgoing.id)}`, { method: 'PUT', body: outgoing });
    if (state.project?.id === outgoing.id && state.changeVersion === outgoingVersion) {
      adoptSaved(updated);
      state.dirty = false;
      document.dispatchEvent(new CustomEvent('atelier:saved'));
    } else if (state.project?.id === outgoing.id) {
      state.project.revision = updated.revision;
      state.dirty = true;
      clearTimeout(state.saveTimer);
      state.saveTimer = window.setTimeout(saveProject, 250);
    }
    updateSaveState();
    renderHeader();
  } catch (error) {
    if (error.status === 409 && !retried && state.project?.id === outgoing.id) {
      try {
        if (await rebaseOnServer(outgoing.id)) {
          state.dirty = true;
          state.changeVersion += 1;
          return await saveProject(true);
        }
      } catch {
        /* fall through to the conflict notice */
      }
    }
    if (error.status === 409)
      showNotice('Ce projet a été modifié ailleurs. Rechargez-le depuis le menu Projet avant de reprendre ' + 'vos changements.');
    else showNotice(error.message);
    updateSaveState(error.status === 409 ? 'Conflit' : 'Échec');
  } finally {
    state.saving = false;
    updateSaveState();
  }
}

export async function flushSave() {
  if (!state.project) return true;
  for (let attempt = 0; attempt < 3 && (state.dirty || state.saving); attempt += 1) {
    clearTimeout(state.saveTimer);
    while (state.saving) await pause(60);
    if (state.dirty) await saveProject();
    while (state.saving) await pause(60);
  }
  if (state.dirty) {
    toast('Les dernières modifications n’ont pas pu être enregistrées. Réessayez avant de quitter ce projet.', { kind: 'error' });
    return false;
  }
  return true;
}

export function mutateMontage(mutator, { history = true, rerender = true } = {}) {
  if (!state.project) return;
  ensureMontage();
  if (history) checkpoint();
  mutator(state.project.montage);
  markDirty();
  if (rerender) render();
}

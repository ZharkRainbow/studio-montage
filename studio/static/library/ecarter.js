// Ne pas garder : un bouton, pas une suppression.
import { api } from '../core/api.js';
import { flushSave, updateSaveState } from '../core/history.js';
import { findProject, refreshProjects, state } from '../core/state.js';
import { toast } from '../core/toast.js';
import { render } from '../editor/shell.js';
import { renderMain } from './sidebar.js';

// Ne pas garder : le projet passe en « Écartée » (rouge) et sort de la boucle. Il reste dans la base,
// et le même geste le remet en jeu.
export async function toggleEcarte(id) {
  const project = findProject(id) || (state.project?.id === id ? state.project : null);
  if (!project) return;
  if (state.project?.id === id && !(await flushSave())) return;
  const next = !project.ecarte_le;
  try {
    const updated = await api(`/api/projects/${encodeURIComponent(id)}/ecarter`, { method: 'POST', body: { ecarte: next } });
    if (state.project?.id === id) {
      for (const key of ['ecarte_le', 'revision', 'updated_at']) {
        if (key in updated) state.project[key] = updated[key];
        else delete state.project[key];
      }
    }
    await refreshProjects();
    if (state.project?.id === id) {
      updateSaveState();
      render();
    } else renderMain();
    toast(next ? 'Écartée : elle sort de la boucle, elle reste dans la base.' : 'Remise en jeu.', { kind: 'info' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

// Le fichier du projet : choix dans le Finder, retrait, diagnostic des outils.
import { api } from '../core/api.js';
import { $, esc, ICONS } from '../core/dom.js';
import { flushSave } from '../core/history.js';
import { state } from '../core/state.js';
import { confirmAction, showNotice, toast } from '../core/toast.js';
import { render } from './shell.js';

// Le dialogue de la source et celui des versions partagent le même sélecteur de fichier,
// avec des identifiants bâtis sur le même modèle.
const PREFIX = { video: 'source', version: 'version' };
const slot = (kind, name) => `#${PREFIX[kind] || 'source'}-${name}`;

export function showPickHint(info, kind = 'video') {
  const button = $(slot(kind, 'pick')),
    hint = $(slot(kind, 'pick-hint'));
  if (!info?.available) {
    button.hidden = true;
    return;
  }
  hint.textContent = `S’ouvre dans ${info.label}`;
  hint.title = info.directory;
}

export async function openSourceDialog() {
  $('#source-path').value = '';
  $('#source-picked').hidden = true;
  $('#source-pick').hidden = false;
  $('#source-dialog').showModal();
  $('#source-pick').focus();
  try {
    showPickHint(await api('/api/pick-file?kind=video'));
  } catch {
    /* le raccourci Finder n’est qu’un confort */
  }
}

export async function pickFile(kind, button) {
  if (button.classList.contains('busy')) return;
  const hint = $(slot(kind, 'pick-hint')),
    previous = hint?.textContent;
  button.classList.add('busy');
  button.setAttribute('aria-busy', 'true');
  if (hint) hint.textContent = 'Fenêtre du Finder ouverte…';
  try {
    const result = await api('/api/pick-file', { method: 'POST', body: { kind: 'video' } });
    if (hint) showPickHint(result, kind);
    if (result.cancelled) return;
    $(slot(kind, 'path')).value = result.path;
    $(slot(kind, 'picked-name')).textContent = result.name;
    $(slot(kind, 'picked-dir')).textContent = result.label;
    $(slot(kind, 'picked')).hidden = false;
    $(slot(kind, 'pick')).hidden = true;
    $(slot(kind, 'submit')).focus();
  } catch (error) {
    if (hint) hint.textContent = previous;
    toast(error.message, { kind: 'error' });
  } finally {
    button.classList.remove('busy');
    button.removeAttribute('aria-busy');
  }
}

export function removeSource() {
  const source = state.project?.sources?.[0];
  if (!source) return;
  confirmAction(
    `Retirer « ${source.name} » du projet ?`,
    'Le fichier reste sur ton disque. Le montage repart de zéro et le proxy de lecture devra être recréé.',
    async () => {
      if (!(await flushSave())) return;
      try {
        state.project = await api(`/api/projects/${encodeURIComponent(state.project.id)}/sources`, { method: 'DELETE' });
        state.history = [];
        state.future = [];
        state.step = 'montage';
        render();
        showNotice('Fichier retiré du projet.', 'success', 2600);
      } catch (error) {
        showNotice(error.message);
      }
    },
    { label: 'Retirer', danger: true },
  );
}

export function sourcesSection() {
  const source = state.project.sources?.[0];
  if (!source) {
    return (
      `<section class="section"><div class="section-title"><h3>Fichier du reel</h3><small>aucun</small></div>` +
      `<p class="field-help">Un projet tient sur un seul fichier, déjà tourné et déjà coupé.</p>` +
      `<button class="button secondary full" style="margin-top:8px" data-open-source>${ICONS.plus} Choisir la vidéo</button></section>`
    );
  }
  const size = source.width && source.height ? `${source.width}×${source.height}` : 'format inconnu';
  return (
    `<section class="section"><div class="section-title"><h3>Fichier du reel</h3><small>${esc(size)}</small></div>` +
    `<div class="source-row"><span><small>Source</small>` +
    `<strong title="${esc(source.path)}">${esc(source.name)}</strong></span>` +
    `<button class="icon-button danger" type="button" data-remove-source="${esc(source.id)}" ` +
    `title="Retirer du projet" aria-label="Retirer ${esc(source.name)}">${ICONS.trash}</button></div></section>`
  );
}

export function diagnosticsHtml() {
  const d = state.diagnostics;
  if (!d) return '';
  const unavailable = (d.tools || []).filter(tool => !tool.available);
  return (
    `<section class="section"><div class="section-title"><h3>Outils locaux</h3><small>` +
    `${unavailable.length ? 'à vérifier' : 'prêts'}</small>` +
    `</div>` +
    (d.tools || [])
      .map(
        tool =>
          `<div class="metric"><span>${esc(tool.name)}</span>` +
          `<strong style="color:${tool.available ? 'var(--green)' : 'var(--red)'}">` +
          `${tool.available ? 'disponible' : 'absent'}</strong></div>`,
      )
      .join('') +
    `</section>`
  );
}

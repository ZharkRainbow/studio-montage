// La colonne Retours : filtres, cartes, et la zone de saisie (Commentaire / Coupe).
import { $, $$, esc, ICONS, setBusy } from '../../core/dom.js';
import { state } from '../../core/state.js';
import { confirmAction, toast } from '../../core/toast.js';
import { createRetour, deleteRetour, frenchDate, imageUrl, shortTc, tc, updateRetour, visibleRetours } from './data.js';
import { renderMarks } from './player.js';
import { quoteAround, setSelection } from './transcript.js';

const FILTERS = [
  ['open', 'Ouverts'],
  ['resolved', 'Résolus'],
  ['all', 'Tous'],
];
const TABS = [
  ['comment', 'Commentaire', ICONS.captions],
  ['cut', 'Coupe', ICONS.scissors],
];
const IDEAS = [
  'Coupe l’hésitation au début.',
  'Ce passage est trop long, resserre-le.',
  'Ajoute un sous-titre sur cette phrase.',
  'Change le cadrage, mon visage est coupé.',
  'Monte le son de la voix ici.',
];

export function retoursHead() {
  const counts = state.review.counts || { total: 0, open: 0, resolved: 0 },
    numbers = { open: counts.open, resolved: counts.resolved, all: counts.total };
  return (
    `<div class="retours-filters" role="tablist">` +
    FILTERS.map(
      ([key, label]) =>
        `<button class="chip${state.review.filter === key ? ' on' : ''}" data-review-filter="${key}" role="tab"` +
        ` aria-selected="${state.review.filter === key}">${label} <span class="chip-count">${numbers[key] || 0}</span></button>`,
    ).join('') +
    `</div>`
  );
}

function thumbs(images, removable) {
  if (!images?.length) return '';
  return (
    `<div class="retour-shots">` +
    images
      .map((image, index) => {
        const src = image.startsWith('data:') ? image : imageUrl(image);
        return (
          `<span class="shot"><img src="${esc(src)}" alt="Capture jointe au retour" loading="lazy">` +
          (removable ? `<button class="shot-drop" data-composer-drop="${index}" title="Retirer">${ICONS.x}</button>` : '') +
          `</span>`
        );
      })
      .join('') +
    `</div>`
  );
}

function cardHtml(item) {
  const range = item.end !== null && item.end !== undefined,
    selected = state.review.selected === item.id,
    label = item.type === 'cut' ? 'Coupe' : 'Commentaire';
  return (
    `<article class="retour${item.resolved ? ' done' : ''}${selected ? ' on' : ''}" data-retour-id="${esc(item.id)}">` +
    `<div class="retour-head">` +
    `<label class="retour-check"><input type="checkbox" data-retour-toggle="${esc(item.id)}"${item.resolved ? ' checked' : ''}` +
    ` aria-label="Marquer ce retour comme résolu"></label>` +
    `<span class="retour-kind ${item.type}">${label}</span>` +
    `<button class="retour-at" data-goto-retour="${esc(item.id)}" title="Lire ce passage">${ICONS.clock}` +
    `${shortTc(item.start)}${range ? ` → ${shortTc(item.end)}` : ''}</button>` +
    `<span class="retour-acts"><button class="icon-button" data-retour-edit="${esc(item.id)}" title="Modifier">${ICONS.pencil}</button>` +
    `<button class="icon-button" data-retour-delete="${esc(item.id)}" title="Supprimer">${ICONS.trash}</button></span>` +
    `</div>` +
    (item.quote ? `<blockquote class="retour-quote">${esc(item.quote)}</blockquote>` : '') +
    `<p class="retour-text">${esc(item.text)}</p>` +
    thumbs(item.images, false) +
    `<footer class="retour-foot">${esc(frenchDate(item.created_at))}` +
    (item.images?.length ? ` · ${ICONS.film} ${item.images.length}` : '') +
    `</footer></article>`
  );
}

export function composerTimeLabel() {
  const selection = state.review.selection;
  return selection ? `De ${tc(selection.start)} à ${tc(selection.end)}` : `À ${tc(state.review.time || 0)}`;
}

function composerWhenHtml(editing) {
  return (
    `<span class="dim">${editing ? 'Retour' : 'Nouveau retour'}</span>` +
    `<span class="time-chip" id="composer-time">${ICONS.clock} <b data-composer-at>${composerTimeLabel()}</b></span>` +
    (state.review.selection ? `<button type="button" class="link-button" data-composer-clear>Effacer la plage</button>` : '')
  );
}

// La lecture avance : seule l'heure change, l'horloge et le bouton de plage restent en place.
export function updateComposerTime() {
  const label = $('[data-composer-at]');
  if (label) label.textContent = composerTimeLabel();
}

// Une plage choisie dans le transcript change aussi le bouton « Effacer la plage ».
export function refreshComposerWhen() {
  const when = $('.composer-when');
  if (when) when.innerHTML = composerWhenHtml(Boolean(state.review.editing));
}

function composerHtml() {
  const review = state.review,
    editing = review.editing ? review.retours.find(item => item.id === review.editing) : null;
  return (
    `<div class="composer" id="composer"${editing ? ' data-editing="1"' : ''}>` +
    `<div class="composer-top"><div class="composer-tabs">` +
    TABS.map(
      ([key, label, icon]) =>
        `<button type="button" class="chip${review.composer === key ? ' on' : ''}" data-composer-tab="${key}">${icon} ${label}</button>`,
    ).join('') +
    `</div><button type="button" class="link-button" data-composer-ideas>${ICONS.sparkle} Idées</button></div>` +
    `<div class="composer-when">${composerWhenHtml(Boolean(editing))}</div>` +
    `<textarea id="composer-text" rows="3" maxlength="2000" placeholder="Décris ce que tu veux changer…">` +
    `${esc(editing?.text || review.draft || '')}</textarea>` +
    thumbs(review.images, true) +
    `<div class="composer-foot"><span class="dim"><kbd>C</kbd> écrire · <kbd>Entrée</kbd> ajouter</span>` +
    `<span class="composer-acts">` +
    (editing ? `<button type="button" class="button ghost compact" data-composer-cancel>Annuler</button>` : '') +
    `<button type="button" class="icon-button" data-composer-attach title="Joindre une image">${ICONS.paperclip}</button>` +
    `<button type="button" class="button primary compact" data-composer-add>${editing ? 'Enregistrer' : 'Ajouter'}</button></span></div>` +
    `<input type="file" id="composer-file" accept="image/png,image/jpeg" hidden></div>`
  );
}

export function retoursHtml() {
  const items = visibleRetours();
  return (
    `<div class="retours-list" id="retours-list">` +
    (items.length
      ? items.map(cardHtml).join('')
      : `<p class="empty-note">${state.review.filter === 'resolved' ? 'Aucun retour résolu.' : 'Aucun retour. Écoute, puis décris ce qui doit changer.'}</p>`) +
    `</div>` +
    composerHtml()
  );
}

export function renderRetours() {
  const body = $('#inspector-content');
  if (!body || state.step !== 'review') return;
  const focused = document.activeElement?.id === 'composer-text',
    caret = focused ? $('#composer-text').selectionStart : 0;
  body.innerHTML = retoursHtml();
  const head = $('#inspector-actions');
  if (head) head.innerHTML = retoursHead();
  if (focused) {
    const field = $('#composer-text');
    field.focus();
    field.setSelectionRange(caret, caret);
  }
  refreshConsigneButton();
  renderMarks();
}

// Le compteur du bouton « Copier la consigne » suit les retours ouverts, sans refaire l’en-tête.
function refreshConsigneButton() {
  const button = $('[data-copy-consigne]');
  if (!button) return;
  const open = state.review.counts?.open || 0,
    badge = button.querySelector('.pill-count');
  button.disabled = !open;
  if (!open) badge?.remove();
  else if (badge) badge.textContent = String(open);
  else button.insertAdjacentHTML('beforeend', `<b class="pill-count">${open}</b>`);
}

export function setFilter(filter) {
  state.review.filter = filter;
  renderRetours();
}

export function focusComposer() {
  const field = $('#composer-text');
  if (!field) return;
  field.focus();
  field.setSelectionRange(field.value.length, field.value.length);
}

export function setComposerTab(kind) {
  state.review.composer = kind;
  $$('[data-composer-tab]').forEach(button => button.classList.toggle('on', button.dataset.composerTab === kind));
}

export function insertIdea() {
  const field = $('#composer-text');
  if (!field) return;
  const idea = IDEAS[Math.floor(Math.random() * IDEAS.length)];
  field.value = field.value.trim() ? `${field.value.trim()} ${idea}` : idea;
  state.review.draft = field.value;
  focusComposer();
}

export async function attachComposerImage(file) {
  if (!file) return;
  if (file.size > 4 * 1024 * 1024) return toast('Capture trop lourde (4 Mo maximum).', { kind: 'error' });
  const png = await toPng(file);
  state.review.images = [...state.review.images, png].slice(0, 6);
  state.review.draft = $('#composer-text')?.value || state.review.draft;
  renderRetours();
}

// Le serveur n’accepte que du PNG : on repasse par un canvas pour tout le reste.
function toPng(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Lecture impossible.'));
    reader.onload = () => {
      if (String(reader.result).startsWith('data:image/png;base64,')) return resolve(String(reader.result));
      const image = new Image();
      image.onerror = () => reject(new Error('Image illisible.'));
      image.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        canvas.getContext('2d').drawImage(image, 0, 0);
        resolve(canvas.toDataURL('image/png'));
      };
      image.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

export function addDrawing(png) {
  state.review.images = [...state.review.images, png].slice(0, 6);
  renderRetours();
  focusComposer();
}

export function dropComposerImage(index) {
  state.review.draft = $('#composer-text')?.value || '';
  state.review.images = state.review.images.filter((_, position) => position !== Number(index));
  renderRetours();
}

export async function submitComposer(button) {
  const field = $('#composer-text'),
    text = (field?.value || '').trim();
  if (!text) {
    field?.focus();
    return toast('Écris d’abord ce que tu veux changer.', { kind: 'error' });
  }
  const review = state.review,
    editing = review.editing,
    selection = review.selection,
    time = review.time || 0,
    body = {
      type: review.composer,
      start: selection ? selection.start : time,
      end: selection ? selection.end : null,
      text,
      quote: selection ? selection.quote : quoteAround(time),
      images: review.images,
    };
  setBusy(button, true, 'Enregistrement');
  try {
    if (editing) await updateRetour(editing, { text, images: review.images, type: review.composer });
    else await createRetour(body);
    Object.assign(review, { images: [], draft: '', editing: null });
    setSelection(null);
    renderRetours();
    toast(editing ? 'Retour modifié.' : 'Retour ajouté.', { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    setBusy(button, false, editing ? 'Enregistrer' : 'Ajouter');
  }
}

export async function toggleRetour(id, resolved) {
  try {
    await updateRetour(id, { resolved });
    renderRetours();
  } catch (error) {
    toast(error.message, { kind: 'error' });
    renderRetours();
  }
}

export function startEdit(id) {
  const item = state.review.retours.find(entry => entry.id === id);
  if (!item) return;
  Object.assign(state.review, { editing: id, selected: id, composer: item.type, images: [...(item.images || [])], draft: item.text });
  renderRetours();
  focusComposer();
}

export function cancelEdit() {
  Object.assign(state.review, { editing: null, images: [], draft: '' });
  renderRetours();
}

export function removeRetour(id) {
  confirmAction('Supprimer ce retour ?', 'Le retour et son dessin partent pour de bon.', async () => {
    try {
      await deleteRetour(id);
      if (state.review.editing === id) Object.assign(state.review, { editing: null, images: [], draft: '' });
      renderRetours();
      toast('Retour supprimé.', { kind: 'success' });
    } catch (error) {
      toast(error.message, { kind: 'error' });
    }
  }, { label: 'Supprimer', danger: true });
}

export function selectRetour(id) {
  state.review.selected = state.review.selected === id ? null : id;
  renderRetours();
}

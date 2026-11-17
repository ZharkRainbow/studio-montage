// Dessin sur l’image figée : feutre, cercle, flèche, carré et texte, puis une capture PNG jointe au retour.
import { $, $$, ICONS } from '../../core/dom.js';
import { state } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import {
  COLORS, DEFAULT_TOOL, TOOLS, WIDTHS, paintInk, pushPoint, textFontOf, worthKeeping,
} from './ink.js';

const radioHtml = (group, id, label, body, on) =>
  `<button type="button" data-draw-${group}="${id}" role="radio" aria-checked="${on}" ` +
  `class="${on ? 'active' : ''}" title="${label}" aria-label="${label}">${body}</button>`;

export function drawToolsHtml() {
  return (
    `<div class="draw-tools" id="draw-tools" hidden>` +
    `<div class="segmented tiny" role="radiogroup" aria-label="Outil de dessin">` +
    TOOLS.map(([id, label, icon]) => radioHtml('tool', id, label, icon, state.review.tool === id)).join('') +
    `</div><div class="segmented tiny" role="radiogroup" aria-label="Épaisseur du trait">` +
    WIDTHS.map(([id, label]) => radioHtml('width', id, label, label, state.review.width === id)).join('') +
    `</div><div class="draw-colors">` +
    COLORS.map(
      color =>
        `<button type="button" data-draw-color="${color}" class="${state.review.color === color ? 'on' : ''}" ` +
        `style="--swatch:${color}" aria-label="Couleur ${color}"></button>`,
    ).join('') +
    `</div><button class="button ghost compact" type="button" data-draw-undo>Annuler <kbd>⌘Z</kbd></button>` +
    `<button class="button primary compact" type="button" data-draw-attach>${ICONS.plus} Joindre au retour</button>` +
    `</div>`
  );
}

export function setDrawing(on) {
  state.review.drawing = on;
  const canvas = $('#review-canvas'),
    tools = $('#draw-tools'),
    button = $('[data-review-draw]');
  if (!canvas || !tools) return;
  if (on) {
    $('#review-video')?.pause();
    state.review.strokes = [];
  } else cancelText();
  canvas.hidden = !on;
  tools.hidden = !on;
  button?.classList.toggle('on', on);
  button?.setAttribute('aria-pressed', String(on));
  $('#review-video-box')?.classList.toggle('drawing', on);
  if (!on) return;
  resizeDrawing();
  wireCanvas(canvas);
  setTool(DEFAULT_TOOL);
}

export function resizeDrawing() {
  const canvas = $('#review-canvas'),
    video = $('#review-video');
  if (!canvas || !video) return;
  const rect = video.getBoundingClientRect();
  if (!rect.width) return;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  repaint();
}

export function repaint() {
  const canvas = $('#review-canvas');
  if (!canvas?.width) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  paintInk(ctx, state.review.strokes, canvas.width, canvas.height);
}

function wireCanvas(canvas) {
  textField(canvas);
  if (canvas.dataset.wired) return;
  canvas.dataset.wired = '1';
  let current = null;
  const pointAt = event => {
    const rect = canvas.getBoundingClientRect();
    return { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height };
  };
  canvas.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !state.review.drawing) return;
    // Sans ça, le clic suit son cours : le navigateur redonne le focus à la page, le champ texte
    // perd le sien et se referme aussitôt. Dessiner n'a de toute façon rien à faire du glisser-copier.
    event.preventDefault();
    commitText();
    const point = pointAt(event);
    if (state.review.tool === 'text') return openText(point);
    canvas.setPointerCapture(event.pointerId);
    current = { kind: state.review.tool, color: state.review.color, width: state.review.width };
    if (current.kind === 'free') current.points = [point];
    else Object.assign(current, { x1: point.x, y1: point.y, x2: point.x, y2: point.y });
    state.review.strokes.push(current);
    repaint();
  });
  canvas.addEventListener('pointermove', event => {
    if (!current) return;
    const point = pointAt(event);
    if (current.kind === 'free') {
      if (!pushPoint(current.points, point)) return;
    } else {
      current.x2 = point.x;
      current.y2 = point.y;
    }
    repaint();
  });
  const release = () => {
    if (!current) return;
    if (!worthKeeping(current)) state.review.strokes.pop();
    current = null;
    repaint();
  };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
}

/* ---------- Le texte, écrit sur place ---------- */
// Un clic pose un champ à l’endroit cliqué : Entrée valide, Échap annule, cliquer ailleurs valide
// aussi pour ne rien perdre. Le champ garde son propre ⌘Z, celui du navigateur.
let pending = null;

function textField(canvas) {
  const box = canvas.parentElement;
  const existing = $('#draw-text', box);
  if (existing) return existing;
  const field = document.createElement('input');
  field.id = 'draw-text';
  field.type = 'text';
  field.className = 'draw-text';
  field.maxLength = 90;
  field.autocomplete = 'off';
  field.placeholder = 'Texte…';
  field.hidden = true;
  field.setAttribute('aria-label', 'Texte à écrire sur l’image');
  field.addEventListener('keydown', event => {
    const meta = event.metaKey || event.ctrlKey;
    if (event.key === 'Enter' && !meta) {
      event.preventDefault();
      event.stopPropagation();
      commitText();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      cancelText();
    } else if (meta && event.key.toLowerCase() === 'z') {
      // ⌘Z pendant la saisie, c’est l’annulation du champ : elle ne doit pas retirer un trait.
      event.stopPropagation();
    }
  });
  field.addEventListener('blur', () => commitText());
  box.appendChild(field);
  return field;
}

function openText(point) {
  const canvas = $('#review-canvas'),
    field = $('#draw-text');
  if (!canvas || !field) return;
  const rect = canvas.getBoundingClientRect(),
    box = canvas.parentElement.getBoundingClientRect();
  pending = { kind: 'text', color: state.review.color, width: state.review.width, x: point.x, y: point.y, text: '' };
  field.value = '';
  field.hidden = false;
  field.style.font = textFontOf(state.review.width, Math.min(rect.width, rect.height));
  field.style.color = state.review.color;
  // Le champ s’aligne sur le texte peint : son bord et son retrait décalent la première lettre.
  field.style.left = `${rect.left - box.left + point.x * rect.width - 6}px`;
  field.style.top = `${rect.top - box.top + point.y * rect.height - 3}px`;
  field.style.maxWidth = `${Math.max(90, rect.width * (1 - point.x) + 12)}px`;
  field.focus();
}

function commitText() {
  const field = $('#draw-text');
  if (!pending || !field) return;
  const item = { ...pending, text: field.value.trim() };
  pending = null;
  field.value = '';
  field.hidden = true;
  if (!worthKeeping(item)) return;
  state.review.strokes.push(item);
  repaint();
}

function cancelText() {
  pending = null;
  const field = $('#draw-text');
  if (!field) return;
  field.value = '';
  field.hidden = true;
}

/* ---------- Les boutons de la barre d’outils ---------- */
function syncRadios(group, value) {
  $$(`[data-draw-${group}]`).forEach(button => {
    const on = button.dataset[`draw${group[0].toUpperCase()}${group.slice(1)}`] === value;
    button.classList.toggle('active', on);
    button.setAttribute('aria-checked', String(on));
  });
}

export function setTool(tool) {
  if (tool !== 'text') commitText();
  state.review.tool = tool;
  syncRadios('tool', tool);
  $('#review-video-box')?.classList.toggle('text-tool', tool === 'text');
}

export function setWidth(width) {
  state.review.width = width;
  syncRadios('width', width);
}

export function setColor(color) {
  state.review.color = color;
  $$('[data-draw-color]').forEach(button => button.classList.toggle('on', button.dataset.drawColor === color));
}

// ⌘Z (ou Ctrl+Z) retire le dernier trait, un par un. Il n’y a pas de « tout effacer ».
export function undoStroke() {
  if (!state.review.strokes.length) return;
  state.review.strokes.pop();
  repaint();
}

// L’image figée et les traits deviennent un seul PNG, à la résolution réelle de la vidéo.
export function captureDrawing() {
  commitText();
  const video = $('#review-video');
  if (!video?.videoWidth) return null;
  if (!state.review.strokes.length) {
    toast('Trace quelque chose avant de joindre la capture.', { kind: 'info' });
    return null;
  }
  const out = document.createElement('canvas');
  out.width = video.videoWidth;
  out.height = video.videoHeight;
  const ctx = out.getContext('2d');
  ctx.drawImage(video, 0, 0, out.width, out.height);
  paintInk(ctx, state.review.strokes, out.width, out.height);
  return out.toDataURL('image/png');
}

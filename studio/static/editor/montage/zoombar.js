// La barre de zoom de la timeline, sa règle de temps et sa mini-barre de navigation.
// Le geste de CapCut : un bouton « ajuster », deux loupes, un curseur, le pourcentage. Tous les
// chemins passent par applyView(), pour que la barre, la règle et la mini-barre restent d’accord.
import { $, clamp, ICONS } from '../../core/dom.js';
import { state } from '../../core/state.js';
import { montage } from '../../core/montage.js';
import { currentBlanks, fitView, reelBounds } from '../../core/blancs.js';
import {
  centerView,
  isZoomed,
  percentFromSlider,
  rulerTicks,
  scaleView,
  sliderFromPercent,
  SLIDER_STEPS,
  viewForPercent,
  viewFrame,
  WAVE_DELAY,
  wholeSpan,
  zoomAnchor,
  zoomPercent,
} from '../../core/zoom.js';
import { trimController, updateTrimDom } from './stage.js';
import { viewBounds } from './edges.js';
import { loadWaveform } from './wave.js';

let waveTimer = 0,
  sliding = false,
  rulerKey = '';

const headTime = () => trimController()?.video.currentTime;

// Le seul chemin pour changer la fenêtre visible : la timeline se redessine, et la forme d’onde se
// recharge — tout de suite pour un geste fini, au repos pour un geste continu (molette, curseur).
export function applyView(next, delay = 0) {
  const cut = montage(),
    now = state.trim;
  if (!next || !cut?.segments?.length) return false;
  if (now && Math.abs(next.start - now.start) < 0.004 && Math.abs(next.end - now.end) < 0.004) return false;
  state.trim = { key: state.project?.id || '', start: next.start, end: next.end, peaks: null };
  updateTrimDom(cut);
  clearTimeout(waveTimer);
  if (delay) waveTimer = window.setTimeout(loadWaveform, delay);
  else loadWaveform();
  return true;
}

// Les loupes et les raccourcis + / − : on zoome autour de la tête de lecture, ou du centre.
export function zoomBy(factor) {
  const view = state.trim;
  if (!view) return;
  const bounds = viewBounds();
  applyView(scaleView(view, factor, bounds, zoomAnchor(view, headTime())));
}

export function slideZoom(value) {
  const view = state.trim;
  if (!view) return;
  sliding = true;
  const bounds = viewBounds();
  applyView(viewForPercent(view, percentFromSlider(value, bounds), bounds, zoomAnchor(view, headTime())), WAVE_DELAY);
}

export function endZoomSlide() {
  sliding = false;
  updateZoomDom();
}

export function zoomBarHtml() {
  const view = state.trim || { start: 0, end: 1 },
    bounds = viewBounds();
  const percent = zoomPercent(view, bounds);
  return (
    `<div class="zoom-bar">` +
    `<button class="zoom-fit" type="button" data-fit-view title="Ajuster : tout le fichier">${ICONS.fitWidth} Tout voir</button>` +
    `<button class="zoom-step" type="button" data-zoom-step="out" title="Dézoomer (−)" aria-label="Dézoomer">${ICONS.zoomOut}</button>` +
    `<input class="zoom-slider" type="range" data-zoom-slider min="0" max="${SLIDER_STEPS}" ` +
    `value="${sliderFromPercent(percent, bounds)}" aria-label="Zoom de la timeline">` +
    `<button class="zoom-step" type="button" data-zoom-step="in" title="Zoomer (+)" aria-label="Zoomer">${ICONS.zoomIn}</button>` +
    `<span class="zoom-percent" id="zoom-percent">${Math.round(percent)} %</span></div>`
  );
}

export function rulerHtml() {
  return `<div class="trim-ruler" id="trim-ruler"></div>`;
}

// La mini-barre : tout le fichier en petit, la zone du reel, les coupes, la tête, le cadre visible.
export function miniBarHtml() {
  return (
    `<div class="trim-mini" id="trim-mini" hidden title="Tout le fichier : attrape le cadre pour te déplacer">` +
    `<div class="trim-mini-reel" id="mini-reel"></div><div id="mini-cuts"></div>` +
    `<i class="trim-mini-head" id="mini-head"></i>` +
    `<div class="trim-mini-frame" id="mini-frame"></div></div>`
  );
}

// Appelé par updateTrimDom : la barre suit tout changement de zoom, d’où qu’il vienne.
export function updateZoomDom() {
  const view = state.trim;
  if (!view) return;
  const bounds = viewBounds(),
    percent = zoomPercent(view, bounds);
  const label = $('#zoom-percent'),
    slider = $('[data-zoom-slider]');
  if (label) label.textContent = `${Math.round(percent)} %`;
  if (slider && !sliding) slider.value = String(sliderFromPercent(percent, bounds));
  renderRuler(view);
  renderMiniBar(view, bounds);
}

function renderRuler(view) {
  const ruler = $('#trim-ruler');
  if (!ruler) return;
  const width = Math.round(ruler.getBoundingClientRect().width),
    key = `${view.start}:${view.end}:${width}`;
  if (key === rulerKey) return;
  rulerKey = key;
  ruler.innerHTML = rulerTicks(view, width)
    .map(tick => `<i style="left:${(tick.part * 100).toFixed(3)}%"><b>${tick.label}</b></i>`)
    .join('');
}

function renderMiniBar(view, bounds) {
  const mini = $('#trim-mini'),
    cut = montage();
  if (!mini || !cut?.segments?.length) return;
  mini.hidden = !isZoomed(view, bounds);
  if (mini.hidden) return;
  const whole = wholeSpan(bounds),
    pct = time => `${clamp(((time - bounds.start) / whole) * 100, 0, 100)}%`;
  const reel = reelBounds(cut) || { start: 0, end: 0 };
  Object.assign($('#mini-reel').style, { left: pct(reel.start), right: `calc(100% - ${pct(reel.end)})` });
  $('#mini-cuts').innerHTML = currentBlanks(cut)
    .filter(blank => blank.cut !== false)
    .map(blank => `<i style="left:${pct(blank.start)}"></i>`)
    .join('');
  const frame = viewFrame(view, bounds);
  Object.assign($('#mini-frame').style, { left: `${frame.left}%`, width: `${frame.width}%` });
  updateMiniHead(headTime());
}

// La tête de lecture de la mini-barre bouge à chaque image : elle se place seule, sans tout refaire.
export function updateMiniHead(time) {
  const head = $('#mini-head');
  if (!head || !Number.isFinite(Number(time))) return;
  const bounds = viewBounds();
  head.style.left = `${clamp(((time - bounds.start) / wholeSpan(bounds)) * 100, 0, 100)}%`;
}

// La règle déplace la tête de lecture, la mini-barre déplace la vue. Les deux rendent la main au
// lâcher, et la mini-barre n’attrape le cadre que si on part dessus.
export function setupZoomViews(alive, scrub) {
  rulerKey = '';
  sliding = false;
  const ruler = $('#trim-ruler'),
    mini = $('#trim-mini');
  if (!ruler || !mini) return;
  const timeIn = (element, clientX, bounds) => {
    const rect = element.getBoundingClientRect();
    return bounds.start + clamp((clientX - rect.left) / Math.max(1, rect.width), 0, 1) * (bounds.end - bounds.start);
  };
  let onRuler = false,
    drag = null;
  ruler.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !state.trim) return;
    event.preventDefault();
    ruler.setPointerCapture(event.pointerId);
    onRuler = true;
    scrub(timeIn(ruler, event.clientX, state.trim));
  });
  ruler.addEventListener('pointermove', event => {
    if (onRuler && alive() && state.trim) scrub(timeIn(ruler, event.clientX, state.trim));
  });
  mini.addEventListener('pointerdown', event => {
    const view = state.trim;
    if (event.button !== 0 || !view) return;
    event.preventDefault();
    mini.setPointerCapture(event.pointerId);
    const span = view.end - view.start,
      bounds = viewBounds();
    if (event.target.closest('#mini-frame')) drag = { grab: timeIn(mini, event.clientX, bounds) - view.start, span };
    else {
      applyView(centerView(view, timeIn(mini, event.clientX, bounds), bounds), WAVE_DELAY);
      drag = { grab: span / 2, span };
    }
  });
  mini.addEventListener('pointermove', event => {
    if (!drag || !alive()) return;
    const bounds = viewBounds(),
      start = timeIn(mini, event.clientX, bounds) - drag.grab;
    applyView(fitView({ start, end: start + drag.span }, bounds), WAVE_DELAY);
  });
  const release = () => {
    onRuler = false;
    drag = null;
  };
  for (const name of ['pointerup', 'pointercancel']) {
    ruler.addEventListener(name, release);
    mini.addEventListener(name, release);
  }
}

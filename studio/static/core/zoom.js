// Le zoom de la timeline, en chiffres : pourcentage, curseur, règle de temps, suivi de la lecture,
// cadre de la mini-barre et sélection. Comme blancs.js, rien ici ne touche au DOM : ce fichier ne
// fait que les calculs, pour qu’ils soient vérifiables sans navigateur.
import { fitView, VIEW_MIN } from './blancs.js';

export const ZOOM_FACTOR = 1.6; // un clic de loupe, ou un appui sur + / −
export const SLIDER_STEPS = 1000; // le curseur parle en millièmes, en échelle logarithmique
export const RULER_STEPS = [0.1, 0.5, 1, 2, 5, 10, 15, 30, 60]; // les pas de la règle, du plus fin au plus large
export const RULER_MIN_PX = 70; // deux étiquettes ne se rapprochent jamais plus que ça
export const FOLLOW_EDGE = 0.1; // la tête de lecture revient à 10 % du bord gauche
export const WAVE_DELAY = 160; // la forme d’onde ne se recharge qu’au repos du geste

const round = value => +Number(value).toFixed(3);
const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

// Tout le fichier, et la fenêtre la plus serrée qu’on s’autorise dedans.
export function wholeSpan(bounds) {
  return Math.max(0.2, Number(bounds.end) - Number(bounds.start));
}

export function tightestSpan(bounds) {
  return Math.min(VIEW_MIN, wholeSpan(bounds));
}

// 100 % = le fichier entier tient dans la piste ; 400 % = on en voit le quart.
export function zoomPercent(view, bounds) {
  const span = Math.max(0.001, Number(view.end) - Number(view.start));
  return (wholeSpan(bounds) / span) * 100;
}

export function maxZoomPercent(bounds) {
  return (wholeSpan(bounds) / tightestSpan(bounds)) * 100;
}

export function isZoomed(view, bounds) {
  if (!view) return false;
  return Number(view.end) - Number(view.start) < wholeSpan(bounds) - 0.01;
}

// Autour de quoi zoomer : la tête de lecture si elle est dans la fenêtre, sinon le centre.
export function zoomAnchor(view, time) {
  const span = Number(view.end) - Number(view.start);
  if (!(span > 0) || !Number.isFinite(Number(time))) return 0.5;
  if (time < view.start || time > view.end) return 0.5;
  return clamp((time - view.start) / span, 0, 1);
}

// Une fenêtre d’une largeur voulue, ancrée : le temps sous l’ancre ne bouge pas. `part` va de 0 à 1.
export function viewForSpan(view, span, bounds, part = 0.5) {
  const place = clamp(part, 0, 1),
    anchor = Number(view.start) + place * (Number(view.end) - Number(view.start));
  const next = clamp(span, tightestSpan(bounds), wholeSpan(bounds));
  return fitView({ start: anchor - place * next, end: anchor - place * next + next }, bounds);
}

export function viewForPercent(view, percent, bounds, part = 0.5) {
  return viewForSpan(view, wholeSpan(bounds) / (Math.max(1, Number(percent)) / 100), bounds, part);
}

// Les loupes : un facteur au-dessus de 1 zoome, en dessous dézoome.
export function scaleView(view, factor, bounds, part = 0.5) {
  return viewForSpan(view, (Number(view.end) - Number(view.start)) / Math.max(0.001, factor), bounds, part);
}

// Le curseur est logarithmique : un millième de glisser vaut le même rapport de zoom partout.
export function percentFromSlider(value, bounds, steps = SLIDER_STEPS) {
  const top = maxZoomPercent(bounds);
  if (!(top > 100)) return 100;
  return 100 * Math.pow(top / 100, clamp(Number(value), 0, steps) / steps);
}

export function sliderFromPercent(percent, bounds, steps = SLIDER_STEPS) {
  const top = maxZoomPercent(bounds);
  if (!(top > 100)) return 0;
  return Math.round((Math.log(clamp(Number(percent), 100, top) / 100) / Math.log(top / 100)) * steps);
}

// Le pas de la règle : le plus fin qui laisse ~70 px entre deux étiquettes.
export function rulerStep(span, width, minPx = RULER_MIN_PX) {
  for (const step of RULER_STEPS) if ((step / Math.max(0.001, span)) * width >= minPx) return step;
  return RULER_STEPS.at(-1);
}

// mm:ss, avec les dixièmes quand le pas est sous la seconde.
export function rulerLabel(time, step) {
  const value = Math.max(0, Number(time)),
    minutes = Math.floor(value / 60),
    seconds = value % 60;
  const body = step < 1 ? seconds.toFixed(1).padStart(4, '0') : String(Math.round(seconds)).padStart(2, '0');
  return `${String(minutes).padStart(2, '0')}:${body}`;
}

export function rulerTicks(view, width, minPx = RULER_MIN_PX) {
  const span = Number(view.end) - Number(view.start);
  if (!(span > 0) || !(width > 0)) return [];
  const step = rulerStep(span, width, minPx),
    out = [];
  const first = Math.ceil(view.start / step - 0.0001) * step;
  for (let index = 0; first + index * step <= view.end + 0.0001 && index < 400; index += 1) {
    const time = round(first + index * step);
    out.push({ time, part: clamp((time - view.start) / span, 0, 1), label: rulerLabel(time, step) });
  }
  return out;
}

// Suivi de la lecture : zoomé, quand la tête sort de la fenêtre, la vue saute d’une page pour la
// remettre à ~10 % du bord gauche. Rien à faire si la tête est dedans, ou si on voit tout le fichier.
export function followView(view, time, bounds, edge = FOLLOW_EDGE) {
  const span = Number(view.end) - Number(view.start);
  if (!(span > 0) || !Number.isFinite(Number(time))) return null;
  if (!isZoomed(view, bounds)) return null;
  if (time >= view.start && time <= view.end) return null;
  const start = Number(time) - edge * span;
  const next = fitView({ start, end: start + span }, bounds);
  return Math.abs(next.start - view.start) < 0.004 ? null : next;
}

// Un clic hors du cadre de la mini-barre : la vue se recentre là, sans changer de largeur.
export function centerView(view, time, bounds) {
  const span = Number(view.end) - Number(view.start),
    start = Number(time) - span / 2;
  return fitView({ start, end: start + span }, bounds);
}

// Le cadre de la mini-barre : la part visible du fichier, en pourcentage de sa largeur.
export function viewFrame(view, bounds) {
  const whole = wholeSpan(bounds),
    left = ((Number(view.start) - Number(bounds.start)) / whole) * 100;
  const width = ((Number(view.end) - Number(view.start)) / whole) * 100;
  return { left: +clamp(left, 0, 100).toFixed(3), width: +clamp(width, 0.6, 100 - clamp(left, 0, 100)).toFixed(3) };
}

// Maj + glisser : les deux bouts d’une sélection, remis dans l’ordre.
export function orderSelection(from, to) {
  const a = Math.min(Number(from), Number(to)),
    b = Math.max(Number(from), Number(to));
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return { start: round(Math.max(0, a)), end: round(b) };
}

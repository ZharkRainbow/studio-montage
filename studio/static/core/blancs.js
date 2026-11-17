// Les blancs du montage : garder ou couper, blanc par blanc, à la main.
//
// Les gestes viennent de l’outil Reels V3 (~/projets/outil-reels, outil/index.html) : un clic
// sur un blanc le garde ou le coupe, ses deux bords se tirent à la souris et s’aimantent aux
// mots, la molette zoome autour du pointeur. Ici, rien ne touche au DOM : ce fichier ne fait
// que les calculs, pour qu’ils soient vérifiables sans navigateur.
export const EDGE_MIN = 0.06; // un blanc plus étroit que ça ne s’entend pas
export const MIN_PIECE = 0.15; // un morceau gardé plus court que ça, le serveur le jette aussi
export const SNAP_RANGE = 0.4; // on cherche un mot à cette distance du bord lâché
export const MARGIN_BEFORE = 0.1; // et on se pose à cette marge avant le mot d’après
export const MARGIN_AFTER = 0.12; // ou après le mot d’avant : les mêmes marges que le serveur
export const VIEW_MIN = 0.4; // on ne zoome pas plus serré qu’un demi-mot
export const HAND_CUT_MIN = 0.05; // une coupe faite à la main plus courte est refusée

const round = value => +Number(value).toFixed(3);
const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

export function blanksOf(cut) {
  return Array.isArray(cut?.blanks) ? cut.blanks : [];
}

// Les bornes du reel : le début du premier morceau, la fin du dernier.
export function trimBounds(cut) {
  const pieces = cut?.segments || [];
  if (!pieces.length) return null;
  return { start: Number(pieces[0].start), end: Number(pieces.at(-1).end) };
}

// La liste affichée : celle du projet, ou celle qu'on déduit des morceaux d'un vieux projet.
export function currentBlanks(cut) {
  const list = blanksOf(cut);
  return list.length ? list : blanksFromSegments(cut);
}

// Les bornes du reel, en remontant les coupes collées au premier et au dernier morceau : couper un
// blanc tout au début ne doit pas perdre le début du reel, sinon un deuxième clic ne le rendrait pas.
export function reelBounds(cut) {
  const inner = trimBounds(cut);
  if (!inner) return null;
  const list = blanksOf(cut)
    .filter(blank => blank.cut !== false)
    .map(blank => ({ start: Number(blank.start), end: Number(blank.end) }));
  let { start, end } = inner,
    moved = true;
  while (moved) {
    moved = false;
    for (const blank of list) {
      if (blank.start < start && Math.abs(blank.end - start) < 0.011) {
        start = blank.start;
        moved = true;
      }
      if (blank.end > end && Math.abs(blank.start - end) < 0.011) {
        end = blank.end;
        moved = true;
      }
    }
  }
  return { start: round(start), end: round(end) };
}

// Les morceaux gardés = les bornes, moins les blancs marqués à couper. C’est la même règle que
// `cut_blanks` côté serveur : le montage reste le même après un aller-retour.
export function segmentsFromBlanks(bounds, list, minPiece = MIN_PIECE) {
  let pieces = [{ start: bounds.start, end: bounds.end }];
  for (const blank of list || []) {
    if (blank.cut === false) continue;
    const a = Number(blank.start),
      b = Number(blank.end);
    if (!(b > a)) continue;
    pieces = pieces.flatMap(piece => {
      if (b <= piece.start || a >= piece.end) return [piece];
      const out = [];
      if (a > piece.start) out.push({ start: piece.start, end: a });
      if (b < piece.end) out.push({ start: b, end: piece.end });
      return out;
    });
  }
  const kept = pieces.filter(piece => piece.end - piece.start >= minPiece);
  const safe = kept.length ? kept : pieces.length ? pieces.slice(0, 1) : [{ start: bounds.start, end: bounds.end }];
  return safe.map(piece => ({ start: round(piece.start), end: round(piece.end) }));
}

// Un bord lâché près d’un mot se cale sur lui, avec la marge de respiration. `words` est la liste
// des mots recalés sur le son, telle que le serveur la renvoie : des paires [début, fin].
export function snapToWords(words, time, range = SNAP_RANGE) {
  let best = Number(time),
    gap = range;
  for (const word of words || []) {
    const a = Number(word[0]),
      b = Number(word[1]);
    if (Math.abs(time - b) < gap) {
      gap = Math.abs(time - b);
      best = b + MARGIN_AFTER;
    }
    if (Math.abs(time - a) < gap) {
      gap = Math.abs(time - a);
      best = a - MARGIN_BEFORE;
    }
  }
  return Math.max(0, round(best));
}

export function blankIndexAt(list, time) {
  return (list || []).findIndex(blank => time >= Number(blank.start) && time <= Number(blank.end));
}

export function toggleBlank(list, index) {
  return list.map((blank, position) => (position === index ? { ...blank, cut: blank.cut === false } : { ...blank }));
}

// Tirer un bord : il ne traverse ni l’autre bord, ni le blanc voisin, et s’aimante aux mots.
export function moveBlankEdge(list, index, edge, time, words, bounds = null) {
  const out = list.map(blank => ({ ...blank }));
  const blank = out[index];
  if (!blank) return out;
  const low = Number(out[index - 1]?.end ?? bounds?.start ?? 0),
    high = Number(out[index + 1]?.start ?? bounds?.end ?? Infinity);
  const wanted = snapToWords(words, time);
  if (edge === 'start') blank.start = round(clamp(wanted, low, Number(blank.end) - EDGE_MIN));
  else blank.end = round(clamp(wanted, Number(blank.start) + EDGE_MIN, high));
  return out;
}

// « Couper ici » : une coupe posée à la main. Elle avale les blancs qu’elle touche, pour que la
// liste reste ordonnée et sans recouvrement — c’est ce que le serveur vérifie à l’enregistrement.
export function addBlank(list, from, to, words = null) {
  let a = Math.min(Number(from), Number(to)),
    b = Math.max(Number(from), Number(to));
  if (words) {
    a = snapToWords(words, a);
    b = snapToWords(words, b);
  }
  if (!(b - a >= HAND_CUT_MIN)) return null;
  const piece = { start: round(a), end: round(b), cut: true, manual: true };
  const out = [];
  for (const blank of list || []) {
    if (Number(blank.end) < piece.start - 0.001 || Number(blank.start) > piece.end + 0.001) {
      out.push({ ...blank });
      continue;
    }
    piece.start = Math.min(piece.start, Number(blank.start));
    piece.end = Math.max(piece.end, Number(blank.end));
  }
  piece.start = round(piece.start);
  piece.end = round(piece.end);
  out.push(piece);
  return out.sort((first, second) => first.start - second.start);
}

// Les blancs qu’on n’a pas dans la liste : la timeline d’un vieux projet ne connaît que ses
// morceaux. On en déduit les coupes déjà faites pour qu’elles restent cliquables.
export function blanksFromSegments(cut) {
  return (cut?.segments || []).slice(1).map((piece, index) => ({
    start: round(cut.segments[index].end),
    end: round(piece.start),
    cut: true,
  }));
}

export function fitView(view, bounds) {
  const whole = Math.max(0.2, bounds.end - bounds.start);
  const span = clamp(view.end - view.start, Math.min(VIEW_MIN, whole), whole);
  const start = clamp(view.start, bounds.start, bounds.end - span);
  return { start: round(start), end: round(start + span) };
}

// Molette : le temps sous le pointeur ne bouge pas. `part` est la position du pointeur sur la
// piste, de 0 à 1. Un pincement (ctrl) zoome plus vite, comme dans l’outil Reels.
export function zoomView(view, part, delta, bounds, fine = false) {
  const span = view.end - view.start;
  const anchor = view.start + clamp(part, 0, 1) * span;
  const wanted = span * Math.exp(delta * (fine ? 0.012 : 0.0025));
  const whole = Math.max(0.2, bounds.end - bounds.start);
  const next = clamp(wanted, Math.min(VIEW_MIN, whole), whole);
  return fitView({ start: anchor - clamp(part, 0, 1) * next, end: anchor - clamp(part, 0, 1) * next + next }, bounds);
}

export function panView(view, seconds, bounds) {
  return fitView({ start: view.start + seconds, end: view.end + seconds }, bounds);
}

// Une molette donne des lignes ou des pages selon la souris : on ramène tout en pixels.
export function wheelDelta(event) {
  const mode = event.deltaMode || 0;
  return Number(event.deltaY) * (mode === 1 ? 16 : mode === 2 ? 400 : 1);
}

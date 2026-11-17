// Transcript mot à mot de la version relue : mot courant surligné, clic pour lire, sélection pour une plage.
import { $, $$, esc, ICONS } from '../../core/dom.js';
import { state } from '../../core/state.js';
import { refreshComposerWhen } from './retours.js';
import { reviewWords } from './data.js';

export function transcriptHtml() {
  const words = reviewWords(),
    version = state.project?.versions?.find(item => item.id === state.review.versionId);
  const status = version?.transcript_state;
  if (!words.length)
    return (
      `<div class="review-transcript empty" id="review-transcript"><span class="eyebrow">Transcript</span>` +
      `<p>` +
      (status === 'failed'
        ? 'La transcription a échoué. Relance-la depuis le menu des versions.'
        : status === 'pending'
          ? 'whisper.cpp écoute la version déposée, mot à mot, sur cette machine.'
          : 'Aucun transcript pour cette version.') +
      `</p></div>`
    );
  return (
    `<div class="review-transcript" id="review-transcript">` +
    `<div class="review-transcript-head"><span class="eyebrow">Transcript</span>` +
    `<span class="transcript-hint" title="Clic : lire ici. Glisser sur plusieurs mots : créer une plage.">${ICONS.alert}</span></div>` +
    `<p class="review-words" id="review-words">` +
    words.map((word, index) => `<span class="w" data-word="${index}">${esc(word.text)}</span>`).join(' ') +
    `</p></div>`
  );
}

export function highlightTranscript(time) {
  const words = reviewWords(),
    root = $('#review-words');
  if (!root || !words.length) return;
  let index = -1;
  for (let i = 0; i < words.length; i += 1) {
    if (words[i].start <= time + 0.01) index = i;
    else break;
  }
  if (index === state.review.wordIndex) return;
  state.review.wordIndex = index;
  const previous = $('.w.now', root);
  if (previous) previous.classList.remove('now');
  const current = index >= 0 ? $(`[data-word="${index}"]`, root) : null;
  if (!current) return;
  current.classList.add('now');
  const box = current.getBoundingClientRect(),
    frame = root.parentElement.getBoundingClientRect();
  if (box.top < frame.top || box.bottom > frame.bottom) current.scrollIntoView({ block: 'center' });
}

export function paintSelection() {
  const selection = state.review.selection;
  $$('#review-words .w').forEach(span => span.classList.remove('picked'));
  if (!selection) return;
  for (let index = selection.first; index <= selection.last; index += 1) $(`#review-words [data-word="${index}"]`)?.classList.add('picked');
}

// Une phrase citée autour d’un instant : le mot courant et ses voisins, jamais un texte inventé.
export function quoteAround(time, span = 3) {
  const words = reviewWords();
  if (!words.length) return '';
  let index = 0;
  for (let i = 0; i < words.length; i += 1) {
    if (words[i].start <= time + 0.01) index = i;
    else break;
  }
  return words
    .slice(Math.max(0, index - span), index + span + 1)
    .map(word => word.text)
    .join(' ')
    .trim();
}

export function setSelection(first, last) {
  const words = reviewWords();
  if (first === null || !words.length) {
    state.review.selection = null;
  } else {
    const a = Math.min(first, last),
      b = Math.max(first, last);
    state.review.selection = {
      first: a,
      last: b,
      start: words[a].start,
      end: Math.max(words[b].end, words[a].start + 0.1),
      quote: words
        .slice(a, b + 1)
        .map(word => word.text)
        .join(' ')
        .trim(),
    };
  }
  paintSelection();
  refreshComposerWhen();
}

export function wireTranscript(token, seek) {
  const root = $('#review-words');
  if (!root) return;
  let anchor = null,
    dragged = false;
  const indexAt = target => {
    const span = target?.closest?.('[data-word]');
    return span ? Number(span.dataset.word) : null;
  };
  root.addEventListener('pointerdown', event => {
    if (event.button !== 0 || token !== state.stageToken) return;
    const index = indexAt(event.target);
    if (index === null) return;
    event.preventDefault();
    root.setPointerCapture(event.pointerId);
    anchor = index;
    dragged = false;
    setSelection(index, index);
  });
  root.addEventListener('pointermove', event => {
    if (anchor === null) return;
    const index = indexAt(document.elementFromPoint(event.clientX, event.clientY));
    if (index === null || index === state.review.selection?.last) return;
    dragged = dragged || index !== anchor;
    setSelection(anchor, index);
  });
  const release = () => {
    if (anchor === null) return;
    const words = reviewWords();
    if (!dragged) {
      const start = words[anchor]?.start ?? 0;
      setSelection(null);
      seek(start);
    }
    anchor = null;
  };
  root.addEventListener('pointerup', release);
  root.addEventListener('pointercancel', release);
}

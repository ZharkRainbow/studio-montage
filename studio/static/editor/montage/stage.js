// Timeline du montage : lecture, blancs et glisser des poignées.
import { montageDuration, proxyUrl, reelToSource, sourceToReel, TITLE_SECONDS } from '../../core/montage.js';
import { $, $$, clamp, clone, esc, fmtTime, ICONS } from '../../core/dom.js';
import { checkpoint } from '../../core/history.js';
import { state } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { drawWave, loadWaveform } from './wave.js';
import { currentBlanks, moveBlankEdge, panView, reelBounds, segmentsFromBlanks, wheelDelta, zoomView } from '../../core/blancs.js';
import { followView, WAVE_DELAY } from '../../core/zoom.js';
import { speedLabel } from '../../core/speed.js';
import {
  applyBlanks, commitTrim, nudgeButtons, rushDuration, silenceToolHtml, toggleBlankAt, trimFits, trimSegments, trimWindowFor,
  viewBounds, zoomHeld,
} from './edges.js';
import { applyView, miniBarHtml, rulerHtml, setupZoomViews, updateMiniHead, updateZoomDom } from './zoombar.js';
import { clearSelection, dragSelection, endSelection, selecting, selectionHtml, startSelection, updateSelectionDom } from './select.js';

export function renderTrimmer(cut) {
  // Un Annuler, un retour depuis la Relecture : le zoom du même projet survit. Un autre projet le remet à plat.
  if (!trimFits(cut) && !zoomHeld()) state.trim = trimWindowFor(cut);
  $('#stage-body').innerHTML =
    `<div class="trim-stage"><div class="trim-video">` +
    `<video id="montage-video" src="${esc(proxyUrl())}" playsinline preload="auto"></video>` +
    `<button class="trim-overlay" id="trim-overlay" type="button" aria-label="Lecture">` +
    `${ICONS.play}</button><span class="trim-badge" id="trim-badge" hidden></span></div></div>`;
  const [startBack, startBackSmall, startFwdSmall, startFwd] = nudgeButtons('start'),
    [endBack, endBackSmall, endFwdSmall, endFwd] = nudgeButtons('end');
  $('#transport').innerHTML =
    `<div class="trim">
    <div class="trim-bar">` +
    `<button class="play-button" id="trim-play" type="button" aria-label="Lecture">` +
    `${ICONS.play}</button><span class="timecode"><strong id="trim-now">00:00.0</strong> / ` +
    `<span id="trim-total">${fmtTime(montageDuration(), true)}</span></span>` +
    `<button class="pill${state.speed === 1 ? '' : ' on'}" type="button" data-trim-speed ` +
    `title="Vitesse de lecture : 1×, 1,2×, 1,5×, 2×">${speedLabel(state.speed)}</button>` +
    `<span class="transport-hint">Espace lecture · I / O fixer début / fin · clic sur un blanc : garder ou couper · ` +
    `molette : zoom · + / − zoomer · Maj+Z tout voir · Maj + glisser : sélectionner · Suppr : couper</span>` +
    `<span id="trim-silence">${silenceToolHtml(cut)}</span></div>
    ` +
    rulerHtml() +
    `<div class="trim-track" id="trim-track"><canvas id="trim-wave"></canvas>` +
    `<div class="trim-shade left" id="trim-shade-left"></div>` +
    `<div class="trim-shade right" id="trim-shade-right"></div><div id="trim-gaps"></div>` +
    `<div class="trim-range" id="trim-range"></div>` +
    `<div class="trim-title" id="trim-title" hidden><span>Titre</span></div>` +
    selectionHtml() +
    `<div class="trim-playhead" id="trim-playhead"></div>` +
    `<div class="trim-handle start" data-trim-handle="start" title="Début du reel"><i></i>` +
    `</div><div class="trim-handle end" data-trim-handle="end" title="Fin du reel"><i></i>` +
    `</div></div>` +
    miniBarHtml() +
    `
    <div class="trim-foot"><div class="trim-edge"><span>Début</span>` +
    `${startBack}${startBackSmall}<b id="trim-start">—</b>${startFwdSmall}${startFwd}</div>` +
    `<span class="trim-window" id="trim-window"></span><div class="trim-edge"><span>Fin</span>` +
    `${endBack}${endBackSmall}<b id="trim-end">—</b>${endFwdSmall}${endFwd}</div></div>
  </div>`;
  updateTrimDom(cut);
  setupTrimmer(cut, state.stageToken);
  loadWaveform();
}

export function updateTrimDom(cut) {
  const w = state.trim,
    track = $('#trim-track');
  if (!w || !track || !cut?.segments?.length) return;
  const span = w.end - w.start,
    pct = time => `${clamp(((time - w.start) / span) * 100, 0, 100)}%`;
  const first = cut.segments[0].start,
    last = cut.segments.at(-1).end;
  $('#trim-shade-left').style.width = pct(first);
  $('#trim-shade-right').style.left = pct(last);
  Object.assign($('#trim-range').style, { left: pct(first), right: `calc(100% - ${pct(last)})` });
  $('[data-trim-handle="start"]', track).style.left = pct(first);
  $('[data-trim-handle="end"]', track).style.left = pct(last);
  $('#trim-gaps').innerHTML = blanksHtml(cut, pct);
  updateTitleMarker(cut, pct);
  $('#trim-start').textContent = fmtTime(first, true);
  $('#trim-end').textContent = fmtTime(last, true);
  $('#trim-total').textContent = fmtTime(montageDuration(), true);
  $('#trim-window').textContent = `Fichier ${fmtTime(w.start)} → ${fmtTime(w.end)}`;
  updateZoomDom();
  updateSelectionDom();
}

// Chaque blanc trouvé est un élément à lui : hachuré s’il est coupé, sourd s’il est gardé. Un clic
// le retourne, ses deux bords se tirent à la souris, et le petit bouton écoute la jointure.
function blanksHtml(cut, pct) {
  const bounds = reelBounds(cut) || { start: 0, end: 0 };
  return currentBlanks(cut)
    .map((blank, index) => {
      const outside = blank.end <= bounds.start + 0.001 || blank.start >= bounds.end - 0.001,
        length = fmtTime(Math.max(0, blank.end - blank.start), true);
      const title = outside
        ? `Hors du reel · ${length}`
        : blank.cut === false
          ? `Blanc gardé · ${length} · clic pour le couper`
          : `Coupé · ${length} · clic pour le garder`;
      return (
        `<i class="trim-blank ${blank.cut === false ? 'kept' : 'cut'}${outside ? ' outside' : ''}` +
        `${blank.manual ? ' manual' : ''}" data-blank="${index}" style="left:${pct(blank.start)};` +
        `width:calc(${pct(blank.end)} - ${pct(blank.start)})" title="${esc(title)}">` +
        `<b data-blank-edge="start"></b><b data-blank-edge="end"></b>` +
        `<button class="trim-listen" type="button" data-blank-listen="${index}" tabindex="-1" ` +
        `aria-label="Écouter la jointure">${ICONS.play}</button></i>`
      );
    })
    .join('');
}

// Le titre s’affiche une durée fixe, réglée dans la compétence : la timeline le montre, sans réglage.
function updateTitleMarker(cut, pct) {
  const marker = $('#trim-title');
  if (!marker) return;
  const title = (state.project?.montage?.title || '').trim();
  if (!title) {
    marker.hidden = true;
    return;
  }
  const start = cut.segments[0].start,
    end = reelToSource(Math.min(TITLE_SECONDS, montageDuration()));
  marker.hidden = false;
  marker.style.left = pct(start);
  marker.style.width = `calc(${pct(end)} - ${pct(start)})`;
  marker.title = `Titre « ${title} » pendant ${String(TITLE_SECONDS).replace('.', ',')} s`;
  $('span', marker).textContent = title;
}

// Le repère du titre suit la frappe : on le redessine seul, sans refaire toute la timeline.
export function refreshTitleMarker() {
  const w = state.trim,
    cut = state.project?.montage;
  if (!w || !cut?.segments?.length || !$('#trim-title')) return;
  const span = w.end - w.start;
  updateTitleMarker(cut, time => `${clamp(((time - w.start) / span) * 100, 0, 100)}%`);
}

export function updateTrimPlayhead(cut, time) {
  const w = state.trim,
    head = $('#trim-playhead');
  if (!w || !head) return;
  head.style.left = `${clamp(((time - w.start) / (w.end - w.start)) * 100, 0, 100)}%`;
  updateMiniHead(time);
  const inside = cut.segments.find(piece => time >= piece.start - 0.02 && time <= piece.end + 0.02);
  $('#trim-now').textContent = fmtTime(
    inside
      ? sourceToReel(clamp(time, inside.start, inside.end))
      : time < cut.segments[0].start
        ? 0
        : time > cut.segments.at(-1).end
          ? montageDuration()
          : sourceToReel(cut.segments.find(piece => piece.start > time)?.start ?? 0),
    true,
  );
  const badge = $('#trim-badge');
  if (badge) {
    const label = inside
      ? ''
      : time < cut.segments[0].start
        ? 'Avant le début du reel'
        : time > cut.segments.at(-1).end
          ? 'Après la fin du reel'
          : 'Partie coupée';
    badge.hidden = !label;
    badge.textContent = label;
  }
}

export function setupTrimmer(cut, token) {
  const video = $('#montage-video'),
    track = $('#trim-track');
  if (!video || !track) return;
  let frame = 0,
    followCuts = false,
    drag = null,
    scrubbing = false,
    seekTimer = 0,
    stopAt = 0;
  const alive = () => token === state.stageToken && document.body.contains(video);
  const setIcons = () => {
    const icon = video.paused ? ICONS.play : ICONS.pause;
    $('#trim-play').innerHTML = icon;
    $('#trim-overlay').innerHTML = icon;
    $('#trim-overlay').classList.toggle('hidden', !video.paused);
  };
  const tick = () => {
    if (!alive()) {
      video.pause();
      return;
    }
    const time = video.currentTime,
      pieces = cut.segments;
    if (stopAt && time >= stopAt) {
      video.pause();
      stopAt = 0;
    }
    if (followCuts) {
      if (!pieces.some(piece => time >= piece.start - 0.05 && time < piece.end)) {
        const next = pieces.find(piece => piece.start > time);
        if (next) video.currentTime = next.start;
        else {
          video.pause();
          video.currentTime = pieces[0].start;
        }
      }
    } else if (time >= pieces[0].start && time < pieces.at(-1).end) followCuts = true;
    else if (time >= state.trim.end) video.pause();
    updateTrimPlayhead(cut, video.currentTime);
    follow(video.currentTime);
    if (!video.paused) frame = requestAnimationFrame(tick);
  };
  // Zoomé, la vue saute d’une page quand la tête sort de la fenêtre. Jamais pendant un glisser.
  const follow = time => {
    if (drag || scrubbing || selecting()) return;
    const next = followView(state.trim, time, viewBounds());
    if (next) applyView(next, WAVE_DELAY);
  };
  const seekTo = time => {
    video.currentTime = clamp(time, 0, rushDuration());
    updateTrimPlayhead(cut, video.currentTime);
  };
  const seek = time => {
    seekTo(time);
    follow(video.currentTime);
  };
  const toggle = () => {
    stopAt = 0;
    if (!video.paused) {
      video.pause();
      return;
    }
    const time = video.currentTime,
      pieces = cut.segments;
    if (time >= pieces.at(-1).end - 0.05 || time < state.trim.start || time >= state.trim.end) video.currentTime = pieces[0].start;
    followCuts = video.currentTime >= pieces[0].start - 0.05 && video.currentTime < pieces.at(-1).end;
    video.play().catch(() => toast('La lecture a été bloquée par le navigateur. Reclique sur lecture.', { kind: 'error' }));
  };
  const audition = index => {
    const blank = currentBlanks(cut)[index];
    if (!blank) return;
    stopAt = Number(blank.end) + 1;
    followCuts = true;
    seek(Math.max(0, Number(blank.start) - 1));
    video.play().catch(() => toast('La lecture a été bloquée par le navigateur. Reclique sur lecture.', { kind: 'error' }));
  };
  video.addEventListener('loadedmetadata', () => seek(cut.segments[0].start), { once: true });
  video.addEventListener('play', () => {
    setIcons();
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(tick);
  });
  video.addEventListener('pause', () => {
    setIcons();
    cancelAnimationFrame(frame);
    updateTrimPlayhead(cut, video.currentTime);
  });
  video.addEventListener('seeked', () => updateTrimPlayhead(cut, video.currentTime));
  video.addEventListener('click', toggle);
  $('#trim-overlay').addEventListener('click', toggle);
  $('#trim-play').addEventListener('click', toggle);
  const timeAt = clientX => {
    const rect = track.getBoundingClientRect();
    return state.trim.start + clamp((clientX - rect.left) / rect.width, 0, 1) * (state.trim.end - state.trim.start);
  };
  const previewAt = time => {
    clearTimeout(seekTimer);
    seekTimer = setTimeout(() => {
      if (alive()) seek(time);
    }, 40);
  };
  track.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    if (event.shiftKey) {
      event.preventDefault();
      track.setPointerCapture(event.pointerId);
      video.pause();
      startSelection(timeAt(event.clientX));
      return;
    }
    clearSelection();
    const listen = event.target.closest('[data-blank-listen]');
    if (listen) {
      event.preventDefault();
      audition(Number(listen.dataset.blankListen));
      return;
    }
    const handle = event.target.closest('[data-trim-handle]'),
      blank = event.target.closest('[data-blank]');
    track.setPointerCapture(event.pointerId);
    event.preventDefault();
    if (blank && !handle) {
      video.pause();
      drag = {
        kind: 'blank',
        index: Number(blank.dataset.blank),
        edge: event.target.closest('[data-blank-edge]')?.dataset.blankEdge || '',
        original: clone(currentBlanks(cut)),
        bounds: reelBounds(cut),
        time: timeAt(event.clientX),
        x: event.clientX,
        moved: false,
      };
      blank.classList.add('dragging');
      track.classList.add('dragging');
      return;
    }
    if (!handle) {
      scrubbing = true;
      video.pause();
      seek(timeAt(event.clientX));
      return;
    }
    video.pause();
    drag = { edge: handle.dataset.trimHandle, original: clone(cut.segments), moved: false };
    handle.classList.add('dragging');
    track.classList.add('dragging');
  });
  track.addEventListener('pointermove', event => {
    if (selecting()) {
      dragSelection(timeAt(event.clientX));
      return;
    }
    if (scrubbing) {
      seek(timeAt(event.clientX));
      return;
    }
    if (!drag) return;
    if (drag.kind === 'blank') {
      drag.time = timeAt(event.clientX);
      if (!drag.edge || (!drag.moved && Math.abs(event.clientX - drag.x) < 2)) return;
      if (!drag.moved) {
        checkpoint();
        drag.moved = true;
      }
      // Pendant le glisser, le bord suit la souris ; l’aimant n’agit qu’au lâcher, comme dans l’outil Reels.
      const list = moveBlankEdge(drag.original, drag.index, drag.edge, drag.time, null, drag.bounds);
      cut.blanks = list;
      cut.segments = segmentsFromBlanks(drag.bounds, list);
      updateTrimDom(cut);
      previewAt(drag.edge === 'start' ? list[drag.index].start : list[drag.index].end);
      return;
    }
    if (!drag.moved) {
      checkpoint();
      drag.moved = true;
    }
    cut.segments = trimSegments(drag.original, drag.edge, timeAt(event.clientX));
    updateTrimDom(cut);
    previewAt(drag.edge === 'start' ? cut.segments[0].start : cut.segments.at(-1).end);
  });
  const release = () => {
    if (selecting()) {
      endSelection();
      return;
    }
    if (scrubbing) {
      scrubbing = false;
      return;
    }
    if (!drag) return;
    const done = drag;
    $$('.trim-handle.dragging, .trim-blank.dragging').forEach(el => el.classList.remove('dragging'));
    track.classList.remove('dragging');
    drag = null;
    if (done.kind === 'blank') {
      if (!done.moved) toggleBlankAt(done.index);
      else applyBlanks(cut, moveBlankEdge(done.original, done.index, done.edge, done.time, state.words, done.bounds), done.bounds);
      return;
    }
    if (done.moved) commitTrim(cut);
  };
  track.addEventListener('pointerup', release);
  track.addEventListener('pointercancel', release);
  // La molette garde son ancre sous le pointeur : le temps pointé ne bouge pas.
  track.addEventListener(
    'wheel',
    event => {
      const view = state.trim;
      if (!view) return;
      event.preventDefault();
      const rect = track.getBoundingClientRect(),
        bounds = viewBounds(),
        part = clamp((event.clientX - rect.left) / rect.width, 0, 1),
        sideways = Math.abs(event.deltaX) > Math.abs(event.deltaY);
      applyView(
        sideways
          ? panView(view, (event.deltaX / rect.width) * (view.end - view.start), bounds)
          : zoomView(view, part, wheelDelta(event), bounds, event.ctrlKey),
        WAVE_DELAY,
      );
    },
    { passive: false },
  );
  const resize = () => {
    if (!alive()) {
      window.removeEventListener('resize', resize);
      return;
    }
    if (state.trim?.peaks) drawWave($('#trim-wave'), state.trim.peaks);
  };
  window.addEventListener('resize', resize);
  setupZoomViews(alive, seekTo);
  video.preservesPitch = true;
  video.playbackRate = state.speed;
  state._trim = { video, toggle, seek, token };
}

export function trimController() {
  const controller = state._trim;
  return controller && controller.token === state.stageToken && document.body.contains(controller.video) ? controller : null;
}

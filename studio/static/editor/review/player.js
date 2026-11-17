// Lecteur de la relecture : le MP4 rendu, la timeline des retours et la barre de transport.
import { $, $$, clamp, esc, ICONS, storage } from '../../core/dom.js';
import { safeSpeed, speedLabel } from '../../core/speed.js';
import { versionUrl } from '../../core/montage.js';
import { state } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { reviewVersion, tc } from './data.js';
import { trimController } from '../montage/stage.js';
import { drawToolsHtml, resizeDrawing } from './draw.js';
import { updateComposerTime } from './retours.js';
import { highlightTranscript } from './transcript.js';

export const SOUND_ICONS = {
  on: '<svg viewBox="0 0 20 20"><path d="M4 8h3l4-3v10l-4-3H4zM14 7.5a3.5 3.5 0 0 1 0 5"/></svg>',
  off: '<svg viewBox="0 0 20 20"><path d="M4 8h3l4-3v10l-4-3H4zM14 8l4 4m0-4-4 4"/></svg>',
  draw: '<svg viewBox="0 0 20 20"><path d="M3 15c4-1 5-9 8-9s2 5 5 4"/><circle cx="16" cy="9.5" r="1.4"/></svg>',
  back: '<svg viewBox="0 0 20 20"><path d="M10 5a5 5 0 1 1-4.9 6"/><path d="M10 2.5 10 7.5 6 5z"/></svg>',
  forward: '<svg viewBox="0 0 20 20"><path d="M10 5a5 5 0 1 0 4.9 6"/><path d="M10 2.5 10 7.5 14 5z"/></svg>',
};

// Le studio de référence saute de 5 s de part et d'autre du timecode.
export const SKIP_SECONDS = 5;

export function playerHtml() {
  const version = reviewVersion();
  return (
    `<div class="review-stage">` +
    `<div class="review-video" id="review-video-box">` +
    `<video id="review-video" src="${esc(versionUrl(version))}" playsinline preload="auto"></video>` +
    `<canvas id="review-canvas" hidden></canvas>` +
    `<button class="trim-overlay" id="review-overlay" type="button" aria-label="Lecture">${ICONS.play}</button>` +
    `</div>` +
    drawToolsHtml() +
    `<div class="review-track" id="review-track" title="Timeline du reel">` +
    `<div class="review-played" id="review-played"></div>` +
    `<div class="review-marks" id="review-marks"></div>` +
    `<div class="review-playhead" id="review-playhead"></div></div>` +
    `<div class="review-transport">` +
    `<button class="play-button" id="review-play" type="button" aria-label="Lecture">${ICONS.play}</button>` +
    `<button class="skip-button" type="button" data-review-skip="-${SKIP_SECONDS}"` +
    ` aria-label="Reculer de ${SKIP_SECONDS} secondes" title="Reculer de ${SKIP_SECONDS} s">${SOUND_ICONS.back}</button>` +
    `<button class="skip-button" type="button" data-review-skip="${SKIP_SECONDS}"` +
    ` aria-label="Avancer de ${SKIP_SECONDS} secondes" title="Avancer de ${SKIP_SECONDS} s">${SOUND_ICONS.forward}</button>` +
    `<span class="timecode"><strong id="review-now">00:00.00</strong> / <span id="review-total">${tc(version?.duration || 0)}</span></span>` +
    `<div class="review-tools">` +
    `<button class="pill" type="button" data-review-draw aria-pressed="false">${SOUND_ICONS.draw} Dessiner <kbd>P</kbd></button>` +
    `<button class="pill${state.speed === 1 ? '' : ' on'}" type="button" data-review-speed ` +
    `title="Vitesse de lecture : 1×, 1,2×, 1,5×, 2×">${speedLabel(state.speed)}</button>` +
    `<button class="pill" type="button" data-review-mute aria-pressed="false" aria-label="Couper le son">${SOUND_ICONS.on}</button>` +
    `</div></div></div>`
  );
}

export function renderMarks() {
  const marks = $('#review-marks'),
    version = reviewVersion();
  if (!marks || !version) return;
  const duration = Number(version.duration) || 1;
  marks.innerHTML = state.review.retours
    .map(item => {
      const left = clamp((item.start / duration) * 100, 0, 100),
        selected = item.id === state.review.selected ? ' on' : '',
        done = item.resolved ? ' done' : '';
      if (item.end === null || item.end === undefined)
        return `<i class="review-mark dot${done}${selected}" style="left:${left}%" data-goto-retour="${esc(item.id)}"></i>`;
      const width = clamp(((item.end - item.start) / duration) * 100, 0.6, 100 - left);
      return `<i class="review-mark bar${done}${selected}" style="left:${left}%;width:${width}%" data-goto-retour="${esc(item.id)}"></i>`;
    })
    .join('');
}

export function updatePlayhead(time) {
  const version = reviewVersion(),
    duration = Number(version?.duration) || 1;
  state.review.time = time;
  const percent = `${clamp((time / duration) * 100, 0, 100)}%`;
  const head = $('#review-playhead');
  if (head) head.style.left = percent;
  const played = $('#review-played');
  if (played) played.style.width = percent;
  const now = $('#review-now');
  if (now) now.textContent = tc(time);
  if (!state.review.selection) updateComposerTime();
  highlightTranscript(time);
}

export function reviewController() {
  const controller = state._review;
  return controller && controller.token === state.stageToken && document.body.contains(controller.video) ? controller : null;
}

export function setupPlayer(token) {
  const video = $('#review-video'),
    track = $('#review-track');
  if (!video || !track) return;
  let frame = 0;
  const alive = () => token === state.stageToken && document.body.contains(video);
  const setIcons = () => {
    const icon = video.paused ? ICONS.play : ICONS.pause;
    $('#review-play').innerHTML = icon;
    $('#review-overlay').innerHTML = icon;
    $('#review-overlay').classList.toggle('hidden', !video.paused);
  };
  const tick = () => {
    if (!alive()) {
      video.pause();
      return;
    }
    updatePlayhead(video.currentTime);
    if (!video.paused) frame = requestAnimationFrame(tick);
  };
  const seek = time => {
    video.currentTime = clamp(time, 0, Number(reviewVersion()?.duration) || video.duration || 0);
    updatePlayhead(video.currentTime);
  };
  // Dessiner suppose une image fixe : la lecture s’arrête dès qu’on prend le crayon.
  const toggle = () => {
    if (!video.paused) {
      video.pause();
      return;
    }
    if (state.review.drawing) return;
    video.play().catch(() => toast('La lecture a été bloquée par le navigateur. Reclique sur lecture.', { kind: 'error' }));
  };
  video.preservesPitch = true;
  video.playbackRate = state.speed;
  video.muted = state.review.muted;
  video.addEventListener('loadedmetadata', () => {
    updatePlayhead(video.currentTime);
    resizeDrawing();
  });
  video.addEventListener('play', () => {
    setIcons();
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(tick);
  });
  video.addEventListener('pause', () => {
    setIcons();
    cancelAnimationFrame(frame);
    updatePlayhead(video.currentTime);
  });
  video.addEventListener('seeked', () => updatePlayhead(video.currentTime));
  video.addEventListener('click', toggle);
  $('#review-overlay').addEventListener('click', toggle);
  $('#review-play').addEventListener('click', toggle);
  let scrubbing = false;
  const timeAt = clientX => {
    const rect = track.getBoundingClientRect();
    return clamp((clientX - rect.left) / rect.width, 0, 1) * (Number(reviewVersion()?.duration) || 0);
  };
  track.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    track.setPointerCapture(event.pointerId);
    scrubbing = true;
    video.pause();
    seek(timeAt(event.clientX));
  });
  track.addEventListener('pointermove', event => {
    if (scrubbing) seek(timeAt(event.clientX));
  });
  const release = () => {
    scrubbing = false;
  };
  track.addEventListener('pointerup', release);
  track.addEventListener('pointercancel', release);
  const resize = () => {
    if (!alive()) {
      window.removeEventListener('resize', resize);
      return;
    }
    resizeDrawing();
  };
  window.addEventListener('resize', resize);
  state._review = { video, toggle, seek, token };
  renderMarks();
  updatePlayhead(0);
}

// La vitesse est la même partout : les deux lecteurs et les deux pastilles suivent, et le son
// garde sa hauteur. Le choix reste d’une étape à l’autre et d’un projet à l’autre.
export function setSpeed(rate) {
  const speed = safeSpeed(rate);
  state.speed = speed;
  storage.set('atelier:speed', String(speed));
  for (const video of [reviewController()?.video, trimController()?.video]) {
    if (!video) continue;
    video.preservesPitch = true;
    video.playbackRate = speed;
  }
  for (const button of $$('[data-review-speed], [data-trim-speed]')) {
    button.textContent = speedLabel(speed);
    button.classList.toggle('on', speed !== 1);
  }
}

export function setMuted(muted) {
  state.review.muted = muted;
  const controller = reviewController();
  if (controller) controller.video.muted = muted;
  const button = $('[data-review-mute]');
  if (button) {
    button.innerHTML = muted ? SOUND_ICONS.off : SOUND_ICONS.on;
    button.classList.toggle('on', muted);
    button.setAttribute('aria-pressed', String(muted));
  }
}

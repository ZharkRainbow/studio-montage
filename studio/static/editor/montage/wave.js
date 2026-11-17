// Forme d’onde de la timeline : la fenêtre visible est demandée au serveur, puis dessinée.
// La réponse porte aussi les mots recalés sur le son : ce sont eux qui aimantent les bords des blancs.
import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { state } from '../../core/state.js';

export async function loadWaveform() {
  const w = state.trim,
    canvas = $('#trim-wave');
  if (!w || !canvas || !state.project) return;
  if (w.peaks) {
    drawWave(canvas, w.peaks);
    return;
  }
  const key = `${state.project.id}:${w.start.toFixed(2)}:${w.end.toFixed(2)}`;
  let data = state.waveCache.get(key);
  if (!data) {
    canvas.classList.add('loading');
    try {
      data = await api(
        `/api/projects/${encodeURIComponent(state.project.id)}/waveform?start=${w.start.toFixed(2)}` + `&end=${w.end.toFixed(2)}&buckets=900`,
      );
      state.waveCache.set(key, data);
    } catch {
      canvas.classList.remove('loading');
      canvas.classList.add('failed');
      return;
    }
  }
  if (state.trim !== w) return;
  if (Array.isArray(data.words)) state.words = data.words;
  if (state.waveCache.size > 48) state.waveCache.delete(state.waveCache.keys().next().value);
  w.peaks = data.peaks;
  const current = $('#trim-wave');
  if (current) {
    current.classList.remove('loading');
    drawWave(current, w.peaks);
  }
}

export function drawWave(canvas, peaks) {
  const rect = canvas.getBoundingClientRect(),
    dpr = Math.min(devicePixelRatio || 1, 2);
  if (!rect.width || !peaks?.length) return;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext('2d'),
    mid = canvas.height / 2,
    step = canvas.width / peaks.length,
    loudest = Math.max(0.04, ...peaks);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'rgba(244, 196, 116, .78)';
  peaks.forEach((peak, index) => {
    const height = Math.max(dpr, Math.pow(peak / loudest, 0.75) * canvas.height * 0.86);
    ctx.fillRect(index * step, mid - height / 2, Math.max(dpr, step * 0.72), height);
  });
}

// Petites aides DOM, icônes, formats de temps et stockage local.

export const $ = (selector, root = document) => root.querySelector(selector);

export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export const ICONS = {
  play: '<svg viewBox="0 0 20 20"><path d="m7 5 8 5-8 5z"/></svg>',
  pause: '<svg viewBox="0 0 20 20"><path d="M7 5v10M13 5v10"/></svg>',
  plus: '<svg viewBox="0 0 20 20"><path d="M10 4v12M4 10h12"/></svg>',
  wand: '<svg viewBox="0 0 20 20">' + '<path d="m4 16 9-9m-7 1 1-2 2-1-2-1-1-2-1 2-2 1 2 1 1 2Zm8-3 1-2 2-1-2-1-1-2-1 2-2 1 2 1 ' + '1 2Z"/></svg>',
  check: '<svg viewBox="0 0 20 20"><path d="m4 10 4 4 8-8"/></svg>',
  download: '<svg viewBox="0 0 20 20"><path d="M10 3v10m-4-4 4 4 4-4M4 16h12"/></svg>',
  film: '<svg viewBox="0 0 20 20"><rect x="3" y="4" width="14" height="12" rx="2"/>' + '<path d="M3 8h14M7 4v4m6-4v4M7 12v4m6-4v4M3 12h14"/></svg>',
  captions:
    '<svg viewBox="0 0 20 20"><rect x="2.5" y="4" width="15" height="12" rx="2"/>' + '<path d="M8.5 8a2 2 0 1 0 0 4m5-4a2 2 0 1 0 0 4"/></svg>',
  pencil: '<svg viewBox="0 0 20 20"><path d="m12.5 4.5 3 3L7 16H4v-3l8.5-8.5Zm-2 2 3 3"/></svg>',
  copy:
    '<svg viewBox="0 0 20 20"><rect x="7" y="7" width="9" height="9" rx="1.5"/>' +
    '<path d="M13 7V5.5A1.5 1.5 0 0 0 11.5 4h-6A1.5 1.5 0 0 0 4 5.5v6A1.5 1.5 0 0 0 5.5 13H7"/></svg>',
  trash: '<svg viewBox="0 0 20 20">' + '<path d="M4 6h12M8 6V4.5h4V6m-6.5 0 .8 9.5h7.4l.8-9.5M8.5 9v4m3-4v4"/></svg>',
  x: '<svg viewBox="0 0 20 20"><path d="m5.5 5.5 9 9M14.5 5.5l-9 9"/></svg>',
  folder:
    '<svg viewBox="0 0 20 20">' +
    '<path d="M3 6.2A1.7 1.7 0 0 1 4.7 4.5h3.1l1.8 1.9h5.7A1.7 1.7 0 0 1 17 8.1v6.2a1.7 1.7 0 ' +
    '0 1-1.7 1.7H4.7A1.7 1.7 0 0 1 3 14.3Z"/></svg>',
  more: '<svg viewBox="0 0 20 20"><path d="M5 10h.01M10 10h.01M15 10h.01" stroke-width="2.6"/></svg>',
  star: '<svg viewBox="0 0 20 20">' + '<path d="m10 3.3 2 4.2 4.6.6-3.4 3.2.9 4.5L10 13.6l-4.1 2.2.9-4.5-3.4-3.2 4.6-.6Z"/></svg>',
  open:
    '<svg viewBox="0 0 20 20">' +
    '<path d="M8 5H5.5A1.5 1.5 0 0 0 4 6.5v8A1.5 1.5 0 0 0 5.5 16h8a1.5 1.5 0 0 0 ' +
    '1.5-1.5V12M11 4h5v5M16 4l-7 7"/></svg>',
  back: '<svg viewBox="0 0 20 20"><path d="M12 4.5 6.5 10l5.5 5.5"/></svg>',
  chevronRight: '<svg viewBox="0 0 20 20" style="width:14px;color:var(--dim)"><path d="m8 5 5 5-5 5"/></svg>',
  grid:
    '<svg viewBox="0 0 20 20"><rect x="3" y="3.5" width="5.5" height="5.5" rx="1.3"/>' +
    '<rect x="11.5" y="3.5" width="5.5" height="5.5" rx="1.3"/>' +
    '<rect x="3" y="11" width="5.5" height="5.5" rx="1.3"/>' +
    '<rect x="11.5" y="11" width="5.5" height="5.5" rx="1.3"/></svg>',
  home: '<svg viewBox="0 0 20 20">' + '<path d="M3.5 9 10 3.5 16.5 9v7a1 1 0 0 1-1 1h-3.5v-4.5h-4V17H4.5a1 1 0 0 1-1-1Z"/></svg>',
  search: '<svg viewBox="0 0 20 20"><circle cx="9" cy="9" r="5.5"/><path d="m13.2 13.2 3.3 3.3"/></svg>',
  clock: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="6.5"/><path d="M10 6.5V10l2.5 1.5"/></svg>',
  alert: '<svg viewBox="0 0 20 20"><path d="M10 3.5 17 16H3Z"/><path d="M10 8.5v3.2M10 13.8h.01"/></svg>',
  sparkle:
    '<svg viewBox="0 0 20 20">' + '<path d="M10 3v3M10 14v3M3 10h3M14 10h3M5.3 5.3l2 2M12.7 12.7l2 2M14.7 5.3l-2 2M7.3 ' + '12.7l-2 2"/></svg>',
  layers: '<svg viewBox="0 0 20 20"><path d="m10 3.5 7 3.8-7 3.8-7-3.8Z"/><path d="m3 11 7 3.8 7-3.8"/></svg>',
  paperclip:
    '<svg viewBox="0 0 20 20">' +
    '<path d="M13.4 9.3 8.6 14a2.6 2.6 0 0 1-3.7-3.7l5.6-5.6a3.4 3.4 0 0 1 4.8 4.8l-5.6 5.6"/></svg>',
  eye: '<svg viewBox="0 0 20 20"><path d="M2.5 10S5.3 4.5 10 4.5 17.5 10 17.5 10 14.7 15.5 10 15.5 2.5 10 2.5 10Z"/><circle cx="10" cy="10" r="2.3"/></svg>',
  eyeOff:
    '<svg viewBox="0 0 20 20"><path d="M3 3l14 14M8.2 5a8 8 0 0 1 1.8-.5c4.7 0 7.5 5.5 7.5 5.5a13 13 0 0 1-2.1 2.8"/>' +
    '<path d="M5.3 6.6A13 13 0 0 0 2.5 10s2.8 5.5 7.5 5.5a7 7 0 0 0 3.2-.8"/></svg>',
  crop: '<svg viewBox="0 0 20 20"><path d="M6 3v11h11M3 6h11v11"/></svg>',
  gear:
    '<svg viewBox="0 0 20 20"><path d="M3 6h6.5M13.5 6H17M3 14h2.5M9.5 14H17"/>' +
    '<circle cx="11.5" cy="6" r="2"/><circle cx="7.5" cy="14" r="2"/></svg>',
  refresh:
    '<svg viewBox="0 0 20 20"><path d="M16 4.5v4h-4M4 15.5v-4h4"/>' + '<path d="M15.4 8.5A6 6 0 0 0 4.7 6.2M4.6 11.5a6 6 0 0 0 10.7 2.3"/></svg>',
  terminal: '<svg viewBox="0 0 20 20"><rect x="2.5" y="3.5" width="15" height="13" rx="2"/>' + '<path d="m6 8 2.5 2L6 12M10.5 12.5H14"/></svg>',
  scissors:
    '<svg viewBox="0 0 20 20"><circle cx="5.5" cy="6" r="2.2"/>' +
    '<circle cx="5.5" cy="14" r="2.2"/><path d="M7.4 7.2 16 13.5M7.4 12.8 16 6.5"/></svg>',
  chevronLeft: '<svg viewBox="0 0 20 20"><path d="M12 5 7 10l5 5"/></svg>',
  chevronsLeft: '<svg viewBox="0 0 20 20"><path d="M10 5 5 10l5 5M15 5l-5 5 5 5"/></svg>',
  chevronRightSm: '<svg viewBox="0 0 20 20"><path d="m8 5 5 5-5 5"/></svg>',
  chevronsRight: '<svg viewBox="0 0 20 20"><path d="m5 5 5 5-5 5M10 5l5 5-5 5"/></svg>',
  zoomIn: '<svg viewBox="0 0 20 20"><circle cx="9" cy="9" r="5.5"/><path d="M9 6.8v4.4M6.8 9h4.4m2 4.2 3.3 3.3"/></svg>',
  zoomOut: '<svg viewBox="0 0 20 20"><circle cx="9" cy="9" r="5.5"/><path d="M6.8 9h4.4m1.8 4.2 3.3 3.3"/></svg>',
  fitWidth: '<svg viewBox="0 0 20 20"><path d="M3 5v10M17 5v10M6 10h8m-8 0 2.5-2.5M6 10l2.5 2.5M14 10l-2.5-2.5M14 10l-2.5 2.5"/></svg>',
};

export function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

export function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function uid(prefix = 'id') {
  return `${prefix}-` + (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`) + ``;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function fmtTime(seconds, precise = false) {
  const value = Math.max(0, Number(seconds) || 0);
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = value % 60;
  return (
    `${h ? `${String(h).padStart(2, '0')}:` : ''}${String(m).padStart(2, '0')}` +
    `:` +
    (precise ? s.toFixed(1).padStart(4, '0') : String(Math.floor(s)).padStart(2, '0')) +
    ``
  );
}

// Un bouton occupé garde ses enfants de côté : son icône et sa pastille ne sont pas du texte.
const busyContent = new WeakMap();

export function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    busyContent.set(button, [...button.childNodes]);
    button.disabled = true;
    button.replaceChildren($('#spinner-template').content.cloneNode(true), document.createTextNode(label ? ` ${label}` : ''));
  } else {
    button.disabled = false;
    const kept = busyContent.get(button);
    busyContent.delete(button);
    if (kept) button.replaceChildren(...kept);
    else if (label) button.textContent = label;
  }
}

export const storage = {
  get(key, fallback) {
    try {
      return localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* storage can be blocked */
    }
  },
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* storage can be blocked */
    }
  },
};

export function normalizeText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

export function fmtDuration(seconds) {
  const s = Math.round(Number(seconds) || 0);
  if (!s) return '';
  const h = Math.floor(s / 3600),
    m = Math.floor((s % 3600) / 60),
    r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}

/* ---------- Project lifecycle ---------- */
export const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

export function plural(count, word) {
  const n = Number(count) || 0;
  return `${n} ${word}${n > 1 ? 's' : ''}`;
}

export function relTime(iso) {
  const time = Date.parse(iso);
  if (!time) return '';
  const seconds = (Date.now() - time) / 1000;
  if (seconds < 60) return 'modifié à l’instant';
  if (seconds < 3600) return `modifié il y a ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `modifié il y a ${Math.floor(seconds / 3600)} h`;
  if (seconds < 172800) return 'modifié hier';
  return `modifié le ` + new Date(time).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }) + ``;
}

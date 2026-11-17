// Notifications et boîtes de dialogue.
import { $, esc, ICONS } from './dom.js';

/* ---------- Toasts ---------- */
export const TOAST_ICONS = {
  success: '<svg viewBox="0 0 20 20"><path d="m5 10.5 3.2 3L15 6.5"/></svg>',
  error: '<svg viewBox="0 0 20 20"><path d="M10 5.5v5.5M10 14.5h.01"/></svg>',
  info: '<svg viewBox="0 0 20 20"><path d="M10 9v5.5M10 5.5h.01"/></svg>',
};

export function toast(message, { kind = 'info', timeout, action, group } = {}) {
  const root = $('#toasts');
  if (!root || !message) return () => {};
  // A newer message of the same group replaces the previous one instead of stacking over the work.
  if (group) for (const existing of [...root.children]) if (existing.dataset.group === group) existing.remove();
  for (const existing of root.children) if (existing.dataset.message === message && !existing.classList.contains('leaving')) return () => {};
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.dataset.message = message;
  if (group) el.dataset.group = group;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.innerHTML =
    `<span class="toast-icon">${TOAST_ICONS[kind] || TOAST_ICONS.info}</span>` +
    `<div class="toast-text"></div>` +
    `<div class="toast-actions"` +
    `>` +
    (action ? `<button class="button ghost compact" type="button" data-toast-action>${esc(action.label)}</button>` : '') +
    `<` +
    `button class="icon-button" type="button" data-toast-close aria-label="Fermer">${ICONS.x}` +
    `</button></div>`;
  $('.toast-text', el).textContent = message;
  let timer = null;
  const close = () => {
    if (el.classList.contains('leaving')) return;
    clearTimeout(timer);
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 260);
  };
  $('[data-toast-close]', el).addEventListener('click', close);
  if (action)
    $('[data-toast-action]', el).addEventListener('click', () => {
      close();
      action.run();
    });
  root.prepend(el);
  while (root.children.length > 4) root.lastElementChild.remove();
  const duration = timeout ?? (kind === 'error' ? 8000 : action ? 6000 : 3200);
  const arm = () => {
    clearTimeout(timer);
    if (duration) timer = setTimeout(close, duration);
  };
  el.addEventListener('pointerenter', () => clearTimeout(timer));
  el.addEventListener('pointerleave', arm);
  arm();
  return close;
}

export function showNotice(message, kind = 'error', timeout = 0) {
  toast(message, { kind: kind === 'success' ? 'success' : kind, timeout: timeout || undefined });
}

export function hideNotice() {
  /* toasts dismiss themselves */
}

/* ---------- Folders ---------- */
export function promptDialog({ kicker, title, label, value = '', submit = 'Valider', maxLength = 150, hint = '' }) {
  return new Promise(resolve => {
    const dialog = $('#prompt-dialog'),
      input = $('#prompt-input'),
      aide = $('#prompt-hint');
    $('#prompt-kicker').textContent = kicker;
    $('#prompt-title').textContent = title;
    $('#prompt-label').textContent = label;
    $('#prompt-submit').textContent = submit;
    aide.textContent = hint;
    aide.hidden = !hint;
    input.maxLength = maxLength;
    input.value = value;
    dialog.returnValue = '';
    dialog.showModal();
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'default' ? input.value.trim() : null), { once: true });
  });
}

export function confirmAction(title, copy, action, { label = 'Continuer', danger = false } = {}) {
  const dialog = $('#confirm-dialog'),
    button = $('#confirm-action');
  $('#confirm-title').textContent = title;
  $('#confirm-copy').textContent = copy;
  button.textContent = label;
  button.className = `button ${danger ? 'danger-solid' : 'primary'}`;
  dialog.returnValue = '';
  dialog.showModal();
  dialog.addEventListener(
    'close',
    () => {
      if (dialog.returnValue === 'default') action();
    },
    { once: true },
  );
}

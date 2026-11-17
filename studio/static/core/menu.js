// Menu contextuel.
import { $, $$, clamp, esc, ICONS } from './dom.js';

/* ---------- Context menu ---------- */
export const menuState = { items: [], stack: [], onClose: null, anchor: null };

export function openMenu(items, anchor, { onClose } = {}) {
  closeMenu();
  Object.assign(menuState, { items, stack: [], onClose, anchor });
  renderMenu();
  positionMenu();
  setTimeout(() => document.addEventListener('pointerdown', menuOutside, true));
}

export function renderMenu() {
  const el = $('#menu'),
    level = menuState.stack.at(-1),
    items = level ? level.children : menuState.items;
  menuState.visible = items;
  el.innerHTML =
    (level
      ? `<button class="menu-item" type="button" data-menu-back>${ICONS.back}<span>` +
        `${esc(level.label)}</span></button><div class="menu-sep"></div>`
      : '') +
    items
      .map((item, index) =>
        item.separator
          ? '<div class="menu-sep"></div>'
          : item.heading
            ? `<div class="menu-heading">${esc(item.heading)}</div>`
            : item.note
              ? `<div class="menu-item static">${item.icon ? ICONS[item.icon] || '' : ''}<span>` +
                `${esc(item.label)}</span>${item.hint ? `<kbd>${esc(item.hint)}</kbd>` : ''}</div>`
              : `<button class="menu-item ${item.danger ? 'danger' : ''}" type="button" role="menuitem" ` +
                `data-menu-index="${index}" ${item.disabled ? 'disabled' : ''}>` +
                `${item.icon ? ICONS[item.icon] || '' : ''}<span>${esc(item.label)}` +
                `</span>` +
                (item.checked ? `<i class="menu-check">${ICONS.check}</i>` : '') +
                `${item.children ? ICONS.chevronRight : ''}` +
                `${item.shortcut ? `<kbd>${esc(item.shortcut)}</kbd>` : ''}</button>`,
      )
      .join('');
  el.hidden = false;
}

export function positionMenu() {
  const el = $('#menu'),
    anchor = menuState.anchor,
    margin = 8;
  el.style.left = '0px';
  el.style.top = '0px';
  const box = { width: el.offsetWidth, height: el.offsetHeight };
  let x,
    y,
    originX = 'left',
    originY = 'top';
  if (anchor instanceof Element) {
    const rect = anchor.getBoundingClientRect();
    x = rect.right - box.width;
    y = rect.bottom + 6;
    originX = 'right';
    if (x < margin) {
      x = rect.left;
      originX = 'left';
    }
    if (y + box.height > innerHeight - margin) {
      y = rect.top - box.height - 6;
      originY = 'bottom';
    }
  } else {
    x = anchor.x;
    y = anchor.y;
    if (x + box.width > innerWidth - margin) {
      x = anchor.x - box.width;
      originX = 'right';
    }
    if (y + box.height > innerHeight - margin) {
      y = anchor.y - box.height;
      originY = 'bottom';
    }
  }
  el.style.left = `${clamp(x, margin, innerWidth - box.width - margin)}px`;
  el.style.top = `${clamp(y, margin, innerHeight - box.height - margin)}px`;
  el.style.setProperty('--origin', `${originY} ${originX}`);
}

export function closeMenu() {
  const el = $('#menu');
  if (!el || el.hidden) return;
  el.hidden = true;
  el.innerHTML = '';
  document.removeEventListener('pointerdown', menuOutside, true);
  const done = menuState.onClose;
  menuState.onClose = null;
  done?.();
}

export function menuOutside(event) {
  if (!event.target.closest('#menu')) closeMenu();
}

export function onMenuClick(event) {
  if (event.target.closest('[data-menu-back]')) {
    menuState.stack.pop();
    renderMenu();
    positionMenu();
    focusMenuItem(0);
    return;
  }
  const button = event.target.closest('[data-menu-index]');
  if (!button) return;
  const item = menuState.visible[+button.dataset.menuIndex];
  if (!item || item.disabled) return;
  if (item.children) {
    menuState.stack.push(item);
    renderMenu();
    positionMenu();
    focusMenuItem(1);
    return;
  }
  closeMenu();
  item.action?.();
}

export function focusMenuItem(index) {
  const items = $$('#menu button.menu-item:not(:disabled)');
  items[clamp(index, 0, items.length - 1)]?.focus();
}

export function onMenuKey(event) {
  const items = $$('#menu button.menu-item:not(:disabled)'),
    current = items.indexOf(document.activeElement);
  if (event.key === 'Escape') {
    event.preventDefault();
    const anchor = menuState.anchor;
    closeMenu();
    if (anchor instanceof Element) anchor.focus();
  } else if (event.key === 'ArrowDown') {
    event.preventDefault();
    items[(current + 1) % items.length]?.focus();
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    items[(current - 1 + items.length) % items.length]?.focus();
  } else if (event.key === 'ArrowRight' && document.activeElement?.matches('[data-menu-index]')) {
    const item = menuState.visible[+document.activeElement.dataset.menuIndex];
    if (item?.children) {
      event.preventDefault();
      document.activeElement.click();
    }
  } else if (event.key === 'ArrowLeft' && menuState.stack.length) {
    event.preventDefault();
    menuState.stack.pop();
    renderMenu();
    positionMenu();
    focusMenuItem(0);
  } else if (event.key === 'Tab') {
    event.preventDefault();
    closeMenu();
  }
}

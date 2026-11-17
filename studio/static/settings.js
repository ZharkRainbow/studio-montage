// Page Réglages.
import { api } from './core/api.js';
import { $, esc, ICONS, plural, setBusy } from './core/dom.js';
import { state } from './core/state.js';
import { toast } from './core/toast.js';
import { renderSidebar } from './library/sidebar.js';

/* ---------- Settings ---------- */
export const SHORTCUTS = [
  ['⌘ K', 'Palette de commandes'],
  ['/', 'Rechercher un projet'],
  ['↵', 'Ouvrir le projet sélectionné'],
  ['F2', 'Renommer'],
  ['⌘ S', 'Enregistrer tout de suite'],
  ['⌘ ↵', 'Envoyer en relecture, puis valider et ouvrir le short suivant'],
  ['⌘ Z', 'Annuler'],
  ['⇧ ⌘ Z', 'Rétablir'],
  ['Espace', 'Lecture / pause'],
  ['I  O', 'Poser le début ou la fin du reel'],
  ['P', 'Dessiner sur l’image'],
  ['C', 'Écrire un retour'],
  ['Échap', 'Fermer un menu'],
];

export async function loadSetup({ announce = false, button = null } = {}) {
  setBusy(button, true, 'Diagnostic…');
  try {
    const [setup, diagnostics] = await Promise.all([api('/api/setup'), api('/api/diagnostics').catch(() => state.diagnostics)]);
    state.setup = setup;
    state.diagnostics = diagnostics;
    renderSidebar();
    if (state.route?.name === 'settings' && !state.project) renderSettings();
    if (announce)
      toast(
        setup.ready === setup.required
          ? 'Diagnostic à jour : tout est prêt.'
          : `Diagnostic à jour : ${plural(setup.required - setup.ready, 'élément')} à installer.`,
        { kind: setup.ready === setup.required ? 'success' : 'info' },
      );
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    setBusy(button, false, 'Relancer le diagnostic');
  }
}

export function copyValue(key) {
  const setup = state.setup || {};
  if (key === 'prompt') return [setup.prompt, 'Prompt d’installation'];
  if (key === 'script') return [setup.script, 'Script d’installation'];
  if (key === 'data-dir') return [setup.data_dir, 'Chemin'];
  const [kind, id] = key.split(':'),
    item = (setup.requirements || []).find(entry => entry.id === id);
  if (kind === 'install') return [item?.install, `Commande ${item?.label || ''}`.trim()];
  if (kind === 'path') return [item?.path, 'Chemin'];
  return ['', ''];
}

export async function copyText(text, label = 'Texte', button = null) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = Object.assign(document.createElement('textarea'), { value: text });
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  if (button) {
    button.classList.add('copied');
    setTimeout(() => button.classList.remove('copied'), 1400);
  }
  toast(`${label} copié dans le presse-papiers.`, { kind: 'success', timeout: 2200 });
}

// Deux réglages : laisser Claude produire la V1 tout seul après chaque validation — éteint par
// défaut, parce qu'une commande qui part toute seule se décide — et le dossier des polices
// ZT Nature, dont l'encadré d'accroche a besoin.
const REGLAGE_MESSAGES = {
  production_claude: value => (value ? 'Claude produira la V1 après chaque validation.' : 'La production reste à lancer à la main.'),
  polices_dir: value => (value ? `Les polices seront cherchées dans ${value}.` : 'Les polices seront cherchées là où elles vivent sur cette machine.'),
};

export async function setReglage(key, value, input = null) {
  const previous = state.reglages?.[key];
  try {
    state.reglages = await api('/api/reglages', { method: 'PUT', body: { [key]: value } });
    toast(REGLAGE_MESSAGES[key]?.(value) || 'Réglage enregistré.', { kind: 'success', timeout: 2600 });
    if (key === 'polices_dir') await loadSetup();
  } catch (error) {
    if (input?.type === 'checkbox') input.checked = Boolean(previous);
    else if (input) input.value = previous || '';
    toast(error.message, { kind: 'error' });
  }
}

function productionCard() {
  const on = Boolean(state.reglages?.production_claude);
  return (
    `<section class="settings-card" id="reg-production"><div class="card-head"><div><h2>Production par Claude</h2>` +
    `<p>Après chaque montage validé, l’export part tout seul. Ensuite, Claude peut produire la V1 ` +
    `sans qu’on lui demande.</p></div></div>` +
    `<label class="reglage"><input type="checkbox" data-reglage="production_claude"${on ? ' checked' : ''}>` +
    `<span><b>Lancer Claude après chaque validation</b>` +
    `<small>${esc('claude -p "/montage-reels produis la V1 de <dossier du projet>"')}, journal visible dans les tâches.</small>` +
    `</span></label>` +
    `<p class="field-help">Éteint, la demande attend dans <code>a-produire</code> : le bouton « Copier la consigne ` +
    `de production » de l’étape Montage la donne à coller dans une session Claude.</p></section>`
  );
}

// L'encadré d'accroche est dessiné en ZT Nature Bold. Sur un Mac elle vit dans ~/Library/Fonts ;
// ailleurs, ou si tu la ranges autrement, ce champ dit où la chercher.
function policesCard() {
  const item = (state.setup?.requirements || []).find(entry => entry.id === 'fonts'),
    value = state.reglages?.polices_dir || '';
  return (
    `<section class="settings-card" id="reg-polices"><div class="card-head"><div><h2>Polices de l’encadré</h2>` +
    `<p>L’encadré d’accroche posé sur le montage envoyé en relecture est écrit en ZT Nature Bold.</p>` +
    `</div></div>` +
    `<label class="reglage field"><span><b>Dossier des polices</b></span>` +
    `<input type="text" spellcheck="false" data-reglage="polices_dir" value="${esc(value)}" ` +
    `placeholder="${esc(item?.path || '')}"></label>` +
    `<p class="field-help">Vide, le studio cherche les polices là où elles vivent sur cette machine. ` +
    (item?.available ? 'ZT Nature répond.' : 'ZT Nature est introuvable : pas d’encadré tant qu’elle manque.') +
    `</p></section>`
  );
}

/* La page est faite de blocs qui se suffisent. On les écrit un par un, puis on les range :
   le bandeau d'état et le bloc d'installation prennent toute la largeur, parce qu'un prompt
   de vingt lignes ne se lit pas dans une colonne étroite. Le reste tient en deux colonnes
   de hauteurs voisines, pour ne plus laisser un grand vide sous les prérequis. */

function entete(titre, chapo) {
  return `<div class="card-head"><div><h2>${titre}</h2>${chapo ? `<p>${chapo}</p>` : ''}</div></div>`;
}

function bandeau(setup) {
  const manquants = setup.required - setup.ready,
    part = setup.required ? setup.ready / setup.required : 0,
    rayon = 26,
    tour = 2 * Math.PI * rayon;
  return (
    `<section class="settings-card status-card ${manquants ? 'warn' : ''}" id="reg-diagnostic">` +
    `<div class="ready-ring" aria-hidden="true"><svg viewBox="0 0 64 64">` +
    `<circle class="track" cx="32" cy="32" r="${rayon}"/>` +
    `<circle class="bar" cx="32" cy="32" r="${rayon}" stroke-dasharray="${tour}" ` +
    `stroke-dashoffset="${tour * (1 - part)}"/></svg>` +
    `<b>${setup.ready}<small>/${setup.required}</small></b></div><div>` +
    `<h2>${manquants ? `${plural(manquants, 'élément')} à installer` : 'Cette machine est prête'}</h2>` +
    `<p>${esc(setup.machine?.system || '')} · ${esc(setup.machine?.arch || '')}` +
    (manquants ? ' · copie la commande indiquée sous chaque élément manquant.' : ' · tous les outils du studio répondent.') +
    `</p></div></section>`
  );
}

function prerequis(item) {
  const etat = item.available ? 'ok' : item.required ? 'missing' : 'optional',
    copie = `data-copy="install:${esc(item.id)}" title="Copier la commande d’installation" ` +
      `aria-label="Copier la commande ${esc(item.label)}"`;
  return (
    `<div class="req ${etat}"><span class="req-state" aria-label="${item.available ? 'Installé' : 'À installer'}">` +
    (item.available ? ICONS.check : item.required ? ICONS.alert : ICONS.sparkle) +
    `</span><div class="req-body"><div class="req-title">${esc(item.label)}` +
    `<span class="tag">${esc(item.group)}</span>${item.required ? '' : '<span class="tag">optionnel</span>'}</div>` +
    `<p class="req-why">${esc(item.why)}</p>` +
    (item.detail ? `<p class="req-detail" title="${esc(item.path || '')}">${esc(item.detail)}</p>` : '') +
    (item.available
      ? ''
      : `<div class="code-inline"><code>${esc(item.install)}</code>` +
        `<button class="icon-button tiny" type="button" ${copie}>${ICONS.copy}</button></div>`) +
    `</div>` +
    (item.available ? `<button class="icon-button" type="button" ${copie}>${ICONS.copy}</button>` : '<span></span>') +
    `</div>`
  );
}

function installCard(setup) {
  const onglet = state.installTab || 'prompt',
    texte = onglet === 'prompt' ? setup.prompt : setup.script,
    repo = setup.repository || {};
  return (
    `<section class="settings-card install-card" id="reg-installation">` +
    entete('Installer sur une autre machine',
      'Pour un nouveau Mac : colle le prompt dans Claude Code, ou lance le script dans un terminal.') +
    `<div class="segmented" role="tablist">` +
    `<button type="button" role="tab" class="${onglet === 'prompt' ? 'active' : ''}" data-action="install-tab" ` +
    `data-tab="prompt">${ICONS.sparkle} Prompt Claude Code</button>` +
    `<button type="button" role="tab" class="${onglet === 'script' ? 'active' : ''}" data-action="install-tab" ` +
    `data-tab="script">${ICONS.terminal} Script terminal</button></div>` +
    `<pre class="code-block" tabindex="0"><code>${esc(texte)}</code></pre>` +
    `<div class="install-actions"><small>Repo <b>` +
    esc((repo.url || '').replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, '')) +
    `</b> · branche <b>${esc(repo.branch || '')}</b></small>` +
    `<button class="button primary" type="button" data-copy="${onglet}">` +
    `${ICONS.copy} Copier ${onglet === 'prompt' ? 'le prompt' : 'le script'}</button></div></section>`
  );
}

function raccourcisCard() {
  return (
    `<section class="settings-card" id="reg-raccourcis">` +
    entete('Raccourcis clavier', '') +
    `<div class="shortcut-grid">` +
    SHORTCUTS.map(([touches, libelle]) =>
      `<div class="shortcut"><span>${libelle}</span><span class="keys">` +
      touches.split(' ').map(touche => `<kbd>${esc(touche)}</kbd>`).join('') +
      `</span></div>`).join('') +
    `</div></section>`
  );
}

function emplacementsCard(setup) {
  const lieux = [
    ['Projets', setup.data_dir, 'data-dir'],
    ...['whisper-model', 'fonts'].map(id => {
      const item = setup.requirements.find(entree => entree.id === id);
      return [item?.label.replace(/ large-v3-turbo/, ''), item?.path, `path:${id}`];
    }),
  ].filter(([, chemin]) => chemin);
  return (
    `<section class="settings-card" id="reg-emplacements">` +
    entete('Emplacements', 'Où le studio lit et écrit sur cette machine.') +
    lieux.map(([libelle, chemin, cle]) =>
      `<div class="location"><span>${esc(libelle)}</span><code title="${esc(chemin)}">${esc(chemin)}</code>` +
      `<button class="icon-button tiny" type="button" data-copy="${cle}" title="Copier le chemin" ` +
      `aria-label="Copier le chemin ${esc(libelle)}">${ICONS.copy}</button></div>`).join('') +
    `</section>`
  );
}

export function renderSettings() {
  const root = $('#settings-view'),
    setup = state.setup;
  document.title = 'Réglages — Atelier';
  const head =
    `<header class="lib-head"><div class="lib-title"><span class="eyebrow">Atelier</span><h1>` +
    `${ICONS.gear}Réglages</h1><p>` +
    `Tout ce qu’il faut pour faire tourner le studio, ici comme sur une autre machine.</p>` +
    `</div><div class="lib-head-actions">` +
    `<button class="button outline" type="button" data-action="refresh-setup">` +
    `${ICONS.refresh} Relancer le diagnostic</button></div></header>`;
  if (!setup) {
    root.innerHTML = `${head}<div class="settings-page"><div class="settings-card skeleton"></div>` +
      `<div class="settings-card skeleton"></div></div>`;
    loadSetup();
    return;
  }
  root.innerHTML =
    head +
    `<div class="settings-page">` +
    `<nav class="settings-toc" aria-label="Sommaire des réglages">` +
    [['reg-diagnostic', 'Diagnostic'], ['reg-installation', 'Installation'],
      ['reg-prerequis', 'Prérequis'], ['reg-production', 'Production'],
      ['reg-polices', 'Polices'], ['reg-emplacements', 'Emplacements'],
      ['reg-raccourcis', 'Raccourcis']]
      .map(([id, label]) => `<button type="button" data-settings-jump="${id}">${label}</button>`).join('') +
    `</nav>` +
    bandeau(setup) +
    installCard(setup) +
    `<div class="settings-grid"><div class="settings-col">` +
    `<section class="settings-card" id="reg-prerequis">` +
    entete('Prérequis', 'Vérifiés en direct sur cette machine.') +
    `<div class="req-list">${setup.requirements.map(prerequis).join('')}</div></section>` +
    `</div><div class="settings-col">` +
    productionCard() +
    policesCard() +
    emplacementsCard(setup) +
    `</div></div>` +
    raccourcisCard() +
    `</div>`;
  root.querySelectorAll('[data-settings-jump]').forEach(button => button.addEventListener('click', () => {
    root.querySelector(`#${button.dataset.settingsJump}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
}

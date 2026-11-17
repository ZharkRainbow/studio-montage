// Les presets : cartes avec pastilles de couleur, polices, rendu d'exemple, et l'édition simple.
import { api } from '../core/api.js';
import { $, esc } from '../core/dom.js';
import { state } from '../core/state.js';
import { openMenu } from '../core/menu.js';
import { confirmAction, promptDialog, toast } from '../core/toast.js';
import { renderSidebar } from './sidebar.js';

// Ce que la carte montre de chaque preset, bloc par bloc.
const CHAMPS = [
  ['polices', 'Polices'],
  ['couleurs', 'Couleurs'],
  ['sous_titres', 'Sous-titres'],
  ['encadre', 'Encadré'],
  ['titre', 'Titre'],
  ['son', 'Son'],
  ['image', 'Image'],
];

export async function loadPresets({ force = false } = {}) {
  if (state.presets && !force) return state.presets;
  const payload = await api('/api/bibliotheque/presets');
  state.presets = payload.presets || [];
  state.presetDefaut = payload.defaut || null;
  renderSidebar();
  return state.presets;
}

// Les couleurs du preset, sans les notes ni les sources.
function pastilles(preset) {
  const couleurs = Object.entries(preset.couleurs || {}).filter(
    ([cle, valeur]) => !cle.startsWith('_') && typeof valeur === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(valeur),
  );
  return couleurs.length
    ? `<div class="pr-dots">` +
        couleurs
          .map(([cle, valeur]) => `<i style="background:${esc(valeur)}" title="${esc(cle)} ${esc(valeur)}"></i>`)
          .join('') +
        `</div>`
    : '';
}

// L'exemple : l'encadré du preset et une ligne de sous-titres, sur fond neutre.
function exemple(preset) {
  const encadre = preset.encadre || {};
  const sousTitres = preset.sous_titres || {};
  const fond = encadre.fond || '#2322E0';
  const texte = encadre.texte || '#FFFFFF';
  const taille = Number(encadre.taille_px) || 64;
  const rayon = Number(encadre.rayon_px) || 20;
  const etiquetteFond = encadre.etiquette_fond || '#FFFFFF';
  const etiquetteTexte = encadre.etiquette_texte || fond;
  // Le rendu d'exemple est à l'échelle du 1080 de référence : tout est divisé par six.
  const e = 1 / 6;
  return (
    `<div class="pr-sample" aria-hidden="true">` +
    `<div class="pr-sample-card" style="background:${esc(fond)};color:${esc(texte)};` +
    `font-size:${(taille * e).toFixed(1)}px;border-radius:${(rayon * e).toFixed(1)}px">Une accroche d’exemple</div>` +
    `<div class="pr-sample-tag" style="background:${esc(etiquetteFond)};color:${esc(etiquetteTexte)}">(précision)</div>` +
    `<div class="pr-sample-sub" style="color:${esc(sousTitres.couleur || '#FFFFFF')}">Un sous-titre d’exemple</div>` +
    `</div>`
  );
}

// Une valeur absente n'est pas une valeur par défaut : on le dit.
function ligne(cle, valeur, bloc) {
  if (cle.startsWith('_')) return '';
  if (valeur === null || valeur === undefined) {
    const note = bloc[`_note_${cle}`];
    return `<dt>${esc(cle)}</dt><dd class="pr-null">non renseignée${note ? ` — ${esc(note)}` : ''}</dd>`;
  }
  if (typeof valeur === 'object') return `<dt>${esc(cle)}</dt><dd>${esc(JSON.stringify(valeur))}</dd>`;
  return `<dt>${esc(cle)}</dt><dd>${esc(String(valeur))}</dd>`;
}

function carte(preset, index) {
  const id = esc(preset.id);
  const defaut = state.presetDefaut === preset.id;
  const ouvert = state.presetOpen === preset.id;
  return (
    `<article class="pr-card${ouvert ? ' open' : ''}" style="--i:${index}" data-preset="${id}">` +
    `<header class="pr-head"><div class="pr-title"><strong>${esc(preset.nom || preset.id)}</strong>` +
    (defaut ? `<span class="status s-done">Mis en avant</span>` : '') +
    `</div>` +
    `<button class="icon-button" type="button" data-preset-menu="${id}" ` +
    `aria-label="Actions du preset ${esc(preset.nom || preset.id)}" aria-haspopup="menu">` +
    `<svg viewBox="0 0 20 20"><circle cx="4.5" cy="10" r="1.4"/><circle cx="10" cy="10" r="1.4"/>` +
    `<circle cx="15.5" cy="10" r="1.4"/></svg></button></header>` +
    `<p class="pr-desc">${esc(preset.description || '')}</p>` +
    pastilles(preset) +
    `<p class="pr-fonts">${esc(
      Object.entries(preset.polices || {})
        .filter(([cle, valeur]) => !cle.startsWith('_') && valeur)
        .map(([cle, valeur]) => `${cle} : ${valeur}`)
        .join(' · ') || 'polices non renseignées',
    )}</p>` +
    exemple(preset) +
    `<button class="link-button pr-toggle" type="button" data-preset-toggle="${id}" aria-expanded="${ouvert}">` +
    `${ouvert ? 'Masquer les valeurs' : 'Voir les valeurs'}</button>` +
    (ouvert
      ? `<div class="pr-values">` +
        CHAMPS.map(([cle, titre]) => {
          const bloc = preset[cle] || {};
          const lignes = Object.entries(bloc)
            .map(([k, v]) => ligne(k, v, bloc))
            .join('');
          if (!lignes) return '';
          return (
            `<section><h3>${esc(titre)}` +
            `<button class="link-button" type="button" data-preset-edit="${id}" data-bloc="${esc(cle)}">` +
            `Modifier</button></h3><dl>${lignes}</dl>` +
            (bloc._source ? `<p class="pr-source">${esc(bloc._source)}</p>` : '') +
            `</section>`
          );
        }).join('') +
        `<section><h3>Animations par défaut</h3>` +
        ((preset.animations_par_defaut || []).length
          ? `<ul class="pr-anims">` +
            preset.animations_par_defaut
              .map(
                ident =>
                  `<li><a href="#/animations">${esc(ident)}</a>` +
                  `<button class="icon-button tiny" type="button" data-preset-remove-anim="${id}" ` +
                  `data-animation-id="${esc(ident)}" aria-label="Retirer ${esc(ident)}">` +
                  `<svg viewBox="0 0 20 20"><path d="m5.5 5.5 9 9m0-9-9 9"/></svg></button></li>`,
              )
              .join('') +
            `</ul>`
          : `<p class="pr-null">aucune</p>`) +
        `</section></div>`
      : '') +
    `</article>`
  );
}

export async function renderPresets() {
  const vue = $('#presets-view');
  if (!state.presets) {
    vue.innerHTML = `<p class="lib-empty">Lecture des presets…</p>`;
    try {
      await loadPresets();
    } catch (error) {
      vue.innerHTML = `<p class="lib-empty">${esc(error.message)}</p>`;
      return;
    }
    if (state.route?.name !== 'presets') return;
  }
  vue.innerHTML =
    `<header class="lib-head"><div class="lib-title">` +
    `<span class="eyebrow">Bibliothèque</span><h1>Presets</h1>` +
    `<p>Un preset tient la charte d’un client : polices, couleurs, encadré, sous-titres. ` +
    `Les valeurs sont recopiées des références, jamais inventées : ce qui manque reste vide et le dit. ` +
    `Le schéma est décrit dans <code>docs/presets.md</code>.</p>` +
    `<p class="pr-mention">Inspiration : pas appliqué automatiquement.</p>` +
    `</div></header>` +
    ((state.presets || []).length
      ? `<div class="pr-grid">${state.presets.map(carte).join('')}</div>`
      : `<p class="lib-empty">Aucun preset pour l’instant.</p>`);
}

export async function togglePreset(id) {
  state.presetOpen = state.presetOpen === id ? null : id;
  await renderPresets();
}

export async function duplicatePreset(id) {
  const preset = (state.presets || []).find(p => p.id === id);
  if (!preset) return;
  const nom = await promptDialog({
    kicker: 'Preset',
    title: 'Dupliquer le preset',
    label: 'Nom de la copie',
    value: `${preset.nom} (copie)`,
    submit: 'Dupliquer',
  });
  if (!nom) return;
  try {
    await api('/api/bibliotheque/presets', { method: 'POST', body: { nom, depuis: id } });
    await loadPresets({ force: true });
    await renderPresets();
    toast(`Preset « ${nom} » créé.`, { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

// « Mettre en avant » ne touche a aucun projet : c'est l'ordre d'affichage de cet onglet,
// et le point de depart propose quand on duplique. Le libelle dit exactement cela.
export async function setDefaultPreset(id) {
  try {
    const payload = await api('/api/bibliotheque/presets/defaut', { method: 'POST', body: { preset_id: id } });
    state.presetDefaut = payload.defaut;
    await renderPresets();
    toast('Preset mis en avant dans cet onglet. Aucun projet ne change.', { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

// L'édition simple : une valeur à la fois, en clair, avec la possibilité de la vider.
export async function editPresetValue(id, bloc) {
  const preset = (state.presets || []).find(p => p.id === id);
  if (!preset) return;
  const valeurs = preset[bloc] || {};
  const cles = Object.keys(valeurs).filter(cle => !cle.startsWith('_'));
  if (!cles.length) return;
  const cle = await promptDialog({
    kicker: `Preset · ${bloc}`,
    title: 'Quelle valeur modifier ?',
    label: `Une de : ${cles.join(', ')}`,
    value: cles[0],
    submit: 'Continuer',
  });
  if (!cle || !cles.includes(cle)) return;
  const actuelle = valeurs[cle];
  const saisie = await promptDialog({
    kicker: `Preset · ${bloc}.${cle}`,
    title: 'Nouvelle valeur',
    label: 'Laisse vide pour marquer la valeur comme non renseignée.',
    value: actuelle === null || actuelle === undefined ? '' : String(actuelle),
    submit: 'Enregistrer',
  });
  if (saisie === null) return;
  try {
    const mis = await api(`/api/bibliotheque/presets/${encodeURIComponent(id)}`, {
      method: 'POST',
      body: { bloc, cle, valeur: saisie === '' ? null : saisie },
    });
    state.presets = (state.presets || []).map(p => (p.id === mis.id ? mis : p));
    await renderPresets();
    toast('Preset mis à jour.', { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export async function removePresetAnimation(presetId, animationId) {
  try {
    const mis = await api(`/api/bibliotheque/presets/${encodeURIComponent(presetId)}/animations`, {
      method: 'POST',
      body: { animation_id: animationId, retirer: true },
    });
    state.presets = (state.presets || []).map(p => (p.id === mis.id ? mis : p));
    await renderPresets();
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

export function deletePreset(id) {
  const preset = (state.presets || []).find(p => p.id === id);
  if (!preset) return;
  confirmAction(
    `Supprimer le preset « ${preset.nom} » ?`,
    'Cette fiche d’inspiration sera supprimée. Les projets et leurs rendus ne changent pas.',
    async () => {
      try {
        await api(`/api/bibliotheque/presets/${encodeURIComponent(id)}`, { method: 'DELETE' });
        await loadPresets({ force: true });
        await renderPresets();
        toast('Preset supprimé.', { kind: 'success' });
      } catch (error) {
        toast(error.message, { kind: 'error' });
      }
    },
    { label: 'Supprimer', danger: true },
  );
}

export function showPresetMenu(id, anchor) {
  const preset = (state.presets || []).find(p => p.id === id);
  if (!preset) return;
  openMenu(
    [
      { label: 'Dupliquer', icon: 'copy', action: () => duplicatePreset(id) },
      {
        label: 'Mettre en avant',
        icon: 'star',
        checked: state.presetDefaut === id,
        action: () => setDefaultPreset(id),
      },
      { separator: true },
      ...CHAMPS.map(([cle, titre]) => ({
        label: `Modifier ${titre.toLowerCase()}`,
        icon: 'pencil',
        action: () => editPresetValue(id, cle),
      })),
      { separator: true },
      { label: 'Supprimer', icon: 'trash', danger: true, action: () => deletePreset(id) },
    ],
    anchor,
  );
}

// Depuis un projet : une copie du preset mis en avant, nommee d'apres le projet.
//
// Un projet ne porte pas de charte. Ce qu'il garde, ce sont ses coupes, son titre, son
// accroche, ses sources et ses versions (voir `studio/store.py`) : aucune police, aucune
// couleur, aucun reglage de sous-titre. Les valeurs de style vivent dans le code. Il n'y a
// donc rien a photographier, et l'action ne pretend plus le faire : elle duplique le preset
// mis en avant pour donner un point de depart a ajuster a la main.
export async function savePresetFromProject(project) {
  const nom = await promptDialog({
    kicker: 'Preset',
    title: 'Dupliquer le preset mis en avant',
    label: 'Nom du preset',
    value: project.name || '',
    hint:
      'Un projet ne garde pas de charte : ses polices et ses couleurs viennent du code, pas de ses réglages. ' +
      'Cette copie part du preset mis en avant, à ajuster ensuite valeur par valeur.',
    submit: 'Dupliquer',
  });
  if (!nom) return;
  try {
    await api('/api/bibliotheque/presets', { method: 'POST', body: { nom, depuis: state.presetDefaut } });
    await loadPresets({ force: true });
    toast(`Preset « ${nom} » créé dans Bibliothèque, Presets. À ajuster à la main.`, { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

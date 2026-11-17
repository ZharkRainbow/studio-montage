// La bibliothèque d'animations : grille, aperçus qui tournent au survol, panneau de détail.
import { api } from '../core/api.js';
import { $, esc } from '../core/dom.js';
import { state } from '../core/state.js';
import { toast } from '../core/toast.js';
import { copyText } from '../settings.js';
import { loadPresets } from './presets.js';
import { renderSidebar } from './sidebar.js';

const APERCU = (id, fichier) =>
  `/api/bibliotheque/apercu?id=${encodeURIComponent(id)}&fichier=${encodeURIComponent(fichier)}`;

// Ce que chaque état veut dire, en clair, au survol de la pastille.
const ETATS = {
  'Validé': 'Composition en place, aperçu rendu : utilisable tel quel.',
  Prototype: 'La composition existe mais n’a pas encore été validée sur un vrai montage.',
  'À construire': 'Repérée, pas encore écrite.',
  'Média à fournir': 'Demande un détourage ou un élément filmé : rien à rendre sans lui.',
};

export async function loadAnimations({ force = false } = {}) {
  if (state.animations && !force) return state.animations;
  const payload = await api('/api/bibliotheque/animations');
  state.animations = payload.animations || [];
  state.animCategories = payload.categories || [];
  state.animCollections = payload.collections || [];
  renderSidebar();
  return state.animations;
}

function visibles() {
  const recherche = (state.animSearch || '').trim().toLowerCase();
  return (state.animations || []).filter(fiche => {
    if (state.animCategory !== 'all' && fiche.categorie !== state.animCategory) return false;
    if (state.animCollection !== 'all' && fiche.collection !== state.animCollection) return false;
    if (!recherche) return true;
    return [fiche.nom, fiche.id, fiche.description, fiche.quand_l_utiliser, fiche.categorie, fiche.collection]
      .join(' ')
      .toLowerCase()
      .includes(recherche);
  });
}

function carte(fiche, index) {
  const id = esc(fiche.id);
  const choisie = state.animSelected === fiche.id;
  // L'aperçu ne se charge qu'au survol : trente-sept vidéos qui démarrent ensemble, personne n'en veut.
  const media = fiche.apercu
    ? `<video class="an-video" muted loop playsinline preload="none" ` +
      `poster="${fiche.vignette ? APERCU(fiche.id, 'apercu.jpg') : ''}" ` +
      `data-apercu="${APERCU(fiche.id, 'apercu.mp4')}"></video>`
    : `<span class="an-vide">Pas encore d’aperçu</span>`;
  return (
    `<article class="an-card${choisie ? ' on' : ''}" style="--i:${index}" tabindex="0" ` +
    `data-animation="${id}" aria-label="${esc(fiche.nom)}">` +
    `<div class="an-thumb">${media}` +
    `<span class="an-etat e-${esc(fiche.etat.normalize('NFD').replace(/[^a-zA-Z]/g, '').toLowerCase())}" ` +
    `title="${esc(ETATS[fiche.etat] || '')}">${esc(fiche.etat)}</span></div>` +
    `<div class="an-body"><strong>${esc(fiche.nom)}</strong>` +
    `<small>${esc(fiche.collection)} · ${esc(fiche.categorie)} · ${esc(fiche.niveau)}</small></div>` +
    `</article>`
  );
}

function panneau() {
  const fiche = (state.animations || []).find(a => a.id === state.animSelected);
  if (!fiche) return '';
  const parametres = Object.entries(fiche.parametres || {});
  const presets = state.presets || [];
  return (
    `<aside class="an-detail panel" aria-label="Détail de l’animation">` +
    `<header class="an-detail-head"><span class="eyebrow">${esc(fiche.collection)}</span>` +
    `<button class="icon-button" type="button" data-animation-close aria-label="Fermer le détail">` +
    `<svg viewBox="0 0 20 20"><path d="m5.5 5.5 9 9m0-9-9 9"/></svg></button></header>` +
    `<div class="an-detail-scroll">` +
    `<div class="an-detail-media">` +
    (fiche.apercu
      ? `<video src="${APERCU(fiche.id, 'apercu.mp4')}" muted loop autoplay playsinline></video>`
      : `<span class="an-vide">Pas encore d’aperçu</span>`) +
    `</div>` +
    `<div class="an-detail-body">` +
    `<h2>${esc(fiche.nom)}</h2>` +
    `<p class="an-id"><code>${esc(fiche.id)}</code></p>` +
    `<p>${esc(fiche.description || '')}</p>` +
    (fiche.quand_l_utiliser ? `<p class="an-quand"><b>Quand s’en servir</b><br>${esc(fiche.quand_l_utiliser)}</p>` : '') +
    (parametres.length
      ? `<dl class="an-params">` +
        parametres.map(([cle, valeur]) => `<dt>${esc(cle)}</dt><dd>${esc(String(valeur))}</dd>`).join('') +
        `</dl>`
      : '') +
    (fiche.reference_image
      ? `<figure class="an-reference">` +
        `<img src="${APERCU(fiche.id, 'reference.jpg')}" alt="Image de référence de ${esc(fiche.nom)}" loading="lazy">` +
        `<figcaption>La source d’inspiration, telle quelle. L’animation la refait avec un fond neutre.</figcaption>` +
        `</figure>`
      : '') +
    `<p class="an-source">${esc(fiche.reference || '')}` +
    (fiche.duree_s ? ` · ${String(fiche.duree_s).replace('.', ',')} s` : '') +
    `</p>` +
    `<div class="an-actions">` +
    `<button class="button outline" type="button" data-animation-nom="${esc(fiche.id)}">Copier le nom</button>` +
    `<button class="button outline" type="button" data-animation-consigne="${esc(fiche.id)}">Copier la consigne</button>` +
    (presets.length
      ? `<label class="select-field"><select data-animation-preset="${esc(fiche.id)}" aria-label="Ajouter à un preset">` +
        `<option value="">Ajouter à un preset…</option>` +
        presets.map(preset => `<option value="${esc(preset.id)}">${esc(preset.nom)}</option>`).join('') +
        `</select></label>`
      : '') +
    `</div></div></div></aside>`
  );
}

export async function renderAnimations() {
  const vue = $('#animations-view');
  if (!state.animations) {
    vue.innerHTML = `<p class="lib-empty">Lecture de la bibliothèque…</p>`;
    try {
      await loadAnimations();
    } catch (error) {
      vue.innerHTML = `<p class="lib-empty">${esc(error.message)}</p>`;
      return;
    }
    if (state.route?.name !== 'animations') return;
  }
  const fiches = visibles();
  const categories = ['all', ...(state.animCategories || [])];
  const total = (state.animations || []).length;
  vue.innerHTML =
    `<header class="lib-head"><div class="lib-title">` +
    `<span class="eyebrow">Bibliothèque</span><h1>Animations</h1>` +
    `<p>${total} entrées, ${(state.animations || []).filter(a => a.apercu).length} avec un aperçu rendu. ` +
    `Les aperçus sont dessinés sur fond neutre : aucune personne réelle.</p>` +
    `</div></header>` +
    `<div class="lib-toolbar"><label class="search-field">` +
    `<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="m13.2 13.2 3.3 3.3"/></svg>` +
    `<input id="anim-search" type="search" placeholder="Rechercher une animation" autocomplete="off" ` +
    `value="${esc(state.animSearch || '')}" aria-label="Rechercher une animation"></label>` +
    `<div class="chips" role="tablist" aria-label="Filtrer par catégorie">` +
    categories
      .map(
        categorie =>
          `<button class="chip${(state.animCategory || 'all') === categorie ? ' active' : ''}" type="button" ` +
          `role="tab" aria-selected="${(state.animCategory || 'all') === categorie}" ` +
          `data-anim-category="${esc(categorie)}">${categorie === 'all' ? 'Toutes' : esc(categorie)}</button>`,
      )
      .join('') +
    `</div><div class="lib-toolbar-end"><label class="select-field">` +
    `<select id="anim-collection" aria-label="Collection"><option value="all">Toutes les collections</option>` +
    (state.animCollections || [])
      .map(
        collection =>
          `<option value="${esc(collection)}"${state.animCollection === collection ? ' selected' : ''}>` +
          `${esc(collection)}</option>`,
      )
      .join('') +
    `</select></label></div></div>` +
    `<div class="an-layout">` +
    (fiches.length
      ? `<div class="an-grid">${fiches.map(carte).join('')}</div>`
      : `<p class="lib-empty">${(state.animations || []).length ? 'Aucune animation ne correspond.' : 'Aucune animation pour l’instant.'}</p>`) +
    panneau() +
    `</div>`;

  const recherche = $('#anim-search');
  if (recherche) {
    recherche.addEventListener('input', event => {
      state.animSearch = event.target.value;
      renderAnimations();
    });
  }
  const collection = $('#anim-collection');
  if (collection) {
    collection.addEventListener('change', event => {
      state.animCollection = event.target.value;
      renderAnimations();
    });
  }
  placerPanneau();
}

// La barre d'outils est collante et passe sur deux lignes quand la fenêtre est étroite :
// le panneau de détail doit s'arrêter juste en dessous, sinon son bouton Fermer passe sous elle.
function placerPanneau() {
  const barre = $('#animations-view .lib-toolbar');
  const layout = $('#animations-view .an-layout');
  if (barre && layout) layout.style.setProperty('--an-sticky', `${Math.round(barre.offsetHeight) + 10}px`);
}

window.addEventListener('resize', () => {
  if (state.route?.name === 'animations') placerPanneau();
});

// Au survol, l'aperçu se charge puis tourne ; il s'arrête dès que la souris part.
export function animationHover(card, entre) {
  const video = card.querySelector('video[data-apercu]');
  if (!video) return;
  if (entre) {
    if (!video.src) video.src = video.dataset.apercu;
    video.play().catch(() => {});
  } else {
    video.pause();
    video.currentTime = 0;
  }
}

export function selectAnimation(id) {
  state.animSelected = state.animSelected === id ? null : id;
  renderAnimations();
  // « Ajouter à un preset » a besoin de la liste des presets : on la lit à la première ouverture.
  if (state.animSelected && !state.presets) loadPresets().then(() => renderAnimations()).catch(() => {});
}

// La consigne qu'on colle à Claude : ce qu'est l'animation, et où elle est décrite.
export async function copyAnimationConsigne(id, button) {
  const fiche = (state.animations || []).find(a => a.id === id);
  if (!fiche) return;
  const parametres = Object.entries(fiche.parametres || {})
    .map(([cle, valeur]) => `- ${cle} : ${valeur}`)
    .join('\n');
  const texte =
    `Animation « ${fiche.nom} » (${fiche.id})\n` +
    `Collection : ${fiche.collection} · Catégorie : ${fiche.categorie} · Niveau : ${fiche.niveau} · État : ${fiche.etat}\n\n` +
    `${fiche.description || ''}\n\n` +
    (fiche.quand_l_utiliser ? `Quand s'en servir : ${fiche.quand_l_utiliser}\n\n` : '') +
    (parametres ? `Paramètres :\n${parametres}\n\n` : '') +
    `Composition : bibliotheque/animations/${fiche.id}/composition/index.html\n` +
    (fiche.reference ? `Référence : ${fiche.reference}\n` : '');
  await copyText(texte, 'Consigne de l’animation', button);
}

export async function copyAnimationNom(id, button) {
  const fiche = (state.animations || []).find(a => a.id === id);
  if (fiche) await copyText(fiche.nom, 'Nom de l’animation', button);
}

export async function addAnimationToPreset(animationId, presetId, select) {
  if (!presetId) return;
  try {
    const preset = await api(`/api/bibliotheque/presets/${encodeURIComponent(presetId)}/animations`, {
      method: 'POST',
      body: { animation_id: animationId },
    });
    state.presets = (state.presets || []).map(p => (p.id === preset.id ? preset : p));
    toast(`« ${animationId} » ajoutée au preset ${preset.nom}.`, { kind: 'success' });
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    if (select) select.value = '';
  }
}

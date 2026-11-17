// La page Skills : ce qu'il faut installer à côté du studio, et comment.
//
// Le studio ne lance pas les skills. Il dit à quoi ils servent, les donne en zip, et
// donne la commande d'installation à coller dans un agent.
import { api } from '../core/api.js';
import { $, esc } from '../core/dom.js';
import { state } from '../core/state.js';
import { toast } from '../core/toast.js';
import { copyText } from '../settings.js';

function taille(octets) {
  if (octets >= 1024 * 1024) return `${(octets / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`;
  return `${Math.max(1, Math.round(octets / 1024))} Ko`;
}

function date(iso) {
  const valeur = new Date(iso);
  return Number.isNaN(valeur.getTime()) ? '' : valeur.toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' });
}

// Claude Code et Codex ne rangent pas les skills au même endroit : on donne les deux.
export function installation(id) {
  return (
    `# Claude Code\n` +
    `mkdir -p ~/.claude/skills && cd ~/.claude/skills \\\n` +
    `  && curl -fsSL "${location.origin}/api/skills/${id}.zip" -o ${id}.zip \\\n` +
    `  && unzip -o ${id}.zip && rm ${id}.zip\n\n` +
    `# Codex\n` +
    `mkdir -p ~/.codex/skills && cd ~/.codex/skills \\\n` +
    `  && curl -fsSL "${location.origin}/api/skills/${id}.zip" -o ${id}.zip \\\n` +
    `  && unzip -o ${id}.zip && rm ${id}.zip\n\n` +
    `# À coller dans l'agent ensuite :\n` +
    `# « Lis le skill ${id} et dis-moi en une phrase quand tu dois l'utiliser. »\n`
  );
}

function carte(skill) {
  return (
    `<article class="skill-card">` +
    `<div class="skill-head"><h2>${esc(skill.nom)}</h2>` +
    `<span class="skill-poids">${esc(taille(skill.octets))} · ${skill.fichiers} fichier${skill.fichiers > 1 ? 's' : ''}</span></div>` +
    (skill.role ? `<p class="skill-role">${esc(skill.role)}</p>` : '') +
    `<p class="skill-desc">${esc(skill.description)}</p>` +
    `<dl class="skill-meta">` +
    `<div><dt>Mis à jour</dt><dd>${esc(date(skill.maj))}</dd></div>` +
    `<div><dt>Demande</dt><dd>${skill.dependances.length ? esc(skill.dependances.join(', ')) : 'rien de plus'}</dd></div>` +
    `</dl>` +
    `<div class="skill-actions">` +
    `<a class="button" href="/api/skills/${encodeURIComponent(skill.id)}.zip" download>Télécharger (.zip)</a>` +
    `<button class="button ghost" type="button" data-skill-copier="${esc(skill.id)}">Copier l’installation</button>` +
    `</div></article>`
  );
}

export function renderSkills() {
  brancher();
  const skills = state.skills || [];
  $('#chantier-view').innerHTML =
    `<header class="lib-head"><div class="lib-title"><span class="eyebrow">Agents</span>` +
    `<h1>Skills</h1><p>Les skills dont le studio a besoin.</p>` +
    `</div></header>` +
    (skills.length
      ? `<div class="skill-liste">${skills.map(carte).join('')}</div>`
      : `<p class="rendu-vide">Aucun skill pour l’instant.</p>`);
}

export async function ouvrirSkills() {
  if (!state.skills) {
    try {
      const payload = await api('/api/skills');
      state.skills = payload.skills || [];
    } catch (error) {
      state.skills = [];
      toast(error.message, { kind: 'error' });
    }
  }
  renderSkills();
}

// La page écoute sa propre zone : le routeur des clics reste court.
let branche = false;
function brancher() {
  if (branche) return;
  branche = true;
  $('#chantier-view')?.addEventListener('click', event => {
    const bouton = event.target.closest('[data-skill-copier]');
    if (bouton) copyText(installation(bouton.dataset.skillCopier), 'Installation du skill', bouton);
  });
}

// Étape Montage : un fichier déjà découpé, ses bornes, son titre et son accroche.
import { $, esc, fmtDuration, fmtTime, ICONS } from '../../core/dom.js';
import { latestJob, plainJobMessage } from '../../core/jobs.js';
import { activeSource, ensureMontage, montage, montageDuration, TITLE_SECONDS } from '../../core/montage.js';
import { currentBlanks } from '../../core/blancs.js';
import { state } from '../../core/state.js';
import { diagnosticsHtml, sourcesSection } from '../sources.js';
import { emptyStage, stageToolbar } from '../shell.js';
import { renderTrimmer } from './stage.js';

export function montageMeta() {
  const cut = montage();
  if (!cut?.segments?.length) return 'Aucun fichier';
  const cuts = cut.segments.length - 1;
  return (
    `${fmtTime(montageDuration(), true)} de reel` +
    (cuts ? ` · ${cuts} coupe${cuts > 1 ? 's' : ''}` : ' · d’un seul tenant') +
    (activeSource()?.duration ? ` · fichier de ${fmtDuration(activeSource().duration)}` : '')
  );
}

export function renderMontageStage() {
  const source = activeSource(),
    cut = montage();
  stageToolbar('Montage', montageMeta());
  if (!source) {
    emptyStage(
      'Dépose la vidéo déjà découpée',
      'Un projet tient sur un seul fichier. Le studio le lit là où il est, sans jamais le copier.',
      `<button class="button primary" type="button" data-open-source>${ICONS.plus} Choisir le fichier</button>`,
    );
    return;
  }
  if (!state.project.proxy_path) {
    renderPrepStage();
    return;
  }
  ensureMontage();
  if (!cut.segments.length) cut.segments = [{ start: 0, end: Number(source.duration) || 0 }];
  renderTrimmer(cut);
}

// Le proxy 720p est la seule préparation du montage : la lecture ne touche jamais au fichier d’origine.
export function renderPrepStage() {
  const source = activeSource(),
    job = latestJob('proxy'),
    running = job && ['queued', 'running'].includes(job.state);
  $('#stage-body').innerHTML =
    `<div class="prep"><div class="prep-card">` +
    `<span class="eyebrow amber">Étape 1 · Montage</span>` +
    `<h2 id="prep-heading">${running ? 'On prépare ta vidéo' : job?.state === 'failed' ? 'La préparation a échoué' : 'Proxy de lecture'}</h2>` +
    `<p class="prep-source">${ICONS.film}<span>${esc(source?.name || '')}</span>` +
    (source?.duration ? `<b>${fmtDuration(source.duration)}</b>` : '') +
    (source?.width ? `<b>${source.width}×${source.height}</b>` : '') +
    `</p>` +
    `<ol class="prep-steps" id="prep-steps">${prepStepHtml(job)}</ol>` +
    `<p class="prep-note">${ICONS.clock} Tu peux changer de page : la préparation continue sur ta machine.</p>` +
    `</div></div>`;
  $('#transport').innerHTML = '';
  state.prepSignature = prepSignature(job);
}

function prepSignature(job) {
  return JSON.stringify([job?.state || 'todo', Math.round(job?.progress || 0), job?.message || '']);
}

function prepStepHtml(job) {
  const kind = job && ['queued', 'running', 'succeeded'].includes(job.state) ? job.state : job?.state === 'failed' ? 'failed' : 'todo';
  const progress = Math.round(job?.progress || 0);
  const text =
    kind === 'failed'
      ? job.error || job.message
      : kind === 'todo'
        ? 'Une copie légère pour lire et poser les bornes sans ralentir cette machine.'
        : kind === 'succeeded'
          ? 'Proxy prêt, ouverture du montage…'
          : plainJobMessage(job.message);
  return (
    `<li class="prep-step s-${kind === 'queued' ? 'queued' : kind}">` +
    `<span class="prep-dot">${kind === 'failed' ? ICONS.alert : kind === 'running' ? '<i class="prep-spin"></i>' : '1'}</span>` +
    `<div class="prep-body"><div class="prep-head"><strong>Proxy de lecture</strong>` +
    `<span class="prep-status">${kind === 'running' ? `${progress} %` : kind === 'queued' ? 'En attente' : kind === 'failed' ? 'Échec' : ''}` +
    `</span></div><p>${esc(text || '')}</p>` +
    (kind === 'running' || kind === 'queued' ? `<div class="prep-bar"><i style="width:${kind === 'queued' ? 0 : progress}%"></i></div>` : '') +
    (kind === 'todo' || kind === 'failed'
      ? `<div class="prep-actions"><button class="button outline compact" type="button" data-job="proxy">${ICONS.refresh} Créer le proxy</button></div>`
      : '') +
    `</div></li>`
  );
}

export function updatePrep() {
  if (!state.project || state.step !== 'montage' || !$('#prep-steps')) return;
  const job = latestJob('proxy'),
    signature = prepSignature(job);
  if (signature === state.prepSignature) return;
  state.prepSignature = signature;
  $('#prep-steps').innerHTML = prepStepHtml(job);
}

export function renderMontageInspector() {
  const cut = montage(),
    root = $('#inspector-content');
  if (!state.project.sources?.length) {
    root.innerHTML = sourcesSection() + diagnosticsHtml();
    return;
  }
  const title = cut?.title || '',
    hook = cut?.hook || '',
    blanks = currentBlanks(cut),
    coupes = blanks.filter(blank => blank.cut !== false).length;
  root.innerHTML =
    sourcesSection() +
    `<section class="section"><div class="section-title"><h3>Titre et accroche</h3>` +
    `<small>${String(TITLE_SECONDS).replace('.', ',')} s</small></div>` +
    `<label class="field"><span>Titre du reel</span>` +
    `<input data-montage-field="title" maxlength="150" value="${esc(title)}" placeholder="Systèmes &amp; talents"></label>` +
    `<label class="field"><span>Accroche</span>` +
    `<textarea data-montage-field="hook" rows="3" maxlength="300" placeholder="Ce qu’on promet dès la première seconde.">${esc(hook)}` +
    `</textarea></label>` +
    `<p class="field-help">Le titre s’affiche ${String(TITLE_SECONDS).replace('.', ',')} s au début du reel. Sa durée est fixée dans la ` +
    `compétence de montage : rien à régler ici.</p></section>` +
    `<section class="section"><div class="section-title"><h3>Résultat</h3><small>montage.json</small></div>` +
    `<div class="metric"><span>Durée du reel</span><strong>${fmtTime(montageDuration(), true)}</strong></div>` +
    `<div class="metric"><span>Morceaux gardés</span><strong>${cut?.segments?.length || 0}</strong></div>` +
    `<div class="metric"><span>Blancs coupés</span><strong>${coupes}</strong></div>` +
    `<div class="metric"><span>Blancs gardés</span><strong>${blanks.length - coupes}</strong></div>` +
    `<p class="field-help">Les bornes, le titre et l’accroche sont écrits dans le dossier du projet, lisibles par Claude.</p></section>` +
    validatedSection();
}

// Ce que « Envoyer en relecture » a produit : le MP4 dans « Montages validés », avec ou sans
// encadré d'accroche. S'y ajoute, une fois le short validé en Relecture, la demande de
// production que Claude lira.
function validatedSection() {
  const project = state.project,
    production = project.production;
  if (!project.validated_at && !project.export && !production) return '';
  const job = latestJob('relecture'),
    running = job && ['queued', 'running'].includes(job.state),
    failed = job?.state === 'failed';
  const exported = project.export || null;
  const ligne = running
    ? `<div class="metric"><span>Export</span><strong>${Math.round(job.progress || 0)} %</strong></div>`
    : failed
      ? `<div class="metric"><span>Export</span><strong class="warn">Échec</strong></div>` +
        `<p class="field-help">${esc(job.error || '')}</p>`
      : exported
        ? `<div class="metric"><span>Export</span><strong>${exported.remux ? 'copié sans ré-encodage' : 'ré-encodé'}</strong></div>` +
          `<div class="metric"><span>Encadré d’accroche</span><strong>${exported.encadre ? 'posé' : 'aucun'}</strong></div>` +
          `<p class="field-help" title="${esc(exported.path)}">${esc(exported.path)}</p>`
        : `<div class="metric"><span>Export</span><strong>À faire</strong></div>`;
  const auto = state.reglages?.production_claude;
  return (
    `<section class="section"><div class="section-title"><h3>Montage envoyé</h3>` +
    `<small>Montages validés</small></div>` +
    ligne +
    (production
      ? `<p class="field-help">La demande de production attend dans <code>a-produire</code>. ` +
        (auto ? 'Claude la prend tout seul après chaque validation.' : 'La production par Claude est éteinte dans les Réglages.') +
        `</p><div class="section-actions">` +
        `<button class="button secondary compact" type="button" data-action="copy-consigne-production">` +
        `${ICONS.copy} Copier la consigne de production</button>` +
        (auto ? '' : `<button class="link-button" type="button" data-action="start-production">Lancer la production</button>`) +
        `</div>`
      : '') +
    (exported && !running
      ? `<div class="section-actions"><button class="link-button" type="button" data-send-review>Renvoyer en relecture</button></div>`
      : '') +
    `</section>`
  );
}

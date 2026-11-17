// « Consigne pour Claude » : le texte exact à coller, relisible et modifiable avant la copie.
import { $, setBusy } from '../../core/dom.js';
import { state } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { fetchConsigne, resolveRetours } from './data.js';
import { renderRetours } from './retours.js';

export async function openConsigne(button) {
  if (!state.project) return;
  const open = state.review.retours.filter(item => !item.resolved);
  if (!open.length) return toast('Aucun retour ouvert à transmettre.', { kind: 'error' });
  setBusy(button, true, 'Préparation');
  try {
    const payload = await fetchConsigne();
    state.review.consigneIds = open.map(item => item.id);
    const count = payload.count ?? open.length;
    $('#consigne-count').textContent =
      `${count} retour${count > 1 ? 's' : ''} ouvert${count > 1 ? 's' : ''}. Relis, modifie si besoin, copie, puis colle dans Claude.`;
    $('#consigne-text').value = payload.text || '';
    const notice = $('#consigne-notice');
    notice.textContent = payload.source_notice || '';
    notice.hidden = !payload.source_notice;
    // Décochée au départ, comme dans le studio de référence : résoudre reste un geste voulu.
    $('#consigne-resolve').checked = false;
    $('#consigne-dialog').showModal();
    $('#consigne-text').setSelectionRange(0, 0);
  } catch (error) {
    toast(error.message, { kind: 'error' });
  } finally {
    setBusy(button, false, 'Copier la consigne');
  }
}

async function writeClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const field = $('#consigne-text');
    field.focus();
    field.select();
    const copied = document.execCommand?.('copy');
    field.setSelectionRange(0, 0);
    return Boolean(copied);
  }
}

export async function copyConsigne(button) {
  const text = $('#consigne-text')?.value || '';
  if (!text.trim()) return;
  setBusy(button, true, 'Copie');
  const copied = await writeClipboard(text);
  setBusy(button, false, 'Copier');
  if (!copied) return toast('Copie refusée par le navigateur. Sélectionne le texte et copie-le à la main.', { kind: 'error' });
  const resolve = $('#consigne-resolve')?.checked,
    ids = state.review.consigneIds || [];
  $('#consigne-dialog').close();
  if (!resolve || !ids.length) return toast('Consigne copiée.', { kind: 'success' });
  try {
    await resolveRetours(ids);
    renderRetours();
    const many = ids.length > 1;
    toast(`Consigne copiée. ${ids.length} retour${many ? 's' : ''} marqué${many ? 's' : ''} comme résolu${many ? 's' : ''}.`, { kind: 'success' });
  } catch (error) {
    toast(`Consigne copiée, mais les retours n’ont pas été marqués : ${error.message}`, { kind: 'error' });
  }
}

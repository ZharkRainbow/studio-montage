// Appels à l’API locale.

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

export async function api(path, options = {}) {
  const init = { ...options, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) } };
  if (init.body && typeof init.body !== 'string') init.body = JSON.stringify(init.body);
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError('Le serveur local ne répond pas. Vérifiez que le studio est lancé.', 0);
  }
  const type = response.headers.get('content-type') || '';
  const payload = type.includes('json') ? await response.json().catch(() => ({})) : await response.text();
  if (!response.ok) throw new ApiError(payload?.error || `Erreur HTTP ${response.status}`, response.status, payload);
  return payload;
}

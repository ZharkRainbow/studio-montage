// La vitesse de lecture, la même partout : le bouton tourne 1× → 1,2× → 1,5× → 2× → 1×.
// Pas de DOM ici : juste le cycle et l’affichage français, vérifiables sans navigateur.
export const SPEEDS = [1, 1.2, 1.5, 2];

export function nextSpeed(rate) {
  const index = SPEEDS.findIndex(speed => Math.abs(speed - Number(rate)) < 0.001);
  return SPEEDS[(index + 1) % SPEEDS.length];
}

export function speedLabel(rate) {
  return `${String(Number(rate)).replace('.', ',')}×`;
}

// Une vitesse relue d’un réglage : on ne garde que celles du cycle.
export function safeSpeed(value) {
  const rate = Number(value);
  return SPEEDS.find(speed => Math.abs(speed - rate) < 0.001) ?? 1;
}

// Contrôles du zoom de la timeline (studio/static/core/zoom.js) et de la vitesse (core/speed.js).
// Les deux modules sont sans DOM : on les charge tels quels et on vérifie les calculs.
//   node --test tests/js/zoom.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const load = async name => import(pathToFileURL(join(root, 'studio/static/core', name)).href);
const Z = await load('zoom.js');
const S = await load('speed.js');
const B = await load('blancs.js');

const file = { start: 0, end: 240 }; // un fichier de 4 min, un cas courant

test('100 % montre le fichier entier, 400 % en montre le quart', () => {
  assert.equal(Z.zoomPercent({ start: 0, end: 240 }, file), 100);
  assert.equal(Z.zoomPercent({ start: 30, end: 90 }, file), 400);
  assert.equal(Math.round(Z.maxZoomPercent(file)), Math.round((240 / B.VIEW_MIN) * 100));
});

test('un pourcentage donne une fenêtre, et la fenêtre redonne le pourcentage', () => {
  for (const percent of [100, 137, 250, 1000, 9000]) {
    const view = Z.viewForPercent({ start: 100, end: 140 }, percent, file);
    const wanted = Math.min(percent, Z.maxZoomPercent(file));
    assert.ok(Math.abs(Z.zoomPercent(view, file) - wanted) < wanted * 0.001, `${percent} %`);
  }
  assert.deepEqual(Z.viewForPercent({ start: 100, end: 140 }, 100, file), { start: 0, end: 240 });
});

test('le curseur est logarithmique : son milieu est la moyenne géométrique', () => {
  assert.equal(Math.round(Z.percentFromSlider(0, file)), 100);
  assert.ok(Math.abs(Z.percentFromSlider(Z.SLIDER_STEPS, file) - Z.maxZoomPercent(file)) < 1);
  const middle = Z.percentFromSlider(Z.SLIDER_STEPS / 2, file);
  assert.ok(Math.abs(middle - Math.sqrt(100 * Z.maxZoomPercent(file))) < 1);
  for (const percent of [100, 180, 600, 4000]) {
    assert.ok(Math.abs(Z.percentFromSlider(Z.sliderFromPercent(percent, file), file) - percent) < percent * 0.01);
  }
  // Un fichier plus court que la fenêtre minimale : le curseur reste au départ, sans division par zéro.
  assert.equal(Z.sliderFromPercent(400, { start: 0, end: 0.3 }), 0);
});

test('les loupes et le curseur zooment autour de la tête de lecture', () => {
  const view = { start: 0, end: 240 };
  assert.equal(Z.zoomAnchor(view, 60), 0.25);
  assert.equal(Z.zoomAnchor(view, 900), 0.5); // dehors : on zoome autour du centre
  assert.equal(Z.zoomAnchor(view, undefined), 0.5);
  const closer = Z.scaleView(view, Z.ZOOM_FACTOR, file, Z.zoomAnchor(view, 60));
  assert.ok(Math.abs(closer.end - closer.start - 240 / Z.ZOOM_FACTOR) < 0.01);
  assert.ok(Math.abs(closer.start + 0.25 * (closer.end - closer.start) - 60) < 0.01, 'le temps sous l’ancre ne bouge pas');
  const wider = Z.scaleView(closer, 1 / Z.ZOOM_FACTOR, file, 0.5);
  assert.deepEqual(wider, { start: 0, end: 240 });
});

test('on ne zoome pas plus serré que la fenêtre minimale, ni plus large que le fichier', () => {
  const tight = Z.viewForPercent({ start: 10, end: 20 }, 10_000_000, file);
  assert.ok(Math.abs(tight.end - tight.start - B.VIEW_MIN) < 0.002);
  assert.deepEqual(Z.scaleView({ start: 10, end: 20 }, 0.001, file), { start: 0, end: 240 });
  assert.equal(Z.isZoomed({ start: 0, end: 240 }, file), false);
  assert.equal(Z.isZoomed({ start: 0, end: 60 }, file), true);
  assert.equal(Z.isZoomed(null, file), false); // pas encore de fenêtre : rien n’est zoomé
});

test('le pas de la règle s’adapte au zoom, deux étiquettes restant à 70 px', () => {
  assert.equal(Z.rulerStep(240, 900), 30);
  assert.equal(Z.rulerStep(60, 900), 5);
  assert.equal(Z.rulerStep(10, 900), 1);
  assert.equal(Z.rulerStep(2, 900), 0.5);
  assert.equal(Z.rulerStep(0.4, 900), 0.1);
  assert.equal(Z.rulerStep(3600, 900), 60); // au-delà, on garde le pas le plus large
  for (const span of [0.4, 2, 10, 60, 240, 700]) {
    const step = Z.rulerStep(span, 900);
    assert.ok((step / span) * 900 >= Z.RULER_MIN_PX, `${span} s : ${step} s trop serré`);
  }
});

test('les étiquettes tombent sur des multiples du pas, en mm:ss', () => {
  const ticks = Z.rulerTicks({ start: 63, end: 123 }, 900);
  assert.deepEqual(
    ticks.map(tick => tick.time),
    [65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120],
  );
  assert.equal(ticks[0].label, '01:05');
  assert.ok(Math.abs(ticks[0].part - 2 / 60) < 0.001);
  assert.equal(Z.rulerLabel(90, 30), '01:30');
  assert.equal(Z.rulerLabel(90.5, 0.5), '01:30.5'); // sous la seconde : les dixièmes
  assert.deepEqual(Z.rulerTicks({ start: 0, end: 0 }, 900), []);
});

test('le suivi de la lecture saute d’une page, la tête à 10 % du bord gauche', () => {
  const view = { start: 60, end: 120 };
  assert.equal(Z.followView(view, 90, file), null, 'dedans : rien à faire');
  const after = Z.followView(view, 121, file);
  assert.deepEqual(after, { start: 115, end: 175 });
  const before = Z.followView(view, 59, file);
  assert.deepEqual(before, { start: 53, end: 113 });
  assert.equal(Z.followView({ start: 0, end: 240 }, 300, file), null, 'pas zoomé : la vue ne bouge pas');
  assert.deepEqual(Z.followView(view, 239, file), { start: 180, end: 240 }, 'la fin du fichier retient la vue');
});

test('la mini-barre : un cadre pour la partie visible, un clic recentre la vue', () => {
  assert.deepEqual(Z.viewFrame({ start: 60, end: 120 }, file), { left: 25, width: 25 });
  assert.deepEqual(Z.viewFrame({ start: 0, end: 240 }, file), { left: 0, width: 100 });
  assert.ok(Z.viewFrame({ start: 100, end: 100.4 }, file).width >= 0.6, 'le cadre reste attrapable');
  assert.deepEqual(Z.centerView({ start: 0, end: 60 }, 120, file), { start: 90, end: 150 });
  assert.deepEqual(Z.centerView({ start: 0, end: 60 }, 5, file), { start: 0, end: 60 });
});

test('une sélection remise dans l’ordre devient une coupe aimantée aux mots', () => {
  assert.deepEqual(Z.orderSelection(12.4, 9.2), { start: 9.2, end: 12.4 });
  assert.deepEqual(Z.orderSelection(-3, 2), { start: 0, end: 2 });
  assert.equal(Z.orderSelection(NaN, 2), null);
  const selection = Z.orderSelection(4.05, 1.9),
    words = [
      [1, 1.5],
      [4.4, 5],
    ];
  const list = B.addBlank([{ start: 2.5, end: 3, cut: false }], selection.start, selection.end, words);
  assert.deepEqual(list, [{ start: 1.62, end: 4.3, cut: true, manual: true }]);
  assert.equal(B.addBlank([], 3, 3.02), null); // une sélection trop courte ne coupe rien
});

test('la vitesse tourne 1 → 1,2 → 1,5 → 2 → 1, et s’écrit en français', () => {
  assert.deepEqual(S.SPEEDS, [1, 1.2, 1.5, 2]);
  assert.equal(S.nextSpeed(1), 1.2);
  assert.equal(S.nextSpeed(1.2), 1.5);
  assert.equal(S.nextSpeed(1.5), 2);
  assert.equal(S.nextSpeed(2), 1);
  assert.equal(S.nextSpeed(3), 1); // une valeur inconnue repart du début
  assert.equal(S.speedLabel(1.2), '1,2×');
  assert.equal(S.speedLabel(2), '2×');
  assert.equal(S.safeSpeed('1.5'), 1.5);
  assert.equal(S.safeSpeed('n’importe quoi'), 1);
});

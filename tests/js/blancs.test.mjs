// Contrôles des blancs de la timeline (studio/static/core/blancs.js).
// Le module ne touche pas au DOM : on le charge tel quel et on vérifie les calculs.
//   node --test tests/js/blancs.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const source = readFileSync(join(root, 'studio/static/core/blancs.js'), 'utf8');
const B = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const bounds = { start: 0, end: 10 };

test('les morceaux gardés sont les bornes moins les blancs coupés', () => {
  const list = [
    { start: 2, end: 3, cut: true },
    { start: 5, end: 6, cut: false },
    { start: 7, end: 8, cut: true },
  ];
  assert.deepEqual(B.segmentsFromBlanks(bounds, list), [
    { start: 0, end: 2 },
    { start: 3, end: 7 },
    { start: 8, end: 10 },
  ]);
});

test('un blanc gardé ne change rien au montage', () => {
  const list = [{ start: 2, end: 3, cut: false }];
  assert.deepEqual(B.segmentsFromBlanks(bounds, list), [{ start: 0, end: 10 }]);
});

test('un clic sur un blanc le coupe, un deuxième le garde', () => {
  let list = [{ start: 2, end: 3, cut: false }];
  list = B.toggleBlank(list, 0);
  assert.equal(list[0].cut, true);
  assert.equal(B.toggleBlank(list, 0)[0].cut, false);
});

test('un bord lâché près d’un mot s’aimante à lui, avec la marge', () => {
  const words = [
    [1, 1.5],
    [3.4, 4],
  ];
  assert.equal(B.snapToWords(words, 1.6), 1.62); // juste après la fin du mot
  assert.equal(B.snapToWords(words, 3.3), 3.3); // trop loin du mot : on ne bouge pas
  assert.equal(B.snapToWords(words, 3.45), 3.3); // juste avant le début du suivant
});

test('un bord ne traverse ni l’autre bord ni le blanc voisin', () => {
  const list = [
    { start: 1, end: 2, cut: true },
    { start: 4, end: 5, cut: true },
  ];
  assert.equal(B.moveBlankEdge(list, 1, 'start', 1.5, [])[1].start, 2);
  assert.equal(B.moveBlankEdge(list, 1, 'start', 9, [])[1].start, 5 - B.EDGE_MIN);
  assert.equal(B.moveBlankEdge(list, 0, 'end', 0.5, [])[0].end, 1 + B.EDGE_MIN);
  assert.equal(B.moveBlankEdge(list, 1, 'end', 20, [], bounds)[1].end, 10);
});

test('« Couper ici » pose une coupe et avale les blancs qu’elle touche', () => {
  const list = [{ start: 2, end: 3, cut: false }];
  const added = B.addBlank(list, 2.8, 4);
  assert.deepEqual(added, [{ start: 2, end: 4, cut: true, manual: true }]);
  assert.deepEqual(B.addBlank(list, 6, 7), [list[0], { start: 6, end: 7, cut: true, manual: true }]);
  assert.equal(B.addBlank(list, 6, 6.02), null); // trop courte pour s’entendre
});

test('la liste reste triée et sans recouvrement', () => {
  const list = B.addBlank([{ start: 5, end: 6, cut: true }], 1, 2);
  assert.deepEqual(
    list.map(blank => blank.start),
    [1, 5],
  );
  for (const [index, blank] of list.entries()) if (index) assert.ok(blank.start >= list[index - 1].end);
});

test('un vieux projet retrouve ses blancs dans ses morceaux', () => {
  const cut = {
    segments: [
      { start: 0, end: 2 },
      { start: 3, end: 10 },
    ],
  };
  assert.deepEqual(B.blanksFromSegments(cut), [{ start: 2, end: 3, cut: true }]);
  assert.deepEqual(B.trimBounds(cut), { start: 0, end: 10 });
});

test('couper un blanc collé au début ne perd pas le début du reel', () => {
  const cut = { segments: [{ start: 0.44, end: 10 }], blanks: [{ start: 0, end: 0.44, cut: true }] };
  assert.deepEqual(B.reelBounds(cut), { start: 0, end: 10 });
  const kept = B.toggleBlank(cut.blanks, 0);
  assert.deepEqual(B.segmentsFromBlanks(B.reelBounds(cut), kept), [{ start: 0, end: 10 }]);
});

test('un vieux projet sans liste de blancs montre quand même ses coupes', () => {
  const cut = { segments: [{ start: 0, end: 2 }, { start: 3, end: 10 }], blanks: [] };
  assert.deepEqual(B.currentBlanks(cut), [{ start: 2, end: 3, cut: true }]);
  assert.deepEqual(B.currentBlanks({ segments: [{ start: 0, end: 2 }], blanks: [{ start: 1, end: 1.2, cut: false }] }),
    [{ start: 1, end: 1.2, cut: false }]);
});

test('la molette zoome autour du pointeur : le temps sous la souris ne bouge pas', () => {
  const view = { start: 0, end: 10 };
  const zoomed = B.zoomView(view, 0.5, -200, { start: 0, end: 60 });
  assert.ok(zoomed.end - zoomed.start < 10);
  assert.ok(Math.abs((zoomed.start + zoomed.end) / 2 - 5) < 0.01);
  const out = B.zoomView(view, 0, 400, { start: 0, end: 60 });
  assert.ok(out.end - out.start > 10);
});

test('on ne zoome pas plus serré que le minimum, ni plus large que le fichier', () => {
  const big = { start: 0, end: 60 };
  const tight = B.zoomView({ start: 10, end: 11 }, 0.5, -5000, big);
  assert.ok(Math.abs(tight.end - tight.start - B.VIEW_MIN) < 0.002);
  const all = B.fitView({ start: -5, end: 900 }, big);
  assert.deepEqual(all, { start: 0, end: 60 });
});

test('la vue déplacée reste dans le fichier', () => {
  const big = { start: 0, end: 60 };
  assert.deepEqual(B.panView({ start: 50, end: 60 }, 30, big), { start: 50, end: 60 });
  assert.deepEqual(B.panView({ start: 10, end: 20 }, -30, big), { start: 0, end: 10 });
});

test('la molette parle en lignes ou en pages selon la souris', () => {
  assert.equal(B.wheelDelta({ deltaY: 3, deltaMode: 1 }), 48);
  assert.equal(B.wheelDelta({ deltaY: 1, deltaMode: 2 }), 400);
  assert.equal(B.wheelDelta({ deltaY: -120 }), -120);
});

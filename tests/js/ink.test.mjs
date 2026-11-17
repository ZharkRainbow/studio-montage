// Contrôles du dessin de la Relecture (studio/static/editor/review/ink.js).
// Le module est écrit pour le navigateur mais ne touche ni au DOM ni à rien d'autre : on le charge
// ici en module ES et on lui donne un contexte 2D factice qui note chaque appel.
//   node --test tests/js/ink.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const source = readFileSync(join(root, 'studio/static/editor/review/ink.js'), 'utf8');
const ink = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

// Un faux contexte 2D : il retient les ordres de dessin dans l'ordre, et les valeurs au moment de
// chaque ordre. C'est ce qui permet de vérifier qu'un texte est contouré AVANT d'être rempli.
function fakeContext() {
  const calls = [];
  const context = { lineWidth: 0, lineCap: '', lineJoin: '', miterLimit: 0, strokeStyle: '', fillStyle: '', font: '', textAlign: '', textBaseline: '' };
  const record = name =>
    (...args) =>
      calls.push({ name, args, lineWidth: context.lineWidth, strokeStyle: context.strokeStyle, fillStyle: context.fillStyle, font: context.font });
  for (const name of ['save', 'restore', 'beginPath', 'closePath', 'moveTo', 'lineTo', 'quadraticCurveTo', 'arc',
    'ellipse', 'stroke', 'fill', 'strokeRect', 'strokeText', 'fillText', 'clearRect'])
    context[name] = record(name);
  context.calls = calls;
  context.names = () => calls.map(call => call.name);
  context.of = name => calls.filter(call => call.name === name);
  return context;
}

const freeStroke = (points, width = 'moyen') => ({ kind: 'free', color: '#e9a84b', width, points });

test('les cinq outils sont là, et le feutre ouvre le dessin', () => {
  assert.deepEqual(ink.TOOLS.map(([id]) => id), ['free', 'circle', 'arrow', 'square', 'text']);
  assert.equal(ink.DEFAULT_TOOL, 'free');
  assert.equal(ink.DEFAULT_WIDTH, 'moyen');
  for (const [, label, body] of ink.TOOLS) assert.ok(label && body, 'chaque outil a un nom et une icône');
});

test('trois épaisseurs, de la plus fine à la plus épaisse', () => {
  assert.deepEqual(ink.WIDTHS.map(([id]) => id), ['fin', 'moyen', 'epais']);
  assert.deepEqual(ink.WIDTHS.map(([, label]) => label), ['Fin', 'Moyen', 'Épais']);
  const traits = ink.WIDTHS.map(([id]) => ink.lineWidthOf(id, 1080));
  const textes = ink.WIDTHS.map(([id]) => ink.textSizeOf(id, 1080));
  assert.ok(traits[0] < traits[1] && traits[1] < traits[2], `épaisseurs ${traits}`);
  assert.ok(textes[0] < textes[1] && textes[1] < textes[2], `tailles de texte ${textes}`);
});

test('une épaisseur suit la taille de l’image, et ne descend jamais sous un pixel', () => {
  assert.equal(ink.lineWidthOf('moyen', 2160), 2 * ink.lineWidthOf('moyen', 1080));
  assert.equal(ink.lineWidthOf('fin', 10), 1);
  assert.equal(ink.textSizeOf('fin', 10), 9);
  // Une épaisseur inconnue retombe sur « Moyen » au lieu de faire disparaître le trait.
  assert.equal(ink.lineWidthOf('n’importe quoi', 1080), ink.lineWidthOf('moyen', 1080));
});

test('le trait à main libre est lissé : une courbe, pas une suite d’angles', () => {
  const points = [0, 1, 2, 3, 4, 5].map(index => ({ x: 0.1 + index * 0.05, y: 0.2 + index * 0.04 }));
  const ctx = fakeContext();
  ink.paintItem(ctx, freeStroke(points), 1080, 1920);
  assert.equal(ctx.of('moveTo').length, 1);
  assert.equal(ctx.of('quadraticCurveTo').length, points.length - 2, 'une courbe par point intermédiaire');
  assert.equal(ctx.of('lineTo').length, 1, 'seul le dernier point se rejoint en ligne droite');
  assert.equal(ctx.of('stroke').length, 1);
  assert.equal(ctx.of('lineTo').length && ctx.names().indexOf('stroke') > ctx.names().indexOf('lineTo'), true);
  // La courbe passe par le milieu de deux points voisins, et s’incurve sur celui du milieu.
  const first = ctx.of('quadraticCurveTo')[0].args;
  assert.deepEqual(first.map(value => Math.round(value)), [162, 461, 189, 499]);
});

test('deux points font un segment, un seul point fait un point', () => {
  const segment = fakeContext();
  ink.paintItem(segment, freeStroke([{ x: 0.2, y: 0.2 }, { x: 0.5, y: 0.6 }]), 1000, 1000);
  assert.deepEqual(segment.of('moveTo')[0].args, [200, 200]);
  assert.deepEqual(segment.of('lineTo')[0].args, [500, 600]);
  assert.equal(segment.of('quadraticCurveTo').length, 0);

  const dot = fakeContext();
  ink.paintItem(dot, freeStroke([{ x: 0.5, y: 0.5 }]), 1000, 1000);
  assert.deepEqual(dot.of('arc')[0].args.slice(0, 3), [500, 500, ink.lineWidthOf('moyen', 1000) / 2]);
  assert.equal(dot.of('fill').length, 1);
  assert.equal(dot.of('stroke').length, 0);
});

test('un trait vide ne dessine rien', () => {
  const ctx = fakeContext();
  ink.paintItem(ctx, freeStroke([]), 1000, 1000);
  assert.deepEqual(ctx.names(), ['save', 'restore']);
});

test('le texte est contouré de sombre puis rempli de la couleur choisie', () => {
  const ctx = fakeContext();
  ink.paintItem(ctx, { kind: 'text', color: '#FAD400', width: 'epais', x: 0.1, y: 0.25, text: 'Recadre ici' }, 1080, 1920);
  const [outline] = ctx.of('strokeText');
  const [fill] = ctx.of('fillText');
  assert.ok(outline && fill, 'le texte est peint deux fois');
  assert.ok(ctx.names().indexOf('strokeText') < ctx.names().indexOf('fillText'), 'le contour passe sous le texte');
  assert.deepEqual(outline.args, ['Recadre ici', 108, 480]);
  assert.deepEqual(fill.args, ['Recadre ici', 108, 480]);
  assert.equal(fill.fillStyle, '#FAD400');
  // Le contour est sombre et assez large pour détacher le texte d'une image claire.
  assert.match(outline.strokeStyle, /^rgba\(10, 9, 8/);
  assert.ok(outline.lineWidth > 3, `contour de ${outline.lineWidth} px`);
  assert.equal(fill.font, ink.textFontOf('epais', 1080));
  assert.match(fill.font, /^600 69\.12px "ZT Nature"/);
  assert.equal(ctx.textBaseline, 'top');
});

test('le cercle, le carré et la flèche gardent leurs repères', () => {
  const box = { color: '#2322E0', width: 'moyen', x1: 0.2, y1: 0.1, x2: 0.6, y2: 0.5 };
  const circle = fakeContext();
  ink.paintItem(circle, { ...box, kind: 'circle' }, 1000, 1000);
  assert.deepEqual(circle.of('ellipse')[0].args.slice(0, 4), [400, 300, 200, 200]);

  const square = fakeContext();
  ink.paintItem(square, { ...box, kind: 'square' }, 1000, 1000);
  assert.deepEqual(square.of('strokeRect')[0].args, [200, 100, 400, 400]);

  const arrow = fakeContext();
  ink.paintItem(arrow, { ...box, kind: 'arrow' }, 1000, 1000);
  assert.deepEqual(arrow.of('moveTo')[0].args, [200, 100]);
  assert.deepEqual(arrow.of('lineTo')[0].args, [600, 500]);
  assert.equal(arrow.of('fill').length, 1, 'la pointe est remplie');
  assert.equal(arrow.of('lineTo').length, 3, 'une ligne et les deux côtés de la pointe');
});

// Le point central : la capture doit contenir exactement ce qui est tracé, à la taille de la vidéo.
test('le même tracé, peint à deux tailles, donne la même image agrandie', () => {
  const items = [
    freeStroke([{ x: 0.2, y: 0.3 }, { x: 0.4, y: 0.45 }, { x: 0.7, y: 0.5 }, { x: 0.8, y: 0.8 }]),
    { kind: 'circle', color: '#fff', width: 'fin', x1: 0.1, y1: 0.1, x2: 0.5, y2: 0.4 },
    { kind: 'text', color: '#ff4d4d', width: 'moyen', x: 0.12, y: 0.7, text: 'ici' },
  ];
  const apercu = fakeContext();
  const capture = fakeContext();
  // Le même 9:16, à l'écran puis à la résolution de la vidéo : exactement quatre fois plus grand.
  ink.paintInk(apercu, items, 270, 480);
  ink.paintInk(capture, items, 1080, 1920);
  const facteur = 4;
  assert.deepEqual(capture.names(), apercu.names(), 'les mêmes ordres de dessin, dans le même ordre');
  // Combien d'arguments de tête portent des coordonnées : le reste (angles de l'ellipse) ne bouge pas.
  const COORDS = { moveTo: 2, lineTo: 2, quadraticCurveTo: 4, strokeRect: 4, ellipse: 4, strokeText: 3, fillText: 3 };
  for (const [index, call] of capture.calls.entries()) {
    const small = apercu.calls[index];
    if (!COORDS[call.name]) continue;
    for (const [position, value] of call.args.slice(0, COORDS[call.name]).entries()) {
      if (typeof value !== 'number') continue;
      assert.ok(Math.abs(value - small.args[position] * facteur) < 0.01,
        `${call.name}[${position}] : ${value} contre ${small.args[position]} × ${facteur}`);
    }
    assert.ok(Math.abs(call.lineWidth - small.lineWidth * facteur) < 0.01, `épaisseur de ${call.name}`);
  }
});

test('ce qui vaut la peine d’être gardé', () => {
  assert.equal(ink.worthKeeping({ kind: 'circle', x1: 0.3, y1: 0.3, x2: 0.3005, y2: 0.301 }), false, 'un clic sans glisser');
  assert.equal(ink.worthKeeping({ kind: 'circle', x1: 0.3, y1: 0.3, x2: 0.42, y2: 0.38 }), true);
  assert.equal(ink.worthKeeping({ kind: 'text', text: '   ' }), false, 'un texte vide');
  assert.equal(ink.worthKeeping({ kind: 'text', text: 'Recadre' }), true);
  assert.equal(ink.worthKeeping(freeStroke([{ x: 0.5, y: 0.5 }])), true, 'un point au feutre reste un point');
  assert.equal(ink.worthKeeping(freeStroke([])), false);
  assert.equal(ink.worthKeeping(null), false);
});

test('le tremblement de la souris est filtré, le vrai mouvement non', () => {
  const points = [{ x: 0.3, y: 0.3 }];
  assert.equal(ink.pushPoint(points, { x: 0.3005, y: 0.3005 }), false);
  assert.equal(points.length, 1, 'un point collé au précédent n’entre pas');
  assert.equal(ink.pushPoint(points, { x: 0.33, y: 0.34 }), true);
  assert.deepEqual(points.at(-1), { x: 0.33, y: 0.34 });
  assert.ok(ink.MIN_STEP > 0 && ink.MIN_STEP < 0.02);
});

test('les couleurs de la charte sont gardées telles quelles', () => {
  assert.deepEqual(ink.COLORS, ['#e9a84b', '#FAD400', '#2322E0', '#ff4d4d', '#ffffff']);
});

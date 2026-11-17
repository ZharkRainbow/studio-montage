// Le dessin lui-même : les outils, les épaisseurs, les couleurs, et la peinture d’un tracé.
// Volontairement sans import ni DOM. La même fonction peint la toile affichée et le PNG joint au
// retour, et un test en Node peut l’appeler avec un contexte factice.
// Les tracés sont rangés en coordonnées normalisées (0 → 1 sur la largeur et la hauteur de l’image) :
// redimensionner la fenêtre ne décale rien, et la capture sort exacte à la résolution de la vidéo.

export const TOOLS = [
  ['free', 'Main libre', '<svg viewBox="0 0 20 20"><path d="M3 15.3c2.6-.3 2.7-8.8 5.3-8.8s1.3 5.9 3.3 5.9 2.2-3.8 5.1-5.3"/></svg>'],
  ['circle', 'Cercle', '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="6"/></svg>'],
  ['arrow', 'Flèche', '<svg viewBox="0 0 20 20"><path d="M4 16 16 4m0 0h-6m6 0v6"/></svg>'],
  ['square', 'Carré', '<svg viewBox="0 0 20 20"><rect x="4" y="4" width="12" height="12" rx="1.5"/></svg>'],
  ['text', 'Texte', '<svg viewBox="0 0 20 20"><path d="M4 5h12M10 5v10M7.5 15h5"/></svg>'],
];

// Épaisseur du trait et taille du texte, en fraction du petit côté de l’image : un trait « Moyen »
// garde la même allure sur l’aperçu de 390 px de large et dans la capture de 1080 px.
export const WIDTHS = [
  ['fin', 'Fin', 0.0045, 0.034],
  ['moyen', 'Moyen', 0.008, 0.047],
  ['epais', 'Épais', 0.0135, 0.064],
];

export const COLORS = ['#e9a84b', '#FAD400', '#2322E0', '#ff4d4d', '#ffffff'];

// Le feutre est l’outil d’ouverture : on entoure d’abord, on choisit une forme ensuite.
export const DEFAULT_TOOL = 'free';
export const DEFAULT_WIDTH = 'moyen';

// En dessous, le relevé de la souris n’est que du tremblement : le point est ignoré.
export const MIN_STEP = 0.004;

// Le texte reprend la police de l’interface, avec les mêmes replis.
const FONT = '"ZT Nature", Avenir, "Segoe UI", ui-sans-serif, system-ui, sans-serif';
// Un contour sombre sous le texte : lisible sur une image claire comme sur une image sombre.
const OUTLINE = 'rgba(10, 9, 8, .92)';

const entry = name => WIDTHS.find(([key]) => key === name) || WIDTHS[1];

export const lineWidthOf = (name, base) => Math.max(1, entry(name)[2] * base);

export const textSizeOf = (name, base) => Math.max(9, entry(name)[3] * base);

export const textFontOf = (name, base) => `600 ${textSizeOf(name, base).toFixed(2)}px ${FONT}`;

// Ajoute un point au trait en cours, sauf s’il colle au précédent. Rend vrai si le trait a bougé.
export function pushPoint(points, point) {
  const last = points.at(-1);
  if (last && Math.hypot(point.x - last.x, point.y - last.y) < MIN_STEP) return false;
  points.push(point);
  return true;
}

// Un clic sans glisser ne fait pas une forme ; au feutre, il fait un point ; un texte vide, rien.
export function worthKeeping(item) {
  if (!item) return false;
  if (item.kind === 'text') return Boolean(item.text && item.text.trim());
  if (item.kind === 'free') return (item.points || []).length >= 1;
  return Math.hypot(item.x2 - item.x1, item.y2 - item.y1) >= 0.012;
}

export function paintInk(ctx, items, width, height) {
  for (const item of items || []) paintItem(ctx, item, width, height);
}

export function paintItem(ctx, item, width, height) {
  const base = Math.min(width, height);
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = lineWidthOf(item.width, base);
  ctx.strokeStyle = item.color;
  ctx.fillStyle = item.color;
  if (item.kind === 'text') paintText(ctx, item, width, height, base);
  else if (item.kind === 'free') paintFree(ctx, item, width, height);
  else if (item.kind === 'circle') paintCircle(ctx, item, width, height);
  else if (item.kind === 'square') paintSquare(ctx, item, width, height);
  else paintArrow(ctx, item, width, height);
  ctx.restore();
}

// Le lissage : la courbe passe par le milieu de deux points voisins et s’incurve sur celui du milieu.
// C’est ce qui enlève les angles du relevé de la souris sans décaler le trait.
function paintFree(ctx, item, width, height) {
  const points = (item.points || []).map(point => ({ x: point.x * width, y: point.y * height }));
  if (!points.length) return;
  if (points.length === 1) {
    ctx.beginPath();
    ctx.arc(points[0].x, points[0].y, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let index = 1; index < points.length - 1; index++) {
    const point = points[index],
      next = points[index + 1];
    ctx.quadraticCurveTo(point.x, point.y, (point.x + next.x) / 2, (point.y + next.y) / 2);
  }
  ctx.lineTo(points.at(-1).x, points.at(-1).y);
  ctx.stroke();
}

// Le point cliqué est le coin haut-gauche du texte : c’est aussi là que se pose le champ de saisie.
function paintText(ctx, item, width, height, base) {
  const size = textSizeOf(item.width, base);
  ctx.font = textFontOf(item.width, base);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.miterLimit = 2;
  ctx.lineWidth = Math.max(2, size * 0.16);
  ctx.strokeStyle = OUTLINE;
  ctx.strokeText(item.text, item.x * width, item.y * height);
  ctx.fillText(item.text, item.x * width, item.y * height);
}

const corners = (item, width, height) => [item.x1 * width, item.y1 * height, item.x2 * width, item.y2 * height];

function paintCircle(ctx, item, width, height) {
  const [x1, y1, x2, y2] = corners(item, width, height);
  ctx.beginPath();
  ctx.ellipse((x1 + x2) / 2, (y1 + y2) / 2, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 2, 0, 0, Math.PI * 2);
  ctx.stroke();
}

function paintSquare(ctx, item, width, height) {
  const [x1, y1, x2, y2] = corners(item, width, height);
  ctx.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
}

function paintArrow(ctx, item, width, height) {
  const [x1, y1, x2, y2] = corners(item, width, height);
  const angle = Math.atan2(y2 - y1, x2 - x1),
    head = Math.max(6, ctx.lineWidth * 3.4);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - head * Math.cos(angle - 0.4), y2 - head * Math.sin(angle - 0.4));
  ctx.lineTo(x2 - head * Math.cos(angle + 0.4), y2 - head * Math.sin(angle + 0.4));
  ctx.closePath();
  ctx.fill();
}

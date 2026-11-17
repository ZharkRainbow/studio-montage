// Headless Chrome driver for the Studio's browser scenarios, with real mouse and keyboard input.
// Usage: node driver.mjs <baseUrl> <scenario.json> [outDir]
// A scenario is {"name", "path", "steps": [...]}. Expressions run in the page with
// A = window.__atelier (page opened with ?qa=1) and P() = the project as saved on the server.
// realhover poses the mouse without clicking. realclick and drag accept {"at": expr} returning client {x, y} instead of a selector;
// drag also accepts {"to": expr} for the release point. wheel takes {sel|at, dx, dy, ctrl}.
import { spawn } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, basename } from 'node:path';

const [baseUrl, scenarioFile, outDir = tmpdir()] = process.argv.slice(2);
if (!baseUrl || !scenarioFile) { console.error('usage: node driver.mjs <baseUrl> <scenario.json> [outDir]'); process.exit(64); }
const scenario = JSON.parse(readFileSync(scenarioFile, 'utf8'));
const name = scenario.name || basename(scenarioFile, '.json');
mkdirSync(outDir, { recursive: true });

const chromePath = process.env.CHROME || '/opt/google/chrome/chrome';
const freePort = port => new Promise(resolve => {
  const probe = createServer();
  probe.once('error', () => resolve(false));
  probe.once('listening', () => probe.close(() => resolve(true)));
  probe.listen(port, '127.0.0.1');
});
// Un Chrome déjà présent sur le port de débogage n'est pas forcément le nôtre : plusieurs sessions
// tournent sur cette machine. S'y attacher piloterait la page d'une autre, sur un code qui n'est
// pas celui du dépôt — c'est passé pour un échec du scénario une fois, on ne recommence pas.
let cdpPort = Number(process.env.CDP_PORT || 0);
if (cdpPort) {
  if (!(await freePort(cdpPort))) {
    console.error(`Le port de débogage ${cdpPort} est déjà occupé : il appartient sans doute à un autre Chrome.`);
    process.exit(2);
  }
} else {
  for (let candidate = 9333; candidate < 9353 && !cdpPort; candidate++) if (await freePort(candidate)) cdpPort = candidate;
  if (!cdpPort) { console.error('Aucun port de débogage libre entre 9333 et 9352.'); process.exit(2); }
}
const profile = mkdtempSync(join(tmpdir(), 'atelier-cdp-'));
const chrome = spawn(chromePath, [
  '--headless=new', `--remote-debugging-port=${cdpPort}`, `--user-data-dir=${profile}`, '--window-size=1600,1000',
  '--hide-scrollbars', '--no-first-run', '--autoplay-policy=no-user-gesture-required', '--mute-audio', 'about:blank',
], { stdio: 'ignore' });

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const logs = [];
const failures = [];
const fail = message => { failures.push(message); logs.push(`ÉCHEC ${message}`); };
const finish = code => {
  console.log(`# ${name}\n${logs.join('\n')}`);
  console.log(failures.length ? `✗ ${name} : ${failures.length} échec(s)` : `✓ ${name}`);
  try { chrome.kill('SIGKILL'); } catch { /* already gone */ }
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ }
  process.exit(code);
};
const budget = scenario.timeout ?? 240000;
const watchdog = setTimeout(() => { fail(`délai global dépassé (${Math.round(budget / 1000)} s)`); finish(2); }, budget);

let target;
for (let i = 0; i < 80 && !target; i++) {
  try { target = (await (await fetch(`http://127.0.0.1:${cdpPort}/json`)).json()).find(t => t.type === 'page'); }
  catch { await sleep(150); }
}
if (!target) { fail(`Chrome headless ne répond pas sur le port ${cdpPort}`); finish(2); }
logs.push(`Chrome headless sur le port ${cdpPort}, profil ${profile}`);

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve));
let seq = 0;
const pending = new Map();
ws.addEventListener('message', event => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  if (msg.method === 'Runtime.exceptionThrown') {
    const detail = msg.params.exceptionDetails;
    fail(`exception dans la page : ${detail.exception?.description ?? detail.text}`);
  }
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    logs.push(`console.error: ${msg.params.args.map(a => a.value ?? a.description).join(' ')}`);
  }
});
const send = (method, params = {}) => new Promise(resolve => { const n = ++seq; pending.set(n, resolve); ws.send(JSON.stringify({ id: n, method, params })); });

async function evaluate(expr) {
  const wrapped = `(async () => { const A = window.__atelier;
    const P = () => fetch('/api/projects/' + A.state.project.id).then(r => r.json());
    return (${expr}); })()`;
  const { result } = await send('Runtime.evaluate', { expression: wrapped, awaitPromise: true, returnByValue: true });
  if (result?.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result?.result?.value;
}
async function centerOf(sel, text = '', fx = 0.5, fy = 0.5) {
  return evaluate(`(() => {
    const wanted = ${JSON.stringify(text)};
    const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find(e => {
      const r = e.getBoundingClientRect();
      return r.width && r.height && (!wanted || e.textContent.includes(wanted) || (e.getAttribute('aria-label') || '').includes(wanted));
    });
    // Cliquer un bouton désactivé ne fait rien : mieux vaut échouer ici que plus loin, sans cause visible.
    if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return null;
    // Un humain fait défiler avant de cliquer : sans ça, un bouton sous la ligne de flottaison
    // reçoit un clic à des coordonnées hors écran, et le scénario échoue sans rien dire.
    const first = el.getBoundingClientRect();
    if (first.top < 0 || first.bottom > innerHeight || first.left < 0 || first.right > innerWidth) {
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
    }
    const r = el.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) return null;
    return { x: r.x + r.width * ${fx}, y: r.y + r.height * ${fy} };
  })()`);
}
const mouse = (type, x, y, buttons = 0, clickCount = 1) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', buttons, clickCount });

const KEYS = { Space: [' ', 'Space', 32], Enter: ['Enter', 'Enter', 13], Escape: ['Escape', 'Escape', 27], Tab: ['Tab', 'Tab', 9],
  ArrowLeft: ['ArrowLeft', 'ArrowLeft', 37], ArrowUp: ['ArrowUp', 'ArrowUp', 38], ArrowRight: ['ArrowRight', 'ArrowRight', 39],
  ArrowDown: ['ArrowDown', 'ArrowDown', 40], Backspace: ['Backspace', 'Backspace', 8], Delete: ['Delete', 'Delete', 46] };
async function press(spec) {
  const [keyName, ...mods] = spec.split('+').reverse();
  const modifiers = mods.reduce((m, k) => m | ({ Alt: 1, Ctrl: 2, Meta: 4, Shift: 8 }[k] || 0), 0);
  let [key, code, vk] = KEYS[keyName] || [keyName, /\d/.test(keyName) ? `Digit${keyName}` : `Key${keyName.toUpperCase()}`, keyName.toUpperCase().charCodeAt(0)];
  const printable = key.length === 1 && !(modifiers & 6);
  if (key === 'Enter') await send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: vk, modifiers, text: '\r', unmodifiedText: '\r' });
  else await send('Input.dispatchKeyEvent', { type: printable ? 'keyDown' : 'rawKeyDown', key, code, windowsVirtualKeyCode: vk, modifiers, ...(printable ? { text: key } : {}) });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk, modifiers });
}

await send('Runtime.enable'); await send('Page.enable');
await send('Page.navigate', { url: new URL(scenario.path || '/?qa=1', baseUrl).href });
await sleep(scenario.settle ?? 2500);

for (const [index, step] of scenario.steps.entries()) {
  const label = step.label ? ` (${step.label})` : '';
  try {
    if (step.wait) await sleep(step.wait);
    if (step.viewport) await send('Emulation.setDeviceMetricsOverride', { width: step.viewport[0], height: step.viewport[1], deviceScaleFactor: 1, mobile: false });
    if (step.click) {
      const ok = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(step.click)}); if (!el) return false; el.click(); return true; })()`);
      if (!ok) fail(`#${index} click ${step.click} introuvable${label}`);
    }
    if (step.realclick) {
      const { sel, text = '', at: where } = typeof step.realclick === 'string' ? { sel: step.realclick } : step.realclick;
      const at = where ? await evaluate(where) : await centerOf(sel, text);
      if (!at) fail(`#${index} realclick ${where || sel} ${text} introuvable${label}`);
      else { await mouse('mouseMoved', at.x, at.y); await mouse('mousePressed', at.x, at.y, 1); await mouse('mouseReleased', at.x, at.y); }
    }
    // La souris se pose sans cliquer : c'est le seul moyen d'éprouver un aperçu au survol.
    if (step.realhover) {
      const { sel, text = '', at: where } = typeof step.realhover === 'string' ? { sel: step.realhover } : step.realhover;
      const at = where ? await evaluate(where) : await centerOf(sel, text);
      if (!at) fail(`#${index} realhover ${where || sel} ${text} introuvable${label}`);
      else await mouse('mouseMoved', at.x, at.y);
    }
    if (step.dblclick) {
      const { sel, text = '', at: where } = typeof step.dblclick === 'string' ? { sel: step.dblclick } : step.dblclick;
      const at = where ? await evaluate(where) : await centerOf(sel, text);
      if (!at) fail(`#${index} dblclick ${where || sel} introuvable${label}`);
      else {
        await mouse('mouseMoved', at.x, at.y);
        for (const count of [1, 2]) { await mouse('mousePressed', at.x, at.y, 1, count); await mouse('mouseReleased', at.x, at.y, 0, count); }
      }
    }
    if (step.drag) {
      const { sel, at: where, to, dx = 0, dy = 0, fx = 0.5, fy = 0.5, steps = 8 } = step.drag;
      const at = where ? await evaluate(where) : await centerOf(sel, '', fx, fy);
      // « to » donne le point d'arrivée en clair : une plage de mots du transcript ne se mesure pas en pixels fixes.
      const end = at && to ? await evaluate(to) : at && { x: at.x + dx, y: at.y + dy };
      if (!at || !end) fail(`#${index} drag ${where || sel} introuvable${label}`);
      else {
        // Les modificateurs tenus pendant tout le geste : « alt », et « shift » pour sélectionner sur la piste.
        const held = (step.drag.alt ? 1 : 0) | (step.drag.shift ? 8 : 0);
        const dispatch = (type, x, y, buttons) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', buttons, clickCount: 1, modifiers: held });
        await dispatch('mouseMoved', at.x, at.y, 0); await dispatch('mousePressed', at.x, at.y, 1);
        for (let i = 1; i <= steps; i++) {
          const x = at.x + (end.x - at.x) * i / steps, y = at.y + (end.y - at.y) * i / steps;
          await dispatch('mouseMoved', x, y, 1);
          await sleep(30);
        }
        await dispatch('mouseReleased', end.x, end.y, 0);
      }
    }
    if (step.wheel) {
      const { sel, at: where, dx = 0, dy = 0, ctrl = false } = step.wheel;
      const at = where ? await evaluate(where) : await centerOf(sel);
      if (!at) fail(`#${index} wheel ${where || sel} introuvable${label}`);
      else {
        await mouse('mouseMoved', at.x, at.y);
        await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: at.x, y: at.y, deltaX: dx, deltaY: dy, modifiers: ctrl ? 2 : 0 });
      }
    }
    if (step.press) await press(step.press);
    if (step.insert) await send('Input.insertText', { text: step.insert });
    if (step.eval) logs.push(`#${index} eval${label} → ${JSON.stringify(await evaluate(step.eval))}`);
    if (step.waitFor) {
      const deadline = Date.now() + (step.timeout ?? 8000);
      let ok = false;
      while (Date.now() < deadline && !(ok = Boolean(await evaluate(step.waitFor)))) await sleep(150);
      if (!ok) fail(`#${index} attente non satisfaite${label} : ${step.waitFor}`);
    }
    if (step.assert) {
      const value = await evaluate(step.assert);
      if (value === true) logs.push(`#${index} ok${label}`);
      else fail(`#${index} assertion${label} : ${step.assert} → ${JSON.stringify(value)}`);
    }
    if (step.shot) {
      const { result } = await send('Page.captureScreenshot', { format: 'png' });
      const file = join(outDir, `${name}-${step.shot}.png`);
      writeFileSync(file, Buffer.from(result.data, 'base64'));
      logs.push(`#${index} capture ${file}`);
    }
    // « save » sort sur le disque une image fabriquée par la page : {"save": "nom", "from": "<expr data:image/png>"}.
    // C'est ce qui permet de regarder vraiment le PNG joint à un retour, et pas seulement sa longueur.
    if (step.save) {
      const url = await evaluate(step.from);
      const comma = typeof url === 'string' ? url.indexOf(',') : -1;
      if (comma < 0 || !url.startsWith('data:image/png;base64,')) fail(`#${index} save ${step.save} : pas un PNG en data: URL${label}`);
      else {
        const file = join(outDir, `${name}-${step.save}.png`);
        writeFileSync(file, Buffer.from(url.slice(comma + 1), 'base64'));
        logs.push(`#${index} image ${file}`);
      }
    }
  } catch (error) { fail(`#${index} erreur${label} : ${error.message}`); }
}

clearTimeout(watchdog);
ws.close();
finish(failures.length ? 1 : 0);

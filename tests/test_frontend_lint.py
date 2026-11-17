"""Checks on the browser modules, which are served without a build step."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

STATIC = Path(__file__).resolve().parent.parent / 'studio' / 'static'
MODULES = sorted(STATIC.rglob('*.js'))
IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from\s*'([^']+)'", re.S)
EXPORT = re.compile(r"^export\s+(?:async\s+)?(?:function\s*\*?|const|let|class)\s+([A-Za-z_$][\w$]*)", re.M)


class FrontendLintTests(unittest.TestCase):
    def test_modules_exist(self):
        self.assertIn(STATIC / 'app.js', MODULES)
        self.assertGreater(len(MODULES), 10)

    def test_files_and_lines_stay_readable(self):
        for path in MODULES:
            lines = path.read_text().splitlines()
            self.assertLessEqual(len(lines), 420, f'{path.relative_to(STATIC)} : {len(lines)} lignes')
            for number, line in enumerate(lines, 1):
                self.assertLessEqual(len(line), 160, f'{path.relative_to(STATIC)}:{number} fait {len(line)} caractères')

    def test_every_import_names_an_existing_export(self):
        exports = {path: set(EXPORT.findall(path.read_text())) for path in MODULES}
        for path in MODULES:
            for names, target in IMPORT.findall(path.read_text()):
                resolved = (path.parent / target).resolve()
                self.assertIn(resolved, exports, f'{path.relative_to(STATIC)} importe {target}, introuvable')
                for name in (n.strip() for n in names.split(',') if n.strip()):
                    self.assertIn(name, exports[resolved], f'{path.relative_to(STATIC)} importe {name} absent de {target}')

    @unittest.skipUnless(shutil.which('node'), 'node absent')
    def test_syntax(self):
        for path in MODULES:
            result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, f'{path.relative_to(STATIC)} : {result.stderr}')

    def test_every_post_carries_a_body(self):
        """Sans `body`, `api()` n'envoie pas de Content-Type et le serveur refuse la requête."""
        for path in MODULES:
            text = path.read_text()
            for match in re.finditer(r"\{[^{}]*?method:\s*'POST'", text):
                start = match.start()
                depth, end = 0, len(text)
                for index in range(start, len(text)):
                    depth += (text[index] == '{') - (text[index] == '}')
                    if depth == 0:
                        end = index + 1
                        break
                options = text[start:end]
                where = f'{path.relative_to(STATIC)}:{text.count(chr(10), 0, start) + 1}'
                self.assertIn('body', options, f'{where} : POST sans body')

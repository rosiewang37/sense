#!/usr/bin/env bash
# Validate Python syntax for backend source files
set -e
cd "$(dirname "$0")/../backend"
echo "[hook] Checking Python syntax..."
python -c "
import ast, pathlib, sys
errors = []
for f in pathlib.Path('app').rglob('*.py'):
    try:
        ast.parse(f.read_text(encoding='utf-8'), filename=str(f))
    except SyntaxError as e:
        errors.append(f'{f}:{e.lineno}: {e.msg}')
if errors:
    print('Syntax errors found:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
print(f'All Python files OK')
"

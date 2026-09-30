"""Local practice registry. Standard library only; no network or model calls."""
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {'in_progress', 'awaiting_device', 'awaiting_limit', 'blocked', 'ready'}


def practice_id(item):
    year = item['academic_year']
    if not re.fullmatch(r'\d{4}-\d{4}', year) or int(year[5:]) != int(year[:4]) + 1:
        raise ValueError('academic_year: expected consecutive years YYYY-YYYY')
    if not re.fullmatch(r'\d{2}\.\d{2}\.\d{2}', item['specialty']):
        raise ValueError('specialty: expected NN.NN.NN')
    if not re.fullmatch(r'[a-z][a-z0-9]*', item['qualification']):
        raise ValueError('qualification: expected short lowercase code')
    if item['practice_type'] not in {'up', 'pp'}:
        raise ValueError('practice_type: expected up or pp')
    if not re.fullmatch(r'\d{2}', item['module']):
        raise ValueError('module: expected two digits')
    semester, part = item['semester'], item.get('part')
    if type(semester) is not int or not 1 <= semester <= 99:
        raise ValueError('semester: expected positive integer below 100')
    if part is not None and (type(part) is not int or not 1 <= part <= 99):
        raise ValueError('part: expected null or positive integer below 100')
    result = f"{year}-{item['specialty']}-{item['qualification']}-{item['practice_type']}-pm.{item['module']}-sem{semester:02d}"
    return result + (f'-part{part:02d}' if part is not None else '')


def validate(item):
    if item['id'] != practice_id(item):
        raise ValueError('id does not match practice metadata')
    if not isinstance(item['title'], str) or not item['title'].strip():
        raise ValueError('title is required')
    if item['status'] not in STATUSES:
        raise ValueError('unknown status')
    for field in ('repository_url', 'site_url'):
        value = item.get(field)
        if value is not None:
            parsed = urlparse(value)
            if parsed.scheme != 'https' or not parsed.netloc or any(c.isspace() for c in value):
                raise ValueError(f'{field}: expected HTTPS URL or null')
    commit = item.get('verified_commit')
    if commit is not None and not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('verified_commit: expected full SHA-1 or null')
    if item['status'] == 'ready' and not all(item.get(k) for k in ('repository_url', 'site_url', 'verified_commit')):
        raise ValueError('ready requires repository_url, site_url and verified_commit')
    if not isinstance(item.get('related_practice_ids', []), list) or not all(isinstance(x, str) for x in item.get('related_practice_ids', [])):
        raise ValueError('related_practice_ids: expected list of strings')
    if not isinstance(item.get('notes', ''), str):
        raise ValueError('notes: expected string')


def read_registry(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1 or not isinstance(data.get('practices'), list):
        raise ValueError('invalid registry schema')
    ids = set()
    for item in data['practices']:
        validate(item)
        if item['id'] in ids:
            raise ValueError('duplicate id')
        ids.add(item['id'])
    return data


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as out:
            name = out.name
            out.write(content)
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def cell(value):
    return str(value or '—').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def render(data):
    lines = ['# Созданные практики', '', 'Сформировано из `practices.json`. Редактируйте основной JSON, затем выполните команду render.', '']
    if not data['practices']:
        return '\n'.join(lines + ['Пока нет зарегистрированных практик.', ''])
    lines += ['| Практика | Идентификатор | Статус | Репозиторий | Сайт |', '|---|---|---|---|---|']
    for item in sorted(data['practices'], key=lambda x: x['id']):
        lines.append('| ' + ' | '.join(cell(item.get(k)) for k in ('title', 'id', 'status', 'repository_url', 'site_url')) + ' |')
    return '\n'.join(lines) + '\n'


def upsert(data, source):
    item = dict(source)
    item.setdefault('part', None)
    item.setdefault('id', practice_id(item))
    existing = next((x for x in data['practices'] if x['id'] == item['id']), None)
    # Require a complete replacement record so missing evidence cannot survive an update.
    for key, default in [('repository_url', None), ('site_url', None), ('verified_commit', None), ('related_practice_ids', []), ('notes', '')]:
        item.setdefault(key, default)
    validate(item)
    now = datetime.now(timezone.utc).isoformat()
    item['created_at'] = existing['created_at'] if existing else now
    item['updated_at'] = now
    data['practices'] = [x for x in data['practices'] if x['id'] != item['id']] + [item]
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=ROOT / 'registry/practices.json')
    parser.add_argument('--markdown', type=Path, default=ROOT / 'registry/PRACTICES.md')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('render')
    add = sub.add_parser('upsert')
    add.add_argument('record', type=Path, help='Complete practice record in JSON')
    args = parser.parse_args()
    try:
        data = read_registry(args.registry)
        if args.command == 'upsert':
            item = upsert(data, json.loads(args.record.read_text(encoding='utf-8-sig')))
            atomic_write(args.registry, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
            print(item['id'])
        if args.command in {'upsert', 'render'}:
            atomic_write(args.markdown, render(data))
        print(f"OK: {len(data['practices'])} records")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()

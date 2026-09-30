"""Merge both source semesters and maintain a binary progress table."""
import argparse
import hashlib
import json
from pathlib import Path
from registry import atomic_write, cell

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['direction', 'curriculum', 'qualification', 'study_mode', 'year_of_study', 'semester', 'practice_type', 'code', 'module', 'subjects', 'hours', 'weeks', 'period', 'date_precision', 'source_status']


def merge_rows(sheets, previous=None):
    prior = {x['id']: x for x in (previous or {}).get('rows', [])}
    result = []
    seen = set()
    for sheet, rows in sheets:
        for number, values in rows:
            if not values[0] or not values[7]:
                raise ValueError(f'Incomplete source row {sheet}:{number}')
            item = dict(zip(FIELDS, values))
            key = json.dumps([item[k] for k in FIELDS[:9]], ensure_ascii=False)
            identifier = 'plan-' + hashlib.sha256(key.encode()).hexdigest()[:16]
            if identifier in seen:
                raise ValueError(f'Duplicate practice identity at {sheet}:{number}; resolve explicitly')
            seen.add(identifier)
            old = prior.get(identifier, {})
            item.update(id=identifier, source_sheet=sheet, source_row=number,
                        completed=old.get('completed', False),
                        repository_url=old.get('repository_url'),
                        completion_basis=old.get('completion_basis'),
                        note=old.get('note', ''))
            result.append(item)
    # Never silently drop a row with saved progress when source changes.
    missing = set(prior) - seen
    if missing:
        raise ValueError(f'Source removed or changed {len(missing)} identities; reconcile before import')
    return {'schema_version': 1, 'source_file': 'Практики_все_курсы_по_направлениям.xlsx', 'rows': result,
            'unmatched_completed': (previous or {}).get('unmatched_completed', [])}


def render(data):
    done = sum(x['completed'] for x in data['rows'])
    lines = ['# Выполнение практик', '', f"План: {len(data['rows'])} позиций, выполнено: {done}, не выполнено: {len(data['rows'])-done}.", '',
             'Оба полугодия объединены. Строки разных учебных планов и семестров сохранены отдельно. «Не выполнено» означает отсутствие подтверждённой готовности именно этой позиции. Полные МДК, часы, периоды и исходные отметки сохранены в `progress.json`.', '',
             '| ID | Выполнено / не выполнено | План / группа | Курс | Семестр | Вид | Код | Модуль | Часы | Источник |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for row in sorted(data['rows'], key=lambda r: (r['direction'], r['curriculum'], r['semester'], r['code'])):
        values = [row['id'], 'Выполнено' if row['completed'] else 'Не выполнено', row['curriculum'], row['year_of_study'], row['semester'], row['practice_type'], row['code'], row['module'], row['hours'], f"{row['source_sheet']}:{row['source_row']}"]
        lines.append('| ' + ' | '.join(cell(x) for x in values) + ' |')
    lines += ['', '## Выполненные практики вне сопоставленных строк плана', '',
              'Готовность подтверждена пользователем. Это не отметка нового полного испытания агентом. Семестры и соответствие строкам Excel пока не установлены.', '',
              '| Практика | Статус | Репозиторий |', '|---|---|---|']
    for row in data['unmatched_completed']:
        lines.append('| ' + ' | '.join(cell(x) for x in [row['title'], 'Выполнено', row['repository_url']]) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=ROOT/'registry/progress.json')
    p.add_argument('--output', type=Path, default=ROOT/'registry/PROGRESS.md')
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import-xlsx'); imp.add_argument('source', type=Path)
    sub.add_parser('render')
    mark = sub.add_parser('mark'); mark.add_argument('id'); mark.add_argument('status', choices=['done', 'todo']); mark.add_argument('--basis', required=True); mark.add_argument('--repo')
    a = p.parse_args()
    try:
        data = json.loads(a.data.read_text(encoding='utf-8')) if a.data.exists() else None
        if a.command == 'import-xlsx':
            import openpyxl
            book = openpyxl.load_workbook(a.source, read_only=True, data_only=True)
            try:
                sheets = [(name, [(i, list(row)) for i, row in enumerate(book[name].iter_rows(min_row=6, max_col=15, values_only=True), 6) if any(v is not None for v in row)]) for name in ['1 полугодие', '2 полугодие']]
                data = merge_rows(sheets, data)
            finally:
                book.close()
        elif data is None:
            raise ValueError('Import the source first')
        elif a.command == 'mark':
            row = next((x for x in data['rows'] if x['id'] == a.id), None)
            if row is None:
                raise ValueError('Unknown practice id')
            row.update(completed=a.status == 'done', completion_basis=a.basis)
            if a.repo:
                if not a.repo.startswith('https://github.com/'):
                    raise ValueError('Expected GitHub HTTPS URL')
                row['repository_url'] = a.repo
        if a.command != 'render':
            atomic_write(a.data, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        atomic_write(a.output, render(data))
        print(f"OK: {len(data['rows'])} plan rows")
    except (ValueError, KeyError, OSError, ImportError) as error:
        p.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()

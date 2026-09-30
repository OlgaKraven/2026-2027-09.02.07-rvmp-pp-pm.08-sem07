"""Copy a legacy practice to schema 2 without touching its original repository."""
import argparse
import copy
import json
import re
import shutil
from pathlib import Path
from .content import source_path, validate


def heading(text):
    return re.sub(r'\bШаг\s+\d+(?:\.\d+)*\s*[/.:—–-]?\s*', '', text, flags=re.I).strip(' /—–-') or 'Выполнение задания'


def convert(raw, practice_type, demonstration):
    data = copy.deepcopy(raw)
    data['schema_version'] = 2
    data['meta'].update(status='draft', practice_type=practice_type)
    for key in ('academic_year', 'specialty_code', 'qualification', 'semester', 'part'):
        data['meta'].setdefault(key, None)
    data['demonstration'] = {'title': demonstration, 'description': 'Отдельный образец решения общей задачи. Не является студенческим вариантом.'}
    areas = []
    for page in raw['areas']:
        if re.match(r'^Вариант\s+\d+', page['title']):
            areas.append(copy.deepcopy(page))
        else:
            for block in page['blocks']:
                if not re.match(r'^Вариант\s+\d+', block['title']):
                    raise ValueError('Unknown grouped area structure; manual migration needed')
                blocks = []
                for line in block['text'].splitlines():
                    if not line.strip():
                        continue
                    title, separator, text = line.partition(': ')
                    blocks.append({'title': title if separator else 'Условие', 'text': text if separator else line, 'kind': 'text'})
                areas.append({'title': block['title'], 'kicker': 'Индивидуальное задание', 'blocks': blocks})
    for page in areas:
        match = re.match(r'^Вариант\s+(\d+)\s*[.·:—–-]?\s*(.*)$', page['title'])
        page['id'] = int(match.group(1))
        page['subject'] = match.group(2).strip()
        page['downloads'] = []
    data['areas'] = areas
    for key in ('assignment', 'guide', 'areas'):
        for page in data[key]:
            page['title'] = heading(page['title'])
            page['kicker'] = heading(page.get('kicker', ''))
            for block in page['blocks']:
                block['title'] = heading(block['title'])
                if block['kind'] == 'code':
                    block.pop('text', None)
    data['downloads'] = []
    data['report'] = {'sections': [
        {'title': 'Исходные данные', 'prompt': 'Укажите тему, цель, условия своего варианта и фактические версии программ.', 'screenshots': []},
        {'title': 'Выполнение задания', 'prompt': 'Опишите выполненные действия, изменения и полученный результат.', 'screenshots': ['Исходное состояние', 'Основной результат']},
        {'title': 'Дополнительные задания варианта', 'prompt': 'Перечислите дополнительные задания своего варианта и результаты их выполнения.', 'screenshots': ['Результат дополнительных заданий']},
        {'title': 'Проверки и вывод', 'prompt': 'Укажите ожидаемые и фактические результаты проверок, ограничения и ссылку на сдаваемый проект.', 'screenshots': ['Подтверждение проверки']}
    ]}
    return data


def migrate(source, destination, practice_type, demonstration):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Destination must be a new independent directory')
    raw = json.loads(source_path(source, 'content/course.json').read_text(encoding='utf-8-sig'))
    data = convert(raw, practice_type, demonstration)
    paths = {item['path'] for item in data['code_files']}
    for key in ('assignment', 'guide', 'areas'):
        for page in data[key]:
            paths.update(b['path'] for b in page['blocks'] if b['kind'] == 'image')
    project = source/'unity-project'
    if project.is_dir():
        excluded = {'Library', 'Temp', 'Logs', 'obj', 'UserSettings', 'Build', '_Recovery'}
        project_files = []
        for file in sorted(project.rglob('*')):
            relative = file.relative_to(source)
            if file.is_file() and not excluded.intersection(relative.parts) and not any(x.startswith('.') for x in relative.parts) and file.suffix not in {'.log', '.csproj', '.sln'}:
                source_path(source, relative.as_posix())
                project_files.append(relative.as_posix())
        paths.update(project_files)
        data['downloads'].append({'name': 'demonstration-project.zip', 'kind': 'archive', 'label': 'Проект демонстрации', 'files': project_files})
    # Resolve every path before writing the new directory.
    resolved = {name: source_path(source, name) for name in paths}
    destination.mkdir(parents=True)
    for name, file in resolved.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
    (destination/'content').mkdir(exist_ok=True)
    validate(destination, data)
    (destination/'content/course.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (destination/'MIGRATION.md').write_text('Черновая миграция. Паспорт и общий отчёт требуют адаптации. Старые отметки готовности не перенесены; повторный запуск учебного проекта не выполнялся.\n', encoding='utf-8')
    return destination


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--type', choices=['up', 'pp'], required=True)
    p.add_argument('--demonstration', required=True)
    args = p.parse_args()
    try:
        print(migrate(args.source, args.destination, args.type, args.demonstration))
    except (ValueError, KeyError, OSError) as error:
        p.exit(1, f'Error: {error}\n')

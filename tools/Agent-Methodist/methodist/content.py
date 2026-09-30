"""Validation, source resolution and reproducible content fingerprints."""
import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ASSETS = Path(__file__).parent / 'assets'
RESERVED = {'assignment.pdf', 'guide.pdf', 'report-template.md'}


def source_path(root, value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise ValueError(f'Expected project-relative POSIX path: {value}')
    relative = PurePosixPath(value)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError(f'Path outside project: {value}')
    root = Path(root).resolve()
    result = root.joinpath(*relative.parts).resolve()
    if not result.is_relative_to(root) or not result.is_file():
        raise ValueError(f'Missing or external file: {value}')
    if relative.parts[0] in {'site', '.git', '.venv'} or any(p.startswith('.') for p in relative.parts):
        raise ValueError(f'Generated or hidden input: {value}')
    return result


def output_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value) or value in {'.', '..'}:
        raise ValueError(f'Invalid download name: {value}')
    return value


def pages(data):
    for section in ('assignment', 'guide', 'areas'):
        yield from data[section]


def inputs(data):
    paths = {x['path'] for x in data['code_files']}
    for item in data['downloads']:
        paths.update(item['files'] if item['kind'] == 'archive' else [item['path']])
    for page in pages(data):
        paths.update(b['path'] for b in page['blocks'] if b['kind'] == 'image')
    return sorted(paths)


def fingerprint(root, raw):
    digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode())
    for name in inputs(raw):
        digest.update(name.encode())
        digest.update(source_path(root, name).read_bytes())
    # A changed generator or design invalidates previous release evidence too.
    for path in sorted(Path(__file__).parent.glob('*.py')) + sorted(ASSETS.iterdir()):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load(root):
    root = Path(root).resolve()
    raw = json.loads(source_path(root, 'content/course.json').read_text(encoding='utf-8-sig'))
    validate(root, raw)
    data = copy.deepcopy(raw)
    for area in data['areas']:
        area['downloads'] = list(dict.fromkeys([*data.get('shared_area_downloads', []), *area.get('downloads', [])]))
    sources = {x['name']: source_path(root, x['path']).read_text(encoding='utf-8-sig').splitlines() for x in data['code_files']}
    for page in pages(data):
        for block in page['blocks']:
            for link in block.get('links', []):
                if not isinstance(link, dict) or not str(link.get('url', '')).startswith('https://') or not link.get('label') or not link.get('description'):
                    raise ValueError('Text links require HTTPS URL, meaningful label and description')
            if block['kind'] == 'code':
                start, end = block['code_lines']
                block['text'] = '\n'.join(sources[block['code_file']][start:end])
    return raw, data


def validate(root, data):
    if data.get('schema_version') != 2:
        raise ValueError('Expected schema_version 2; migrate legacy content first')
    for name in ('assignment', 'guide', 'areas'):
        if not isinstance(data.get(name), list) or not data[name]:
            raise ValueError(f'Missing section {name}')
    for name in ('code_files', 'downloads'):
        if not isinstance(data.get(name), list):
            raise ValueError(f'{name} must be a list (may be empty)')
    meta = data['meta']
    for name in ('title', 'subtitle', 'version', 'organization', 'specialty', 'module'):
        if not isinstance(meta.get(name), str) or not meta[name].strip():
            raise ValueError(f'Missing meta.{name}')
    if meta.get('practice_type') not in ('up', 'pp'):
        raise ValueError('meta.practice_type must be up or pp')
    demonstration = data['demonstration']
    if not demonstration.get('title') or not demonstration.get('description'):
        raise ValueError('Separate demonstration title and description required')
    if len(data['areas']) != 30:
        raise ValueError('Exactly 30 student areas required')
    ids = [a.get('id') for a in data['areas']]
    if any(type(x) is not int for x in ids) or set(ids) != set(range(1, 31)):
        raise ValueError('Area ids must be integers 1 through 30')
    names = [a.get('subject', '').strip().casefold() for a in data['areas']]
    if '' in names or len(set(names)) != 30 or demonstration['title'].strip().casefold() in names:
        raise ValueError('Student subjects must be distinct and exclude the demonstration')
    bodies = [json.dumps(a['blocks'], sort_keys=True, ensure_ascii=False) for a in data['areas']]
    if len(set(bodies)) != 30:
        raise ValueError('Identical area content is not allowed')
    filenames = set(RESERVED)
    sources = {}
    for item in data['code_files']:
        name = output_name(item['name'])
        if name.casefold() in {x.casefold() for x in filenames}:
            raise ValueError(f'Duplicate output {name}')
        filenames.add(name)
        sources[name] = source_path(root, item['path']).read_text(encoding='utf-8-sig').splitlines()
    downloads = {}
    for item in data['downloads']:
        name = output_name(item['name'])
        if name.casefold() in {x.casefold() for x in filenames}:
            raise ValueError(f'Duplicate output {name}')
        filenames.add(name)
        downloads[name] = item
        if item['kind'] == 'file':
            source_path(root, item['path'])
        elif item['kind'] == 'archive':
            if not name.endswith('.zip') or not item.get('files') or len(set(item['files'])) != len(item['files']):
                raise ValueError('Archive needs a .zip name and unique explicit file list')
            for path in item['files']:
                source_path(root, path)
                if {'Library', 'Temp', 'Logs', 'obj', 'UserSettings', 'Build', '_Recovery'}.intersection(PurePosixPath(path).parts):
                    raise ValueError(f'Cache directory in archive: {path}')
        else:
            raise ValueError('Download kind must be file or archive')
    coverage = {name: [] for name in sources}
    for page in pages(data):
        if not page.get('title') or not page.get('blocks'):
            raise ValueError('Empty page')
        if re.search(r'\bшаг\s*\d+', page['title'] + ' ' + page.get('kicker', ''), re.I):
            raise ValueError('Use descriptive page titles, not Шаг N')
        for block in page['blocks']:
            if not block.get('title') or block.get('kind') not in {'text', 'note', 'code', 'image'}:
                raise ValueError('Invalid block title or kind')
            if re.search(r'\bшаг\s*\d+', block['title'], re.I):
                raise ValueError('Use descriptive block titles, not Шаг N')
            if block['kind'] == 'code':
                name = block['code_file']
                span = block['code_lines']
                if name not in sources or not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span):
                    raise ValueError('Invalid code source or range')
                start, end = span
                if not 0 <= start < end <= len(sources[name]):
                    raise ValueError('Code range outside source')
                if page in data['guide']:
                    coverage[name].extend(range(start, end))
            elif not isinstance(block.get('text'), str) or not block['text'].strip():
                raise ValueError('Empty text/caption')
            if block['kind'] == 'image':
                source_path(root, block['path'])
    for name, covered in coverage.items():
        if covered != list(range(len(sources[name]))):
            raise ValueError(f'Guide must include all lines once in source order: {name}')
    shared = data.get('shared_area_downloads', [])
    if not isinstance(shared, list) or any(not isinstance(name, str) or name not in downloads for name in shared):
        raise ValueError('Unknown shared area download')
    for area in data['areas']:
        for name in area.get('downloads', []):
            if name not in downloads:
                raise ValueError(f'Unknown area download {name}')
    report = data['report']
    if not report.get('sections'):
        raise ValueError('Report sections required')
    count = 0
    for section in report['sections']:
        if not section.get('title') or not section.get('prompt'):
            raise ValueError('Report section requires title and prompt')
        captions = section.get('screenshots', [])
        if not isinstance(captions, list) or not all(isinstance(x, str) and x.strip() for x in captions):
            raise ValueError('Invalid screenshot captions')
        count += len(captions)
    if count > 30:
        raise ValueError('Report may request at most 30 screenshots')


def require_release(root, raw, evidence_path):
    meta = raw['meta']
    for key in ('academic_year', 'specialty_code', 'qualification', 'semester'):
        if not meta.get(key):
            raise ValueError(f'Release requires meta.{key}')
    year = meta['academic_year']
    if not isinstance(year, str) or not re.fullmatch(r'\d{4}-\d{4}', year) or int(year[5:]) != int(year[:4])+1:
        raise ValueError('Invalid academic year')
    if not re.fullmatch(r'\d{2}\.\d{2}\.\d{2}', meta['specialty_code']):
        raise ValueError('Invalid specialty code')
    if not re.fullmatch(r'[a-z][a-z0-9]*', meta['qualification']):
        raise ValueError('Invalid qualification code')
    if type(meta['semester']) is not int or not 1 <= meta['semester'] <= 99:
        raise ValueError('Invalid semester')
    if meta.get('part') is not None and (type(meta['part']) is not int or not 1 <= meta['part'] <= 99):
        raise ValueError('Invalid part')
    if not evidence_path:
        raise ValueError('Release requires independent verification evidence')
    evidence = json.loads(Path(evidence_path).read_text(encoding='utf-8-sig'))
    if evidence.get('fingerprint') != fingerprint(root, raw):
        raise ValueError('Stale verification: content, sources or generator changed')
    for key in ('demonstration', 'variants', 'screenshots', 'visual_review'):
        entry = evidence.get('checks', {}).get(key, {})
        if entry.get('status') != 'passed' or not entry.get('summary') or not entry.get('files'):
            raise ValueError(f'Missing verification: {key}')
        for path in entry['files']:
            source_path(root, path)
    return evidence

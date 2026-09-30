"""Stage orchestration for Codex; never invokes a model or a billing API."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .content import fingerprint, inputs, load, source_path
from .state import DEFAULT_DB, Memory, STAGES, now, resume, track
from scripts.registry import practice_id, read_registry, upsert, render, atomic_write

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = {
    'scenario': 'Согласовать паспорт и сохранить подтверждение пользователя.',
    'content': 'Создать content/course.json: задание, 30 вариантов, демонстрация, отчёт и исходники.',
    'execution': 'Выполнить демонстрацию и технически разные варианты, получить реальные скриншоты и evidence.json.',
    'assembly': 'Собрать черновой сайт, PDF и отчёт.',
    'validation': 'Проверить визуально сайт/PDF, дополнить evidence.json и собрать выпуск.',
    'publication': 'Опубликовать проверенный комплект в репозитории практики и проверить сайт.',
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def next_stage(data):
    return STAGES[len(data['completed'])] if len(data['completed']) < len(STAGES) else None


def check_ready(data, root, device):
    result = resume(data, root, device)
    if not result['can_continue']:
        raise ValueError('; '.join(result['reasons']) + ': ' + ', '.join(result['changed_files']))
    if not data.get('approval'):
        raise ValueError('Use workflow start with the approved passport first')


def complete(memory, data, stage, root, files, note):
    updated = dict(data, completed=[*data['completed'], stage], revision=data['revision']+1,
                   updated_at=now(), note=note, status='working', device='any')
    updated['files'] = {**data['files'], **track(root, files)}
    updated['next_action'] = ACTIONS.get(next_stage(updated), 'Работа завершена')
    if not next_stage(updated):
        updated['status'] = 'done'
    return memory.save(updated, data['revision'])


def start(memory, task_id, root, passport, approval):
    path = source_path(root, passport)
    if not path.read_text(encoding='utf-8-sig').strip() or not approval.strip():
        raise ValueError('Nonempty passport and actual user approval required')
    return memory.save(dict(schema_version=1, id=task_id, title=task_id, revision=1,
        status='working', device='any', completed=['scenario'], next_action=ACTIONS['content'],
        note='Паспорт согласован', files=track(root, [passport]), updated_at=now(),
        approval={'user_message': approval, 'passport': passport}), 0)


def execution_evidence(root, raw, evidence_name):
    evidence_path = source_path(root, evidence_name)
    evidence = read_json(evidence_path)
    if evidence.get('fingerprint') != fingerprint(root, raw):
        raise ValueError('Stale execution evidence')
    # Visual review is appended after the draft build; freeze the final evidence at validation.
    paths = []
    for key in ('demonstration', 'variants', 'screenshots'):
        check = evidence.get('checks', {}).get(key, {})
        if check.get('status') != 'passed' or not check.get('summary') or not check.get('files'):
            raise ValueError(f'Missing execution evidence: {key}')
        for name in check['files']:
            source_path(root, name)
            paths.append(name)
    return paths


def advance(memory, task_id, root, device, evidence='evidence.json'):
    data = memory.get(task_id)
    check_ready(data, root, device)
    stage = next_stage(data)
    if stage not in ('content', 'execution', 'assembly', 'validation'):
        raise ValueError('Use finish after publication; no automatic completion')
    raw, content = load(root)
    files = ['content/course.json', *inputs(raw)]
    if stage == 'content':
        pass
    elif stage == 'execution':
        files += execution_evidence(root, raw, evidence)
    elif stage == 'assembly':
        from .build import build
        build(root)
    elif stage == 'validation':
        from .build import build
        build(root, release=True, evidence=source_path(root, evidence))
        proof = read_json(root/evidence)
        files += [evidence, *[name for check in proof['checks'].values() for name in check.get('files', [])]]
        files += ['site/manifest.json']
    return complete(memory, data, stage, root, files, f'Этап {stage} проверен')


def release_manifest(root):
    from .build import check_output, check_pdf_content
    raw, content = load(root)
    check_output(root/'site')
    check_pdf_content(root/'site', content)
    manifest = read_json(root/'site/manifest.json')
    if not manifest.get('release') or manifest.get('fingerprint') != fingerprint(root, raw):
        raise ValueError('Publication requires a current release build')
    return raw, manifest


def publication_plan(root, owner, module):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', owner):
        raise ValueError('Invalid GitHub owner')
    raw, manifest = release_manifest(root)
    meta = raw['meta']
    record = dict(academic_year=meta['academic_year'], specialty=meta['specialty_code'],
        qualification=meta['qualification'], practice_type=meta['practice_type'], module=module,
        semester=meta['semester'], part=meta.get('part'), title=meta['title'], status='in_progress')
    record['id'] = practice_id(record)
    return {'record': record, 'repository_url': f"https://github.com/{owner}/{record['id']}",
        'site_url': f"https://{owner.lower()}.github.io/{record['id']}/",
        'source_files': ['content/course.json', *inputs(raw)],
        'site_files': ['site/manifest.json', *['site/'+name for name in manifest['files']]],
        'instruction': 'Publish only these files plus reviewed README/deployment config. Never git add . in the working practice directory.'}


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'Agent-Methodist', 'Cache-Control': 'no-cache'}), timeout=30) as response:
        return response.read()


def verify_publication(plan, manifest, commit, fetcher=fetch):
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Full commit SHA required')
    repo_path = urlsplit(plan['repository_url']).path.strip('/')
    remote = json.loads(fetcher(f'https://api.github.com/repos/{repo_path}/commits/{commit}'))
    if remote.get('sha') != commit:
        raise ValueError('Commit not found in target repository')
    remote_manifest = json.loads(fetcher(f'https://raw.githubusercontent.com/{repo_path}/{commit}/site/manifest.json'))
    if remote_manifest != manifest:
        raise ValueError('Published commit does not contain this release')
    base = plan['site_url']
    if json.loads(fetcher(base+'manifest.json')) != manifest:
        raise ValueError('Site deployment is stale')
    for name, digest in manifest['files'].items():
        if hashlib.sha256(fetcher(base+quote(name, safe='/'))).hexdigest() != digest:
            raise ValueError(f'Published file differs: {name}')


def finish(memory, task_id, root, device, owner, module, commit, registry, markdown, fetcher=fetch):
    data = memory.get(task_id)
    check_ready(data, root, device)
    if next_stage(data) != 'publication':
        raise ValueError('All previous stages must be complete')
    plan = publication_plan(root, owner, module)
    manifest = read_json(root/'site/manifest.json')
    verify_publication(plan, manifest, commit, fetcher)
    repo_path = urlsplit(plan['repository_url']).path.strip('/')
    for name in plan['source_files']:
        remote = fetcher(f'https://raw.githubusercontent.com/{repo_path}/{commit}/{quote(name, safe="/")}')
        if hashlib.sha256(remote).digest() != hashlib.sha256(source_path(root, name).read_bytes()).digest():
            raise ValueError(f'Published source differs: {name}')
    catalog = read_registry(registry)
    record = dict(plan['record'], status='ready', repository_url=plan['repository_url'],
                  site_url=plan['site_url'], verified_commit=commit)
    upsert(catalog, record)
    # Registry first: retry after interruption is an idempotent upsert, never another repository.
    atomic_write(registry, json.dumps(catalog, ensure_ascii=False, indent=2)+'\n')
    atomic_write(markdown, render(catalog))
    data['publication'] = record
    return complete(memory, data, 'publication', root, ['site/manifest.json'], 'Сайт, загрузки и коммит проверены; реестр обновлён')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('start', 'next', 'advance', 'publication-plan', 'finish'):
        child = sub.add_parser(name)
        child.add_argument('id')
        child.add_argument('--project', type=Path, required=True)
        child.add_argument('--device', choices=('windows', 'mac'), required=True)
        if name == 'start':
            child.add_argument('--passport', default='passport.md')
            child.add_argument('--approval', required=True)
        if name == 'advance':
            child.add_argument('--evidence', default='evidence.json')
        if name in ('publication-plan', 'finish'):
            child.add_argument('--owner', required=True)
            child.add_argument('--module', required=True)
        if name == 'finish':
            child.add_argument('--commit', required=True)
            child.add_argument('--registry', type=Path, default=ROOT/'registry/practices.json')
            child.add_argument('--markdown', type=Path, default=ROOT/'registry/PRACTICES.md')
    args = parser.parse_args()
    memory = None
    try:
        memory = Memory(args.db)
        root = args.project.resolve(strict=True)
        if args.command == 'start':
            result = start(memory, args.id, root, args.passport, args.approval)
        elif args.command == 'next':
            data = memory.get(args.id)
            result = resume(data, root, args.device)
            result.update(stage=next_stage(data), action=ACTIONS.get(next_stage(data), 'Завершено'))
        elif args.command == 'advance':
            result = advance(memory, args.id, root, args.device, args.evidence)
        elif args.command == 'publication-plan':
            data = memory.get(args.id)
            check_ready(data, root, args.device)
            if next_stage(data) != 'publication':
                raise ValueError('Finish validation before preparing publication')
            result = publication_plan(root, args.owner, args.module)
        else:
            result = finish(memory, args.id, root, args.device, args.owner, args.module,
                            args.commit, args.registry, args.markdown)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, ImportError, sqlite3.Error) as error:
        parser.exit(1, f'Error: {error}\n')
    finally:
        if memory:
            memory.close()


if __name__ == '__main__':
    main()

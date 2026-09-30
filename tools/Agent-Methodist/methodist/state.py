"""Local transactional task memory; no network or model calls."""
import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

STAGES = ('scenario', 'content', 'execution', 'assembly', 'validation', 'publication')
STATUSES = ('working', 'awaiting_device', 'awaiting_limit', 'blocked', 'done')
DEFAULT_DB = Path(__file__).resolve().parents[1] / 'local/state/tasks.sqlite3'


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('State must be an object')
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported state schema')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,119}', data.get('id', '')):
        raise ValueError('Use a portable lowercase task id')
    if data.get('status') not in STATUSES or data.get('device') not in ('any', 'windows', 'mac'):
        raise ValueError('Invalid status or device')
    if not isinstance(data.get('revision'), int) or data['revision'] < 1:
        raise ValueError('Invalid revision')
    for field in ('title', 'next_action', 'note', 'updated_at'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f'Missing {field}')
    if not isinstance(data.get('completed'), list) or any(s not in STAGES for s in data['completed']):
        raise ValueError('Invalid completed stages')
    if data['completed'] != list(STAGES[:len(data['completed'])]):
        raise ValueError('Completed stages must form an ordered prefix')
    if data['status'] == 'done' and data['completed'] != list(STAGES):
        raise ValueError('Finish every stage before marking done')
    if not isinstance(data.get('files'), dict):
        raise ValueError('Invalid files')
    for name, digest in data['files'].items():
        path = PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
            raise ValueError('Only portable project-relative file paths are allowed')
        if not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Invalid file hash')
    return data


class Memory:
    def __init__(self, path=DEFAULT_DB):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT, revision INTEGER, payload TEXT NOT NULL, PRIMARY KEY(id, revision))')

    def close(self):
        self.db.close()

    def get(self, task_id):
        row = self.db.execute('SELECT payload FROM events WHERE id=? ORDER BY revision DESC LIMIT 1', (task_id,)).fetchone()
        if not row:
            raise ValueError('Task not found')
        return json.loads(row[0])

    def save(self, data, expected):
        validate(data)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            actual = self.db.execute('SELECT COALESCE(MAX(revision),0) FROM events WHERE id=?', (data['id'],)).fetchone()[0]
            if actual != expected:
                raise ValueError('State changed or task already exists; read latest state first')
            if data['revision'] != expected + 1:
                raise ValueError('Invalid next revision')
            self.db.execute('INSERT INTO events VALUES (?,?,?)', (data['id'], data['revision'], json.dumps(data, ensure_ascii=False)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return data


def now():
    return datetime.now(timezone.utc).isoformat()


def track(project, names):
    root = project.resolve(strict=True)
    result = {}
    for name in names:
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Tracked files must belong to the project')
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def resume(data, project, device):
    changed = []
    for name, digest in data['files'].items():
        try:
            actual = track(project, [name]).get(name)
        except (ValueError, OSError):
            actual = None
        if actual != digest:
            changed.append(name)
    reasons = []
    if changed:
        reasons.append('Tracked files changed or missing; repeat affected checks')
    if data['device'] not in ('any', device):
        reasons.append('Next action requires another device')
    if data['status'] in ('awaiting_limit', 'blocked', 'done'):
        reasons.append('Explicit checkpoint required before continuing this status')
    return {'task': data, 'can_continue': not reasons, 'reasons': reasons, 'changed_files': changed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create')
    create.add_argument('id')
    create.add_argument('--title', required=True)
    create.add_argument('--next', required=True, dest='next_action')
    for name in ('show', 'history', 'checkpoint', 'resume', 'export'):
        cmd = sub.add_parser(name)
        cmd.add_argument('id')
        if name == 'checkpoint':
            cmd.add_argument('--revision', type=int, required=True)
            cmd.add_argument('--status', choices=STATUSES, required=True)
            cmd.add_argument('--device', choices=('any', 'windows', 'mac'), required=True)
            cmd.add_argument('--next', dest='next_action', required=True)
            cmd.add_argument('--note', required=True)
            cmd.add_argument('--complete', choices=STAGES)
            cmd.add_argument('--invalidate-from', choices=STAGES)
            cmd.add_argument('--project', type=Path)
            cmd.add_argument('--track', nargs='+')
        if name == 'resume':
            cmd.add_argument('--project', type=Path, required=True)
            cmd.add_argument('--device', choices=('windows', 'mac'), required=True)
        if name == 'export':
            cmd.add_argument('output', type=Path)
    imp = sub.add_parser('import')
    imp.add_argument('input', type=Path)
    args = parser.parse_args()
    memory = None
    try:
        memory = Memory(args.db)
        if args.command == 'create':
            result = memory.save(dict(schema_version=1, id=args.id, title=args.title, revision=1,
                status='working', device='any', completed=[], next_action=args.next_action,
                note='Task created', files={}, updated_at=now()), 0)
        elif args.command == 'import':
            result = validate(json.loads(args.input.read_text(encoding='utf-8')))
            # Import only into an empty task slot: never overwrite another device's work.
            result = dict(result, revision=1, note=f"Imported revision {result['revision']}: {result['note']}", updated_at=now())
            result = memory.save(result, 0)
        else:
            result = memory.get(args.id)
            if args.command == 'checkpoint':
                if args.complete and args.invalidate_from:
                    raise ValueError('Complete and invalidate are mutually exclusive')
                if args.invalidate_from:
                    result['completed'] = result['completed'][:STAGES.index(args.invalidate_from)]
                if args.complete:
                    result['completed'].append(args.complete)
                if args.track:
                    if not args.project:
                        raise ValueError('--track requires --project')
                    result['files'].update(track(args.project, args.track))
                result.update(revision=args.revision + 1, status=args.status, device=args.device,
                    next_action=args.next_action, note=args.note, updated_at=now())
                result = memory.save(result, args.revision)
            elif args.command == 'resume':
                result = resume(result, args.project, args.device)
            elif args.command == 'history':
                result = [json.loads(row[0]) for row in memory.db.execute('SELECT payload FROM events WHERE id=? ORDER BY revision', (args.id,))]
            elif args.command == 'export':
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open('x', encoding='utf-8') as output:
                    output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
                result = {'exported': str(args.output)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'Error: {error}\n')
    finally:
        if memory:
            memory.close()


if __name__ == '__main__':
    main()

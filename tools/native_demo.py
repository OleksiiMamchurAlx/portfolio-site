"""Read only the exact reviewed browser subset from the pinned public commit."""
from pathlib import PurePosixPath
import re

from publication_guard import Blocked, digest, path_ok, scan


def reviewed_paths(policy):
    config = policy.get('approved_web_demo')
    if config is None:
        return None
    if (not isinstance(config, dict) or set(config) != {'entry', 'files'}
            or config['entry'] != 'web/index.html'
            or not isinstance(config['files'], list)
            or not 1 <= len(config['files']) <= 20
            or not all(isinstance(name, str) for name in config['files'])
            or config['files'] != sorted(set(config['files']))
            or config['entry'] not in config['files']):
        raise Blocked('WEB_DEMO_REVIEW_SCHEMA')
    for name in config['files']:
        if (not isinstance(name, str) or not name.startswith('web/')
                or not path_ok(name) or PurePosixPath(name).suffix not in {'.html', '.js', '.json', '.py', '.md'}
                or name not in policy['allowed_files']
                or not re.fullmatch('[0-9a-f]{64}', policy['reviewed_hashes'].get(name, ''))):
            raise Blocked('WEB_DEMO_UNREVIEWED_PATH')
    return config['files']


def verify_bundle(policy, files):
    paths = reviewed_paths(policy)
    if paths is None or not isinstance(files, dict) or set(files) != set(paths):
        raise Blocked('WEB_DEMO_UNREVIEWED_BUNDLE')
    for name in paths:
        data = files[name]
        if not isinstance(data, bytes):
            raise Blocked('WEB_DEMO_INVALID_CONTENT')
        scan(name, data)
        if digest(data) != policy['reviewed_hashes'][name]:
            raise Blocked('WEB_DEMO_HASH_MISMATCH')
    return {'file_count': len(paths), 'sha256': digest(b''.join(
        name.encode() + b'\0' + bytes.fromhex(digest(files[name])) for name in paths))}


def fetch_reviewed_bundle(record, policy, fetcher):
    paths = reviewed_paths(policy)
    if paths is None:
        return None
    if (record['source_repository'] != 'OleksiiMamchurAlx/adaptive-ai-router-demo'
            or not re.fullmatch('[0-9a-f]{40}', record['source_commit'])):
        raise Blocked('WEB_DEMO_SOURCE_MISMATCH')
    base = 'https://raw.githubusercontent.com/' + record['source_repository'] + '/' + record['source_commit'] + '/'
    files = {name: fetcher(base + name) for name in paths}
    verify_bundle(policy, files)
    return files

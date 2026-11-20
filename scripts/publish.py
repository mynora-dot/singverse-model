#!/usr/bin/env python3
"""Publish checked assets to an existing stable Release without overwriting assets."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from models import catalog, check_tag, digest, verify_release


def gh_json(*args):
    return json.loads(subprocess.check_output(['gh', 'api', *args], text=True))


def release_info(lock, tag):
    check_tag(tag)
    repository = lock['repository']
    release = gh_json('repos/' + repository + '/releases/tags/' + tag)
    if release['tag_name'] != tag or release['draft'] or release['prerelease']:
        raise ValueError('Only an existing published stable Release can receive model assets')
    if release.get('immutable'):
        raise ValueError('This Release is immutable; assets must be attached before publication')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    revision = subprocess.check_output(['git', 'rev-parse', 'refs/tags/' + tag + '^{commit}'], text=True).strip()
    if head != revision:
        raise ValueError('Check out the exact release tag before publishing')
    if gh_json('repos/' + repository + '/commits/' + tag)['sha'] != head:
        raise ValueError('The remote release tag no longer matches this checkout')
    # Include every page so an existing asset cannot be missed during retries.
    assets = gh_json('--paginate', '--slurp', 'repos/' + repository + '/releases/' + str(release['id']) + '/assets?per_page=100')
    return {file['name']: file for page in assets for file in page}


def publish(lock, directory, tag):
    verify_release(directory, tag, lock)
    existing = release_info(lock, tag)
    files = sorted(directory.iterdir())
    # Preflight every conflict before uploading the first byte.
    missing = []
    for path in files:
        remote = existing.get(path.name)
        if remote is None:
            missing.append(path)
            continue
        if remote['size'] != path.stat().st_size:
            raise ValueError('Existing Release asset differs: ' + path.name)
        checksum = remote.get('digest')
        if not checksum:
            with tempfile.TemporaryDirectory() as temporary:
                subprocess.run(['gh', 'release', 'download', tag, '--repo', lock['repository'], '--pattern', path.name, '--dir', temporary], check=True)
                checksum = 'sha256:' + digest(Path(temporary) / path.name)
        if checksum != 'sha256:' + digest(path):
            raise ValueError('Existing Release asset differs; use a new version: ' + path.name)
    # models.json is a completion marker: publish it after the payload and checksums.
    missing.sort(key=lambda path: (path.name == 'models.json', path.name))
    for path in missing:
        subprocess.run(['gh', 'release', 'upload', tag, str(path), '--repo', lock['repository']], check=True)
        print('Published:', path.name, flush=True)
    print('Release assets complete:', tag, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'upload'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    lock = catalog()
    if args.command == 'preflight':
        release_info(lock, args.tag)
    elif args.output is None:
        parser.error('upload requires --output')
    else:
        publish(lock, args.output, args.tag)


if __name__ == '__main__':
    main()

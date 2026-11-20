#!/usr/bin/env python3
"""Fetch pinned weights, convert RKNN graphs, and build versioned release assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RKNN = 'uvr-mdxnet-9482-rknn'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_file(path, specification):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != specification['size'] or digest(path) != specification['sha256']:
        raise ValueError('File size or SHA-256 mismatch: ' + str(path))


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.=+-]*', value):
        raise ValueError('Invalid asset name: ' + str(value))
    return value


def check_tag(tag):
    if not re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', tag):
        raise ValueError('Use a stable release tag: vMAJOR.MINOR.PATCH')
    return tag


def catalog():
    value = json.loads((ROOT / 'models.lock.json').read_text())
    if value['schemaVersion'] != 1:
        raise ValueError('Unsupported model lock format')
    identifiers, names = set(), set()
    for model in value['models']:
        if model['id'] in identifiers:
            raise ValueError('Duplicate model id')
        identifiers.add(model['id'])
        safe_name(model['importAsset'])
        for file in model['files']:
            name = safe_name(file['name'])
            if name in names or type(file['size']) is not int or file['size'] <= 0 or not re.fullmatch(r'[0-9a-f]{64}', file['sha256']):
                raise ValueError('Invalid or duplicate model file')
            if not file['upstreamUrl'].startswith('https://'):
                raise ValueError('Model sources must use HTTPS')
            names.add(name)
    conversion = rknn_spec(value)['conversion']
    source = next(model for model in value['models'] if model['id'] == conversion['sourceModel'])
    if len(source['files']) != 1 or conversion['sourceSha256'] != source['files'][0]['sha256']:
        raise ValueError('RKNN lineage must match the pinned source model')
    return value


def rknn_spec(lock):
    return next(model for model in lock['models'] if model['id'] == RKNN)


def fetch(lock, cache, reuse_dirs=()):
    cache.mkdir(parents=True, exist_ok=True)
    for model in lock['models']:
        for file in model['files']:
            target = cache / file['name']
            if target.exists():
                check_file(target, file)
                print('Checked cache:', target, flush=True)
                continue
            reusable = next((directory / file['name'] for directory in reuse_dirs if (directory / file['name']).exists()), None)
            with tempfile.TemporaryDirectory(prefix='.fetch-', dir=cache) as temporary:
                stage = Path(temporary) / file['name']
                if reusable is not None:
                    check_file(reusable, file)
                    shutil.copyfile(reusable, stage)
                else:
                    print('Downloading:', file['name'], flush=True)
                    for attempt in range(3):
                        try:
                            offset = stage.stat().st_size if stage.exists() else 0
                            if offset == file['size']:
                                break
                            headers = {'User-Agent': 'SingVerse-Model/1'}
                            if offset:
                                headers['Range'] = 'bytes=' + str(offset) + '-'
                            request = Request(file['upstreamUrl'], headers=headers)
                            with urlopen(request, timeout=60) as source:
                                if not source.url.startswith('https://'):
                                    raise ValueError('Model source redirected away from HTTPS')
                                if offset and source.status == 206:
                                    prefix = 'bytes ' + str(offset) + '-'
                                    if not source.headers.get('Content-Range', '').startswith(prefix):
                                        raise ValueError('Model server returned an unexpected byte range')
                                else:
                                    offset = 0
                                size = offset
                                with stage.open('ab' if offset else 'wb') as output:
                                    while block := source.read(1024**2):
                                        size += len(block)
                                        if size > file['size']:
                                            raise ValueError('Model exceeds pinned size')
                                        output.write(block)
                                if size != file['size']:
                                    raise OSError('Truncated model transfer: ' + str(size) + ' / ' + str(file['size']))
                            break
                        except (OSError, TimeoutError):
                            if attempt == 2:
                                raise
                            time.sleep(2 ** attempt)
                check_file(stage, file)
                # Publish the complete cache file without replacing an existing file.
                os.link(stage, target)
            print('Verified:', target, flush=True)


def validate_rknn(directory, target, specification):
    if {path.name for path in directory.iterdir()} != {'manifest.json', 'uvr.rknn'}:
        raise ValueError('RKNN directory must contain exactly manifest.json and uvr.rknn')
    document = directory / 'manifest.json'
    if document.is_symlink() or not 0 < document.stat().st_size <= 65536:
        raise ValueError('Invalid RKNN manifest')
    metadata = json.loads(document.read_text())
    for name, expected in {'target': target, 'profile': specification['profile'], 'toolkit': specification['toolkit'], 'sourceSha256': specification['sourceSha256']}.items():
        if metadata.get(name) != expected:
            raise ValueError('RKNN conversion metadata mismatch: ' + name)
    if type(metadata.get('size')) is not int or not 0 < metadata['size'] <= specification['maxBytes'] or not isinstance(metadata.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', metadata['sha256']):
        raise ValueError('Invalid RKNN size or digest')
    check_file(directory / 'uvr.rknn', metadata)
    return metadata


def convert(lock, cache, output):
    from importlib.metadata import version
    specification = rknn_spec(lock)['conversion']
    if version('rknn-toolkit2') != specification['toolkit']:
        raise ValueError('Use the pinned rknn-toolkit2 conversion environment')
    from rknn.api import RKNN
    model = next(model for model in lock['models'] if model['id'] == specification['sourceModel'])['files'][0]
    source = (cache / model['name']).resolve()
    check_file(source, model)
    output.mkdir(parents=True, exist_ok=True)
    for target in specification['targets']:
        destination = output / target
        if destination.exists():
            validate_rknn(destination, target, specification)
            print('Checked conversion:', destination, flush=True)
            continue
        with tempfile.TemporaryDirectory(prefix='.convert-', dir=output) as temporary:
            stage = Path(temporary).resolve()
            # Toolkit writes intermediate ONNX files to the working directory.
            original = Path.cwd()
            runtime = RKNN(verbose=False)
            try:
                os.chdir(stage)
                print('Converting:', target, flush=True)
                runtime.config(target_platform=target)
                if runtime.load_onnx(model=str(source), inputs=[specification['inputName']], input_size_list=[specification['inputShape']], outputs=[specification['outputName']]) != 0:
                    raise RuntimeError('RKNN ONNX load failed: ' + target)
                if runtime.build(do_quantization=specification['quantization']) != 0:
                    raise RuntimeError('RKNN conversion failed: ' + target)
                result = stage / 'uvr.rknn'
                if runtime.export_rknn(str(result)) != 0:
                    raise RuntimeError('RKNN export failed: ' + target)
            finally:
                runtime.release()
                os.chdir(original)
            metadata = {'profile': specification['profile'], 'target': target, 'toolkit': specification['toolkit'], 'sourceSha256': specification['sourceSha256'], 'size': result.stat().st_size, 'sha256': digest(result)}
            # Keep intermediates outside the deployable model directory.
            ready = stage / 'ready'
            ready.mkdir()
            result.rename(ready / result.name)
            write_json(ready / 'manifest.json', metadata)
            validate_rknn(ready, target, specification)
            ready.rename(destination)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def zip_files(path, members):
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, source in sorted(members):
            member = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            member.compress_type = zipfile.ZIP_DEFLATED
            with Path(source).open('rb') as input_stream, bundle.open(member, 'w') as output_stream:
                shutil.copyfileobj(input_stream, output_stream, 1024**2)


def asset(path, base):
    return {'name': path.name, 'size': path.stat().st_size, 'sha256': digest(path), 'url': base + quote(path.name, safe='')}


def bundle(lock, cache, rknn_dir, output, tag):
    check_tag(tag)
    if output.exists():
        raise FileExistsError('Refusing to replace a release directory: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    base = 'https://github.com/' + lock['repository'] + '/releases/download/' + tag + '/'
    with tempfile.TemporaryDirectory(prefix='.bundle-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'release'
        stage.mkdir()
        models = []
        for model in lock['models']:
            entry = {**model, 'files': []}
            for file in model['files']:
                source = cache / file['name']
                check_file(source, file)
                shutil.copyfile(source, stage / file['name'])
                entry['files'].append({**file, 'url': base + quote(file['name'], safe='')})
            if model['id'] == RKNN:
                specification = model['conversion']
                members, variants = [], []
                for target in specification['targets']:
                    directory = rknn_dir / target
                    variants.append(validate_rknn(directory, target, specification))
                    members.extend((target + '/' + name, directory / name) for name in ('manifest.json', 'uvr.rknn'))
                if sum(path.stat().st_size for _, path in members) > specification['maxBytes']:
                    raise ValueError('RKNN expanded bundle exceeds compute import limit')
                zip_files(stage / model['importAsset'], members)
                if (stage / model['importAsset']).stat().st_size > specification['maxBytes']:
                    raise ValueError('RKNN ZIP exceeds compute import limit')
                entry['variants'] = variants
            elif model['importAsset'].endswith('.zip'):
                zip_files(stage / model['importAsset'], [(file['name'], cache / file['name']) for file in model['files']])
            entry['import'] = asset(stage / model['importAsset'], base)
            models.append(entry)
        rknn_asset = stage / rknn_spec(lock)['importAsset']
        rknn_asset.with_name(rknn_asset.name + '.sha256').write_text(digest(rknn_asset) + '  ' + rknn_asset.name + '\n')
        shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', stage / 'THIRD_PARTY_NOTICES.md')
        assets = [asset(path, base) for path in sorted(stage.iterdir())]
        write_json(stage / 'models.json', {'schemaVersion': 1, 'tag': tag, 'repository': lock['repository'], 'catalogSha256': digest(ROOT / 'models.lock.json'), 'consumer': lock['consumer'], 'models': models, 'assets': assets})
        (stage / 'SHA256SUMS').write_text(''.join(digest(path) + '  ' + path.name + '\n' for path in sorted(stage.iterdir())), encoding='utf-8')
        stage.rename(output)
    print('Release assets:', output, flush=True)


def verify_release(directory, tag, lock=None):
    lock = catalog() if lock is None else lock
    check_tag(tag)
    metadata = json.loads((directory / 'models.json').read_text())
    if metadata.get('schemaVersion') != 1 or metadata.get('tag') != tag or metadata.get('repository') != lock['repository'] or metadata.get('catalogSha256') != digest(ROOT / 'models.lock.json'):
        raise ValueError('Release metadata does not match the checked-out model catalog')
    expected = {safe_name(file['name']): file for file in metadata['assets']}
    if len(expected) != len(metadata['assets']):
        raise ValueError('Duplicate release asset')
    required = {file['name'] for model in lock['models'] for file in model['files']} | {model['importAsset'] for model in lock['models']} | {'THIRD_PARTY_NOTICES.md', rknn_spec(lock)['importAsset'] + '.sha256'}
    if set(expected) != required or {path.name for path in directory.iterdir()} != required | {'models.json', 'SHA256SUMS'}:
        raise ValueError('Missing or extra release assets')
    for name, file in expected.items():
        check_file(directory / name, file)
    for model in lock['models']:
        for file in model['files']:
            check_file(directory / file['name'], file)
    sums = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ', 1)
        safe_name(name)
        if name in sums or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ValueError('Invalid checksum entry')
        sums[name] = checksum
    if set(sums) != required | {'models.json'}:
        raise ValueError('Checksum list does not cover the release')
    if any(digest(directory / name) != checksum for name, checksum in sums.items()):
        raise ValueError('Release checksum mismatch')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    for command in ('fetch', 'convert', 'bundle', 'verify'):
        sub = commands.add_parser(command)
        if command != 'verify':
            sub.add_argument('--cache', type=Path, default=ROOT / '.cache' / 'upstream')
        if command == 'fetch':
            sub.add_argument('--reuse-dir', action='append', type=Path, default=[])
        if command in ('convert', 'bundle'):
            sub.add_argument('--rknn-dir', type=Path, default=ROOT / '.cache' / 'rknn')
        if command in ('bundle', 'verify'):
            sub.add_argument('--tag', required=True)
            sub.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    lock = catalog()
    if args.command == 'list':
        for model in lock['models']:
            print(model['id'] + '\t' + model['importAsset'])
    elif args.command == 'fetch':
        fetch(lock, args.cache, args.reuse_dir)
    elif args.command == 'convert':
        convert(lock, args.cache, args.rknn_dir)
    elif args.command == 'bundle':
        bundle(lock, args.cache, args.rknn_dir, args.output, args.tag)
    else:
        verify_release(args.output, args.tag, lock)
        print('Release checksums verified:', args.output)


if __name__ == '__main__':
    main()

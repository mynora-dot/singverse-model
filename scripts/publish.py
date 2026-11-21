#!/usr/bin/env python3
"""Publish checked assets to an existing stable Release without overwriting assets."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from models import METADATA_LABELS, asset_labels, catalog, check_tag, digest, verify_release

GUIDE_START = '<!-- singverse-model-downloads:start -->'
GUIDE_END = '<!-- singverse-model-downloads:end -->'


def gh_json(*args, payload=None):
    options = {}
    if payload is not None:
        args = (*args, '--input', '-')
        options['input'] = json.dumps(payload, ensure_ascii=False)
    return json.loads(subprocess.check_output(['gh', 'api', *args], text=True, **options))


def download_guide(metadata):
    lines = [
        '## 模型下载指南', '',
        '按需要使用的功能和设备选择，通常无需下载全部文件。点击下面的中文名称即可下载。', '',
        '| 下载文件 | 用途 | 适用设备 | 后台对应模型 |',
        '| --- | --- | --- | --- |',
    ]
    for model in metadata['models']:
        link = '[' + model['import']['label'] + '](' + model['import']['url'] + ')'
        lines.append('| ' + ' | '.join((link, model['purpose'], model['devices'], model['importTarget'])) + ' |')
    lines.extend([
        '',
        '**导入方法：** 在后台的模型管理页面找到表格中的“后台对应模型”，点击“离线导入”，直接选择下载的 `.zip` 或 `.th` 文件，无需解压或手动改名。分离模型安装后仍需在目标设备完成试跑。',
        '',
        '瑞芯微版同时包含 RK3566、RK3568、RK3588，导入时自动选择当前芯片。使用独立 CPU 参考试跑或后台的轻量两轨分离能力时，还需安装“轻量人声伴奏分离-通用版”。',
        '',
        '<details>', '<summary>原始模型文件、校验码与许可说明</summary>', '',
        '附件中标注“原始模型文件”的文件供程序逐文件下载和高级用途使用；手动离线导入请选择上表的对应文件。标准伴奏的 `.th` 本身就是导入文件，只发布一份。', '',
        '| 附件名称 | 说明 |', '| --- | --- |',
    ])
    imports = {model['importAsset'] for model in metadata['models']}
    raw_names = {file['assetName'] for model in metadata['models'] for file in model['files']}
    for file in metadata['assets']:
        if file['name'] not in imports:
            description = '供程序下载或高级用途使用' if file['name'] in raw_names else '按需下载'
            lines.append('| [' + file['label'] + '](' + file['url'] + ') | ' + description + ' |')
    base = 'https://github.com/' + metadata['repository'] + '/releases/download/' + metadata['tag'] + '/'
    for name in ('models.json', 'SHA256SUMS'):
        lines.append('| [' + METADATA_LABELS[name] + '](' + base + name + ') | 按需下载 |')
    lines.extend([
        '',
        '`models.json` 是程序使用的模型清单；`SHA256SUMS` 用于检查下载是否完整。瑞芯微 ZIP 旁的 `.sha256` 提供完整包校验码，可用于后台“下载到节点”。第三方来源与许可说明随附件提供。',
        '',
        'GitHub 自动提供的 Source code（源码）压缩包是项目代码，不包含模型。',
        '', '</details>',
    ])
    return '\n'.join(lines) + '\n'


def merge_download_guide(body, guide):
    body = body or ''
    block = GUIDE_START + '\n' + guide.rstrip() + '\n' + GUIDE_END
    if GUIDE_START in body or GUIDE_END in body:
        if body.count(GUIDE_START) != 1 or body.count(GUIDE_END) != 1 or body.index(GUIDE_START) > body.index(GUIDE_END):
            raise ValueError('Invalid download guide markers; preserve and repair the release notes')
        start = body.index(GUIDE_START)
        end = body.index(GUIDE_END) + len(GUIDE_END)
        return body[:start] + block + body[end:]
    return block + ('\n\n' + body if body else '\n')


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
    return release, {file['name']: file for page in assets for file in page}


def update_download_guide(lock, tag, release_id, guide):
    endpoint = 'repos/' + lock['repository'] + '/releases/' + str(release_id)
    # Re-read the notes so edits made while uploading are preserved.
    release = gh_json(endpoint)
    if release['tag_name'] != tag or release['draft'] or release['prerelease'] or release.get('immutable'):
        raise ValueError('Release changed while publishing; cannot update its download guide')
    body = merge_download_guide(release.get('body'), guide)
    if body != (release.get('body') or ''):
        gh_json('--method', 'PATCH', endpoint, payload={'body': body})


def publish(lock, directory, tag):
    metadata = verify_release(directory, tag, lock)
    release, existing = release_info(lock, tag)
    labels = asset_labels(lock)
    guide = download_guide(metadata)
    merge_download_guide(release.get('body'), guide)
    files = sorted(directory.iterdir())
    # Preflight every conflict before uploading the first byte.
    missing, relabel = [], []
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
        if remote.get('label') != labels[path.name]:
            relabel.append((remote['id'], labels[path.name]))
    # models.json is a completion marker: publish it after the payload and checksums.
    missing.sort(key=lambda path: (path.name == 'models.json', path.name))
    for path in missing:
        if path.name == 'models.json':
            continue
        subprocess.run(['gh', 'release', 'upload', tag, str(path) + '#' + labels[path.name], '--repo', lock['repository']], check=True)
        print('Published:', path.name, flush=True)
    for identifier, label in relabel:
        gh_json('--method', 'PATCH', 'repos/' + lock['repository'] + '/releases/assets/' + str(identifier), payload={'label': label})
    update_download_guide(lock, tag, release['id'], guide)
    marker = directory / 'models.json'
    if marker in missing:
        subprocess.run(['gh', 'release', 'upload', tag, str(marker) + '#' + labels[marker.name], '--repo', lock['repository']], check=True)
        print('Published:', marker.name, flush=True)
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

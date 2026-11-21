import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import models
import publish


class ModelReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = copy.deepcopy(models.catalog())
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.rknn = self.root / 'rknn'
        self.rknn.mkdir()
        for model in self.lock['models']:
            for file in model['files']:
                data = ('controlled fixture for ' + file['name']).encode()
                (self.cache / file['name']).write_bytes(data)
                file.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        specification = models.rknn_spec(self.lock)['conversion']
        source = next(model for model in self.lock['models'] if model['id'] == specification['sourceModel'])
        specification['sourceSha256'] = source['files'][0]['sha256']
        for target in specification['targets']:
            directory = self.rknn / target
            directory.mkdir()
            graph = directory / 'uvr.rknn'
            graph.write_bytes(('compiled fixture ' + target).encode())
            models.write_json(directory / 'manifest.json', {
                'profile': specification['profile'], 'target': target, 'toolkit': specification['toolkit'],
                'sourceSha256': specification['sourceSha256'], 'size': graph.stat().st_size, 'sha256': models.digest(graph),
            })
        models.write_json(self.root / 'models.lock.json', self.lock)
        (self.root / 'THIRD_PARTY_NOTICES.md').write_text('Controlled attribution fixture\n')
        patcher = patch.object(models, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.output = self.root / 'release'

    def build(self):
        models.bundle(self.lock, self.cache, self.rknn, self.output, 'v1.0.0')
        return models.verify_release(self.output, 'v1.0.0', self.lock)

    def release(self, body='手写发布说明\n'):
        return {'id': 1, 'tag_name': 'v1.0.0', 'draft': False, 'prerelease': False, 'body': body}

    def remote_assets(self, exclude=()):
        labels = models.asset_labels(self.lock)
        return {
            path.name: {'id': index, 'size': path.stat().st_size, 'digest': 'sha256:' + models.digest(path), 'label': labels[path.name]}
            for index, path in enumerate(sorted(self.output.iterdir()), 10) if path.name not in exclude
        }

    def test_bundles_fit_the_consumers_exact_import_layout(self):
        metadata = self.build()
        self.assertEqual(len(metadata['models']), 5)
        for model in self.lock['models']:
            if not model['importAsset'].endswith('.zip'):
                continue
            with zipfile.ZipFile(self.output / model['importAsset']) as archive:
                expected = {file['name'] for file in model['files']}
                if model['id'] == models.RKNN:
                    expected = {target + '/' + name for target in model['conversion']['targets'] for name in ('manifest.json', 'uvr.rknn')}
                self.assertEqual(set(archive.namelist()), expected)
                self.assertIsNone(archive.testzip())
                self.assertTrue(all((item.external_attr >> 16) & 0o170000 == 0o100000 for item in archive.infolist()))
        self.assertTrue(all('/singverse-model/releases/download/v1.0.0/' in file['url'] for file in metadata['assets']))

    def test_friendly_download_names_labels_and_original_file_names_agree(self):
        metadata = self.build()
        imports = {
            'panns-cnn6': ('singverse-track-recognition-universal.zip', '原唱与伴奏识别-通用版.zip'),
            'htdemucs': ('singverse-accompaniment-universal.th', '标准伴奏生成-通用版.th'),
            'htdemucs-openvino': ('singverse-accompaniment-intel.zip', '标准伴奏生成-Intel显卡版.zip'),
            'uvr-mdxnet-9482': ('singverse-vocal-accompaniment-universal.zip', '轻量人声伴奏分离-通用版.zip'),
            models.RKNN: ('singverse-vocal-accompaniment-rockchip.zip', '人声伴奏分离-瑞芯微版.zip'),
        }
        self.assertEqual(len(list(self.output.iterdir())), 13)
        assets = {file['name']: file for file in metadata['assets']}
        for model in metadata['models']:
            name, label = imports[model['id']]
            self.assertEqual((model['import']['name'], model['import']['label']), (name, label))
            self.assertEqual(model['import'], assets[name])
            for file in model['files']:
                self.assertTrue(file['url'].endswith('/' + file['assetName']))
                self.assertEqual((self.output / file['assetName']).read_bytes(), (self.cache / file['name']).read_bytes())
                self.assertFalse((self.output / file['name']).exists())
                if file['assetName'] != model['importAsset']:
                    self.assertIn('原始模型文件', assets[file['assetName']]['label'])
        self.assertTrue((self.cache / 'Cnn6_mAP=0.343.pth').is_file())
        rockchip = 'singverse-vocal-accompaniment-rockchip.zip'
        self.assertEqual((self.output / (rockchip + '.sha256')).read_text(), models.digest(self.output / rockchip) + '  ' + rockchip + '\n')

    def test_release_metadata_cannot_point_to_old_names_or_unchecked_labels(self):
        original = self.build()
        for field, value in (('url', 'https://example.invalid/old-name.zip'), ('label', 'incorrect label')):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed['assets'][0][field] = value
                models.write_json(self.output / 'models.json', changed)
                with self.assertRaisesRegex(ValueError, 'label or URL'):
                    models.verify_release(self.output, 'v1.0.0', self.lock)
        changed = copy.deepcopy(original)
        changed['models'][0]['files'][0]['url'] = 'https://example.invalid/old-name.pth'
        models.write_json(self.output / 'models.json', changed)
        with self.assertRaisesRegex(ValueError, 'model does not match'):
            models.verify_release(self.output, 'v1.0.0', self.lock)

    def test_catalog_rejects_normalized_names_and_colliding_output_files(self):
        for invalid in ('Cnn6_mAP=0.343.pth', '中文.pth', '../escaped.pth', 'weights.pth.'):
            with self.subTest(name=invalid):
                changed = copy.deepcopy(self.lock)
                changed['models'][0]['files'][0]['assetName'] = invalid
                models.write_json(self.root / 'models.lock.json', changed)
                with self.assertRaisesRegex(ValueError, 'published asset name'):
                    models.catalog()
        changed = copy.deepcopy(self.lock)
        changed['models'][1]['files'][0]['assetName'] = changed['models'][0]['importAsset']
        models.write_json(self.root / 'models.lock.json', changed)
        with self.assertRaisesRegex(ValueError, 'Duplicate published'):
            models.catalog()

    def test_source_mtimes_do_not_change_zip_or_release_bytes(self):
        self.build()
        for path in self.cache.iterdir():
            os.utime(path, (1730000000, 1730000000))
        second = self.root / 'second'
        models.bundle(self.lock, self.cache, self.rknn, second, 'v1.0.0')
        self.assertEqual({path.name: models.digest(path) for path in self.output.iterdir()}, {path.name: models.digest(path) for path in second.iterdir()})

    def test_invalid_rknn_target_or_graph_never_publishes_a_directory(self):
        document = self.rknn / 'rk3566' / 'manifest.json'
        metadata = json.loads(document.read_text())
        metadata['target'] = 'rk3588'
        models.write_json(document, metadata)
        with self.assertRaisesRegex(ValueError, 'target'):
            self.build()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.bundle-*')))

    def test_corrupt_weights_and_release_assets_are_rejected(self):
        self.build()
        target = self.output / 'singverse-vocal-accompaniment-universal.onnx'
        target.write_bytes(b'x' * target.stat().st_size)
        with self.assertRaises(ValueError):
            models.verify_release(self.output, 'v1.0.0', self.lock)
        with self.assertRaises(FileExistsError):
            self.build()

    def test_incomplete_or_extra_release_files_are_rejected(self):
        self.build()
        extra = self.output / 'private.txt'
        extra.write_text('not a release asset')
        with self.assertRaisesRegex(ValueError, 'extra'):
            models.verify_release(self.output, 'v1.0.0', self.lock)
        extra.unlink()
        (self.output / 'singverse-track-recognition-universal.zip').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            models.verify_release(self.output, 'v1.0.0', self.lock)

    def test_failed_fetch_does_not_leave_an_installable_cache_file(self):
        file = self.lock['models'][0]['files'][0]
        target = self.cache / file['name']
        target.unlink()
        response = io.BytesIO(b'x' * file['size'])
        response.url = file['upstreamUrl']
        with patch.object(models, 'urlopen', return_value=response):
            with self.assertRaises(ValueError):
                models.fetch(self.lock, self.cache)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.cache.glob('.fetch-*')))

    def test_an_existing_bad_cache_is_preserved(self):
        file = self.lock['models'][0]['files'][0]
        target = self.cache / file['name']
        target.write_bytes(b'preserve existing local file')
        with patch.object(models, 'urlopen') as fetch:
            with self.assertRaises(ValueError):
                models.fetch(self.lock, self.cache)
        fetch.assert_not_called()
        self.assertEqual(target.read_bytes(), b'preserve existing local file')

    def test_truncated_download_resumes_before_the_final_checksum(self):
        file = self.lock['models'][0]['files'][0]
        target = self.cache / file['name']
        data = target.read_bytes()
        target.unlink()
        first, second = io.BytesIO(data[:7]), io.BytesIO(data[7:])
        first.url = second.url = file['upstreamUrl']
        first.status, second.status = 200, 206
        second.headers = {'Content-Range': f'bytes 7-{len(data)-1}/{len(data)}'}
        with patch.object(models, 'urlopen', side_effect=[first, second]) as request, patch.object(models.time, 'sleep'):
            models.fetch(self.lock, self.cache)
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(request.call_args_list[1].args[0].get_header('Range'), 'bytes=7-')

    def test_invalid_version_never_causes_a_network_request(self):
        with patch.object(publish, 'gh_json') as request:
            for tag in ('latest', 'v01.0.0', 'v1.0.0-beta', '../v1.0.0', 'v1.0.0;echo'):
                with self.assertRaises(ValueError):
                    publish.release_info(self.lock, tag)
            request.assert_not_called()

    def test_a_moved_remote_tag_is_rejected(self):
        release = {'id': 1, 'tag_name': 'v1.0.0', 'draft': False, 'prerelease': False}
        with patch.object(publish, 'gh_json', side_effect=[release, {'sha': 'b' * 40}]), patch.object(publish.subprocess, 'check_output', return_value='a' * 40 + '\n'):
            with self.assertRaisesRegex(ValueError, 'no longer matches'):
                publish.release_info(self.lock, 'v1.0.0')

    def test_an_immutable_release_stops_before_source_or_upload_operations(self):
        release = {'tag_name': 'v1.0.0', 'draft': False, 'prerelease': False, 'immutable': True}
        with patch.object(publish, 'gh_json', return_value=release), patch.object(publish.subprocess, 'check_output') as git:
            with self.assertRaisesRegex(ValueError, 'immutable'):
                publish.release_info(self.lock, 'v1.0.0')
            git.assert_not_called()

    def test_a_remote_conflict_is_found_before_any_upload(self):
        self.build()
        name = 'singverse-vocal-accompaniment-universal.zip'
        existing = {name: {'size': (self.output / name).stat().st_size, 'digest': 'sha256:' + '0' * 64}}
        with patch.object(publish, 'release_info', return_value=(self.release(), existing)), patch.object(publish.subprocess, 'run') as run, patch.object(publish, 'gh_json') as api:
            with self.assertRaisesRegex(ValueError, 'differs'):
                publish.publish(self.lock, self.output, 'v1.0.0')
            run.assert_not_called()
            api.assert_not_called()

    def test_retry_reuses_existing_bytes_and_publishes_manifest_last(self):
        metadata = self.build()
        name = 'singverse-track-recognition-universal.zip'
        existing = self.remote_assets(exclude=('models.json', name))
        events = []

        def api(*args, **kwargs):
            events.append(('api', args, kwargs))
            return self.release('上传期间补充的手写说明\n')

        def upload(command, **kwargs):
            events.append(('upload', command[4]))

        with patch.object(publish, 'release_info', return_value=(self.release(), existing)), patch.object(publish.subprocess, 'run', side_effect=upload) as run, patch.object(publish, 'gh_json', side_effect=api):
            publish.publish(self.lock, self.output, 'v1.0.0')
        uploaded = [Path(call.args[0][4].split('#')[0]).name for call in run.call_args_list]
        self.assertEqual(uploaded, [name, 'models.json'])
        self.assertEqual(events[-1], ('upload', str(self.output / 'models.json') + '#' + models.METADATA_LABELS['models.json']))
        patch_body = next(event[2]['payload']['body'] for event in events if event[0] == 'api' and 'payload' in event[2])
        self.assertTrue(patch_body.endswith('上传期间补充的手写说明\n'))
        self.assertIn(publish.download_guide(metadata).strip(), patch_body)

    def test_initial_upload_sets_every_label_and_keeps_manifest_last(self):
        self.build()
        with patch.object(publish, 'release_info', return_value=(self.release(), {})), patch.object(publish.subprocess, 'run') as run, patch.object(publish, 'gh_json', return_value=self.release()):
            publish.publish(self.lock, self.output, 'v1.0.0')
        uploaded = [call.args[0][4] for call in run.call_args_list]
        self.assertEqual(set(uploaded), {str(self.output / name) + '#' + label for name, label in models.asset_labels(self.lock).items()})
        self.assertTrue(uploaded[-1].endswith('models.json#' + models.METADATA_LABELS['models.json']))

    def test_retry_repairs_labels_without_reuploading_matching_assets(self):
        metadata = self.build()
        release = self.release(publish.merge_download_guide('', publish.download_guide(metadata)))
        existing = self.remote_assets()
        for file in existing.values():
            file['label'] = None
        with patch.object(publish, 'release_info', return_value=(release, existing)), patch.object(publish.subprocess, 'run') as run, patch.object(publish, 'gh_json', return_value=release) as api:
            publish.publish(self.lock, self.output, 'v1.0.0')
        run.assert_not_called()
        edits = [call for call in api.call_args_list if call.kwargs.get('payload')]
        self.assertEqual(len(edits), 13)
        for name, file in existing.items():
            api.assert_any_call('--method', 'PATCH', 'repos/' + self.lock['repository'] + '/releases/assets/' + str(file['id']), payload={'label': models.asset_labels(self.lock)[name]})

    def test_completed_publication_does_not_repeat_uploads_or_edit_notes(self):
        metadata = self.build()
        release = self.release(publish.merge_download_guide('作者说明\n', publish.download_guide(metadata)))
        with patch.object(publish, 'release_info', return_value=(release, self.remote_assets())), patch.object(publish.subprocess, 'run') as run, patch.object(publish, 'gh_json', return_value=release) as api:
            publish.publish(self.lock, self.output, 'v1.0.0')
        run.assert_not_called()
        api.assert_called_once_with('repos/' + self.lock['repository'] + '/releases/1')

    def test_download_guide_links_all_user_downloads_and_preserves_manual_notes(self):
        metadata = self.build()
        guide = publish.download_guide(metadata)
        for model in metadata['models']:
            self.assertIn('[' + model['import']['label'] + '](' + model['import']['url'] + ')', guide)
            self.assertIn(model['importTarget'], guide)
        for chip in ('RK3566', 'RK3568', 'RK3588'):
            self.assertIn(chip, guide)
        self.assertIn('原始模型文件', guide)
        notes = '手写说明：保留空行、`$()`、中文和 # 标题。\n\n原文结束\n'
        merged = publish.merge_download_guide(notes, guide)
        self.assertTrue(merged.startswith(publish.GUIDE_START))
        self.assertTrue(merged.endswith(notes))
        self.assertEqual(publish.merge_download_guide(merged, guide), merged)
        updated = publish.merge_download_guide(merged, '更新后的下载指南\n')
        self.assertEqual(updated.count(publish.GUIDE_START), 1)
        self.assertTrue(updated.endswith(notes))
        self.assertNotIn(guide.strip(), updated)

    def test_invalid_guide_markers_stop_before_remote_writes(self):
        self.build()
        for body in (publish.GUIDE_START, publish.GUIDE_END + publish.GUIDE_START, publish.GUIDE_START * 2 + publish.GUIDE_END):
            with self.subTest(body=body), patch.object(publish, 'release_info', return_value=(self.release(body), {})), patch.object(publish.subprocess, 'run') as run, patch.object(publish, 'gh_json') as api:
                with self.assertRaisesRegex(ValueError, 'guide markers'):
                    publish.publish(self.lock, self.output, 'v1.0.0')
                run.assert_not_called()
                api.assert_not_called()

    def test_guide_update_failure_does_not_publish_completion_marker(self):
        self.build()
        with patch.object(publish, 'release_info', return_value=(self.release(), {})), patch.object(publish.subprocess, 'run') as run, patch.object(publish, 'gh_json', side_effect=[self.release(), RuntimeError('notes update failed')]):
            with self.assertRaisesRegex(RuntimeError, 'notes update failed'):
                publish.publish(self.lock, self.output, 'v1.0.0')
        self.assertEqual(len(run.call_args_list), 12)
        self.assertFalse(any('models.json#' in call.args[0][4] for call in run.call_args_list))

    def test_unicode_label_and_multiline_notes_are_sent_as_json_on_stdin(self):
        payload = {'label': '原唱与伴奏识别-通用版.zip', 'body': '第一行\n第二行 `$(literal)`\n'}
        with patch.object(publish.subprocess, 'check_output', return_value='{}') as run:
            publish.gh_json('--method', 'PATCH', 'repos/example/releases/1', payload=payload)
        self.assertEqual(run.call_args.args[0][-2:], ['--input', '-'])
        self.assertEqual(json.loads(run.call_args.kwargs['input']), payload)


if __name__ == '__main__':
    unittest.main()

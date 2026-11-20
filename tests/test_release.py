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
        target = self.output / 'UVR_MDXNET_9482.onnx'
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
        (self.output / 'panns-cnn6.zip').unlink()
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
        name = 'uvr-mdxnet-9482.zip'
        existing = {name: {'size': (self.output / name).stat().st_size, 'digest': 'sha256:' + '0' * 64}}
        with patch.object(publish, 'release_info', return_value=existing), patch.object(publish.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'differs'):
                publish.publish(self.lock, self.output, 'v1.0.0')
            run.assert_not_called()

    def test_retry_reuses_existing_bytes_and_publishes_manifest_last(self):
        self.build()
        existing = {path.name: {'size': path.stat().st_size, 'digest': 'sha256:' + models.digest(path)} for path in self.output.iterdir() if path.name not in ('models.json', 'panns-cnn6.zip')}
        with patch.object(publish, 'release_info', return_value=existing), patch.object(publish.subprocess, 'run') as run:
            publish.publish(self.lock, self.output, 'v1.0.0')
            uploaded = [Path(call.args[0][4]).name for call in run.call_args_list]
            self.assertEqual(uploaded, ['panns-cnn6.zip', 'models.json'])


if __name__ == '__main__':
    unittest.main()

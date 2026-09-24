"""Original-file metadata and endpoint contracts; no device access."""
import json
import shutil
import subprocess

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.media_metadata import extract_metadata
from app.services.files import FileBrowser

client = TestClient(create_app())


def photo(path):
    exif = Image.Exif()
    exif[271] = 'Test Camera'
    exif[272] = 'Phone Model'
    exif[34665] = {36867: '2026:09:21 10:20:30', 36881: '-05:00', 42036: 'Wide Lens'}
    exif[34853] = {1: 'S', 2: (0.0, 15.0, 0.0), 3: 'W', 4: (78.0, 30.0, 0.0)}
    Image.new('RGB', (40, 30)).save(path, exif=exif)


@pytest.mark.parametrize('fallback', [False, True])
def test_original_photo_dates_camera_gps_and_dimensions(tmp_path, monkeypatch, fallback):
    path = tmp_path / 'photo.jpg'
    photo(path)
    if fallback:
        monkeypatch.setattr('app.services.media_metadata.shutil.which', lambda _: None)
    elif not shutil.which('exiftool'):
        pytest.skip('ExifTool not installed')
    data = extract_metadata(path)
    summary = {f['label']: f['value'] for f in data['summary']}
    assert '2026:09:21 10:20:30' in summary['Captured']
    assert summary['Time zone'] == '-05:00'
    assert summary['Camera make'] == 'Test Camera'
    assert summary['Lens'] == 'Wide Lens'
    assert summary['Width'] == '40'
    assert summary['Height'] == '30'
    assert 'Location' in summary
    if fallback:
        assert summary['Location'] == '-0.250000, -78.500000'
    else:
        assert 'S' in summary['Location'] and 'W' in summary['Location']
    assert str(tmp_path) not in json.dumps(data)
    assert 'File Modification Date' not in json.dumps(data)


def test_video_original_tags_and_streams(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg not installed')
    path = tmp_path / 'video.mov'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=32x24:rate=10',
                    '-t', '0.2', '-c:v', 'mpeg4', '-metadata', 'creation_time=2026-09-21T15:20:30Z',
                    '-metadata', 'location=-00.2500-078.5000/', str(path)], check=True, timeout=20)
    data = extract_metadata(path)
    summary = {f['label']: f['value'] for f in data['summary']}
    assert '2026' in summary['Captured']
    assert 'Location' in summary
    assert summary['Width'] == '32' and summary['Height'] == '24'
    assert 'Duration' in summary and 'Frame rate' in summary and 'Codec' in summary
    assert any(s['name'] == 'Stream 1 (video)' for s in data['sections'])
    assert str(tmp_path) not in json.dumps(data)


def test_corrupt_file_and_missing_tools_are_honest(tmp_path, monkeypatch):
    monkeypatch.setattr('app.services.media_metadata.shutil.which', lambda _: None)
    path = tmp_path / 'broken.jpg'
    path.write_bytes(b'not an image')
    data = extract_metadata(path)
    assert data['sections'] == [] and data['summary'] == []
    assert data['notes']


def test_plain_image_does_not_invent_capture_time_or_location(tmp_path, monkeypatch):
    monkeypatch.setattr('app.services.media_metadata.shutil.which', lambda _: None)
    path = tmp_path / 'plain.png'
    Image.new('RGB', (10, 20)).save(path)
    data = extract_metadata(path)
    assert not {'Captured', 'Location'} & {f['label'] for f in data['summary']}
    assert data['sections']


def test_metadata_endpoint_validates_and_reports_unavailable():
    assert client.get('/files/metadata', params={'path': '/a/../b'}).status_code == 400
    assert client.get('/files/metadata', params={'path': '/DCIM/photo.jpg'}).status_code == 404


def test_metadata_endpoint_cleans_original(tmp_path, monkeypatch):
    folder = tmp_path / 'pulled'
    folder.mkdir()
    path = folder / 'photo.jpg'
    photo(path)
    browser = FileBrowser(available=True)
    monkeypatch.setattr(FileBrowser, 'remote_size', lambda *a: 100)
    monkeypatch.setattr(FileBrowser, 'pull_file', lambda *a, **kw: path)
    monkeypatch.setattr('app.routers.files.get_browser', lambda: browser)
    response = client.get('/files/metadata', params={'udid': 'TEST', 'path': '/DCIM/photo.jpg'})
    assert response.status_code == 200
    assert response.json()['summary']
    assert not folder.exists()


def test_metadata_endpoint_rejects_large_files_without_pulling(monkeypatch):
    browser = FileBrowser(available=True)
    monkeypatch.setattr(FileBrowser, 'remote_size', lambda *a: 501 * 1024 * 1024)
    def fail(*a, **kw):
        pytest.fail('oversized file must not be pulled')
    monkeypatch.setattr(FileBrowser, 'pull_file', fail)
    monkeypatch.setattr('app.routers.files.get_browser', lambda: browser)
    response = client.get('/files/metadata', params={'udid': 'TEST', 'path': '/DCIM/video.mov'})
    assert response.status_code == 413

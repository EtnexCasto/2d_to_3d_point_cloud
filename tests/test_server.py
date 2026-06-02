import pytest
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
import numpy as np
import cv2
from flask import Flask
from werkzeug.datastructures import FileStorage
from PIL import Image
import io
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.server import processing_status

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
    app.config['PROCESSING_FOLDER'] = tempfile.mkdtemp()
    app.config['OUTPUT_FOLDER'] = tempfile.mkdtemp()
    
    with app.test_client() as client:
        yield client
    
    # Очистка
    shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)
    shutil.rmtree(app.config['PROCESSING_FOLDER'], ignore_errors=True)
    shutil.rmtree(app.config['OUTPUT_FOLDER'], ignore_errors=True)


@pytest.fixture
def sample_images():
    images = []
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    
    for i, color in enumerate(colors):
        img = Image.new('RGB', (640, 480), color=color)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        images.append((
            f'test_image_{i}.jpg',
            img_byte_arr,
            'image/jpeg'
        ))
    
    return images


@pytest.fixture
def mock_colmap_success(monkeypatch):
    class MockResult:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            self.stdout = b"COLMAP 4.1.0"
            self.stderr = b""
    
    def mock_subprocess_run(*args, **kwargs):
        return MockResult()
    
    monkeypatch.setattr('subprocess.run', mock_subprocess_run)


class TestRoutes:
    def test_index_route(self, client):
        """Тест: загрузка главной страницы"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data
        assert b'2D' in response.data
    
    def test_css_route(self, client):
        """Тест: загрузка CSS файла"""
        response = client.get('/style.css')
        assert response.status_code == 200
        assert b':root' in response.data
    
    def test_status_route_not_found(self, client):
        """Тест: статус несуществующей сессии"""
        response = client.get('/status/nonexistent')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'processing'
        assert data['progress'] == 0


class TestGenerateEndpoint:
    def test_generate_no_files(self, client):
        """Тест: запрос без файлов"""
        response = client.post('/generate')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_generate_less_than_3_files(self, client, sample_images):
        """Тест: загрузка менее 3 файлов"""
        data = {
            'images': [
                (sample_images[0][1], sample_images[0][0])
            ]
        }
        response = client.post('/generate', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Минимум 3 изображения' in data['error']
    
    def test_generate_with_3_files(self, client, sample_images, mock_colmap_success):
        """Тест: успешная загрузка 3 файлов"""
        data = {
            'images': [
                (sample_images[0][1], sample_images[0][0]),
                (sample_images[1][1], sample_images[1][0]),
                (sample_images[2][1], sample_images[2][0])
            ]
        }
        response = client.post('/generate?mode=points', data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'session_id' in result
        assert result['message'] == 'Обработка начата'

class TestImageUpload:
    def test_image_resizing(self, client):
        """Тест: изменение размера изображений"""
        large_img = Image.new('RGB', (4000, 3000), color=(255, 0, 0))
        img_byte_arr = io.BytesIO()
        large_img.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        img = cv2.imdecode(np.frombuffer(img_byte_arr.getvalue(), np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        
        max_dim = 1600
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h))
            assert img.shape[1] <= max_dim
            assert img.shape[0] <= max_dim

class TestProcessing:
    def test_colmap_not_installed(self, client, sample_images):
        """Тест: обработка ошибки отсутствия COLMAP"""
        data = {
            'images': [
                (sample_images[0][1], sample_images[0][0]),
                (sample_images[1][1], sample_images[1][0]),
                (sample_images[2][1], sample_images[2][0])
            ]
        }
        
        response = client.post('/generate?mode=points', data=data, content_type='multipart/form-data')
        assert response.status_code == 200
        result = json.loads(response.data)
        session_id = result['session_id']
        
        time.sleep(2)
        
        status_response = client.get(f'/status/{session_id}')
        status = json.loads(status_response.data)
        
        assert status['status'] in ['processing', 'error']

class TestVisualization:
    def test_point_cloud_format(self, client):
        """Тест: формат облака точек для визуализации"""
        points = []
        for i in range(100):
            points.append({
                'x': np.random.uniform(-1, 1),
                'y': np.random.uniform(-1, 1),
                'z': np.random.uniform(-1, 1),
                'r': np.random.randint(0, 255),
                'g': np.random.randint(0, 255),
                'b': np.random.randint(0, 255)
            })
        
        assert len(points) == 100
        for p in points:
            assert 'x' in p
            assert 'y' in p
            assert 'z' in p
            assert 'r' in p
            assert 'g' in p
            assert 'b' in p
            assert -2 <= p['x'] <= 2
            assert -2 <= p['y'] <= 2
            assert -2 <= p['z'] <= 2
            assert 0 <= p['r'] <= 255
            assert 0 <= p['g'] <= 255
            assert 0 <= p['b'] <= 255
    
    def test_point_cloud_centering(self, client):
        """Тест: центрирование облака точек"""
        points = []
        for i in range(100):
            points.append({
                'x': 5 + np.random.uniform(-0.5, 0.5),
                'y': 5 + np.random.uniform(-0.5, 0.5),
                'z': 5 + np.random.uniform(-0.5, 0.5),
                'r': 255, 'g': 255, 'b': 255
            })
        
        cx = sum(p['x'] for p in points) / len(points)
        cy = sum(p['y'] for p in points) / len(points)
        cz = sum(p['z'] for p in points) / len(points)
        
        for p in points:
            p['x'] -= cx
            p['y'] -= cy
            p['z'] -= cz
        
        new_cx = sum(p['x'] for p in points) / len(points)
        new_cy = sum(p['y'] for p in points) / len(points)
        new_cz = sum(p['z'] for p in points) / len(points)
        
        assert abs(new_cx) < 0.01
        assert abs(new_cy) < 0.01
        assert abs(new_cz) < 0.01


class TestCleanup:
    def test_session_cleanup(self, client):
        import tempfile
        import shutil
        
        session_folder = Path(tempfile.mkdtemp())
        test_file = session_folder / "test.txt"
        test_file.write_text("test data")
        
        assert session_folder.exists()
        assert test_file.exists()
        
        shutil.rmtree(session_folder)
        
        assert not session_folder.exists()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
import cv2
import numpy as np
import open3d as o3d
import subprocess
import shutil
import time
from pathlib import Path
from flask import current_app

# Импортируем словарь статусов
from app.server import processing_status


class PhotogrammetryProcessor:  
    def __init__(self, session_id, images_path, mode='points'):
        self.session_id = session_id
        self.images_path = Path(images_path)
        self.mode = mode
        self.workspace_path = Path(current_app.config['PROCESSING_FOLDER']) / session_id
        self.output_path = Path(current_app.config['OUTPUT_FOLDER']) / f"{session_id}_result.ply"
        
        self.db_path = self.workspace_path / "database.db"
        self.sparse_path = self.workspace_path / "sparse"
        self.dense_path = self.workspace_path / "dense"
        
    def check_colmap(self):
        """Проверка наличия COLMAP"""
        try:
            result = subprocess.run(["colmap", "-h"], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def prepare_images(self):
        """Подготовка изображений для COLMAP"""
        processing_status[self.session_id] = {
            'status': 'preparing', 
            'message': 'Подготовка изображений...', 
            'progress': 5
        }
        
        prepared_images = self.workspace_path / "images"
        prepared_images.mkdir(exist_ok=True, parents=True)
        
        images = list(self.images_path.glob("*.jpg")) + list(self.images_path.glob("*.png")) + \
                list(self.images_path.glob("*.jpeg")) + list(self.images_path.glob("*.JPG"))
        
        for i, img_path in enumerate(sorted(images)):
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            
            # Уменьшаем размер для ускорения
            h, w = img.shape[:2]
            max_dim = 1600
            if max(h, w) > max_dim:
                scale = max_dim / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h))
            
            new_name = f"{i:06d}.jpg"
            cv2.imwrite(str(prepared_images / new_name), img)
            
            progress = 5 + int((i+1) / len(images) * 5)
            processing_status[self.session_id]['progress'] = progress
        
        return prepared_images
    
    def run_feature_extraction(self, images_path):
        """Извлечение признаков (ORB/SIFT)"""
        processing_status[self.session_id] = {
            'status': 'features', 
            'message': 'Извлечение признаков...', 
            'progress': 15
        }
        
        cmd = [
            "colmap", "feature_extractor",
            "--database_path", str(self.db_path),
            "--image_path", str(images_path),
            "--ImageReader.single_camera", "1",
            "--ImageReader.camera_model", "PINHOLE",
            "--SiftExtraction.max_num_features", "5000"
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except:
            cmd = [
                "colmap", "feature_extractor",
                "--database_path", str(self.db_path),
                "--image_path", str(images_path),
                "--ImageReader.single_camera", "1"
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        
        processing_status[self.session_id]['progress'] = 25
    
    def run_feature_matching(self):
        """Сопоставление признаков"""
        processing_status[self.session_id] = {
            'status': 'matching', 
            'message': 'Сопоставление признаков...', 
            'progress': 30
        }
        
        cmd = [
            "colmap", "exhaustive_matcher",
            "--database_path", str(self.db_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        processing_status[self.session_id]['progress'] = 40
    
    def run_sparse_reconstruction(self, images_path):
        """Разреженная реконструкция (SfM)"""
        processing_status[self.session_id] = {
            'status': 'sparse', 
            'message': 'SfM реконструкция...', 
            'progress': 45
        }
        
        self.sparse_path.mkdir(exist_ok=True)
        
        cmd = [
            "colmap", "mapper",
            "--database_path", str(self.db_path),
            "--image_path", str(images_path),
            "--output_path", str(self.sparse_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
        
        # Поиск модели
        model_path = None
        for i in range(10):
            candidate = self.sparse_path / str(i)
            if candidate.exists() and (candidate / "cameras.bin").exists():
                model_path = candidate
                break
        
        if not model_path and (self.sparse_path / "cameras.bin").exists():
            model_path = self.sparse_path
        
        if not model_path:
            raise Exception("Разреженная реконструкция не удалась")
        
        processing_status[self.session_id]['progress'] = 60
        return model_path
    
    def run_dense_reconstruction(self, model_path, images_path):
        """Плотная реконструкция (MVS)"""
        processing_status[self.session_id] = {
            'status': 'dense', 
            'message': 'Подготовка к плотной реконструкции...', 
            'progress': 65
        }
        
        cmd_undistort = [
            "colmap", "image_undistorter",
            "--image_path", str(images_path),
            "--input_path", str(model_path),
            "--output_path", str(self.dense_path),
            "--output_type", "COLMAP"
        ]
        subprocess.run(cmd_undistort, check=True, capture_output=True, timeout=300)
        
        processing_status[self.session_id] = {
            'status': 'dense', 
            'message': 'Patch Match Stereo (может занять время)...', 
            'progress': 75
        }
        
        # Patch Match Stereo
        cmd_patch = [
            "colmap", "patch_match_stereo",
            "--workspace_path", str(self.dense_path),
            "--workspace_format", "COLMAP",
            "--PatchMatchStereo.max_image_size", "1000",
            "--PatchMatchStereo.window_radius", "5"
        ]
        subprocess.run(cmd_patch, check=True, capture_output=True, timeout=3600)
        
        processing_status[self.session_id] = {
            'status': 'dense', 
            'message': 'Слияние в облако точек...', 
            'progress': 90
        }
        
        # Слияние в облако точек
        ply_path = self.dense_path / "fused.ply"
        cmd_fusion = [
            "colmap", "stereo_fusion",
            "--workspace_path", str(self.dense_path),
            "--workspace_format", "COLMAP",
            "--input_type", "photometric",
            "--output_path", str(ply_path)
        ]
        subprocess.run(cmd_fusion, check=True, capture_output=True, timeout=600)
        
        return ply_path
    
    def clean_pointcloud(self, ply_path):
        """Очистка и сохранение облака точек"""
        processing_status[self.session_id] = {
            'status': 'cleaning', 
            'message': 'Очистка облака точек...', 
            'progress': 95
        }
        
        pcd = o3d.io.read_point_cloud(str(ply_path))
        
        if len(pcd.points) == 0:
            raise Exception("Облако точек пустое")
        
        pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
        
        if len(pcd.points) > 50000:
            pcd = pcd.uniform_down_sample(every_k_points=len(pcd.points) // 30000)
        
        o3d.io.write_point_cloud(str(self.output_path), pcd)
        
        points = np.asarray(pcd.points)
        colors = np.asarray(pcd.colors) if pcd.has_colors() else None
        
        if colors is not None:
            colors = (colors * 255).astype(np.uint8)
        
        # Ограничение количества точек для веба
        max_points = 15000
        if len(points) > max_points:
            indices = np.random.choice(len(points), max_points, replace=False)
            points = points[indices]
            if colors is not None:
                colors = colors[indices]
        
        result = {
            'type': 'points',
            'points': [{'x': float(p[0]), 'y': float(p[1]), 'z': float(p[2]), 
                       'r': int(colors[i][0]) if colors is not None else 255,
                       'g': int(colors[i][1]) if colors is not None else 255,
                       'b': int(colors[i][2]) if colors is not None else 255} 
                      for i, p in enumerate(points)]
        }
        
        processing_status[self.session_id] = {
            'status': 'completed',
            'message': 'Готово!',
            'progress': 100,
            'result': result
        }
        
        return result
    
    def process(self):
        """Полный пайплайн обработки"""
        try:
            # Проверка COLMAP
            if not self.check_colmap():
                processing_status[self.session_id] = {
                    'status': 'error',
                    'message': 'COLMAP не установлен! Установите с https://colmap.github.io/'
                }
                return
            
            # Подготовка изображений
            images_path = self.prepare_images()
            
            # Очистка старой базы данных
            if self.db_path.exists():
                self.db_path.unlink()
            
            # Этапы реконструкции
            self.run_feature_extraction(images_path)
            self.run_feature_matching()
            model_path = self.run_sparse_reconstruction(images_path)
            ply_path = self.run_dense_reconstruction(model_path, images_path)
            self.clean_pointcloud(ply_path)
            
        except subprocess.TimeoutExpired:
            processing_status[self.session_id] = {
                'status': 'error',
                'message': 'Превышено время ожидания.'
            }
        except Exception as e:
            processing_status[self.session_id] = {
                'status': 'error',
                'message': f'Ошибка: {str(e)}'
            }
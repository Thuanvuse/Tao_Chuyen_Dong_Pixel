import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QSlider, QComboBox, QFileDialog, 
    QCheckBox, QSpinBox, QMessageBox, QFrame, QSplitter,
    QDialog, QProgressBar, QTabWidget, QGridLayout
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QIcon, QImage, QAction, QFont, QKeySequence, QBrush, QPainter, QPen, QMouseEvent
from PIL import Image

from canvas import ImageCanvas
from processor import ImageProcessor, pil_to_qimage, qimage_to_pil

# Helper function for resource paths (useful when compiled with PyInstaller)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class LoadingDialog(QDialog):
    def __init__(self, message: str, parent=None):
        super().__init__(parent, Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.setWindowTitle("Đang xử lý (Processing)")
        self.setModal(True)
        self.setFixedSize(320, 110)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Infinite animation
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        
        # Apply dark styling matching the main app
        self.setStyleSheet("""
            QDialog {
                background-color: #141419;
                border: 1px solid #252530;
                border-radius: 8px;
            }
            QLabel {
                color: #e5e9f0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
            }
            QProgressBar {
                border: 1px solid #2d2d3a;
                background-color: #14141a;
                height: 14px;
                border-radius: 7px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #00adb5;
                border-radius: 7px;
            }
        """)
        
    def set_range(self, minimum: int, maximum: int):
        self.progress.setRange(minimum, maximum)
        self.progress.setTextVisible(True)
        
    def set_value(self, value: int):
        self.progress.setValue(value)
        
    def set_message(self, message: str):
        self.label.setText(message)

class LoadImageWorker(QThread):
    finished = pyqtSignal(object, object, str)  # Emits (RGBA PIL Image, QImage, file_path) or (Exception, None, file_path)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        
    def run(self):
        try:
            pil_img = Image.open(self.file_path)
            rgba_img = pil_img.convert("RGBA")
            qimg = pil_to_qimage(rgba_img)
            self.finished.emit(rgba_img, qimg, self.file_path)
        except Exception as e:
            self.finished.emit(e, None, self.file_path)

class SaveImageWorker(QThread):
    finished = pyqtSignal(object)  # Emits True or Exception
    
    def __init__(self, image, file_path, file_format):
        super().__init__()
        self.image = image
        self.file_path = file_path
        self.file_format = file_format
        
    def run(self):
        try:
            if self.file_format == "JPEG":
                save_img = Image.new("RGB", self.image.size, (255, 255, 255))
                save_img.paste(self.image, mask=self.image.split()[3])
            else:
                save_img = self.image
                
            save_img.save(self.file_path, format=self.file_format)
            self.finished.emit(True)
        except Exception as e:
            self.finished.emit(e)

class SliceImageWorker(QThread):
    progress = pyqtSignal(int, int)  # Emits (current_index, total_count)
    finished = pyqtSignal(object)    # Emits True or Exception
    
    def __init__(self, pil_image, dest_dir, mode="grid", cols=1, rows=1, boxes=None, equalize_size=False, offsets=None):
        super().__init__()
        self.pil_image = pil_image
        self.dest_dir = dest_dir
        self.mode = mode
        self.cols = cols
        self.rows = rows
        self.boxes = boxes if boxes is not None else []
        self.equalize_size = equalize_size
        self.offsets = offsets if offsets is not None else {}
        
    def run(self):
        try:
            W, H = self.pil_image.size
            
            if self.mode in ("auto", "manual"):
                total = len(self.boxes)
                prefix = "slice_auto" if self.mode == "auto" else "slice_manual"
                
                if self.equalize_size and self.boxes:
                    max_w = max(b[2] for b in self.boxes)
                    max_h = max(b[3] for b in self.boxes)
                
                for idx, (bx, by, bw, bh) in enumerate(self.boxes):
                    sub_img = self.pil_image.crop((bx, by, bx + bw, by + bh))
                    if self.equalize_size:
                        # Center the sprite in a larger canvas or use custom offset
                        padded = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
                        if self.offsets and idx in self.offsets:
                            offset_x, offset_y = self.offsets[idx]
                        else:
                            offset_x = (max_w - bw) // 2
                            offset_y = (max_h - bh) // 2
                        padded.paste(sub_img, (offset_x, offset_y))
                        save_img = padded
                    else:
                        save_img = sub_img
                        
                    file_name = f"{prefix}_{idx}.png"
                    save_img.save(os.path.join(self.dest_dir, file_name), "PNG")
                    self.progress.emit(idx + 1, total)
            else:
                C, R = self.cols, self.rows
                total = C * R
                current = 0
                for r in range(R):
                    for c in range(C):
                        x1 = int(c * W / C)
                        y1 = int(r * H / R)
                        x2 = int((c + 1) * W / C)
                        y2 = int((r + 1) * H / R)
                        
                        sub_img = self.pil_image.crop((x1, y1, x2, y2))
                        file_name = f"slice_r{r}_c{c}.png"
                        sub_img.save(os.path.join(self.dest_dir, file_name), "PNG")
                        
                        current += 1
                        self.progress.emit(current, total)
                        
            self.finished.emit(True)
        except Exception as e:
            self.finished.emit(e)

class ExportGifWorker(QThread):
    progress = pyqtSignal(int, int)  # Emits (current, total)
    finished = pyqtSignal(object)    # Emits True or Exception
    
    def __init__(self, frames, file_path, fps):
        super().__init__()
        self.frames = frames
        self.file_path = file_path
        self.fps = fps
        
    def run(self):
        try:
            total = len(self.frames)
            if total == 0:
                raise ValueError("Không có khung ảnh nào để xuất (No frames to export)")
                
            duration_ms = int(1000 / self.fps)
            self.progress.emit(10, 100)
            
            first_frame = self.frames[0]
            self.progress.emit(50, 100)
            first_frame.save(
                self.file_path,
                save_all=True,
                append_images=self.frames[1:],
                duration=duration_ms,
                loop=0,
                disposal=2  # Prevents frames stacking transparent overlays
            )
            self.progress.emit(100, 100)
            self.finished.emit(True)
        except Exception as e:
            self.finished.emit(e)

class ExportVideoWorker(QThread):
    progress = pyqtSignal(int, int)  # Emits (current, total)
    finished = pyqtSignal(object)    # Emits True or Exception
    
    def __init__(self, frames, file_path, fps, bg_color=(0, 0, 0)):
        super().__init__()
        self.frames = frames
        self.file_path = file_path
        self.fps = fps
        self.bg_color = bg_color # (R, G, B)
        
    def run(self):
        try:
            import cv2
            import numpy as np
            
            total = len(self.frames)
            if total == 0:
                raise ValueError("Không có khung ảnh nào để xuất (No frames to export)")
                
            W, H = self.frames[0].size
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(self.file_path, fourcc, self.fps, (W, H))
            
            for idx, frame in enumerate(self.frames):
                rgba = frame.convert("RGBA")
                bg = Image.new("RGBA", (W, H), self.bg_color + (255,))
                composite = Image.alpha_composite(bg, rgba).convert("RGB")
                
                numpy_img = np.array(composite)
                bgr_img = cv2.cvtColor(numpy_img, cv2.COLOR_RGB2BGR)
                
                video_writer.write(bgr_img)
                self.progress.emit(idx + 1, total)
                
            video_writer.release()
            self.finished.emit(True)
        except Exception as e:
            self.finished.emit(e)

class ImageWorker(QThread):
    finished = pyqtSignal(object, object)  # Emits (processed PIL Image, QImage) or (Exception, None)
    
    def __init__(self, base_pil, target_color, tolerance, softness, mode, replace_color):
        super().__init__()
        self.base_pil = base_pil
        self.target_color = target_color
        self.tolerance = tolerance
        self.softness = softness
        self.mode = mode
        self.replace_color = replace_color
        
    def run(self):
        try:
            result_pil = ImageProcessor.process_color_operation(
                pil_image=self.base_pil,
                target_color=self.target_color,
                tolerance=self.tolerance,
                softness=self.softness,
                mode=self.mode,
                replace_color=self.replace_color
            )
            result_qimg = pil_to_qimage(result_pil)
            self.finished.emit(result_pil, result_qimg)
        except Exception as e:
            self.finished.emit(e, None)

class AlignmentCanvas(QWidget):
    offset_changed = pyqtSignal(int, int) # Emits (ox, oy)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(400, 400) # Fixed size display
        
        self.max_w = 100
        self.max_h = 100
        self.sprite_img = None # QImage of the cropped sprite
        self.ox = 0
        self.oy = 0
        self.zoom = 1.0
        
        # Checkerboard brush
        self.checker_brush = self._create_checker_brush()
        
        # Dragging state
        self.is_dragging = False
        self.drag_start_offset = QPoint()
        self.drag_start_mouse = QPoint()
        
    def _create_checker_brush(self) -> QBrush:
        from PyQt6.QtGui import QPixmap
        tile = QPixmap(16, 16)
        tile.fill(QColor(240, 240, 240))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 8, 8, QColor(215, 215, 215))
        painter.fillRect(8, 8, 8, 8, QColor(215, 215, 215))
        painter.end()
        return QBrush(tile)
        
    def set_sprite(self, qimage: QImage, max_w: int, max_h: int, ox: int, oy: int):
        self.sprite_img = qimage
        self.max_w = max_w
        self.max_h = max_h
        self.ox = ox
        self.oy = oy
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Draw dark background
        painter.fillRect(self.rect(), QColor(20, 20, 25))
        
        # Zoom fitting
        margin = 40
        zoom_w = (self.width() - margin) / self.max_w
        zoom_h = (self.height() - margin) / self.max_h
        self.zoom = min(zoom_w, zoom_h, 8.0)
        if self.zoom < 1.0:
            self.zoom = 1.0
            
        sw = self.max_w * self.zoom
        sh = self.max_h * self.zoom
        self.frame_rect = QRect(
            int((self.width() - sw) / 2),
            int((self.height() - sh) / 2),
            int(sw),
            int(sh)
        )
        
        # 1. Checkerboard
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.checker_brush)
        painter.drawRect(self.frame_rect)
        painter.restore()
        
        # 2. Draw Sprite
        if self.sprite_img:
            sprite_x = self.frame_rect.left() + self.ox * self.zoom
            sprite_y = self.frame_rect.top() + self.oy * self.zoom
            sprite_w = self.sprite_img.width() * self.zoom
            sprite_h = self.sprite_img.height() * self.zoom
            
            dest_rect = QRect(int(sprite_x), int(sprite_y), int(sprite_w), int(sprite_h))
            painter.drawImage(dest_rect, self.sprite_img)
            
            # Draw border
            painter.setPen(QPen(QColor(0, 173, 181, 150), 1, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(dest_rect)
            
        # 3. Guides
        cx = self.frame_rect.left() + self.frame_rect.width() / 2
        cy = self.frame_rect.top() + self.frame_rect.height() / 2
        
        guide_pen = QPen(QColor(255, 0, 0, 120), 1, Qt.PenStyle.DashLine)
        painter.setPen(guide_pen)
        painter.drawLine(int(cx), self.frame_rect.top(), int(cx), self.frame_rect.bottom())
        painter.drawLine(self.frame_rect.left(), int(cy), self.frame_rect.right(), int(cy))
        
        # 4. Outer border
        painter.setPen(QPen(QColor(100, 100, 120), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.frame_rect)
        
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.sprite_img:
            sprite_x = self.frame_rect.left() + self.ox * self.zoom
            sprite_y = self.frame_rect.top() + self.oy * self.zoom
            sprite_w = self.sprite_img.width() * self.zoom
            sprite_h = self.sprite_img.height() * self.zoom
            
            click_rect = QRect(int(sprite_x), int(sprite_y), int(sprite_w), int(sprite_h))
            if click_rect.contains(event.position().toPoint()):
                self.is_dragging = True
                self.drag_start_offset = QPoint(self.ox, self.oy)
                self.drag_start_mouse = event.position().toPoint()
                
    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging:
            delta = event.position().toPoint() - self.drag_start_mouse
            dx = int(round(delta.x() / self.zoom))
            dy = int(round(delta.y() / self.zoom))
            
            self.ox = self.drag_start_offset.x() + dx
            self.oy = self.drag_start_offset.y() + dy
            self.offset_changed.emit(self.ox, self.oy)
            self.update()
            
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False

class SpriteAlignmentDialog(QDialog):
    def __init__(self, pil_image, boxes, initial_offsets=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Căn Chỉnh Vị Trí Khung Hình (Sprite Alignment)")
        self.setModal(True)
        self.setFixedSize(500, 600)
        
        self.pil_image = pil_image
        self.boxes = boxes
        self.current_idx = 0
        
        # Calculate max_w and max_h
        self.max_w = max(b[2] for b in boxes) if boxes else 100
        self.max_h = max(b[3] for b in boxes) if boxes else 100
        
        # Initialize offsets
        self.offsets = {}
        for idx, (bx, by, bw, bh) in enumerate(boxes):
            if initial_offsets and idx in initial_offsets:
                self.offsets[idx] = initial_offsets[idx]
            else:
                self.offsets[idx] = ((self.max_w - bw) // 2, (self.max_h - bh) // 2)
            
        self.init_ui()
        self.load_frame(0)
        
    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #141419;
                color: #e5e9f0;
            }
            QLabel {
                color: #e5e9f0;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 600;
            }
            QPushButton {
                background-color: #262633;
                color: #e5e9f0;
                border-radius: 6px;
                border: 1px solid #343447;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2f2f42;
                border-color: #4a4a66;
            }
            QPushButton#saveBtn {
                background-color: #00adb5;
                color: #0a0a0f;
                border: 1px solid #00c7d1;
            }
            QPushButton#saveBtn:hover {
                background-color: #00cfda;
                border-color: #00e5f2;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header Label
        self.lbl_title = QLabel("Căn chỉnh ô 1/1 - Tọa độ: (0, 0)")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_title)
        
        # Guide Label
        lbl_guide = QLabel("Kéo chuột hoặc Mũi Tên để di chuyển.\nSpace: Khung tiếp | Ctrl+Z: Khung trước")
        lbl_guide.setStyleSheet("color: #8c909e; font-size: 10px; font-weight: normal;")
        lbl_guide.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_guide)
        
        # Canvas
        self.canvas = AlignmentCanvas(self)
        self.canvas.offset_changed.connect(self.on_offset_changed)
        layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.btn_prev = QPushButton("Ảnh trước (Ctrl+Z)")
        self.btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_prev.clicked.connect(self.prev_frame)
        
        self.btn_next = QPushButton("Ảnh tiếp (Space)")
        self.btn_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_next.clicked.connect(self.next_frame)
        
        self.btn_center = QPushButton("Đặt lại giữa")
        self.btn_center.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_center.clicked.connect(self.reset_to_center)
        
        btn_layout.addWidget(self.btn_prev)
        btn_layout.addWidget(self.btn_next)
        btn_layout.addWidget(self.btn_center)
        layout.addLayout(btn_layout)
        
        # Done / Cancel buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        
        btn_cancel = QPushButton("Hủy bỏ")
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("Cắt & Lưu ảnh (Save)")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save.clicked.connect(self.accept)
        
        bottom_layout.addWidget(btn_cancel)
        bottom_layout.addWidget(self.btn_save)
        layout.addLayout(bottom_layout)
        
    def load_frame(self, idx):
        if not self.boxes or idx < 0 or idx >= len(self.boxes):
            return
            
        self.current_idx = idx
        bx, by, bw, bh = self.boxes[idx]
        
        # Crop and convert
        sub_pil = self.pil_image.crop((bx, by, bx + bw, by + bh))
        qimg = pil_to_qimage(sub_pil)
        
        ox, oy = self.offsets[idx]
        
        self.canvas.set_sprite(qimg, self.max_w, self.max_h, ox, oy)
        
        # Update label
        self.lbl_title.setText(f"Căn chỉnh ô {idx + 1}/{len(self.boxes)} - Tọa độ: ({ox}, {oy})")
        
        # Update button states
        self.btn_prev.setEnabled(idx > 0)
        if idx == len(self.boxes) - 1:
            self.btn_next.setText("Hoàn thành (Done)")
        else:
            self.btn_next.setText("Ảnh tiếp (Space)")
            
    def on_offset_changed(self, ox, oy):
        self.offsets[self.current_idx] = (ox, oy)
        self.lbl_title.setText(f"Căn chỉnh ô {self.current_idx + 1}/{len(self.boxes)} - Tọa độ: ({ox}, {oy})")
        
    def reset_to_center(self):
        bx, by, bw, bh = self.boxes[self.current_idx]
        ox = (self.max_w - bw) // 2
        oy = (self.max_h - bh) // 2
        self.on_offset_changed(ox, oy)
        self.canvas.ox = ox
        self.canvas.oy = oy
        self.canvas.update()
        
    def prev_frame(self):
        if self.current_idx > 0:
            self.load_frame(self.current_idx - 1)
            
    def next_frame(self):
        if self.current_idx < len(self.boxes) - 1:
            self.load_frame(self.current_idx + 1)
        else:
            self.accept()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.canvas.ox -= 1
            self.on_offset_changed(self.canvas.ox, self.canvas.oy)
            self.canvas.update()
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            self.canvas.ox += 1
            self.on_offset_changed(self.canvas.ox, self.canvas.oy)
            self.canvas.update()
            event.accept()
        elif event.key() == Qt.Key.Key_Up:
            self.canvas.oy -= 1
            self.on_offset_changed(self.canvas.ox, self.canvas.oy)
            self.canvas.update()
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            self.canvas.oy += 1
            self.on_offset_changed(self.canvas.ox, self.canvas.oy)
            self.canvas.update()
            event.accept()
        elif event.key() == Qt.Key.Key_Space:
            self.next_frame()
            event.accept()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.prev_frame()
            event.accept()
        else:
            super().keyPressEvent(event)

class PostSliceChoiceDialog(QDialog):
    def __init__(self, frame_count, current_fps, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tùy Chọn Sau Khi Cắt (Export Options)")
        self.setModal(True)
        self.setFixedSize(380, 320)
        self.selected_action = None
        self.frame_count = frame_count
        self.fps = current_fps
        
        self.init_ui()
        
    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #141419;
                color: #e5e9f0;
                border: 1px solid #252530;
                border-radius: 8px;
            }
            QLabel {
                color: #e5e9f0;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 600;
            }
            QSpinBox {
                background-color: #20202a;
                color: #e5e9f0;
                border: 1px solid #2e2e3d;
                border-radius: 4px;
                padding: 4px;
                min-width: 60px;
                font-size: 12px;
                font-weight: bold;
            }
            QSpinBox:hover {
                border-color: #46465c;
            }
            QPushButton {
                background-color: #262633;
                color: #e5e9f0;
                border-radius: 6px;
                border: 1px solid #343447;
                padding: 10px 15px;
                font-size: 12px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2f2f42;
                border-color: #00adb5;
            }
            QPushButton#cancelBtn {
                background-color: #2d1d22;
                color: #ff5252;
                border: 1px solid #5d1c24;
                text-align: center;
                padding: 6px;
            }
            QPushButton#cancelBtn:hover {
                background-color: #3f2229;
                border-color: #8c2a33;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Info Label
        lbl_info = QLabel(f"Đã cắt thành {self.frame_count} khung hình.")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet("color: #00adb5; font-size: 13px; font-weight: bold;")
        layout.addWidget(lbl_info)
        
        # FPS Choice Row
        fps_layout = QHBoxLayout()
        lbl_fps = QLabel("Tốc độ chuyển động (FPS):")
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(self.fps)
        fps_layout.addWidget(lbl_fps)
        fps_layout.addWidget(self.spin_fps)
        layout.addLayout(fps_layout)
        
        layout.addSpacing(5)
        
        # Buttons for actions
        self.btn_save = QPushButton("📂  Lưu bộ ảnh PNG riêng lẻ")
        self.btn_save.clicked.connect(lambda: self.choose_action('save'))
        layout.addWidget(self.btn_save)
        
        self.btn_preview = QPushButton("▶  Xem trước hoạt ảnh lặp")
        self.btn_preview.clicked.connect(lambda: self.choose_action('preview'))
        layout.addWidget(self.btn_preview)
        
        self.btn_gif = QPushButton("🖼  Tải ảnh động GIF (Trong suốt)")
        self.btn_gif.clicked.connect(lambda: self.choose_action('gif'))
        layout.addWidget(self.btn_gif)
        
        self.btn_mp4 = QPushButton("🎥  Tải video MP4 (Phông nền đen)")
        self.btn_mp4.clicked.connect(lambda: self.choose_action('mp4'))
        layout.addWidget(self.btn_mp4)
        
        layout.addSpacing(5)
        
        btn_cancel = QPushButton("Hủy bỏ")
        btn_cancel.setObjectName("cancelBtn")
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)
        
    def choose_action(self, action):
        self.selected_action = action
        self.fps = self.spin_fps.value()
        self.accept()

class ColorEditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Window settings
        self.setWindowTitle("Tạo Chuyển Động Pixel - by Thuanvuse")
        self.setMinimumSize(1100, 750)
        self.setAcceptDrops(True)
        
        # Window icon
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # State variables
        self.original_image_path = None
        self.active_pil_base = None  # Base PIL Image for current edit step
        self.active_pil_result = None # Result PIL Image after current sliders/adjustments
        self.custom_slice_offsets = {}
        
        # Undo/Redo stacks (Holds PIL Images)
        self.history = []
        self.history_index = -1
        
        # Active editing parameters
        self.selected_color = QColor(255, 0, 0) # Default Red
        self.replace_color = QColor(0, 255, 0)   # Default Green for replacement
        
        # Threading and debouncing
        self.processing_thread = None
        self.pending_process = False
        
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(120)  # 120ms debounce
        self.debounce_timer.timeout.connect(self.process_image)
        
        # Dialog loaders
        self.loading_dialog = None
        self.has_active_color_selection = False
        
        # Animation preview states
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.play_next_animation_frame)
        self.is_playing_animation = False
        self.animation_qimages = []
        self.animation_index = 0
        
        # Setup UI
        self.init_ui()
        self.apply_theme()
        self.update_controls_state()
        
    def init_ui(self):
        # Central Widget & Main Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Main Splitter to separate sidebar and canvas
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- SIDEBAR PANEL (Left) ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(340)
        sidebar.setMaximumWidth(380)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 15, 15, 15)
        sidebar_layout.setSpacing(15)
        
        # App Title Card
        title_card = QFrame()
        title_card.setObjectName("titleCard")
        title_card_layout = QVBoxLayout(title_card)
        title_card_layout.setContentsMargins(0, 0, 0, 5)
        title_card_layout.setSpacing(4)
        
        title_label = QLabel("TẠO CHUYỂN ĐỘNG PIXEL")
        title_label.setObjectName("appTitle")
        subtitle_label = QLabel("Bộ Công Cụ Tách Màu & Tạo Hoạt Ảnh Pixel")
        subtitle_label.setObjectName("appSubtitle")
        credit_label = QLabel("by Thuanvuse · Telegram: @chimdangxem")
        credit_label.setStyleSheet("color: #4a4f60; font-size: 10px; font-family: 'Segoe UI'; font-style: italic;")
        title_card_layout.addWidget(title_label)
        title_card_layout.addWidget(subtitle_label)
        title_card_layout.addWidget(credit_label)
        sidebar_layout.addWidget(title_card)
        
        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setObjectName("sidebarTabs")
        
        # Create tabs
        tab_edit = QWidget()
        tab_edit_layout = QVBoxLayout(tab_edit)
        tab_edit_layout.setContentsMargins(10, 10, 10, 10)
        tab_edit_layout.setSpacing(12)
        
        tab_file = QWidget()
        tab_file_layout = QVBoxLayout(tab_file)
        tab_file_layout.setContentsMargins(10, 10, 10, 10)
        tab_file_layout.setSpacing(12)
        
        tab_slice = QWidget()
        tab_slice_layout = QVBoxLayout(tab_slice)
        tab_slice_layout.setContentsMargins(10, 10, 10, 10)
        tab_slice_layout.setSpacing(12)
        
        tab_anim = QWidget()
        tab_anim_layout = QVBoxLayout(tab_anim)
        tab_anim_layout.setContentsMargins(10, 10, 10, 10)
        tab_anim_layout.setSpacing(12)
        
        self.tabs.addTab(tab_edit, "Chỉnh Sửa (Edit)")
        self.tabs.addTab(tab_file, "Tập Tin & Lịch Sử (File)")
        self.tabs.addTab(tab_slice, "Cắt Ảnh (Slice)")
        self.tabs.addTab(tab_anim, "Chuyển Động (Anim)")
        sidebar_layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Helper to create headers
        def create_header(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("cardHeader")
            return lbl
            
        # --- TAB 1: EDIT LAYOUT ---
        tab_edit_layout.addWidget(create_header("1. Hộp Công Cụ (Toolbox)"))
        
        # Tools Grid Layout
        tools_layout = QGridLayout()
        tools_layout.setSpacing(8)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_tool_pan = QPushButton("✋ Dịch Chuyển")
        self.btn_tool_pan.setCheckable(True)
        self.btn_tool_pan.setChecked(True)
        self.btn_tool_pan.setObjectName("secondaryBtn")
        self.btn_tool_pan.clicked.connect(lambda: self.select_tool("pan"))
        
        self.btn_tool_pipette = QPushButton("🧪 Hút Màu")
        self.btn_tool_pipette.setCheckable(True)
        self.btn_tool_pipette.setObjectName("secondaryBtn")
        self.btn_tool_pipette.clicked.connect(lambda: self.select_tool("pipette"))
        
        self.btn_tool_brush = QPushButton("✏️ Cọ Vẽ")
        self.btn_tool_brush.setCheckable(True)
        self.btn_tool_brush.setObjectName("secondaryBtn")
        self.btn_tool_brush.clicked.connect(lambda: self.select_tool("brush"))
        
        self.btn_tool_eraser = QPushButton("🧽 Cục Tẩy")
        self.btn_tool_eraser.setCheckable(True)
        self.btn_tool_eraser.setObjectName("secondaryBtn")
        self.btn_tool_eraser.clicked.connect(lambda: self.select_tool("eraser"))
        
        tools_layout.addWidget(self.btn_tool_pan, 0, 0)
        tools_layout.addWidget(self.btn_tool_pipette, 0, 1)
        tools_layout.addWidget(self.btn_tool_brush, 1, 0)
        tools_layout.addWidget(self.btn_tool_eraser, 1, 1)
        tab_edit_layout.addLayout(tools_layout)
        
        # Section Separator Helper
        def create_separator() -> QFrame:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setStyleSheet("background-color: #202026; max-height: 1px; border: none; margin: 4px 0;")
            return line
            
        tab_edit_layout.addWidget(create_separator())
        
        # Color Selection Sub-section
        tab_edit_layout.addWidget(create_header("2. Chọn Màu Gốc (Source Color)"))
        
        # Compact Color Block
        color_block_layout = QHBoxLayout()
        color_block_layout.setSpacing(10)
        
        self.color_swatch = QFrame()
        self.color_swatch.setObjectName("colorSwatch")
        self.color_swatch.setFixedSize(36, 36)
        
        self.lbl_color_info = QLabel("RGB: 255, 0, 0\nHEX: #FF0000")
        self.lbl_color_info.setObjectName("colorLabel")
        self.lbl_color_info.setStyleSheet("font-size: 11px;")
        
        self.btn_custom_color = QPushButton("🎨 Chọn màu")
        self.btn_custom_color.setObjectName("secondaryBtn")
        self.btn_custom_color.setMinimumHeight(36)
        self.btn_custom_color.clicked.connect(self.open_color_dialog)
        
        color_block_layout.addWidget(self.color_swatch)
        color_block_layout.addWidget(self.lbl_color_info, 1)
        color_block_layout.addWidget(self.btn_custom_color)
        tab_edit_layout.addLayout(color_block_layout)
        
        tab_edit_layout.addWidget(create_separator())
        
        # Operation Sub-section
        tab_edit_layout.addWidget(create_header("3. Chế Độ Xử Lý (Operation)"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Xóa màu đã chọn (Erase Color)",
            "Chỉ giữ màu đã chọn (Isolate Color)",
            "Giữ màu & Chuyển Trắng Đen (Color Splash)",
            "Thay thế bằng màu mới (Replace Color)"
        ])
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        tab_edit_layout.addWidget(self.combo_mode)
        
        # Replacement Color Selector Row
        self.replace_container = QWidget()
        replace_layout = QHBoxLayout(self.replace_container)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(10)
        
        lbl_to = QLabel("Đổi thành (To):")
        lbl_to.setStyleSheet("font-size: 11px; color: #a0a5b5;")
        
        self.replace_swatch = QFrame()
        self.replace_swatch.setObjectName("replaceSwatch")
        self.replace_swatch.setFixedSize(36, 36)
        
        self.btn_replace_color = QPushButton("🎨 Chọn màu mới")
        self.btn_replace_color.setObjectName("secondaryBtn")
        self.btn_replace_color.setMinimumHeight(36)
        self.btn_replace_color.clicked.connect(self.open_replace_color_dialog)
        
        replace_layout.addWidget(lbl_to)
        replace_layout.addWidget(self.replace_swatch)
        replace_layout.addWidget(self.btn_replace_color, 1)
        tab_edit_layout.addWidget(self.replace_container)
        
        tab_edit_layout.addWidget(create_separator())
        
        # Fine-Tuning Sub-section
        tab_edit_layout.addWidget(create_header("4. Tinh Chỉnh (Fine-Tuning)"))
        
        # Helper to create unified slider label with fixed width to align sliders nicely
        def create_slider_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("sliderLabel")
            lbl.setMinimumWidth(110)
            lbl.setMaximumWidth(110)
            return lbl
            
        # Tolerance Slider Row
        tol_layout = QHBoxLayout()
        tol_layout.setSpacing(8)
        lbl_tol = create_slider_label("Độ Lệch (Tol):")
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 250)
        self.slider_tolerance.setValue(30)
        self.slider_tolerance.valueChanged.connect(self.on_param_changed)
        self.spin_tolerance = QSpinBox()
        self.spin_tolerance.setRange(0, 250)
        self.spin_tolerance.setValue(30)
        self.spin_tolerance.valueChanged.connect(self.slider_tolerance.setValue)
        self.slider_tolerance.valueChanged.connect(self.spin_tolerance.setValue)
        tol_layout.addWidget(lbl_tol)
        tol_layout.addWidget(self.slider_tolerance, 1)
        tol_layout.addWidget(self.spin_tolerance)
        tab_edit_layout.addLayout(tol_layout)
        
        # Softness Slider Row
        soft_layout = QHBoxLayout()
        soft_layout.setSpacing(8)
        lbl_soft = create_slider_label("Độ Mịn (Soft):")
        self.slider_softness = QSlider(Qt.Orientation.Horizontal)
        self.slider_softness.setRange(0, 250)
        self.slider_softness.setValue(10)
        self.slider_softness.valueChanged.connect(self.on_param_changed)
        self.spin_softness = QSpinBox()
        self.spin_softness.setRange(0, 250)
        self.spin_softness.setValue(10)
        self.spin_softness.valueChanged.connect(self.slider_softness.setValue)
        self.slider_softness.valueChanged.connect(self.spin_softness.setValue)
        soft_layout.addWidget(lbl_soft)
        soft_layout.addWidget(self.slider_softness, 1)
        soft_layout.addWidget(self.spin_softness)
        tab_edit_layout.addLayout(soft_layout)
        
        self.chk_live = QCheckBox("Xem trực tiếp (Live Preview)")
        self.chk_live.setChecked(True)
        tab_edit_layout.addWidget(self.chk_live)
        
        # --- Drawing parameters sub-panel ---
        self.draw_params_widget = QWidget()
        draw_params_layout = QVBoxLayout(self.draw_params_widget)
        draw_params_layout.setContentsMargins(0, 0, 0, 0)
        draw_params_layout.setSpacing(10)
        
        draw_params_layout.addWidget(create_separator())
        draw_params_layout.addWidget(create_header("5. Cài Đặt Cọ (Brush Config)"))
        
        # Brush Size
        bs_layout = QHBoxLayout()
        bs_layout.setSpacing(8)
        lbl_bs = create_slider_label("Cỡ Cọ (Size):")
        self.slider_brush_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_brush_size.setRange(1, 100)
        self.slider_brush_size.setValue(15)
        self.slider_brush_size.valueChanged.connect(self.on_brush_params_changed)
        self.spin_brush_size = QSpinBox()
        self.spin_brush_size.setRange(1, 100)
        self.spin_brush_size.setValue(15)
        self.spin_brush_size.valueChanged.connect(self.slider_brush_size.setValue)
        self.slider_brush_size.valueChanged.connect(self.spin_brush_size.setValue)
        bs_layout.addWidget(lbl_bs)
        bs_layout.addWidget(self.slider_brush_size, 1)
        bs_layout.addWidget(self.spin_brush_size)
        draw_params_layout.addLayout(bs_layout)
        
        # Brush Hardness
        bh_layout = QHBoxLayout()
        bh_layout.setSpacing(8)
        lbl_bh = create_slider_label("Độ Cứng (Hard):")
        self.slider_brush_hardness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brush_hardness.setRange(0, 100)
        self.slider_brush_hardness.setValue(80)
        self.slider_brush_hardness.valueChanged.connect(self.on_brush_params_changed)
        self.spin_brush_hardness = QSpinBox()
        self.spin_brush_hardness.setRange(0, 100)
        self.spin_brush_hardness.setValue(80)
        self.spin_brush_hardness.valueChanged.connect(self.slider_brush_hardness.setValue)
        self.slider_brush_hardness.valueChanged.connect(self.spin_brush_hardness.setValue)
        bh_layout.addWidget(lbl_bh)
        bh_layout.addWidget(self.slider_brush_hardness, 1)
        bh_layout.addWidget(self.spin_brush_hardness)
        draw_params_layout.addLayout(bh_layout)
        
        # Brush Opacity
        bo_layout = QHBoxLayout()
        bo_layout.setSpacing(8)
        lbl_bo = create_slider_label("Độ Đục (Opac):")
        self.slider_brush_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_brush_opacity.setRange(0, 100)
        self.slider_brush_opacity.setValue(100)
        self.slider_brush_opacity.valueChanged.connect(self.on_brush_params_changed)
        self.spin_brush_opacity = QSpinBox()
        self.spin_brush_opacity.setRange(0, 100)
        self.spin_brush_opacity.setValue(100)
        self.spin_brush_opacity.valueChanged.connect(self.slider_brush_opacity.setValue)
        self.slider_brush_opacity.valueChanged.connect(self.spin_brush_opacity.setValue)
        bo_layout.addWidget(lbl_bo)
        bo_layout.addWidget(self.slider_brush_opacity, 1)
        bo_layout.addWidget(self.spin_brush_opacity)
        draw_params_layout.addLayout(bo_layout)
        
        tab_edit_layout.addWidget(self.draw_params_widget)
        self.draw_params_widget.setVisible(False)
        
        tab_edit_layout.addStretch(1)
        
        # --- TAB 2: FILE & HISTORY LAYOUT ---
        tab_file_layout.addWidget(create_header("1. Tập Tin (File)"))
        
        self.btn_open = QPushButton("Mở Ảnh (Open Image)")
        self.btn_open.setObjectName("secondaryBtn")
        self.btn_open.clicked.connect(self.open_image_dialog)
        tab_file_layout.addWidget(self.btn_open)
        
        self.btn_save = QPushButton("Lưu Ảnh (Save Image)")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.clicked.connect(self.save_image_dialog)
        tab_file_layout.addWidget(self.btn_save)
        
        tab_file_layout.addWidget(create_header("2. Lịch Sử & Thao Tác (History)"))
        
        self.btn_apply = QPushButton("Áp Dụng Bước Này (Bake Edit)")
        self.btn_apply.setObjectName("primaryBtn")
        self.btn_apply.clicked.connect(self.bake_current_edit)
        tab_file_layout.addWidget(self.btn_apply)
        
        # Undo / Redo buttons
        history_btn_layout = QHBoxLayout()
        self.btn_undo = QPushButton("Hoàn Tác (Undo)")
        self.btn_undo.setObjectName("secondaryBtn")
        self.btn_undo.clicked.connect(self.undo)
        
        self.btn_redo = QPushButton("Làm Lại (Redo)")
        self.btn_redo.setObjectName("secondaryBtn")
        self.btn_redo.clicked.connect(self.redo)
        
        history_btn_layout.addWidget(self.btn_undo)
        history_btn_layout.addWidget(self.btn_redo)
        tab_file_layout.addLayout(history_btn_layout)
        
        self.btn_reset = QPushButton("Khôi Phục Gốc (Reset)")
        self.btn_reset.setObjectName("dangerBtn")
        self.btn_reset.clicked.connect(self.reset_to_original)
        tab_file_layout.addWidget(self.btn_reset)
        tab_file_layout.addStretch(1)
        
        # --- TAB 3: SLICE LAYOUT ---
        tab_slice_layout.addWidget(create_header("1. Phương Thức Cắt (Slice Mode)"))
        
        self.combo_slice_mode = QComboBox()
        self.combo_slice_mode.addItems([
            "Cắt theo lưới ô đều (Grid Layout)",
            "Tự động nhận diện (Auto-Detect)",
            "Cắt thủ công (Manual Draw)"
        ])
        self.combo_slice_mode.currentIndexChanged.connect(self.on_slice_mode_changed)
        tab_slice_layout.addWidget(self.combo_slice_mode)
        
        # Grid settings container widget
        self.grid_settings_widget = QWidget()
        grid_settings_layout = QVBoxLayout(self.grid_settings_widget)
        grid_settings_layout.setContentsMargins(0, 0, 0, 0)
        grid_settings_layout.setSpacing(10)
        
        grid_settings_layout.addWidget(create_header("2. Cài Đặt Lưới (Grid Settings)"))
        
        lbl_slice_desc = QLabel("Chia hình ảnh thành các ô đều nhau để cắt và lưu riêng biệt.")
        lbl_slice_desc.setObjectName("sliderLabel")
        lbl_slice_desc.setWordWrap(True)
        grid_settings_layout.addWidget(lbl_slice_desc)
        
        grid_params_layout = QHBoxLayout()
        grid_params_layout.setSpacing(8)
        
        lbl_cols = QLabel("Số cột (Cols):")
        lbl_cols.setObjectName("sliderLabel")
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 100)
        self.spin_cols.setValue(1)
        self.spin_cols.valueChanged.connect(self.on_slice_grid_changed)
        
        lbl_rows = QLabel("Số hàng (Rows):")
        lbl_rows.setObjectName("sliderLabel")
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 100)
        self.spin_rows.setValue(1)
        self.spin_rows.valueChanged.connect(self.on_slice_grid_changed)
        
        grid_params_layout.addWidget(lbl_cols)
        grid_params_layout.addWidget(self.spin_cols, 1)
        grid_params_layout.addWidget(lbl_rows)
        grid_params_layout.addWidget(self.spin_rows, 1)
        grid_settings_layout.addLayout(grid_params_layout)
        
        tab_slice_layout.addWidget(self.grid_settings_widget)
        
        # Auto-detect settings container widget
        self.auto_settings_widget = QWidget()
        auto_settings_layout = QVBoxLayout(self.auto_settings_widget)
        auto_settings_layout.setContentsMargins(0, 0, 0, 0)
        auto_settings_layout.setSpacing(10)
        
        auto_settings_layout.addWidget(create_header("2. Nhận Diện Vật Thể (Auto Settings)"))
        
        lbl_auto_desc = QLabel("Tự động nhận diện các nhân vật độc lập nằm rời rạc trong ảnh phông trong suốt.")
        lbl_auto_desc.setObjectName("sliderLabel")
        lbl_auto_desc.setWordWrap(True)
        auto_settings_layout.addWidget(lbl_auto_desc)
        
        auto_params_layout = QHBoxLayout()
        auto_params_layout.setSpacing(8)
        
        lbl_obj = QLabel("Số vật thể:")
        lbl_obj.setObjectName("sliderLabel")
        self.spin_obj_count = QSpinBox()
        self.spin_obj_count.setRange(1, 1000)
        self.spin_obj_count.setValue(10)
        self.spin_obj_count.valueChanged.connect(self.on_auto_detect_changed)
        
        lbl_size = QLabel("Cỡ tối thiểu (px):")
        lbl_size.setObjectName("sliderLabel")
        self.spin_min_size = QSpinBox()
        self.spin_min_size.setRange(1, 500)
        self.spin_min_size.setValue(10)
        self.spin_min_size.valueChanged.connect(self.on_auto_detect_changed)
        
        auto_params_layout.addWidget(lbl_obj)
        auto_params_layout.addWidget(self.spin_obj_count, 1)
        auto_params_layout.addWidget(lbl_size)
        auto_params_layout.addWidget(self.spin_min_size, 1)
        auto_settings_layout.addLayout(auto_params_layout)
        
        lbl_tip = QLabel("Mẹo: Hãy xóa nền trước để thuật toán tìm cạnh chính xác!")
        lbl_tip.setObjectName("appSubtitle")
        lbl_tip.setWordWrap(True)
        auto_settings_layout.addWidget(lbl_tip)
        
        tab_slice_layout.addWidget(self.auto_settings_widget)
        self.auto_settings_widget.setVisible(False)

        # Manual settings container widget
        self.manual_settings_widget = QWidget()
        manual_settings_layout = QVBoxLayout(self.manual_settings_widget)
        manual_settings_layout.setContentsMargins(0, 0, 0, 0)
        manual_settings_layout.setSpacing(10)
        
        manual_settings_layout.addWidget(create_header("2. Cắt Thủ Công (Manual Settings)"))
        
        lbl_manual_desc = QLabel("Nhấp và kéo chuột trên ảnh để vẽ từng ô cắt tùy chọn.")
        lbl_manual_desc.setObjectName("sliderLabel")
        lbl_manual_desc.setWordWrap(True)
        manual_settings_layout.addWidget(lbl_manual_desc)
        
        self.btn_clear_manual = QPushButton("Xóa Hết Ô Vẽ (Clear Boxes)")
        self.btn_clear_manual.setObjectName("dangerBtn")
        self.btn_clear_manual.clicked.connect(self.clear_manual_boxes)
        manual_settings_layout.addWidget(self.btn_clear_manual)
        
        tab_slice_layout.addWidget(self.manual_settings_widget)
        self.manual_settings_widget.setVisible(False)
        
        # Equalize size options
        self.chk_equalize_size = QCheckBox("Đồng bộ cỡ bằng ô lớn nhất (Equalize sizes)")
        self.chk_equalize_size.setChecked(True)
        tab_slice_layout.addWidget(self.chk_equalize_size)
        
        # Alignment editor button
        self.btn_align_sprites = QPushButton("Căn Chỉnh Vị Trí Từng Ô (Align Sprites)")
        self.btn_align_sprites.setObjectName("secondaryBtn")
        self.btn_align_sprites.setEnabled(False)
        self.btn_align_sprites.clicked.connect(self.open_alignment_dialog)
        tab_slice_layout.addWidget(self.btn_align_sprites)
        
        # Slice Action Button
        self.btn_slice = QPushButton("Cắt & Lưu Khung Ảnh (Slice & Save)")
        self.btn_slice.setObjectName("primaryBtn")
        self.btn_slice.clicked.connect(self.slice_image)
        tab_slice_layout.addWidget(self.btn_slice)
        
        tab_slice_layout.addStretch(1)
        
        # --- TAB 4: ANIM LAYOUT ---
        tab_anim_layout.addWidget(create_header("1. Xem Trước Chuyển Động"))
        
        lbl_anim_desc = QLabel("Phát hoạt ảnh trực tiếp trên khung vẽ dựa vào lưới ảnh đã cắt.")
        lbl_anim_desc.setObjectName("sliderLabel")
        lbl_anim_desc.setWordWrap(True)
        tab_anim_layout.addWidget(lbl_anim_desc)
        
        # FPS selector
        fps_layout = QHBoxLayout()
        lbl_fps = QLabel("Tốc độ (FPS):")
        lbl_fps.setObjectName("sliderLabel")
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(10)
        self.spin_fps.valueChanged.connect(self.on_fps_changed)
        fps_layout.addWidget(lbl_fps)
        fps_layout.addWidget(self.spin_fps)
        tab_anim_layout.addLayout(fps_layout)
        
        # Preview Button
        self.btn_play_preview = QPushButton("Xem Trước Chuyển Động (Play Preview)")
        self.btn_play_preview.setObjectName("primaryBtn")
        self.btn_play_preview.clicked.connect(self.toggle_animation_preview)
        tab_anim_layout.addWidget(self.btn_play_preview)
        
        tab_anim_layout.addWidget(create_header("2. Xuất File (Export)"))
        
        # Export Buttons
        self.btn_export_gif = QPushButton("Xuất File GIF (Export to GIF)")
        self.btn_export_gif.setObjectName("secondaryBtn")
        self.btn_export_gif.clicked.connect(self.export_gif)
        tab_anim_layout.addWidget(self.btn_export_gif)
        
        self.btn_export_mp4 = QPushButton("Xuất File Video MP4 (Export to MP4)")
        self.btn_export_mp4.setObjectName("secondaryBtn")
        self.btn_export_mp4.clicked.connect(self.export_mp4)
        tab_anim_layout.addWidget(self.btn_export_mp4)
        
        tab_anim_layout.addStretch(1)
        
        # Add sidebar to splitter
        splitter.addWidget(sidebar)
        
        # --- CANVAS VIEW PANEL (Right) ---
        canvas_panel = QFrame()
        canvas_panel.setObjectName("canvasPanel")
        canvas_layout = QVBoxLayout(canvas_panel)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(8)
        
        # Top toolbar over canvas for quick view operations
        view_toolbar = QFrame()
        view_toolbar.setObjectName("viewToolbar")
        view_toolbar_layout = QHBoxLayout(view_toolbar)
        view_toolbar_layout.setContentsMargins(10, 8, 10, 8)
        view_toolbar_layout.setSpacing(10)
        
        self.lbl_filename = QLabel("Chưa mở ảnh nào")
        self.lbl_filename.setObjectName("filenameLabel")
        view_toolbar_layout.addWidget(self.lbl_filename)
        
        view_toolbar_layout.addStretch(1)
        
        # Zoom buttons
        btn_zoom_in = QPushButton("Zoom +")
        btn_zoom_in.setObjectName("toolBtn")
        btn_zoom_in.clicked.connect(lambda: self.canvas.zoom_in())
        
        btn_zoom_out = QPushButton("Zoom -")
        btn_zoom_out.setObjectName("toolBtn")
        btn_zoom_out.clicked.connect(lambda: self.canvas.zoom_out())
        
        btn_zoom_fit = QPushButton("Khớp Khung (Fit)")
        btn_zoom_fit.setObjectName("toolBtn")
        btn_zoom_fit.clicked.connect(lambda: self.canvas.zoom_to_fit())
        
        btn_zoom_actual = QPushButton("100% (Actual)")
        btn_zoom_actual.setObjectName("toolBtn")
        btn_zoom_actual.clicked.connect(lambda: self.canvas.reset_zoom())
        
        view_toolbar_layout.addWidget(btn_zoom_in)
        view_toolbar_layout.addWidget(btn_zoom_out)
        view_toolbar_layout.addWidget(btn_zoom_fit)
        view_toolbar_layout.addWidget(btn_zoom_actual)
        
        canvas_layout.addWidget(view_toolbar)
        
        # Interactive Custom Canvas
        self.canvas = ImageCanvas()
        self.canvas.color_selected.connect(self.on_canvas_color_picked)
        self.canvas.mouse_hover_color.connect(self.on_canvas_hover)
        self.canvas.drawing_finished.connect(self.on_drawing_finished)
        self.canvas.manual_boxes_changed.connect(self.on_manual_boxes_changed)
        canvas_layout.addWidget(self.canvas, 1)
        
        # Add canvas panel to splitter
        splitter.addWidget(canvas_panel)
        
        # Set splitter sizes (sidebar takes 340px, canvas takes the rest)
        splitter.setSizes([340, 760])
        splitter.setCollapsible(0, False)
        
        # --- STATUS BAR ---
        self.lbl_status_coords = QLabel("Tọa độ: -")
        self.lbl_status_color = QLabel("Màu dưới con trỏ: -")
        self.lbl_status_zoom = QLabel("Thu phóng: 100%")
        
        self.statusBar().addPermanentWidget(self.lbl_status_coords, 1)
        self.statusBar().addPermanentWidget(self.lbl_status_color, 2)
        self.statusBar().addPermanentWidget(self.lbl_status_zoom, 1)
        
        # Hotkeys
        self.setup_shortcuts()
        
        # Update swatches visually
        self.update_color_swatch_display()
        self.update_replace_swatch_display()
        
        # Initialize default active tool to Pan
        self.select_tool("pan")
        
    # (create_card method removed, functionality implemented in CollapsibleCard class)
        
    def setup_shortcuts(self):
        # Ctrl+O : Open
        act_open = QAction("Open", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self.open_image_dialog)
        self.addAction(act_open)
        
        # Ctrl+S : Save
        act_save = QAction("Save", self)
        act_save.setShortcut(QKeySequence("Ctrl+S"))
        act_save.triggered.connect(self.save_image_dialog)
        self.addAction(act_save)
        
        # Ctrl+Z : Undo
        act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.triggered.connect(self.undo)
        self.addAction(act_undo)
        
        # Ctrl+Y : Redo
        act_redo = QAction("Redo", self)
        act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        act_redo.triggered.connect(self.redo)
        self.addAction(act_redo)
        
        # Ctrl+T : Redo alternate
        act_redo_t = QAction("Redo Alternate", self)
        act_redo_t.setShortcut(QKeySequence("Ctrl+T"))
        act_redo_t.triggered.connect(self.redo)
        self.addAction(act_redo_t)
        
        # Esc : Cancel current active tool and reset to Pan/Zoom mode
        act_esc = QAction("Cancel Tool", self)
        act_esc.setShortcut(QKeySequence("Esc"))
        act_esc.triggered.connect(lambda: self.select_tool("pan"))
        self.addAction(act_esc)
        
    def apply_theme(self):
        # GORGEOUS PREMIUM DARK CLASSMORPHISM THEME QSS
        qss = """
        QMainWindow {
            background-color: #0d0d10;
        }
        
        QStatusBar {
            background-color: #141419;
            color: #8c909e;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            border-top: 1px solid #202026;
        }
        
        QStatusBar QLabel {
            padding: 3px 10px;
            border-right: 1px solid #202026;
        }
        
        /* Sidebar container */
        QFrame#sidebar {
            background-color: #141419;
            border-radius: 12px;
            border: 1px solid #202026;
        }
        
        QFrame#titleCard {
            background: transparent;
            border: none;
        }
        
        QLabel#appTitle {
            color: #00adb5;
            font-family: 'Outfit', 'Segoe UI', sans-serif;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 2.5px;
        }
        
        QLabel#appSubtitle {
            color: #6a6f80;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 600;
        }
        
        /* Tabs Styling */
        QTabWidget::pane {
            border: 1px solid #252530;
            background-color: #141419;
            border-radius: 8px;
            top: -1px;
        }
        QTabBar::tab {
            background-color: #1a1a22;
            color: #a0a5b5;
            border: 1px solid #252530;
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 8px 16px;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: bold;
            margin-right: 4px;
        }
        QTabBar::tab:selected {
            background-color: #141419;
            color: #00adb5;
            border-color: #252530;
        }
        QTabBar::tab:hover {
            color: #ffffff;
        }
        
        QLabel#cardHeader {
            color: #d1d4dc;
            font-family: 'Outfit', 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid #2e2e3d;
            padding-bottom: 4px;
            margin-top: 5px;
            margin-bottom: 5px;
        }
        
        /* Buttons */
        QPushButton {
            background-color: #262633;
            color: #e5e9f0;
            border-radius: 6px;
            border: 1px solid #343447;
            padding: 7px 14px;
            font-family: 'Segoe UI', sans-serif;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #2f2f42;
            border-color: #4a4a66;
        }
        QPushButton:pressed {
            background-color: #1f1f2a;
        }
        QPushButton:disabled {
            background-color: #141419;
            color: #4f525d;
            border-color: #1e1e24;
        }
        
        QPushButton#primaryBtn {
            background-color: #00adb5;
            color: #0a0a0f;
            border: 1px solid #00c7d1;
        }
        QPushButton#primaryBtn:hover {
            background-color: #00cfda;
            border-color: #00e5f2;
        }
        QPushButton#primaryBtn:pressed {
            background-color: #008f96;
        }
        QPushButton#primaryBtn:disabled {
            background-color: #003639;
            color: #006b70;
            border-color: #004547;
        }
        
        QPushButton#accentBtn {
            background-color: #162a35;
            color: #00e5f2;
            border: 1px solid #005f63;
        }
        QPushButton#accentBtn:hover {
            background-color: #1c3c4b;
            border-color: #009ca3;
        }
        QPushButton#accentBtn:checked {
            background-color: #00adb5;
            color: #0a0a0f;
            border-color: #00e5f2;
        }
        
        QPushButton#dangerBtn {
            background-color: #2d1d22;
            color: #ff5252;
            border: 1px solid #5d1c24;
        }
        QPushButton#dangerBtn:hover {
            background-color: #3f2229;
            border-color: #8c2a33;
        }
        
        /* ComboBox */
        QComboBox {
            background-color: #20202a;
            color: #e5e9f0;
            border: 1px solid #2e2e3d;
            border-radius: 6px;
            padding: 6px 12px;
            font-family: 'Segoe UI', sans-serif;
            font-size: 12px;
        }
        QComboBox:hover {
            border-color: #46465c;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left-width: 0px;
        }
        QComboBox QAbstractItemView {
            background-color: #1e1e26;
            color: #e5e9f0;
            selection-background-color: #00adb5;
            selection-color: #0a0a0f;
            border: 1px solid #2e2e3d;
            outline: 0;
        }
        
        /* Sliders */
        QSlider::groove:horizontal {
            border: 1px solid #2d2d3a;
            height: 6px;
            background: #14141a;
            margin: 2px 0;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #00adb5;
            border: 1px solid #00c7d1;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QSlider::handle:horizontal:hover {
            background: #00cfda;
            border-color: #00e5f2;
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }
        QSlider::sub-page:horizontal {
            background: #005f63;
            border-radius: 3px;
        }
        
        /* SpinBoxes */
        QSpinBox {
            background-color: #20202a;
            color: #e5e9f0;
            border: 1px solid #2e2e3d;
            border-radius: 4px;
            padding: 4px;
            min-width: 50px;
            font-size: 11px;
            font-weight: 600;
        }
        QSpinBox:hover {
            border-color: #46465c;
        }
        
        /* Labels & Info Styles */
        QLabel#sliderLabel, QLabel#colorLabel {
            color: #a0a5b5;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 600;
        }
        QLabel#sliderValue {
            color: #00adb5;
            font-weight: bold;
            font-size: 12px;
        }
        
        QCheckBox {
            color: #a0a5b5;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            font-weight: 600;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #2e2e3d;
            border-radius: 4px;
            background-color: #20202a;
        }
        QCheckBox::indicator:hover {
            border-color: #46465c;
        }
        QCheckBox::indicator:checked {
            background-color: #00adb5;
            border-color: #00c7d1;
        }
        
        /* Swatches */
        QFrame#colorSwatch {
            border-radius: 6px;
            border: 2px solid #2d2d3a;
        }
        QFrame#replaceSwatch {
            border-radius: 4px;
            border: 2px solid #2d2d3a;
        }
        
        /* Canvas View Panel */
        QFrame#canvasPanel {
            background-color: #101014;
            border-radius: 12px;
            border: 1px solid #202026;
        }
        
        QFrame#viewToolbar {
            background-color: #141419;
            border-bottom: 1px solid #202026;
            border-top-left-radius: 11px;
            border-top-right-radius: 11px;
        }
        
        QLabel#filenameLabel {
            color: #d1d4dc;
            font-family: 'Outfit', 'Segoe UI', sans-serif;
            font-size: 12px;
            font-weight: 600;
        }
        
        QPushButton#toolBtn {
            background-color: #1c1c24;
            border: 1px solid #2a2a35;
            padding: 4px 10px;
            font-size: 11px;
            border-radius: 4px;
        }
        QPushButton#toolBtn:hover {
            background-color: #262632;
            border-color: #38384a;
        }
        """
        self.setStyleSheet(qss)
        
    def update_controls_state(self):
        """Enable/disable buttons based on whether an image is loaded."""
        has_image = (self.active_pil_base is not None)
        
        # Individual controls within tabs are disabled below — tabs themselves stay clickable
        
        # Toolbox
        self.btn_tool_pan.setEnabled(has_image)
        self.btn_tool_pipette.setEnabled(has_image)
        self.btn_tool_brush.setEnabled(has_image)
        self.btn_tool_eraser.setEnabled(has_image)
        
        # Enable elements only when image is present
        self.btn_custom_color.setEnabled(has_image)
        self.btn_save.setEnabled(has_image)
        self.combo_mode.setEnabled(has_image)
        self.replace_container.setEnabled(has_image)
        self.slider_tolerance.setEnabled(has_image)
        self.slider_softness.setEnabled(has_image)
        self.spin_tolerance.setEnabled(has_image)
        self.spin_softness.setEnabled(has_image)
        self.chk_live.setEnabled(has_image)
        self.btn_apply.setEnabled(has_image)
        self.btn_reset.setEnabled(has_image)
        
        # Slicing controls
        self.combo_slice_mode.setEnabled(has_image)
        self.spin_cols.setEnabled(has_image)
        self.spin_rows.setEnabled(has_image)
        self.spin_obj_count.setEnabled(has_image)
        self.spin_min_size.setEnabled(has_image)
        self.btn_slice.setEnabled(has_image)
        
        if hasattr(self, 'btn_align_sprites'):
            slice_mode_idx = self.combo_slice_mode.currentIndex()
            if has_image and slice_mode_idx == 1:
                self.btn_align_sprites.setEnabled(len(self.canvas.auto_slice_boxes) > 0)
            elif has_image and slice_mode_idx == 2:
                self.btn_align_sprites.setEnabled(len(self.canvas.manual_slice_boxes) > 0)
            else:
                self.btn_align_sprites.setEnabled(False)
        
        # Animation controls
        self.spin_fps.setEnabled(has_image)
        self.btn_play_preview.setEnabled(has_image)
        self.btn_export_gif.setEnabled(has_image)
        self.btn_export_mp4.setEnabled(has_image)
        
        # Undo/Redo states
        can_undo = (self.history_index > 0)
        can_redo = (self.history_index < len(self.history) - 1)
        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)
        
        # Show/hide replacement color widget
        is_replace_mode = (self.combo_mode.currentIndex() == 3)
        self.replace_container.setVisible(is_replace_mode)
        
    # --- FILE OPERATIONS ---
    
    def open_image_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Mở Ảnh (Open Image)", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tiff)"
        )
        if file_path:
            self.load_image_file(file_path)
            
    def load_image_file(self, file_path: str):
        # Create loading dialog
        self.loading_dialog = LoadingDialog("Đang tải ảnh... (Loading Image...)", self)
        
        # Setup worker
        self.loader_worker = LoadImageWorker(file_path)
        self.loader_worker.finished.connect(self.on_image_loaded)
        self.loader_worker.start()
        
        # Show dialog
        self.loading_dialog.exec()
        
    def on_image_loaded(self, result_pil, result_qimg, file_path):
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
            
        if isinstance(result_pil, Exception):
            QMessageBox.critical(self, "Lỗi (Error)", f"Không thể tải tệp ảnh:\n{str(result_pil)}")
            return
            
        # Store base images and reset history
        self.original_image_path = file_path
        self.lbl_filename.setText(os.path.basename(file_path))
        
        # Setup history with the new original image (in RGBA)
        self.history = [result_pil]
        self.history_index = 0
        self.active_pil_base = result_pil
        self.active_pil_result = result_pil
        self.custom_slice_offsets = {}
        
        # Set image directly on canvas (uses pre-converted QImage)
        self.canvas.set_image(result_qimg)
        
        # Update zoom label
        self.lbl_status_zoom.setText(f"Thu phóng: {int(self.canvas.zoom_factor * 100)}%")
        
        # Re-enable controls
        self.update_controls_state()
        
        self.has_active_color_selection = False
        
        # Automatically switch to edit tab when image is loaded
        self.tabs.setCurrentIndex(0)
        
        # Trigger first process to match defaults
        self.process_image()
        
    def save_image_dialog(self):
        if self.active_pil_result is None:
            return
            
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Lưu Ảnh (Save Image)", "edited_image.png", "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
        )
        if file_path:
            file_format = "PNG"
            if file_path.lower().endswith((".jpg", ".jpeg")) or "JPEG" in selected_filter:
                file_format = "JPEG"
                
            self.loading_dialog = LoadingDialog("Đang lưu ảnh... (Saving Image...)", self)
            
            self.saver_worker = SaveImageWorker(self.active_pil_result, file_path, file_format)
            self.saver_worker.finished.connect(self.on_image_saved)
            self.saver_worker.start()
            
            self.loading_dialog.exec()
            
    def on_image_saved(self, result):
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
            
        if isinstance(result, Exception):
            QMessageBox.critical(self, "Lỗi (Error)", f"Không thể lưu ảnh:\n{str(result)}")
        else:
            QMessageBox.information(self, "Thành công (Success)", "Đã lưu ảnh thành công!")
                
    # --- DRAG AND DROP ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff')):
                self.load_image_file(file_path)
                break
                
    def auto_bake_if_needed(self):
        """Automatically bake the current active edit if there are unbaked changes."""
        if not self.has_active_color_selection:
            return
            
        if self.active_pil_base is not None and self.active_pil_result is not None:
            # If the result is different from the base, silently bake it
            if self.active_pil_base != self.active_pil_result:
                self.history = self.history[:self.history_index + 1]
                self.history.append(self.active_pil_result)
                self.history_index += 1
                self.active_pil_base = self.active_pil_result
                
                # Update canvas images (PRESERVING zoom/pan)
                qimg_base = pil_to_qimage(self.active_pil_base)
                self.canvas.orig_image = qimg_base
                self.canvas.display_image = qimg_base.copy()
                self.canvas.update()
                
                # Reset sliders without triggering signals
                self.slider_tolerance.blockSignals(True)
                self.slider_softness.blockSignals(True)
                self.spin_tolerance.blockSignals(True)
                self.spin_softness.blockSignals(True)
                
                self.slider_tolerance.setValue(30)
                self.slider_softness.setValue(10)
                self.spin_tolerance.setValue(30)
                self.spin_softness.setValue(10)
                
                self.slider_tolerance.blockSignals(False)
                self.slider_softness.blockSignals(False)
                self.spin_tolerance.blockSignals(False)
                self.spin_softness.blockSignals(False)
                
                self.update_controls_state()
                
        self.has_active_color_selection = False

    # --- TOOLBOX SELECTION ---
    def select_tool(self, tool):
        # Auto-bake if we are switching tools and had an active color edit
        self.auto_bake_if_needed()
        
        # Reset check states on all tool buttons
        self.btn_tool_pan.setChecked(tool == "pan")
        self.btn_tool_pipette.setChecked(tool == "pipette")
        self.btn_tool_brush.setChecked(tool == "brush")
        self.btn_tool_eraser.setChecked(tool == "eraser")
        
        # Update canvas states
        self.canvas.set_pipette_active(tool == "pipette")
        
        if tool in ("brush", "eraser"):
            self.canvas.set_drawing_mode(tool)
            self.on_brush_params_changed()
        else:
            self.canvas.set_drawing_mode("none")
            
        # Show brush settings panel only when drawing/erasing
        self.draw_params_widget.setVisible(tool in ("brush", "eraser"))
        
    def on_brush_params_changed(self):
        self.canvas.brush_size = self.slider_brush_size.value()
        self.canvas.brush_hardness = self.slider_brush_hardness.value()
        self.canvas.brush_opacity = self.slider_brush_opacity.value()
        self.canvas.brush_color = QColor(self.selected_color)
        
    def on_drawing_finished(self, qimg):
        # Stroke completed, convert updated canvas view back to PIL
        pil_img = qimage_to_pil(qimg)
        
        # Save to history stack
        self.history = self.history[:self.history_index + 1]
        self.history.append(pil_img)
        self.history_index += 1
        
        self.active_pil_base = pil_img
        self.active_pil_result = pil_img
        
        # Update canvas orig_image with drawing
        self.canvas.orig_image = qimg.copy()
        self.update_controls_state()

    def on_canvas_color_picked(self, color: QColor):
        self.selected_color = color
        self.update_color_swatch_display()
        # Automatically restore pan/zoom tool
        self.select_tool("pan")
        self.has_active_color_selection = True
        self.process_image()
        
    def open_color_dialog(self):
        self.auto_bake_if_needed()
        color = QFileDialog.getColor(self.selected_color, self, "Chọn màu gốc (Source Color)")
        if color.isValid():
            self.selected_color = color
            self.update_color_swatch_display()
            self.has_active_color_selection = True
            self.process_image()
            
    def open_replace_color_dialog(self):
        color = QFileDialog.getColor(self.replace_color, self, "Chọn màu thay thế (Target Color)")
        if color.isValid():
            self.replace_color = color
            self.update_replace_swatch_display()
            self.process_image()
            
    def update_color_swatch_display(self):
        rgb_str = f"RGB: {self.selected_color.red()}, {self.selected_color.green()}, {self.selected_color.blue()}"
        hex_str = f"HEX: {self.selected_color.name().upper()}"
        self.lbl_color_info.setText(f"{rgb_str}\n{hex_str}")
        self.color_swatch.setStyleSheet(f"background-color: {self.selected_color.name()};")
        
    def update_replace_swatch_display(self):
        self.replace_swatch.setStyleSheet(f"background-color: {self.replace_color.name()};")
        
    # --- EVENTS & PROCESSORS ---
    def on_mode_changed(self, index):
        self.update_controls_state()
        self.process_image()
        
    def on_param_changed(self):
        if self.chk_live.isChecked():
            # Trigger process after a short delay to group quick drags (debounce)
            self.debounce_timer.start()
            
    def process_image(self):
        if self.active_pil_base is None:
            return
            
        # If thread is currently running, set pending flag and return
        if self.processing_thread is not None and self.processing_thread.isRunning():
            self.pending_process = True
            return
            
        mode_idx = self.combo_mode.currentIndex()
        modes = ['erase', 'isolate', 'splash', 'replace']
        selected_mode = modes[mode_idx]
        
        target = (self.selected_color.red(), self.selected_color.green(), self.selected_color.blue())
        replace = (self.replace_color.red(), self.replace_color.green(), self.replace_color.blue())
        
        # Show feedback in status bar
        self.statusBar().showMessage("Đang xử lý tách màu... (Processing colors...)")
        
        # Start worker thread
        self.processing_thread = ImageWorker(
            base_pil=self.active_pil_base,
            target_color=target,
            tolerance=float(self.slider_tolerance.value()),
            softness=float(self.slider_softness.value()),
            mode=selected_mode,
            replace_color=replace
        )
        self.processing_thread.finished.connect(self.on_process_finished)
        self.processing_thread.start()
        
    def on_process_finished(self, result_pil, result_qimg):
        self.processing_thread = None
        self.statusBar().clearMessage()
        
        if isinstance(result_pil, Exception):
            self.statusBar().showMessage(f"Lỗi xử lý: {str(result_pil)}", 5000)
            return
            
        self.active_pil_result = result_pil
        
        # Display the pre-converted QImage directly
        self.canvas.set_display_image(result_qimg)
        
        # If another process was requested during execution, run it now
        if self.pending_process:
            self.pending_process = False
            self.process_image()
        
    def bake_current_edit(self):
        """Save the current active image changes into the undo history stack."""
        if self.active_pil_result is None:
            return
            
        # Truncate history forward if we are in the middle of undo edits
        self.history = self.history[:self.history_index + 1]
        
        # Append the new baked step
        self.history.append(self.active_pil_result)
        self.history_index += 1
        
        # Update current working base to this baked result
        self.active_pil_base = self.active_pil_result
        
        # Set original canvas state to reflect this new base for pipette color pickers
        qimg_base = pil_to_qimage(self.active_pil_base)
        self.canvas.orig_image = qimg_base
        self.canvas.display_image = qimg_base.copy()
        self.canvas.update()
        
        self.has_active_color_selection = False
        
        # Reset tolerance sliders and update UI controls
        self.slider_tolerance.setValue(30)
        self.slider_softness.setValue(10)
        self.update_controls_state()
        
        # Notify user subtly in status bar
        self.statusBar().showMessage("Đã lưu giữ các chỉnh sửa hiện tại!", 3000)

    # --- UNDO / REDO / RESET ---
    def undo(self):
        if self.tabs.currentIndex() == 2 and self.combo_slice_mode.currentIndex() == 2:
            if self.canvas.undo_manual():
                self.statusBar().showMessage("Đã hoàn tác ô vẽ thủ công (Undo box)!", 2000)
            else:
                self.statusBar().showMessage("Không thể hoàn tác!", 2000)
        else:
            if self.history_index > 0:
                self.history_index -= 1
                self.restore_history_state()
                self.statusBar().showMessage("Đã hoàn tác (Undo)!", 2000)
            
    def redo(self):
        if self.tabs.currentIndex() == 2 and self.combo_slice_mode.currentIndex() == 2:
            if self.canvas.redo_manual():
                self.statusBar().showMessage("Đã làm lại ô vẽ thủ công (Redo box)!", 2000)
            else:
                self.statusBar().showMessage("Không thể làm lại!", 2000)
        else:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.restore_history_state()
                self.statusBar().showMessage("Đã làm lại (Redo)!", 2000)
            
    def restore_history_state(self):
        """Update working images based on history_index."""
        self.active_pil_base = self.history[self.history_index]
        self.active_pil_result = self.active_pil_base
        
        # Push to canvas (preserving zoom/pan)
        qimg = pil_to_qimage(self.active_pil_base)
        self.canvas.orig_image = qimg
        self.canvas.display_image = qimg.copy()
        self.canvas.update()
        
        self.has_active_color_selection = False
        
        # Reset sliders to avoid double applying immediately
        self.slider_tolerance.setValue(30)
        self.slider_softness.setValue(10)
        
        self.update_controls_state()
        self.process_image()
        
    def reset_to_original(self):
        if not self.history:
            return
            
        reply = QMessageBox.question(
            self, "Xác nhận khôi phục", "Bạn có chắc chắn muốn khôi phục ảnh gốc không? Tất cả các bước chỉnh sửa trước đó sẽ bị xóa.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Set index to 0 (the initial original image loaded)
            self.history_index = 0
            self.history = [self.history[0]] # Truncate everything else
            self.restore_history_state()
            self.statusBar().showMessage("Đã khôi phục về ảnh gốc!", 3000)
            
    # --- CANVAS FEEDBACK EVENTS ---
    def on_canvas_hover(self, color: QColor, pixel_pos: QPoint):
        # Update mouse coordinates
        self.lbl_status_coords.setText(f"Tọa độ: {pixel_pos.x()}, {pixel_pos.y()}")
        
        # Update mouse hover color
        if color.isValid():
            r, g, b = color.red(), color.green(), color.blue()
            hex_name = color.name().upper()
            self.lbl_status_color.setText(f"Màu dưới con trỏ: RGB({r},{g},{b}) | {hex_name}")
        else:
            self.lbl_status_color.setText("Màu dưới con trỏ: -")
            
        # Update zoom indicator
        self.lbl_status_zoom.setText(f"Thu phóng: {int(self.canvas.zoom_factor * 100)}%")

    # --- SLICING EVENT HANDLERS ---
    def on_tab_changed(self, index):
        # Stop animation preview if playing and switching away from tab 3 (Chuyển Động)
        if index != 3 and hasattr(self, 'is_playing_animation') and self.is_playing_animation:
            self.stop_animation_preview()
            
        if index == 2:  # Tab Cắt Ảnh
            self.auto_bake_if_needed()
            self.canvas.show_slice_grid = True
            
            slice_mode_idx = self.combo_slice_mode.currentIndex()
            if slice_mode_idx == 1:
                self.canvas.slice_mode = "auto"
                self.run_auto_object_detection()
            elif slice_mode_idx == 2:
                self.canvas.slice_mode = "manual"
            else:
                self.canvas.slice_mode = "grid"
                self.canvas.slice_cols = self.spin_cols.value()
                self.canvas.slice_rows = self.spin_rows.value()
        else:
            self.canvas.show_slice_grid = False
        
        self.canvas.update_canvas_cursor()
        self.canvas.update()
        self.update_controls_state()
        
    def on_slice_mode_changed(self, index):
        self.grid_settings_widget.setVisible(index == 0)
        self.auto_settings_widget.setVisible(index == 1)
        self.manual_settings_widget.setVisible(index == 2)
        
        if index == 1:
            self.canvas.slice_mode = "auto"
            self.run_auto_object_detection()
        elif index == 2:
            self.canvas.slice_mode = "manual"
        else:
            self.canvas.slice_mode = "grid"
            self.canvas.slice_cols = self.spin_cols.value()
            self.canvas.slice_rows = self.spin_rows.value()
            
        if self.tabs.currentIndex() == 2:
            self.canvas.show_slice_grid = True
            
        self.canvas.update_canvas_cursor()
        self.canvas.update()
        self.update_controls_state()
        
    def on_auto_detect_changed(self):
        if self.combo_slice_mode.currentIndex() == 1:
            self.run_auto_object_detection()
            
    def run_auto_object_detection(self):
        if self.active_pil_result is None:
            self.canvas.auto_slice_boxes = []
            return
            
        try:
            import cv2
            import numpy as np
            
            arr = np.array(self.active_pil_result)
            alpha = arr[:, :, 3]
            
            _, thresh = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            boxes = []
            min_sz = self.spin_min_size.value()
            
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if w >= min_sz and h >= min_sz:
                    boxes.append((x, y, w, h))
                    
            boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
            
            target_count = self.spin_obj_count.value()
            boxes = boxes[:target_count]
            
            row_threshold = max(20, self.active_pil_result.height // 15)
            boxes.sort(key=lambda b: (b[1] // row_threshold, b[0]))
            
            self.canvas.auto_slice_boxes = boxes
        except Exception as e:
            self.canvas.auto_slice_boxes = []
            self.statusBar().showMessage(f"Lỗi nhận diện vật thể: {str(e)}", 4000)
            
        self.canvas.update()
        self.update_controls_state()
        
    def on_slice_grid_changed(self):
        self.canvas.slice_cols = self.spin_cols.value()
        self.canvas.slice_rows = self.spin_rows.value()
        if self.tabs.currentIndex() == 2:
            self.canvas.show_slice_grid = True
        self.canvas.update()

    def clear_manual_boxes(self):
        self.canvas.clear_manual_boxes()
        self.statusBar().showMessage("Đã xóa tất cả các ô vẽ thủ công!", 2000)

    def on_manual_boxes_changed(self, boxes):
        self.statusBar().showMessage(f"Đã vẽ {len(boxes)} ô cắt thủ công", 3000)
        self.update_controls_state()

    def open_alignment_dialog(self):
        if self.active_pil_result is None:
            return
            
        slice_mode_idx = self.combo_slice_mode.currentIndex()
        if slice_mode_idx == 1:
            boxes = self.canvas.auto_slice_boxes
        elif slice_mode_idx == 2:
            boxes = self.canvas.manual_slice_boxes
        else:
            return
            
        if not boxes:
            return
            
        dialog = SpriteAlignmentDialog(self.active_pil_result, boxes, self.custom_slice_offsets, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.custom_slice_offsets = dialog.offsets
            if self.is_playing_animation:
                self.start_animation_preview()
            self.statusBar().showMessage("Đã lưu tọa độ căn chỉnh vị trí!", 3000)
            self.slice_image()

    def slice_image(self):
        if self.active_pil_result is None:
            return
            
        slice_mode_idx = self.combo_slice_mode.currentIndex()
        
        if slice_mode_idx == 1:
            boxes = self.canvas.auto_slice_boxes
            if not boxes:
                QMessageBox.warning(self, "Cảnh báo (Warning)", "Không tìm thấy vật thể nào! Hãy chắc chắn đã xóa nền phông ảnh.")
                return
            total = len(boxes)
        elif slice_mode_idx == 2:
            boxes = self.canvas.manual_slice_boxes
            if not boxes:
                QMessageBox.warning(self, "Cảnh báo (Warning)", "Không có ô cắt nào được vẽ! Hãy nhấp và kéo chuột trên ảnh để vẽ ô cắt.")
                return
            total = len(boxes)
        else:
            cols = self.spin_cols.value()
            rows = self.spin_rows.value()
            total = cols * rows
            boxes = []
            
        # Open choice dialog
        choice_dialog = PostSliceChoiceDialog(total, self.spin_fps.value(), self)
        if choice_dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        action = choice_dialog.selected_action
        chosen_fps = choice_dialog.fps
        
        # Synchronize app FPS
        self.spin_fps.setValue(chosen_fps)
        
        if action == 'save':
            dest_dir = QFileDialog.getExistingDirectory(
                self, "Chọn thư mục lưu các ảnh cắt (Select Output Folder)", ""
            )
            if not dest_dir:
                return
                
            # Create loading dialog
            self.loading_dialog = LoadingDialog("Bắt đầu cắt ảnh... (Preparing slicing...)", self)
            self.loading_dialog.set_range(0, total)
            
            # Setup worker
            if slice_mode_idx == 1:
                self.slice_worker = SliceImageWorker(
                    pil_image=self.active_pil_result,
                    dest_dir=dest_dir,
                    mode="auto",
                    boxes=boxes,
                    equalize_size=self.chk_equalize_size.isChecked(),
                    offsets=self.custom_slice_offsets
                )
            elif slice_mode_idx == 2:
                self.slice_worker = SliceImageWorker(
                    pil_image=self.active_pil_result,
                    dest_dir=dest_dir,
                    mode="manual",
                    boxes=boxes,
                    equalize_size=self.chk_equalize_size.isChecked(),
                    offsets=self.custom_slice_offsets
                )
            else:
                self.slice_worker = SliceImageWorker(
                    pil_image=self.active_pil_result,
                    dest_dir=dest_dir,
                    mode="grid",
                    cols=self.spin_cols.value(),
                    rows=self.spin_rows.value()
                )
                
            self.slice_worker.progress.connect(self.on_slice_progress)
            self.slice_worker.finished.connect(self.on_slice_finished)
            self.slice_worker.start()
            
            # Show dialog
            self.loading_dialog.exec()
            
        elif action == 'preview':
            self.tabs.setCurrentIndex(3)  # Switch to Anim tab
            self.start_animation_preview()
            self.statusBar().showMessage(f"Đang xem trước hoạt ảnh ở tốc độ {chosen_fps} FPS!", 3000)
            
        elif action == 'gif':
            self.export_gif()
            
        elif action == 'mp4':
            self.export_mp4()
        
    def on_slice_progress(self, current, total):
        if self.loading_dialog:
            self.loading_dialog.set_value(current)
            self.loading_dialog.set_message(f"Đang cắt ảnh: {current}/{total}...")
            
    def on_slice_finished(self, result):
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
            
        if isinstance(result, Exception):
            QMessageBox.critical(
                self, "Lỗi (Error)", 
                f"Đã xảy ra lỗi trong quá trình cắt ảnh:\n{str(result)}"
            )
        else:
            slice_mode_idx = self.combo_slice_mode.currentIndex()
            if slice_mode_idx == 1:
                count = len(self.canvas.auto_slice_boxes)
            elif slice_mode_idx == 2:
                count = len(self.canvas.manual_slice_boxes)
            else:
                count = self.spin_cols.value() * self.spin_rows.value()
            QMessageBox.information(
                self, "Thành công (Success)", 
                f"Đã cắt và lưu thành công tất cả {count} ảnh!"
            )
 
    # --- ANIMATION & EXPORT WORKERS AND HANDLERS ---
    def get_slice_frames(self):
        """Helper to get list of PIL Images for the sliced grid/auto boxes."""
        if self.active_pil_result is None:
            return []
            
        slice_mode_idx = self.combo_slice_mode.currentIndex()
        frames = []
        
        if slice_mode_idx in (1, 2):
            boxes = self.canvas.auto_slice_boxes if slice_mode_idx == 1 else self.canvas.manual_slice_boxes
            if not boxes:
                return []
                
            equalize = self.chk_equalize_size.isChecked()
            if equalize:
                max_w = max(b[2] for b in boxes)
                max_h = max(b[3] for b in boxes)
                
            for idx, (bx, by, bw, bh) in enumerate(boxes):
                sub_img = self.active_pil_result.crop((bx, by, bx + bw, by + bh))
                if equalize:
                    from PIL import Image
                    padded = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
                    if hasattr(self, 'custom_slice_offsets') and idx in self.custom_slice_offsets:
                        offset_x, offset_y = self.custom_slice_offsets[idx]
                    else:
                        offset_x = (max_w - bw) // 2
                        offset_y = (max_h - bh) // 2
                    padded.paste(sub_img, (offset_x, offset_y))
                    frames.append(padded)
                else:
                    frames.append(sub_img)
        else:
            W, H = self.active_pil_result.size
            C, R = self.spin_cols.value(), self.spin_rows.value()
            for r in range(R):
                for c in range(C):
                    x1 = int(c * W / C)
                    y1 = int(r * H / R)
                    x2 = int((c + 1) * W / C)
                    y2 = int((r + 1) * H / R)
                    sub_img = self.active_pil_result.crop((x1, y1, x2, y2))
                    frames.append(sub_img)
        return frames

    def on_fps_changed(self):
        if self.is_playing_animation:
            self.start_animation_preview()

    def toggle_animation_preview(self):
        if self.is_playing_animation:
            self.stop_animation_preview()
        else:
            self.start_animation_preview()

    def start_animation_preview(self):
        if self.active_pil_result is None:
            return
            
        frames = self.get_slice_frames()
        if len(frames) <= 1:
            QMessageBox.warning(self, "Cảnh báo (Warning)", "Hãy chia lưới ô ngang hoặc dọc lớn hơn 1 để chạy hoạt ảnh!")
            return
            
        # Store QImages directly for zero-latency screen renders
        self.animation_qimages = [pil_to_qimage(img) for img in frames]
        self.animation_index = 0
        
        self.animation_timer.stop()
        fps = self.spin_fps.value()
        self.animation_timer.start(int(1000 / fps))
        
        self.btn_play_preview.setText("Dừng Xem Trước (Pause)")
        self.btn_play_preview.setObjectName("dangerBtn")
        self.btn_play_preview.setStyleSheet("background-color: #2d1d22; color: #ff5252; border: 1px solid #5d1c24;")
        self.is_playing_animation = True
        
    def stop_animation_preview(self):
        self.animation_timer.stop()
        self.btn_play_preview.setText("Xem Trước Chuyển Động (Play Preview)")
        self.btn_play_preview.setObjectName("primaryBtn")
        self.btn_play_preview.setStyleSheet("")
        self.is_playing_animation = False
        
        # Restore normal display image on canvas
        if self.active_pil_result:
            self.canvas.set_display_image(pil_to_qimage(self.active_pil_result))

    def play_next_animation_frame(self):
        if not self.animation_qimages:
            return
        
        self.animation_index = (self.animation_index + 1) % len(self.animation_qimages)
        self.canvas.set_display_image(self.animation_qimages[self.animation_index])

    def export_gif(self):
        if self.active_pil_result is None:
            return
            
        frames = self.get_slice_frames()
        if len(frames) <= 1:
            QMessageBox.warning(self, "Cảnh báo (Warning)", "Chia lưới ô ngang/dọc > 1 để chạy chuyển động trước khi xuất!")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Xuất Ảnh Động GIF (Export animated GIF)", "animation.gif", "GIF Animation (*.gif)"
        )
        if not file_path:
            return
            
        self.loading_dialog = LoadingDialog("Đang chuẩn bị xuất tệp tin GIF...", self)
        self.loading_dialog.set_range(0, 100)
        
        self.gif_worker = ExportGifWorker(frames, file_path, self.spin_fps.value())
        self.gif_worker.progress.connect(self.on_export_progress)
        self.gif_worker.finished.connect(self.on_export_finished)
        self.gif_worker.start()
        
        self.loading_dialog.exec()

    def export_mp4(self):
        if self.active_pil_result is None:
            return
            
        frames = self.get_slice_frames()
        if len(frames) <= 1:
            QMessageBox.warning(self, "Cảnh báo (Warning)", "Chia lưới ô ngang/dọc > 1 để chạy chuyển động trước khi xuất!")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Xuất Video MP4 (Export Video)", "animation.mp4", "MP4 Video (*.mp4)"
        )
        if not file_path:
            return
            
        self.loading_dialog = LoadingDialog("Đang khởi tạo codec & biên dịch video...", self)
        self.loading_dialog.set_range(0, len(frames))
        
        self.video_worker = ExportVideoWorker(frames, file_path, self.spin_fps.value(), bg_color=(0, 0, 0))
        self.video_worker.progress.connect(self.on_export_progress)
        self.video_worker.finished.connect(self.on_export_finished)
        self.video_worker.start()
        
        self.loading_dialog.exec()

    def on_export_progress(self, current, total):
        if self.loading_dialog:
            self.loading_dialog.set_value(current)
            self.loading_dialog.set_message(f"Đang xuất file: {int(current * 100 / total)}% ({current}/{total})...")
            
    def on_export_finished(self, result):
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None
            
        if isinstance(result, Exception):
            QMessageBox.critical(self, "Lỗi (Error)", f"Không thể xuất tệp tin chuyển động:\n{str(result)}")
        else:
            QMessageBox.information(self, "Thành công (Success)", "Đã xuất tệp tin hoạt ảnh thành công!")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self.tabs.currentIndex() == 2 and self.combo_slice_mode.currentIndex() == 2:
                self.canvas.space_pressed = True
                self.canvas.update_canvas_cursor()
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if hasattr(self.canvas, 'space_pressed'):
                self.canvas.space_pressed = False
                self.canvas.update_canvas_cursor()
                event.accept()
                return
        super().keyReleaseEvent(event)

def main():
    app = QApplication(sys.argv)
    
    # Set a clean modern default font
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    editor = ColorEditorApp()
    editor.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

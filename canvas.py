from PyQt6.QtWidgets import QWidget, QFrame
from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal, QRect, QRectF
from PyQt6.QtGui import (
    QPainter, QPixmap, QColor, QBrush, QPen, QImage, 
    QMouseEvent, QWheelEvent, QCursor, QPainterPath, QFont,
    QRadialGradient
)
import math

class ImageCanvas(QFrame):
    color_selected = pyqtSignal(QColor)
    mouse_hover_color = pyqtSignal(QColor, QPoint)  # Emits (color, pixel_coords)
    drawing_finished = pyqtSignal(QImage)           # Emits the updated display QImage
    manual_boxes_changed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        
        # Image states
        self.orig_image = None       # Original QImage (for color sampling)
        self.display_image = None    # Processed QImage (to display)
        self.display_pixmap = None   # Cached QPixmap for fast drawing
        
        # Grid slicing states
        self.slice_cols = 1
        self.slice_rows = 1
        self.show_slice_grid = False
        self.slice_mode = "grid"      # "grid", "auto", or "manual"
        self.auto_slice_boxes = []    # list of (x, y, w, h) in image coordinates
        self.manual_slice_boxes = []  # list of (x, y, w, h) in image coordinates
        self.temp_manual_box = None
        self.is_drawing_manual_box = False
        self.draw_start_point = QPoint()
        self.space_pressed = False
        self.manual_undo_stack = []   # stack of lists of boxes
        self.manual_redo_stack = []   # stack of lists of boxes
        
        # View navigation states
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.last_mouse_pos = QPoint()
        self.is_panning = False
        
        # Pipette states
        self.pipette_active = False
        self.mouse_in_widget = False
        self.current_mouse_pos = QPoint()
        
        # Checkerboard brush for transparency preview
        self.checker_brush = self._create_checker_brush()
        
        # Drawing / brush states
        self.drawing_mode = "none" # "brush", "eraser", "none"
        self.brush_size = 15
        self.brush_hardness = 80 # 0 to 100
        self.brush_opacity = 100 # 0 to 100
        self.brush_color = QColor(255, 0, 0)
        self.is_drawing = False
        self.last_draw_point = QPoint()
        
    def _create_checker_brush(self) -> QBrush:
        # Create a 16x16 checkerboard pixmap
        tile = QPixmap(16, 16)
        tile.fill(QColor(240, 240, 240))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 8, 8, QColor(215, 215, 215))
        painter.fillRect(8, 8, 8, 8, QColor(215, 215, 215))
        painter.end()
        return QBrush(tile)
        
    def set_image(self, orig_qimage: QImage, display_qimage: QImage = None):
        """Set the image to display on the canvas."""
        self.orig_image = orig_qimage
        if display_qimage is not None:
            self.display_image = display_qimage
        else:
            self.display_image = orig_qimage.copy()
            
        self.display_pixmap = QPixmap.fromImage(self.display_image) # Cache QPixmap
        self.zoom_to_fit()
        self.update()
        
    def set_display_image(self, display_qimage: QImage):
        """Update only the processed image shown on screen (maintaining zoom/pan)."""
        self.display_image = display_qimage
        self.display_pixmap = QPixmap.fromImage(self.display_image) # Cache QPixmap
        self.update()

    def update_canvas_cursor(self):
        if getattr(self, 'space_pressed', False):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self.drawing_mode in ("brush", "eraser"):
            self.setCursor(Qt.CursorShape.BlankCursor)
        elif self.pipette_active:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.slice_mode == "manual" and self.show_slice_grid:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_pipette_active(self, active: bool):
        self.pipette_active = active
        self.update_canvas_cursor()
        self.update()
        
    def set_drawing_mode(self, mode: str):
        self.drawing_mode = mode
        self.update_canvas_cursor()
        self.update()
        
    def zoom_in(self):
        self._zoom(1.25, self.rect().center())
        
    def zoom_out(self):
        self._zoom(0.8, self.rect().center())
        
    def reset_zoom(self):
        self.zoom_factor = 1.0
        if self.display_image:
            # Center the image
            w_w, w_h = self.width(), self.height()
            i_w, i_h = self.display_image.width(), self.display_image.height()
            self.pan_offset = QPointF((w_w - i_w) / 2.0, (w_h - i_h) / 2.0)
        else:
            self.pan_offset = QPointF(0, 0)
        self.update()
        
    def zoom_to_fit(self):
        if not self.display_image:
            return
        
        w_w, w_h = self.width(), self.height()
        i_w, i_h = self.display_image.width(), self.display_image.height()
        
        # Calculate scale to fit with a 20px margin
        margin = 40
        scale_w = (w_w - margin) / i_w
        scale_h = (w_h - margin) / i_h
        
        self.zoom_factor = min(scale_w, scale_h, 10.0) # Cap fit zoom at 10x
        if self.zoom_factor < 0.05:
            self.zoom_factor = 0.05
            
        # Center image
        new_w = i_w * self.zoom_factor
        new_h = i_h * self.zoom_factor
        self.pan_offset = QPointF((w_w - new_w) / 2.0, (w_h - new_h) / 2.0)
        self.update()
        
    def _zoom(self, factor: float, center_point: QPoint):
        if not self.display_image:
            return
            
        old_zoom = self.zoom_factor
        self.zoom_factor = max(0.05, min(self.zoom_factor * factor, 50.0))
        
        # Zoom centered on the cursor / point
        p_widget = QPointF(center_point)
        p_img = (p_widget - self.pan_offset) / old_zoom
        self.pan_offset = p_widget - p_img * self.zoom_factor
        self.update()
        
    # Coordination conversion
    def widget_to_image_coords(self, pt: QPoint) -> QPoint:
        if not self.display_image:
            return QPoint(-1, -1)
        
        x = (pt.x() - self.pan_offset.x()) / self.zoom_factor
        y = (pt.y() - self.pan_offset.y()) / self.zoom_factor
        
        return QPoint(int(math.floor(x)), int(math.floor(y)))

    def image_to_widget_coords(self, pt: QPointF) -> QPointF:
        x = pt.x() * self.zoom_factor + self.pan_offset.x()
        y = pt.y() * self.zoom_factor + self.pan_offset.y()
        return QPointF(x, y)
        
    def is_pixel_in_bounds(self, pt: QPoint) -> bool:
        if not self.display_image:
            return False
        return 0 <= pt.x() < self.display_image.width() and 0 <= pt.y() < self.display_image.height()
        
    def get_color_at_pixel(self, pt: QPoint) -> QColor:
        if not self.orig_image or not self.is_pixel_in_bounds(pt):
            return QColor()
        return QColor(self.orig_image.pixel(pt.x(), pt.y()))
        
    # Events
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        # If no image, draw background text
        if not self.display_image:
            painter.setPen(QPen(QColor(130, 140, 150), 2))
            painter.setFont(QFont("Outfit", 14, QFont.Weight.Medium))
            painter.drawText(
                self.rect(), 
                Qt.AlignmentFlag.AlignCenter, 
                "Drag & Drop an image here\nor click 'Open Image' to start"
            )
            painter.end()
            return
            
        # 1. Draw Checkerboard background matching the image boundaries
        i_w = self.display_image.width() * self.zoom_factor
        i_h = self.display_image.height() * self.zoom_factor
        img_rect = QRectF(self.pan_offset.x(), self.pan_offset.y(), i_w, i_h)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.checker_brush)
        painter.drawRect(img_rect)
        
        # 2. Draw Processed/Display Image
        painter.drawPixmap(img_rect, self.display_pixmap, QRectF(self.display_pixmap.rect()))
        
        # 3. Draw border around image
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(100, 110, 120, 100), 1))
        painter.drawRect(img_rect)
        
        # 4. Draw slice grid overlay or auto bounding boxes if active
        if self.show_slice_grid:
            if self.slice_mode == "auto":
                self._draw_auto_boxes(painter, img_rect)
            elif self.slice_mode == "manual":
                self._draw_manual_boxes(painter, img_rect)
            else:
                self._draw_slice_grid(painter, img_rect)
            
        # 5. Draw magnifier glass if pipette is active and mouse is in widget
        img_pixel = self.widget_to_image_coords(self.current_mouse_pos)
        if self.pipette_active and self.mouse_in_widget and self.is_pixel_in_bounds(img_pixel):
            self._draw_magnifier(painter, self.current_mouse_pos, img_pixel)
            
        # 6. Draw brush cursor outline if drawing mode is active and mouse is in widget
        if self.drawing_mode in ("brush", "eraser") and self.mouse_in_widget and self.display_image:
            self._draw_brush_outline(painter)
            
        painter.end()
        
    def _draw_magnifier(self, painter: QPainter, mouse_pos: QPoint, center_pixel: QPoint):
        # Configuration for magnifier
        radius = 70
        magnification = 12
        grid_cells = 9  # odd number
        half_cells = grid_cells // 2
        
        # Get color at center pixel
        target_color = self.get_color_at_pixel(center_pixel)
        if not target_color.isValid():
            return
            
        # Positions
        # Offset magnifier slightly above and to the left of the cursor to keep it visible
        mag_center = mouse_pos + QPoint(-radius - 10, -radius - 10)
        # Keep magnifier inside widget bounds if it goes offscreen
        margin = 10
        if mag_center.x() - radius < margin:
            mag_center.setX(mouse_pos.x() + radius + 10)
        if mag_center.y() - radius < margin:
            mag_center.setY(mouse_pos.y() + radius + 10)
            
        painter.save()
        
        # Create clipping path for circular magnifier
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(mag_center), radius, radius)
        painter.setClipPath(clip_path)
        
        # Draw zoom grid pixels inside the circle
        painter.fillRect(
            QRect(mag_center.x() - radius, mag_center.y() - radius, radius * 2, radius * 2), 
            QColor(40, 40, 40)
        )
        
        cell_size = (radius * 2) / grid_cells
        
        for dy in range(-half_cells, half_cells + 1):
            for dx in range(-half_cells, half_cells + 1):
                px = center_pixel.x() + dx
                py = center_pixel.y() + dy
                
                cell_rect = QRectF(
                    mag_center.x() + dx * cell_size - cell_size / 2,
                    mag_center.y() + dy * cell_size - cell_size / 2,
                    cell_size,
                    cell_size
                )
                
                if 0 <= px < self.orig_image.width() and 0 <= py < self.orig_image.height():
                    pixel_color = QColor(self.orig_image.pixel(px, py))
                    # Draw pixel
                    painter.fillRect(cell_rect, pixel_color)
                else:
                    # Draw out of bounds checkerboard
                    is_even = (px + py) % 2 == 0
                    painter.fillRect(cell_rect, QColor(80, 80, 80) if is_even else QColor(50, 50, 50))
                    
        # Draw grid lines
        grid_pen = QPen(QColor(128, 128, 128, 60), 1)
        painter.setPen(grid_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(grid_cells + 1):
            # Vertical lines
            x_pos = mag_center.x() - radius + i * cell_size - cell_size / 2
            painter.drawLine(QPointF(x_pos, mag_center.y() - radius), QPointF(x_pos, mag_center.y() + radius))
            # Horizontal lines
            y_pos = mag_center.y() - radius + i * cell_size - cell_size / 2
            painter.drawLine(QPointF(mag_center.x() - radius, y_pos), QPointF(mag_center.x() + radius, y_pos))
            
        # Draw central pixel highlight border
        center_rect = QRectF(
            mag_center.x() - cell_size / 2,
            mag_center.y() - cell_size / 2,
            cell_size,
            cell_size
        )
        # Contrast border (black and white outline)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRect(center_rect)
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawRect(center_rect.adjusted(1, 1, -1, -1))
        
        # Restore clipping path to draw outer ring
        painter.restore()
        
        # Draw outer ring border
        painter.setPen(QPen(QColor(80, 200, 255), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(mag_center), radius, radius)
        
        # Draw tiny center crosshair on outer ring for pointer context
        painter.setPen(QPen(QColor(80, 200, 255, 120), 1))
        painter.drawLine(mag_center.x() - 10, mag_center.y(), mag_center.x() + 10, mag_center.y())
        painter.drawLine(mag_center.x(), mag_center.y() - 10, mag_center.x(), mag_center.y() + 10)
        
        # Draw Hex Code / RGB label pill below the magnifier
        hex_text = target_color.name().upper()
        font = QFont("Outfit", 9, QFont.Weight.Bold)
        painter.setFont(font)
        
        text_rect = painter.fontMetrics().boundingRect(hex_text)
        pill_w = text_rect.width() + 16
        pill_h = text_rect.height() + 8
        pill_rect = QRectF(
            mag_center.x() - pill_w / 2,
            mag_center.y() + radius + 5,
            pill_w,
            pill_h
        )
        
        # Draw pill background (black with transparency)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(20, 20, 20, 220)))
        painter.drawRoundedRect(pill_rect, 4.0, 4.0)
        
        # Draw pill text
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, hex_text)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = True
            self.update_canvas_cursor()
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = False
            self.update_canvas_cursor()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.space_pressed = False
        self.update_canvas_cursor()
        super().focusOutEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if not self.display_image:
            return
            
        img_pixel = self.widget_to_image_coords(event.position().toPoint())
        
        if self.drawing_mode in ("brush", "eraser"):
            if event.button() == Qt.MouseButton.LeftButton and self.is_pixel_in_bounds(img_pixel):
                self.is_drawing = True
                self.last_draw_point = img_pixel
                self._draw_brush_stroke(img_pixel, img_pixel)
                self.update()
        elif self.pipette_active:
            if event.button() == Qt.MouseButton.LeftButton and self.is_pixel_in_bounds(img_pixel):
                color = self.get_color_at_pixel(img_pixel)
                self.color_selected.emit(color)
                self.set_pipette_active(False)
        else:
            if getattr(self, 'space_pressed', False):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.is_panning = True
                    self.last_mouse_pos = event.position().toPoint()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return
            
            if self.slice_mode == "manual" and self.show_slice_grid and event.button() == Qt.MouseButton.LeftButton:
                # Clamp coordinates to image boundaries
                x_clamped = max(0, min(img_pixel.x(), self.display_image.width() - 1))
                y_clamped = max(0, min(img_pixel.y(), self.display_image.height() - 1))
                
                self.is_drawing_manual_box = True
                self.draw_start_point = QPoint(x_clamped, y_clamped)
                self.temp_manual_box = (x_clamped, y_clamped, 0, 0)
                self.update()
            elif event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
                self.is_panning = True
                self.last_mouse_pos = event.position().toPoint()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                
    def mouseMoveEvent(self, event: QMouseEvent):
        self.current_mouse_pos = event.position().toPoint()
        
        if not self.display_image:
            return
            
        img_pixel = self.widget_to_image_coords(self.current_mouse_pos)
        
        # 1. Update Hover Status bar color
        if self.is_pixel_in_bounds(img_pixel):
            color = self.get_color_at_pixel(img_pixel)
            self.mouse_hover_color.emit(color, img_pixel)
            
        # 2. Handle drawing or panning or updates
        if self.drawing_mode in ("brush", "eraser") and self.is_drawing:
            self._draw_brush_stroke(self.last_draw_point, img_pixel)
            self.last_draw_point = img_pixel
            self.update()
        elif self.is_drawing_manual_box:
            # Clamp coordinates to image boundaries
            x_clamped = max(0, min(img_pixel.x(), self.display_image.width() - 1))
            y_clamped = max(0, min(img_pixel.y(), self.display_image.height() - 1))
            
            # Calculate coordinates
            x1 = min(self.draw_start_point.x(), x_clamped)
            y1 = min(self.draw_start_point.y(), y_clamped)
            x2 = max(self.draw_start_point.x(), x_clamped)
            y2 = max(self.draw_start_point.y(), y_clamped)
            
            self.temp_manual_box = (x1, y1, x2 - x1, y2 - y1)
            self.update()
        elif self.is_panning:
            delta = self.current_mouse_pos - self.last_mouse_pos
            self.pan_offset += QPointF(delta)
            self.last_mouse_pos = self.current_mouse_pos
            self.update()
        else:
            # Repaint so the brush outline cursor follows the mouse smoothly
            self.update()
            
    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.drawing_mode in ("brush", "eraser") and self.is_drawing:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_drawing = False
                self.drawing_finished.emit(self.display_image.copy())
        elif self.is_drawing_manual_box:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_drawing_manual_box = False
                if self.temp_manual_box:
                    x, y, w, h = self.temp_manual_box
                    # Require at least a 3x3 pixel box to avoid noise clicks
                    if w > 2 and h > 2:
                        self.save_manual_state()
                        self.manual_slice_boxes.append((x, y, w, h))
                        self.manual_boxes_changed.emit(self.manual_slice_boxes)
                self.temp_manual_box = None
                self.update()
        elif self.is_panning:
            self.is_panning = False
            self.update_canvas_cursor()
                
    def wheelEvent(self, event: QWheelEvent):
        num_degrees = event.angleDelta().y() / 8
        num_steps = num_degrees / 15
        
        # Compute zoom scale step
        factor = 1.15 if num_steps > 0 else 0.85
        self._zoom(factor, event.position().toPoint())
        
    def enterEvent(self, event):
        self.mouse_in_widget = True
        self.update()
        
    def leaveEvent(self, event):
        self.mouse_in_widget = False
        self.update()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Center image on initial show or resize if zoom to fit is expected
        # (We don't force zoom to fit on every minor window resize to prevent overriding user zooms)
        pass
        
    def _draw_slice_grid(self, painter: QPainter, img_rect: QRectF):
        cols = self.slice_cols
        rows = self.slice_rows
        if cols <= 1 and rows <= 1:
            return
            
        painter.save()
        
        # Pen for grid lines: dashed neon orange for high visibility
        grid_pen = QPen(QColor(255, 100, 0, 200), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        
        x_offset = img_rect.x()
        y_offset = img_rect.y()
        w = img_rect.width()
        h = img_rect.height()
        
        # Draw vertical lines
        for c in range(1, cols):
            cx = x_offset + (c * w) / cols
            painter.drawLine(QPointF(cx, y_offset), QPointF(cx, y_offset + h))
            
        # Draw horizontal lines
        for r in range(1, rows):
            cy = y_offset + (r * h) / rows
            painter.drawLine(QPointF(x_offset, cy), QPointF(x_offset + w, cy))
            
        # Draw index labels in each cell
        label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor(255, 255, 255, 220)))
        
        cell_w = w / cols
        cell_h = h / rows
        
        for r in range(rows):
            for c in range(cols):
                # Calculate cell rect
                cell_rect = QRectF(
                    x_offset + c * cell_w,
                    y_offset + r * cell_h,
                    cell_w,
                    cell_h
                )
                
                # Draw small index text at the top-left of each cell with drop shadow
                index_str = f"{r},{c}"
                padded_rect = cell_rect.adjusted(5, 5, -5, -5)
                
                # Shadow
                painter.setPen(QPen(QColor(0, 0, 0, 200)))
                painter.drawText(padded_rect.translated(1, 1), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, index_str)
                
                # Text
                painter.setPen(QPen(QColor(255, 255, 255, 220)))
                painter.drawText(padded_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, index_str)
                
        painter.restore()

    def _draw_brush_outline(self, painter: QPainter):
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Calculate screen radii
        r_outer = (self.brush_size * self.zoom_factor) / 2.0
        r_inner = r_outer * (self.brush_hardness / 100.0)
        
        center = QPointF(self.current_mouse_pos)
        
        # 1. Outer dashed ring representing the brush boundary
        pen_white = QPen(Qt.GlobalColor.white, 1.0, Qt.PenStyle.DashLine)
        painter.setPen(pen_white)
        painter.drawEllipse(center, r_outer, r_outer)
        
        pen_black = QPen(Qt.GlobalColor.black, 1.0, Qt.PenStyle.SolidLine)
        painter.setPen(pen_black)
        painter.drawEllipse(center.translated(0.5, 0.5), r_outer, r_outer)
        
        # 2. Inner solid ring representing the hardness core (only if hardness is between 1 and 99)
        if 0 < self.brush_hardness < 100:
            pen_core = QPen(QColor(0, 173, 181, 150), 1.0, Qt.PenStyle.SolidLine) # cyan core indicator
            painter.setPen(pen_core)
            painter.drawEllipse(center, r_inner, r_inner)
            
        painter.restore()

    def _draw_soft_circle(self, painter: QPainter, center: QPointF, color: QColor, size: float, hardness: float):
        radius = size / 2.0
        if radius <= 0:
            return
            
        grad = QRadialGradient(center, radius)
        # Full opacity color up to hardness percentage
        h_stop = max(0.0, min(hardness / 100.0, 0.99))
        grad.setColorAt(0.0, color)
        grad.setColorAt(h_stop, color)
        # Fade to transparent at 1.0 (outer edge)
        transparent_color = QColor(color.red(), color.green(), color.blue(), 0)
        grad.setColorAt(1.0, transparent_color)
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius, radius)

    def _draw_brush_stroke(self, p1: QPoint, p2: QPoint):
        if not self.display_image:
            return
            
        painter = QPainter(self.display_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Determine brush color and composition mode
        color = QColor(self.brush_color)
        # Scale 0-100 to 0-255 opacity
        alpha = int(self.brush_opacity * 2.55)
        color.setAlpha(alpha)
        
        if self.drawing_mode == "eraser":
            # CompositionMode_DestinationOut erases destination pixels proportional to source alpha
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            # The color's channels don't matter, but alpha controls eraser opacity/strength
            color = QColor(0, 0, 0, alpha)
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            
        # Interpolate points between p1 and p2 to prevent scalloped lines
        d_x = p2.x() - p1.x()
        d_y = p2.y() - p1.y()
        distance = math.sqrt(d_x**2 + d_y**2)
        
        # Step size is 10% of brush size, minimum 1 pixel
        step = max(1.0, self.brush_size * 0.1)
        steps = int(math.ceil(distance / step)) if distance > 0 else 1
        
        for i in range(steps + 1):
            t = i / steps if steps > 0 else 1.0
            cx = p1.x() + t * d_x
            cy = p1.y() + t * d_y
            self._draw_soft_circle(painter, QPointF(cx, cy), color, self.brush_size, self.brush_hardness)
            
        painter.end()
        # Update display pixmap cache
        self.display_pixmap = QPixmap.fromImage(self.display_image)

    def _draw_auto_boxes(self, painter: QPainter, img_rect: QRectF):
        if not self.auto_slice_boxes:
            return
            
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Dashed neon orange pen for bounding boxes
        box_pen = QPen(QColor(255, 100, 0, 220), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(box_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        x_offset = img_rect.x()
        y_offset = img_rect.y()
        
        for idx, (bx, by, bw, bh) in enumerate(self.auto_slice_boxes):
            # Scale coordinates from image space to canvas coordinates
            sx = x_offset + bx * self.zoom_factor
            sy = y_offset + by * self.zoom_factor
            sw = bw * self.zoom_factor
            sh = bh * self.zoom_factor
            
            rect = QRectF(sx, sy, sw, sh)
            painter.drawRect(rect)
            
            # Label
            index_str = f"#{idx}"
            label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(label_font)
            
            # Draw text shadow
            painter.setPen(QPen(QColor(0, 0, 0, 200)))
            painter.drawText(QPointF(sx + 4, sy + 13), index_str)
            
            # Draw text
            painter.setPen(QPen(QColor(255, 255, 255, 220)))
            painter.drawText(QPointF(sx + 3, sy + 12), index_str)
            
            # Restore pen
            painter.setPen(box_pen)
            
        painter.restore()

    def _draw_manual_boxes(self, painter: QPainter, img_rect: QRectF):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Pen for completed boxes: solid bright orange
        box_pen = QPen(QColor(255, 100, 0, 220), 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(box_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        x_offset = img_rect.x()
        y_offset = img_rect.y()
        
        # Draw completed boxes
        if hasattr(self, 'manual_slice_boxes'):
            for idx, (bx, by, bw, bh) in enumerate(self.manual_slice_boxes):
                sx = x_offset + bx * self.zoom_factor
                sy = y_offset + by * self.zoom_factor
                sw = bw * self.zoom_factor
                sh = bh * self.zoom_factor
                
                rect = QRectF(sx, sy, sw, sh)
                painter.drawRect(rect)
                
                # Label: M#0, M#1, etc.
                index_str = f"M#{idx}"
                label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
                painter.setFont(label_font)
                
                # Draw text shadow
                painter.setPen(QPen(QColor(0, 0, 0, 200)))
                painter.drawText(QPointF(sx + 4, sy + 13), index_str)
                
                # Draw text
                painter.setPen(QPen(QColor(255, 255, 255, 220)))
                painter.drawText(QPointF(sx + 3, sy + 12), index_str)
                
                painter.setPen(box_pen)
                
        # Draw temporary active drag box
        if getattr(self, 'temp_manual_box', None) is not None:
            bx, by, bw, bh = self.temp_manual_box
            sx = x_offset + bx * self.zoom_factor
            sy = y_offset + by * self.zoom_factor
            sw = bw * self.zoom_factor
            sh = bh * self.zoom_factor
            
            # Semi-transparent cyan fill with dashed cyan border
            temp_pen = QPen(QColor(0, 173, 181, 240), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(temp_pen)
            
            # Fill with very light cyan
            painter.setBrush(QBrush(QColor(0, 173, 181, 40)))
            painter.drawRect(QRectF(sx, sy, sw, sh))
            
        painter.restore()

    def save_manual_state(self):
        self.manual_undo_stack.append(list(self.manual_slice_boxes))
        self.manual_redo_stack.clear()

    def clear_manual_boxes(self):
        if self.manual_slice_boxes:
            self.save_manual_state()
            self.manual_slice_boxes = []
            self.manual_boxes_changed.emit(self.manual_slice_boxes)
            self.update()

    def undo_manual(self) -> bool:
        if not self.manual_undo_stack:
            return False
        self.manual_redo_stack.append(list(self.manual_slice_boxes))
        self.manual_slice_boxes = self.manual_undo_stack.pop()
        self.manual_boxes_changed.emit(self.manual_slice_boxes)
        self.update()
        return True

    def redo_manual(self) -> bool:
        if not self.manual_redo_stack:
            return False
        self.manual_undo_stack.append(list(self.manual_slice_boxes))
        self.manual_slice_boxes = self.manual_redo_stack.pop()
        self.manual_boxes_changed.emit(self.manual_slice_boxes)
        self.update()
        return True

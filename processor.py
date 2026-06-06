import numpy as np
from PIL import Image

def qimage_to_pil(qimg):
    """Convert QImage to PIL Image instantly using memory buffer."""
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QImage
    
    qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    width = qimg.width()
    height = qimg.height()
    
    try:
        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4))
        return Image.fromarray(arr.copy(), "RGBA")
    except Exception:
        # Fallback to in-memory PNG bytes if SIP buffer protocols fail
        import io
        byte_arr = io.BytesIO()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buffer, "PNG")
        return Image.open(io.BytesIO(buffer.data()))

def pil_to_qimage(pil_img):
    """Convert PIL Image to QImage instantly using memory buffer."""
    from PyQt6.QtGui import QImage
    
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
        
    width, height = pil_img.size
    raw_data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(raw_data, width, height, QImage.Format.Format_RGBA8888)
    return qimg.copy()

class ImageProcessor:
    @staticmethod
    def process_color_operation(
        pil_image: Image.Image,
        target_color: tuple,  # (r, g, b)
        tolerance: float,     # 0 to 255
        softness: float,      # 0 to 255
        mode: str,            # 'erase', 'isolate', 'splash', 'replace'
        replace_color: tuple = None  # (r, g, b)
    ) -> Image.Image:
        """
        Process the image according to the selected mode and color matching parameters.
        All calculations are vectorized in NumPy for speed.
        """
        # Ensure we have an RGBA numpy array
        img_rgba = pil_image.convert("RGBA")
        arr = np.array(img_rgba, dtype=np.float32)
        
        # Split channels
        r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
        
        # Target color RGB
        tr, tg, tb = target_color
        
        # Calculate Euclidean distance in RGB space
        # dist is shape (H, W)
        dist = np.sqrt((r - tr)**2 + (g - tg)**2 + (b - tb)**2)
        
        # Calculate mask: 1.0 = fully matching target color, 0.0 = not matching at all
        # To avoid division by zero:
        softness = max(softness, 0.001)
        
        # Match mask calculation (soft thresholding)
        # 1.0 inside tolerance, fades to 0.0 outside tolerance + softness
        mask = np.clip(1.0 - (dist - tolerance) / softness, 0.0, 1.0)
        # If distance <= tolerance, mask is 1.0
        mask[dist <= tolerance] = 1.0
        
        # Output array
        out_arr = arr.copy()
        
        if mode == 'erase':
            # Make matched areas transparent
            # New alpha = original alpha * (1 - mask)
            out_arr[:, :, 3] = a * (1.0 - mask)
            
        elif mode == 'isolate':
            # Make unmatched areas transparent
            # New alpha = original alpha * mask
            out_arr[:, :, 3] = a * mask
            
        elif mode == 'splash':
            # Keep matched areas in color, make unmatched areas grayscale
            # Grayscale calculation: Y = 0.299R + 0.587G + 0.114B
            gray = 0.299 * r + 0.587 * g + 0.114 * b
            
            # Combine color and grayscale using the mask
            # For mask=1.0: color. For mask=0.0: grayscale.
            out_arr[:, :, 0] = r * mask + gray * (1.0 - mask)
            out_arr[:, :, 1] = g * mask + gray * (1.0 - mask)
            out_arr[:, :, 2] = b * mask + gray * (1.0 - mask)
            # Alpha remains unchanged
            
        elif mode == 'replace' and replace_color is not None:
            # Shift the color of matching pixels
            # To preserve lighting details (luminance differences), we compute the offset:
            # Offset = (Replace Color - Target Color) * mask
            # New Color = Original Color + Offset
            rr, rg, rb = replace_color
            offset_r = (rr - tr) * mask
            offset_g = (rg - tg) * mask
            offset_b = (rb - tb) * mask
            
            out_arr[:, :, 0] = np.clip(r + offset_r, 0, 255)
            out_arr[:, :, 1] = np.clip(g + offset_g, 0, 255)
            out_arr[:, :, 2] = np.clip(b + offset_b, 0, 255)
            # Alpha remains unchanged
            
        # Convert back to uint8 RGBA and return as PIL Image
        out_arr = np.clip(out_arr, 0, 255).astype(np.uint8)
        return Image.fromarray(out_arr, "RGBA")

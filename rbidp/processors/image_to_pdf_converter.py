import os
import tempfile
from typing import Optional

try:
    from PIL import Image, ImageSequence, ImageOps
except Exception:
    Image = None
    ImageSequence = None
    ImageOps = None


def convert_image_to_pdf(image_path: str, output_dir: Optional[str] = None) -> str:
    if Image is None:
        raise RuntimeError("Pillow is required for image to PDF conversion")
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        fd, tmp_pdf = tempfile.mkstemp(prefix="img2pdf_", suffix=".pdf", dir=output_dir)
        os.close(fd)
    else:
        fd, tmp_pdf = tempfile.mkstemp(prefix="img2pdf_", suffix=".pdf")
        os.close(fd)
    with Image.open(image_path) as im:
        frames = []
        try:
            for frame in ImageSequence.Iterator(im):
                f = frame.copy()
                try:
                    f = ImageOps.exif_transpose(f)
                except Exception:
                    pass
                if f.mode not in ("RGB", "L"):
                    f = f.convert("RGB")
                frames.append(f)
        except Exception:
            f = im.copy()
            try:
                f = ImageOps.exif_transpose(f)
            except Exception:
                pass
            if f.mode not in ("RGB", "L"):
                f = f.convert("RGB")
            frames = [f]
        if len(frames) == 1:
            frames[0].save(tmp_pdf, format="PDF", resolution=300.0)
        else:
            first, rest = frames[0], frames[1:]
            first.save(tmp_pdf, format="PDF", resolution=300.0, save_all=True, append_images=rest)
        for fr in frames:
            try:
                fr.close()
            except Exception:
                pass
    return tmp_pdf

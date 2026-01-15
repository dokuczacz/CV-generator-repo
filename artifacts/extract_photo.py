from pathlib import Path
from src.docx_photo import extract_first_photo_from_docx_bytes

p = Path(r"wzory/Lebenslauf_Mariusz_Horodecki_CH.docx")
img = extract_first_photo_from_docx_bytes(p.read_bytes())

if not img:
    raise SystemExit("NO_PHOTO_FOUND")

ext = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}.get(img.mime, ".bin")

out = Path(r"artifacts") / ("lebenslauf_mariusz_horodecki_photo" + ext)
out.write_bytes(img.data)

data_uri = img.as_data_uri()
print("MIME:", img.mime)
print("Saved:", out.as_posix())
print("Bytes:", len(img.data))
print("Data URI prefix:", data_uri[:80] + "...")

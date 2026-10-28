"""PDF « scan » : chaque page d'un PDF natif est rastérisée puis réassemblée en PDF image seule.

Le résultat ne contient aucun texte extractible (comme une numérisation non océrisée) ; la
mention DOCUMENT SYNTHÉTIQUE TEST reste visible dans l'image de chaque page et dans les
métadonnées. Rastérisation : pdfium (pypdfium2) ; images JPEG (couleur, gris) ou noir et
blanc compressé sans perte (Flate).
"""

from __future__ import annotations

import io
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import pypdfium2
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from synthetic_doc_gen.options import ScanSettings

#: Seuil de binarisation (0-255) du mode noir et blanc.
BW_THRESHOLD = 160


@dataclass(frozen=True)
class ScanPage:
    """Page numérisée prête à être assemblée : JPEG, ou image 1 bit noir/blanc."""

    width_pt: float
    height_pt: float
    jpeg: bytes | None = None
    image: Image.Image | None = None


def pdfium_version() -> str:
    return str(pypdfium2.PDFIUM_INFO.version)


def page_count(pdf: bytes) -> int:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return len(document)
    finally:
        document.close()


def iter_rasters(
    pdf: bytes, dpi: int, pages: Sequence[int] | None = None
) -> Iterator[tuple[float, float, Image.Image]]:
    """Rend les pages demandées (toutes par défaut), une à la fois pour limiter la mémoire."""
    document = pypdfium2.PdfDocument(pdf)
    try:
        for number in range(len(document)) if pages is None else pages:
            page = document[number]
            try:
                width, height = page.get_size()
                yield width, height, page.render(scale=dpi / 72).to_pil().convert("RGB")
            finally:
                page.close()
    finally:
        document.close()


def _binarize(image: Image.Image) -> Image.Image:
    return image.convert("L").point(lambda value: 255 if value >= BW_THRESHOLD else 0).convert("1")


def encode_page(
    width: float, height: float, raster: Image.Image, settings: ScanSettings
) -> ScanPage:
    if settings.color == "bw":
        return ScanPage(width, height, image=_binarize(raster))
    image = raster if settings.color == "color" else raster.convert("L")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=settings.jpeg_quality)
    return ScanPage(width, height, jpeg=buffer.getvalue())


def encoded_size(page: ScanPage) -> int:
    """Octets du flux image d'une page (hors structure PDF, négligeable)."""
    if page.jpeg is not None:
        return len(page.jpeg)
    assert page.image is not None
    return len(zlib.compress(page.image.tobytes(), 6))


def assemble(
    pages: Sequence[ScanPage], *, title: str, subject: str, keywords: str, creator: str
) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(
        buffer,
        pagesize=(pages[0].width_pt, pages[0].height_pt),
        invariant=1,
        pageCompression=1,
        initialFontName="Helvetica",
    )
    canvas.setTitle(title)
    canvas.setAuthor("synthetic-doc-gen")
    canvas.setSubject(subject)
    canvas.setKeywords(keywords)
    canvas.setCreator(creator)
    for page in pages:
        canvas.setPageSize((page.width_pt, page.height_pt))
        source = io.BytesIO(page.jpeg) if page.jpeg is not None else page.image
        info = {"imgObj": None}
        canvas.drawImage(ImageReader(source), 0, 0, page.width_pt, page.height_pt, extraReturn=info)
        if page.image is not None:
            obj = info["imgObj"]
            obj.bitsPerComponent = 1
            obj.colorSpace = "DeviceGray"
            obj.streamContent = zlib.compress(page.image.tobytes())
            obj._filters = ("FlateDecode",)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def scan_pdf(
    pdf: bytes, settings: ScanSettings, *, title: str, subject: str, keywords: str, creator: str
) -> tuple[bytes, int]:
    """PDF image seule équivalent à ``pdf`` ; retourne (octets, nombre de pages)."""
    pages = [
        encode_page(width, height, raster, settings)
        for width, height, raster in iter_rasters(pdf, settings.dpi)
    ]
    return assemble(pages, title=title, subject=subject, keywords=keywords, creator=creator), len(
        pages
    )

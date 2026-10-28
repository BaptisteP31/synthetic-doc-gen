"""Images synthétiques des comptes rendus d'imagerie : fantômes procéduraux, jamais d'image réelle.

Chaque image est une fonction pure de (modalité, graine, dimensions en pixels) : formes
géométriques abstraites, bruit (speckle, grain) tiré d'un ``random.Random`` seul. Elle porte,
dans ses pixels, un bandeau « IMAGE SYNTHÉTIQUE - DOCUMENT SYNTHÉTIQUE TEST » et une étiquette
de modalité fictive ; le JPEG porte en plus un commentaire (segment COM) avec la mention. Le
flux est intégré tel quel au PDF (JPEG : DCTDecode ; PNG : pixels bruts, Flate).
"""

from __future__ import annotations

import functools
import hashlib
import io
import os
import random
import zlib
from dataclasses import dataclass

import reportlab
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable

from synthetic_doc_gen import SYNTHETIC_MARKER
from synthetic_doc_gen.options import ImageSettings

MODALITIES = ("echographie", "irm", "radiographie")
LABELS = {"echographie": "ÉCHOGRAPHIE", "irm": "IRM", "radiographie": "RADIOGRAPHIE"}
BANNER = f"IMAGE SYNTHÉTIQUE - {SYNTHETIC_MARKER}"
_FONT = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
_BANNER_SHADE, _INK = 232, 20


def pixel_size(width_pt: float, height_pt: float, dpi: int) -> tuple[int, int]:
    return max(1, round(width_pt * dpi / 72)), max(1, round(height_pt * dpi / 72))


def _noise(rng: random.Random, size: tuple[int, int]) -> Image.Image:
    return Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))


def _scale(value: float, low: float, high: float) -> int:
    return round(max(low, min(high, value)))


def _ultrasound(rng: random.Random, width: int, height: int) -> Image.Image:
    """Secteur échographique : tissu granuleux, cavités sombres et structures échogènes."""
    centre_x, radius = width / 2, height * 1.05
    box = (centre_x - radius, -height * 0.05 - radius, centre_x + radius, -height * 0.05 + radius)
    sector = Image.new("L", (width, height), 0)
    ImageDraw.Draw(sector).pieslice(box, 50, 130, fill=255)
    tissue = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(tissue)
    draw.pieslice(box, 50, 130, fill=70)
    for _ in range(rng.randint(3, 5)):
        x, y = rng.uniform(0.25, 0.75) * width, rng.uniform(0.3, 0.8) * height
        rx, ry = rng.uniform(0.06, 0.16) * width, rng.uniform(0.06, 0.14) * height
        draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=rng.choice((20, 40, 110, 130)))
    tissue = tissue.filter(ImageFilter.GaussianBlur(width / 150))
    speckle = _noise(rng, (width, height)).filter(ImageFilter.GaussianBlur(0.8))
    speckle = ImageChops.multiply(speckle, speckle).point(lambda v: _scale(v * 3, 0, 255))
    lit = ImageChops.multiply(tissue, speckle.point(lambda v: 90 + v * 0.6))
    return ImageChops.multiply(lit.point(lambda v: _scale(v * 2, 0, 255)), sector)


def _mri(rng: random.Random, width: int, height: int) -> Image.Image:
    """Coupe axiale abstraite : contour clair, parenchyme, cavités sombres, bruit fin."""
    image = Image.new("L", (width, height), 6)
    draw = ImageDraw.Draw(image)
    cx, cy = width / 2, height / 2
    rx, ry = width * rng.uniform(0.30, 0.36), height * rng.uniform(0.40, 0.46)
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=190)
    inset = rng.uniform(0.86, 0.9)
    draw.ellipse((cx - rx * inset, cy - ry * inset, cx + rx * inset, cy + ry * inset), fill=95)
    for _ in range(rng.randint(5, 9)):
        x, y = cx + rng.uniform(-0.6, 0.6) * rx, cy + rng.uniform(-0.6, 0.6) * ry
        r = rng.uniform(0.05, 0.14) * width
        draw.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=rng.choice((60, 125, 150)))
    for side in (-1, 1):  # cavités centrales symétriques
        x = cx + side * rx * 0.2
        draw.ellipse((x - rx * 0.1, cy - ry * 0.3, x + rx * 0.1, cy + ry * 0.1), fill=25)
    image = image.filter(ImageFilter.GaussianBlur(width / 120))
    grain = _noise(rng, (width, height)).point(lambda v: 112 + (v - 128) * 0.55)
    return ImageChops.multiply(image, grain.point(lambda v: _scale(v * 2.1, 0, 255)))


def _radiograph(rng: random.Random, width: int, height: int) -> Image.Image:
    """Cliché thoracique abstrait : champs clairs, médiastin dense, côtes en arcs."""
    image = Image.new("L", (width, height), 70)
    draw = ImageDraw.Draw(image)
    spread = rng.uniform(0.18, 0.23)
    for side in (-1, 1):
        x = width / 2 + side * width * 0.2
        draw.ellipse(
            (x - width * spread, height * 0.1, x + width * spread, height * 0.82), fill=135
        )
        for rib in range(7):  # côtes : arcs obliques tous les ~10 % de la hauteur
            top = height * (0.15 + 0.09 * rib)
            draw.arc(
                (x - width * spread, top, x + width * spread, top + height * 0.16),
                200 if side < 0 else 340,
                340 if side < 0 else 200,
                fill=95,
                width=max(2, width // 90),
            )
    draw.rounded_rectangle(
        (width * 0.43, height * 0.08, width * 0.57, height * 0.9),
        radius=width // 20,
        fill=rng.randint(30, 45),
    )
    image = image.filter(ImageFilter.GaussianBlur(width / 110))
    grain = _noise(rng, (width, height)).point(lambda v: 122 + (v - 128) * 0.3)
    return ImageChops.multiply(image, grain.point(lambda v: _scale(v * 2.05, 0, 255)))


_PAINTERS = {"echographie": _ultrasound, "irm": _mri, "radiographie": _radiograph}


@functools.lru_cache(maxsize=4)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_FONT, size)


def _mark(image: Image.Image, modality: str) -> None:
    """Bandeau de mention en pied d'image et étiquette de modalité fictive en haut à gauche."""
    width, height = image.size
    band = max(8, round(height * 0.085))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, height - band, width, height), fill=_BANNER_SHADE)
    size = max(6, round(band * 0.62))
    while size > 6 and _font(size).getlength(BANNER) > width * 0.96:
        size -= 1
    draw.text((width / 2, height - band / 2), BANNER, font=_font(size), fill=_INK, anchor="mm")
    tag = f"{LABELS[modality]} FICTIVE"
    tag_font = _font(max(6, round(band * 0.5)))
    left, top, right, bottom = draw.textbbox((0, 0), tag, font=tag_font)
    pad = max(2, band // 6)
    draw.rectangle((0, 0, right - left + 2 * pad, bottom - top + 2 * pad), fill=_BANNER_SHADE)
    draw.text((pad - left, pad - top), tag, font=tag_font, fill=_INK)


@functools.lru_cache(maxsize=8)
def synthesize(modality: str, seed: int, width: int, height: int) -> Image.Image:
    """Image « L » (niveaux de gris) marquée ; ne pas la modifier (résultat mis en cache)."""
    try:
        painter = _PAINTERS[modality]
    except KeyError:
        raise ValueError(
            f"modalité d'image inconnue : {modality!r} ({', '.join(MODALITIES)})"
        ) from None
    image = painter(random.Random(f"{modality}:{seed}"), width, height)
    _mark(image, modality)
    return image


@dataclass(frozen=True)
class EncodedImage:
    """Flux d'image tel qu'écrit dans le PDF."""

    width: int
    height: int
    data: bytes
    jpeg: bool


@functools.lru_cache(maxsize=32)
def encode(
    modality: str, seed: int, width: int, height: int, format: str, jpeg_quality: int
) -> EncodedImage:
    image = synthesize(modality, seed, width, height)
    if format == "png":
        return EncodedImage(width, height, zlib.compress(image.tobytes(), 6), jpeg=False)
    buffer = io.BytesIO()
    image.save(
        buffer,
        "JPEG",
        quality=jpeg_quality,
        comment=f"{SYNTHETIC_MARKER} - synthetic image ({modality}, seed {seed})",
    )
    return EncodedImage(width, height, buffer.getvalue(), jpeg=True)


def encode_for(
    modality: str, seed: int, width_pt: float, height_pt: float, settings: ImageSettings
) -> EncodedImage:
    width, height = pixel_size(width_pt, height_pt, settings.dpi)
    # La qualité n'agit qu'en JPEG : une seule entrée de cache pour toutes les qualités PNG.
    quality = settings.jpeg_quality if settings.format == "jpeg" else 0
    return encode(modality, seed, width, height, settings.format, quality)


class SyntheticImage(Flowable):
    """Image synthétique à la taille imprimée donnée, résolution fixée par ``settings``."""

    def __init__(
        self,
        modality: str,
        seed: int,
        width: float,
        height: float,
        settings: ImageSettings,
    ) -> None:
        super().__init__()
        self.modality, self.seed, self.settings = modality, seed, settings
        self.width, self.height = width, height

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        encoded = encode_for(self.modality, self.seed, self.width, self.height, self.settings)
        # ReportLab décoderait puis recompresserait tous les pixels pour rien : on lui donne une
        # image témoin minuscule, propre au contenu (ReportLab en déduit le nom de l'image, qui
        # doit être unique), puis on renseigne l'objet avec le flux déjà encodé.
        digest = hashlib.sha256(encoded.data).digest()
        placeholder = Image.frombytes("L", (4, 4), digest[:16])
        info = {"imgObj": None}
        self.canv.drawImage(
            ImageReader(placeholder), 0, 0, self.width, self.height, extraReturn=info
        )
        obj = info["imgObj"]
        obj.width, obj.height = encoded.width, encoded.height
        obj.colorSpace, obj.bitsPerComponent = "DeviceGray", 8
        obj.streamContent = encoded.data
        obj._filters = ("DCTDecode",) if encoded.jpeg else ("FlateDecode",)

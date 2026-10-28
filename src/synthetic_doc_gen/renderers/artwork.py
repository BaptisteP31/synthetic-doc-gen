"""Logo et signature fictifs, dessinés en vectoriel et déterministes.

Le logo est une forme géométrique abstraite (fonction du nom de l'établissement) légendée
« LOGO FICTIF » ; la signature est un griffonnage sans lecture possible (fonction du nom du
signataire) légendé « signature fictive ». Aucun élément ne reproduit une marque ou une
écriture réelle.
"""

from __future__ import annotations

import hashlib
import random

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Flowable

LOGO_SIZE = 11 * mm
SIGNATURE_WIDTH = 62 * mm
SIGNATURE_HEIGHT = 24 * mm
INK = colors.HexColor("#1a237e")


def _rng(label: str, text: str) -> random.Random:
    digest = hashlib.sha256(f"{label}:{text}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


class FictionalLogo(Flowable):
    """Marque abstraite à gauche, légende à droite ; même établissement, même logo."""

    def __init__(self, issuer: str, accent: str) -> None:
        super().__init__()
        self.issuer = issuer
        self.accent = colors.HexColor(accent)
        self.width = 60 * mm
        self.height = LOGO_SIZE
        self.hAlign = "LEFT"

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        rng = _rng("logo", self.issuer)
        canvas, size = self.canv, LOGO_SIZE
        style = rng.randrange(3)
        canvas.saveState()
        canvas.setFillColor(self.accent)
        canvas.setStrokeColor(self.accent)
        canvas.setLineWidth(1.2)
        if style == 0:  # anneau, carré tourné, point
            canvas.circle(size / 2, size / 2, size / 2 - 0.6, stroke=1, fill=0)
            canvas.saveState()
            canvas.translate(size / 2, size / 2)
            canvas.rotate(rng.choice((0, 45)))
            canvas.rect(-size * 0.22, -size * 0.22, size * 0.44, size * 0.44, stroke=0, fill=1)
            canvas.restoreState()
        elif style == 1:  # barres de hauteurs variables
            bar = size / 6
            for i in range(4):
                height = size * rng.uniform(0.35, 1.0)
                canvas.rect(i * 1.5 * bar, 0, bar, height, stroke=0, fill=1)
        else:  # deux disques se chevauchant
            canvas.setFillAlpha(0.65)
            canvas.circle(size * 0.38, size / 2, size * 0.36, stroke=0, fill=1)
            canvas.setFillColor(colors.HexColor("#555555"))
            canvas.circle(size * 0.64, size / 2, size * 0.36, stroke=0, fill=1)
        canvas.restoreState()
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.setFont("Helvetica-Oblique", 6)
        canvas.drawString(size + 3 * mm, size / 2 - 2, "LOGO FICTIF")
        canvas.restoreState()


class FictionalSignature(Flowable):
    """Griffonnage manuscrit illisible au-dessus du nom du signataire."""

    def __init__(self, signer: str) -> None:
        super().__init__()
        self.signer = signer
        self.width = SIGNATURE_WIDTH
        self.height = SIGNATURE_HEIGHT
        self.hAlign = "RIGHT"

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        rng = _rng("signature", self.signer)
        canvas = self.canv
        base = 8 * mm
        canvas.saveState()
        canvas.setStrokeColor(INK)
        canvas.setLineCap(1)
        canvas.setLineJoin(1)
        # Trait continu de gauche à droite, avec boucles et élan final.
        x, y = 4 * mm, base + 4 * mm
        path = canvas.beginPath()
        path.moveTo(x, y)
        steps = rng.randint(6, 9)
        step = (self.width - 14 * mm) / steps
        for _ in range(steps):
            c1 = (x + step * rng.uniform(0.1, 0.5), y + rng.uniform(-3, 11) * mm)
            c2 = (x + step * rng.uniform(0.5, 1.0), base + rng.uniform(-1, 11) * mm)
            x, y = x + step, base + rng.uniform(1, 9) * mm
            path.curveTo(*c1, *c2, x, y)
        path.curveTo(x + 3 * mm, y + 2 * mm, x + 7 * mm, base - 1 * mm, x + 9 * mm, base + 1 * mm)
        canvas.setLineWidth(1.3)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.restoreState()
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#999999"))
        canvas.setLineWidth(0.4)
        canvas.line(0, base - 1.5 * mm, self.width, base - 1.5 * mm)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(self.width, base - 5 * mm, self.signer)
        canvas.setFont("Helvetica-Oblique", 6)
        canvas.drawRightString(self.width, base - 8 * mm, "signature fictive")
        canvas.restoreState()

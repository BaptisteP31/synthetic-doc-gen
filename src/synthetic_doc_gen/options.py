"""Options de rendu choisies à l'appel : scan, logo, signature, bornes réalistes."""

from __future__ import annotations

from dataclasses import dataclass

SCAN_COLORS = ("color", "gray", "bw")

#: Valeurs acceptées pour une demande explicite.
DPI_LIMITS = (72, 600)
QUALITY_LIMITS = (1, 95)

#: Plages dans lesquelles l'ajustement automatique (taille cible) a le droit de travailler :
#: des réglages de numérisation courants, pas des valeurs extrêmes pour atteindre un poids.
TUNING_DPI = (100, 400)
TUNING_QUALITY = (40, 95)

DEFAULT_SCAN_DPI = 150
DEFAULT_JPEG_QUALITY = 75


@dataclass(frozen=True)
class ScanSettings:
    """Réglages de numérisation : un PDF « scan » ne contient que des images de pages."""

    dpi: int = DEFAULT_SCAN_DPI
    color: str = "color"  # "color" (RVB), "gray" (niveaux de gris) ou "bw" (noir et blanc)
    #: Qualité JPEG (ignorée en noir et blanc, compressé sans perte).
    jpeg_quality: int = DEFAULT_JPEG_QUALITY

    def __post_init__(self) -> None:
        if self.color not in SCAN_COLORS:
            raise ValueError(
                f"couleur de scan inconnue : {self.color!r} ({', '.join(SCAN_COLORS)})"
            )
        if not DPI_LIMITS[0] <= self.dpi <= DPI_LIMITS[1]:
            raise ValueError(f"dpi de scan hors de {DPI_LIMITS[0]}-{DPI_LIMITS[1]} : {self.dpi}")
        if not QUALITY_LIMITS[0] <= self.jpeg_quality <= QUALITY_LIMITS[1]:
            raise ValueError(
                f"qualité JPEG hors de {QUALITY_LIMITS[0]}-{QUALITY_LIMITS[1]} : "
                f"{self.jpeg_quality}"
            )


@dataclass(frozen=True)
class RenderOptions:
    """Options propres à un document rendu (le contenu textuel n'en dépend pas)."""

    logo: bool = False
    signature: bool = False
    #: ``None`` : PDF natif (texte sélectionnable) ; sinon PDF image seule (scan).
    scan: ScanSettings | None = None

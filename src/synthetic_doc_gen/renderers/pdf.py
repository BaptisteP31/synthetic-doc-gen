"""Rendu PDF avec ReportLab (moteur par défaut).

Chaque page porte la mention DOCUMENT SYNTHÉTIQUE TEST en en-tête, en filigrane et en pied.
``invariant=1`` fige dates et identifiants internes : à environnement égal (versions de
Python et de ReportLab), le même document est rendu à l'identique octet pour octet.
"""

from __future__ import annotations

import functools
import io
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from synthetic_doc_gen import SYNTHETIC_MARKER, __version__, model
from synthetic_doc_gen.options import RenderOptions
from synthetic_doc_gen.profiles import Profile
from synthetic_doc_gen.renderers import Rendered, scan
from synthetic_doc_gen.renderers.artwork import FictionalLogo, FictionalSignature

PAGE_SIZES = {"A4": A4, "LETTER": LETTER}
DISCLAIMER = "Données entièrement fictives - aucun patient réel - ne pas utiliser en pratique"
WARNING_RED = colors.HexColor("#b00020")


class _NumberedCanvas(Canvas):
    """Canvas qui ajoute filigrane et pied « Page x / N » une fois le total de pages connu."""

    def __init__(self, *args, footer_text: str = "", footer_margin: float = 15 * mm, **kwargs):
        super().__init__(*args, **kwargs)
        self._footer_text = footer_text
        self._footer_margin = footer_margin
        self._saved_states: list[dict] = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_overlay(total)
            super().showPage()
        super().save()

    def _draw_overlay(self, total: int) -> None:
        width, _ = self._pagesize
        # Filigrane diagonal, au-dessus du contenu pour que les fonds de tableau ne le masquent pas.
        self.saveState()
        self.setFillColor(colors.black)
        self.setFillAlpha(0.07)
        self.setFont("Helvetica-Bold", 44)
        self.translate(width / 2, self._pagesize[1] / 2)
        self.rotate(40)
        self.drawCentredString(0, 0, SYNTHETIC_MARKER)
        self.restoreState()
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#555555"))
        self.drawString(self._footer_margin, 9 * mm, f"{SYNTHETIC_MARKER} - {self._footer_text}")
        self.drawRightString(
            width - self._footer_margin, 9 * mm, f"Page {self._pageNumber} / {total}"
        )
        self.restoreState()


def _styles(profile: Profile) -> dict[str, ParagraphStyle]:
    size = profile.font_size
    accent = colors.HexColor(profile.accent_color)
    return {
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=size, leading=size * 1.35, spaceAfter=size * 0.5
        ),
        "cell": ParagraphStyle(
            "cell", fontName="Helvetica", fontSize=size * 0.92, leading=size * 1.15
        ),
        "cell_head": ParagraphStyle(
            "cell_head",
            fontName="Helvetica-Bold",
            fontSize=size * 0.92,
            leading=size * 1.15,
            textColor=colors.white,
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName="Helvetica-Bold",
            fontSize=size * 1.25,
            leading=size * 1.5,
            textColor=accent,
            spaceBefore=size * 0.8,
            spaceAfter=size * 0.3,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="Helvetica-Bold",
            fontSize=size * 1.05,
            leading=size * 1.3,
            textColor=accent,
            spaceBefore=size * 0.6,
            spaceAfter=size * 0.3,
            keepWithNext=True,
        ),
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=size * 1.7,
            leading=size * 2.0,
            textColor=accent,
            spaceAfter=size * 0.6,
        ),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text), style)


def _table(block: model.Table, profile: Profile, styles, width: float) -> Table:
    weights = block.col_weights or (1.0,) * len(block.header)
    total = sum(weights)
    col_widths = [width * w / total for w in weights]
    accent = colors.HexColor(profile.accent_color)

    def cell(text: str, bold: bool) -> Paragraph:
        body = f"<b>{escape(text)}</b>" if bold else escape(text)
        return Paragraph(body, styles["cell"])

    data = [[Paragraph(escape(h), styles["cell_head"]) for h in block.header]]
    for i, row in enumerate(block.rows):
        data.append([cell(c, i in block.emphasized_rows) for c in row])

    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if profile.table_style == "grid":
        commands.append(("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#888888")))
    elif profile.table_style == "zebra":
        commands.append(
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")])
        )
    else:
        commands.append(("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")))
    for i in block.emphasized_rows:
        commands.append(("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#fdeaea")))
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(commands))
    return table


def _flowables(
    document: model.Document, profile: Profile, width: float, options: RenderOptions
) -> list[Flowable]:
    styles = _styles(profile)
    out: list[Flowable] = []
    if options.logo:
        out += [FictionalLogo(document.issuer, profile.accent_color), Spacer(1, 6)]
    out.append(_p(document.title, styles["title"]))
    for block in document.blocks:
        if isinstance(block, model.Heading):
            out.append(_p(block.text, styles["h1" if block.level == 1 else "h2"]))
        elif isinstance(block, model.Paragraph):
            out.append(_p(block.text, styles["body"]))
        elif isinstance(block, model.KeyValues):
            rows = [
                [
                    _p(
                        k,
                        styles["cell_head"].clone(
                            "k", textColor=colors.black, fontName="Helvetica-Bold"
                        ),
                    ),
                    _p(v, styles["cell"]),
                ]
                for k, v in block.items
            ]
            kv = Table(rows, colWidths=[width * 0.28, width * 0.72])
            kv.setStyle(
                TableStyle(
                    [
                        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            out += [KeepTogether(kv), Spacer(1, 4)]
        elif isinstance(block, model.Table):
            out += [_table(block, profile, styles, width), Spacer(1, 6)]
        else:  # pragma: no cover - garde pour les futurs blocs
            raise TypeError(f"bloc non pris en charge : {type(block).__name__}")
    if options.signature and document.signer:
        # Solidaire du dernier élément : la signature ne se retrouve pas seule sur une page.
        last = out.pop()
        out.append(KeepTogether([last, Spacer(1, 10), FictionalSignature(document.signer)]))
    return out


def _decorate_page(canvas: Canvas, doc: SimpleDocTemplate, *, issuer: str, accent: str) -> None:
    width, height = doc.pagesize
    margin = doc.leftMargin
    canvas.saveState()
    # Bandeau d'en-tête
    top = height - 10 * mm
    canvas.setFillColor(WARNING_RED)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(margin, top, SYNTHETIC_MARKER)
    canvas.setFillColor(colors.HexColor(accent))
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(width - margin, top, issuer)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.drawString(margin, top - 9, DISCLAIMER)
    canvas.setStrokeColor(WARNING_RED)
    canvas.setLineWidth(0.8)
    canvas.line(margin, top - 13, width - margin, top - 13)
    canvas.restoreState()


class ReportLabPdfRenderer:
    name = "reportlab"
    extension = "pdf"

    def version(self) -> str:
        return reportlab.Version

    def render(
        self,
        document: model.Document,
        profile: Profile,
        doc_id: str,
        options: RenderOptions | None = None,
    ) -> Rendered:
        """PDF natif, ou PDF image seule si ``options.scan`` est défini."""
        options = options or RenderOptions()
        native = self.render_native(document, profile, doc_id, options)
        if options.scan is None:
            return native
        data, pages = scan.scan_pdf(
            native.data,
            options.scan,
            title=f"{SYNTHETIC_MARKER} - {document.title} (scan)",
            subject=f"{SYNTHETIC_MARKER} - {document.doc_type}",
            keywords=f"synthetic, test, fictional, scan, {document.doc_type}",
            creator=f"synthetic-doc-gen {__version__}",
        )
        return Rendered(data=data, pages=pages)

    def render_native(
        self,
        document: model.Document,
        profile: Profile,
        doc_id: str,
        options: RenderOptions | None = None,
    ) -> Rendered:
        options = options or RenderOptions()
        pagesize = PAGE_SIZES[profile.page_size]
        margin = profile.margin_mm * mm
        buffer = io.BytesIO()
        footer = f"{doc_id} - {DISCLAIMER}"
        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin + 8 * mm,
            bottomMargin=margin,
            title=f"{SYNTHETIC_MARKER} - {document.title}",
            author="synthetic-doc-gen",
            subject=f"{SYNTHETIC_MARKER} - {document.doc_type}",
            keywords=f"synthetic, test, fictional, {document.doc_type}",
            creator=f"synthetic-doc-gen {__version__}",
            invariant=1,
        )
        decorate = functools.partial(
            _decorate_page, issuer=document.issuer, accent=profile.accent_color
        )
        doc.build(
            _flowables(document, profile, pagesize[0] - 2 * margin, options),
            onFirstPage=decorate,
            onLaterPages=decorate,
            canvasmaker=functools.partial(
                _NumberedCanvas, footer_text=footer, footer_margin=margin
            ),
        )
        return Rendered(data=buffer.getvalue(), pages=doc.page)

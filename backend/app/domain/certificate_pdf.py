from datetime import datetime
from decimal import Decimal
from functools import cache
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.certificate import CertificateData
from app.domain.hours import to_hours

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

@cache
def _register_fonts() -> None:
    pdfmetrics.registerFont(TTFont(FONT, str(FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONTS_DIR / "DejaVuSans-Bold.ttf")))

def _hours(value: Decimal | str | float) -> str:
    h = to_hours(Decimal(str(value)))
    return f"{h:g}".replace(".", ",")

def _qr(url: str, size: float) -> Drawing:
    widget = QrCodeWidget(url)
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    drawing.add(widget)
    return drawing

def _image(png: bytes | None, width: float, height: float) -> Flowable | str:
    if not png:
        return ""
    try:
        reader = ImageReader(BytesIO(png))
        iw, ih = reader.getSize()
    except Exception:
        return ""
    scale = min(width / iw, height / ih)
    return Image(BytesIO(png), width=iw * scale, height=ih * scale)

def render_pdf(data: CertificateData, tz: ZoneInfo) -> bytes:
    _register_fonts()
    base = ParagraphStyle("base", fontName=FONT, fontSize=10, leading=13)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10, textColor=colors.grey)
    title = ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=16, leading=20)
    bold = ParagraphStyle("bold", parent=base, fontName=FONT_BOLD)

    def fmt_date(value: str | datetime) -> str:
        dt = datetime.fromisoformat(value) if isinstance(value, str) else value
        return dt.astimezone(tz).strftime("%d.%m.%Y")

    story: list[Flowable] = [
        Paragraph("Справка о волонтёрских часах", title),
        Spacer(1, 4 * mm),
        Paragraph(f"Участник: <b>{_esc(data.first_name)}</b>, {_esc(data.university)}", base),
        Paragraph(f"Период: {_esc(data.period_label)}", base),
        Paragraph(f"Сформирована: {fmt_date(data.generated_at)}", base),
        Spacer(1, 6 * mm),
    ]

    table_rows: list[list[Flowable | str]] = [
        [Paragraph(h, bold) for h in ("Дата", "Дело", "Организация", "Часы")]
    ]
    for row in data.rows:
        table_rows.append(
            [
                fmt_date(row["date"]),
                Paragraph(_esc(row["title"]), base),
                Paragraph(_esc(row["org"]), base),
                _hours(row["hours"]),
            ]
        )
    table_rows.append(["", Paragraph("Итого", bold), "", _hours(data.total)])
    table = Table(table_rows, colWidths=[24 * mm, 76 * mm, 55 * mm, 15 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story += [table, Spacer(1, 8 * mm)]

    for signer in data.signers:
        who = ", ".join(
            part for part in (signer.org, f"{signer.position} {signer.name}".strip()) if part
        )
        story.append(
            Table(
                [
                    [
                        Paragraph(_esc(who), base),
                        _image(signer.signature_png, 30 * mm, 14 * mm),
                        _image(signer.seal_png, 24 * mm, 24 * mm),
                    ]
                ],
                colWidths=[110 * mm, 35 * mm, 27 * mm],
                style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
            )
        )

    story += [
        Spacer(1, 8 * mm),
        Table(
            [
                [
                    _qr(data.verify_url, 28 * mm),
                    Paragraph(
                        f"Код подлинности: <b>{data.code}</b><br/>"
                        f"Проверка: {_esc(data.verify_url)}<br/>"
                        "Документ подписан электронной подписью платформы «Время с пользой».",
                        small,
                    ),
                ]
            ],
            colWidths=[32 * mm, 140 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
        ),
    ]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Справка о волонтёрских часах",
        author="Время с пользой",
    )
    doc.build(story)
    return buf.getvalue()

def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

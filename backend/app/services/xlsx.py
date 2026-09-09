"""Eng kichik XLSX yozuvchi — tashqi kutubxonasiz.

Nega o'zimiz yozdik: hisobot eksporti oddiy tekis jadval (matn va son), buning uchun butun
bir kutubxona olib kelish shart emas. Foydasi amaliy — eksport har qanday muhitda, jumladan
sinov mashinasida ham ishlaydi va sinovdan o'tadi; qism-qismlari standart `zipfile` bilan
qayta ochib tekshiriladi.

Fayl tuzilishi OOXML minimal to'plami: [Content_Types], _rels, workbook, styles, sheet1.
Matnlar `inlineStr` bo'lib yoziladi — sharedStrings jadvali kerak emas.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PNS = "http://schemas.openxmlformats.org/package/2006/relationships"
CNS = "http://schemas.openxmlformats.org/package/2006/content-types"

NORMAL, BOLD, HEADER = 0, 1, 2   # styles.xml dagi cellXfs tartibi


def col_name(n: int) -> str:
    """1 -> A, 27 -> AA"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _esc(v: str) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _cell(ref: str, value, style: int) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, bool):
        value = str(value)
    elif isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{_esc(value)}</t></is></c>'


_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{NS}">
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEAEFEC"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">
<alignment horizontal="center" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

_CONTENT_TYPES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CNS}">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_ROOT_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PNS}">
<Relationship Id="rId1" Type="{RNS}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WB_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PNS}">
<Relationship Id="rId1" Type="{RNS}/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="{RNS}/styles" Target="styles.xml"/>
</Relationships>"""


def write(rows: list[list], *, sheet_name: str = "Sheet1", styles: dict[int, int] | None = None,
          widths: list[int] | None = None, freeze_rows: int = 0) -> bytes:
    """`rows` — satrlar ro'yxati. `styles` — {satr raqami (1 dan): style} (BOLD / HEADER)."""
    styles = styles or {}
    body = []
    for r, row in enumerate(rows, start=1):
        style = styles.get(r, NORMAL)
        cells = "".join(_cell(f"{col_name(c)}{r}", v, style) for c, v in enumerate(row, start=1))
        body.append(f'<row r="{r}">{cells}</row>')

    cols = ""
    if widths:
        cols = "<cols>" + "".join(
            f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
            for i, w in enumerate(widths, start=1)) + "</cols>"
    pane = ""
    if freeze_rows:
        pane = (f'<pane ySplit="{freeze_rows}" topLeftCell="A{freeze_rows + 1}" '
                f'activePane="bottomLeft" state="frozen"/>')
    sheet = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             f'<worksheet xmlns="{NS}">'
             f'<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>'
             f'{cols}<sheetData>{"".join(body)}</sheetData></worksheet>')

    workbook = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<workbook xmlns="{NS}" xmlns:r="{RNS}">'
                f'<sheets><sheet name="{_esc(sheet_name)[:31]}" sheetId="1" r:id="rId1"/></sheets>'
                f'</workbook>')

    buf = io.BytesIO()
    stamp = datetime(2026, 1, 1).timetuple()[:6]   # bir xil kirish -> bir xil fayl
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("[Content_Types].xml", _CONTENT_TYPES),
                           ("_rels/.rels", _ROOT_RELS),
                           ("xl/workbook.xml", workbook),
                           ("xl/_rels/workbook.xml.rels", _WB_RELS),
                           ("xl/styles.xml", _STYLES),
                           ("xl/worksheets/sheet1.xml", sheet)):
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue()


def read_values(data: bytes) -> list[list[str]]:
    """Sinov uchun: yozilgan faylni qaytadan o'qiydi (hamma qiymat matn ko'rinishida)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode()
    return [_row_values(row) for row in re.findall(r"<row\b[^>]*>(.*?)</row>", xml, re.S)]


def _row_values(row: str) -> list[str]:
    vals = []
    for m in re.finditer(r"<c\b[^>]*?(?:/>|>(.*?)</c>)", row, re.S):
        inner = m.group(1) or ""
        t = re.search(r"<t[^>]*>(.*?)</t>", inner, re.S)
        v = re.search(r"<v>(.*?)</v>", inner, re.S)
        raw = t.group(1) if t else (v.group(1) if v else "")
        vals.append(raw.replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&quot;", '"').replace("&amp;", "&"))
    return vals

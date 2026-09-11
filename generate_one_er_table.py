from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from db import get_connection

TABLE = "job_cards"

OUTPUT = Path(
    r"D:\Het\db_backups\ER_tables\job_cards_auto.png"
)

SCHEMA = "jms_demo2"


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


font_normal = load_font(
    r"C:\Windows\Fonts\segoeui.ttf",
    14,
)

font_bold = load_font(
    r"C:\Windows\Fonts\segoeuib.ttf",
    14,
)

font_header = load_font(
    r"C:\Windows\Fonts\segoeuib.ttf",
    15,
)


conn = get_connection()
cur = conn.cursor(dictionary=True)

cur.execute(
    """
    SELECT
        COLUMN_NAME,
        COLUMN_TYPE,
        IS_NULLABLE,
        COLUMN_KEY
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = %s
      AND TABLE_NAME = %s
    ORDER BY ORDINAL_POSITION
    """,
    (SCHEMA, TABLE),
)

columns = cur.fetchall()

cur.close()
conn.close()


if not columns:
    raise SystemExit(
        f"Table not found: {TABLE}"
    )


# ---------------------------------------------------------
# Image dimensions
# ---------------------------------------------------------

width = 440
header_h = 34
row_h = 25
footer_h = 30
padding = 10

height = (
    header_h
    + (len(columns) * row_h)
    + footer_h
)

img = Image.new(
    "RGB",
    (width, height),
    "white",
)

draw = ImageDraw.Draw(img)


# ---------------------------------------------------------
# Workbench-like table body
# ---------------------------------------------------------

draw.rounded_rectangle(
    (0, 0, width - 1, height - 1),
    radius=8,
    fill=(242, 242, 242),
    outline=(145, 145, 145),
    width=1,
)


# ---------------------------------------------------------
# Header
# ---------------------------------------------------------

draw.rectangle(
    (1, 1, width - 2, header_h),
    fill=(155, 199, 225),
)

# Small table icon
draw.rectangle(
    (10, 9, 24, 23),
    fill=(230, 240, 250),
    outline=(80, 120, 160),
)

draw.line(
    (13, 12, 21, 12),
    fill=(80, 120, 160),
)

draw.line(
    (13, 16, 21, 16),
    fill=(80, 120, 160),
)

draw.line(
    (13, 20, 21, 20),
    fill=(80, 120, 160),
)

draw.text(
    (31, 7),
    TABLE,
    font=font_header,
    fill=(0, 0, 0),
)


# Triangle at right
cx = width - 18
cy = 16

draw.polygon(
    [
        (cx - 5, cy - 3),
        (cx + 5, cy - 3),
        (cx, cy + 4),
    ],
    fill=(90, 100, 105),
)


# ---------------------------------------------------------
# Column rows
# ---------------------------------------------------------

y = header_h

for col in columns:

    y2 = y + row_h

    draw.rectangle(
        (1, y, width - 2, y2),
        fill=(250, 250, 250),
    )

    draw.line(
        (1, y2, width - 2, y2),
        fill=(225, 225, 225),
    )

    key_type = col.get("COLUMN_KEY") or ""

    icon_x = 15
    icon_y = y + (row_h // 2)

    if key_type == "PRI":

        # Yellow key
        draw.ellipse(
            (
                icon_x - 4,
                icon_y - 4,
                icon_x + 3,
                icon_y + 3,
            ),
            fill=(244, 196, 35),
            outline=(190, 145, 0),
        )

        draw.line(
            (
                icon_x + 2,
                icon_y,
                icon_x + 8,
                icon_y,
            ),
            fill=(190, 145, 0),
            width=2,
        )

    else:

        # Cyan Workbench-style diamond
        draw.polygon(
            [
                (icon_x, icon_y - 4),
                (icon_x + 4, icon_y),
                (icon_x, icon_y + 4),
                (icon_x - 4, icon_y),
            ],
            fill=(175, 225, 230),
            outline=(90, 170, 180),
        )


    text = (
        f"{col['COLUMN_NAME']} "
        f"{col['COLUMN_TYPE'].upper()}"
    )

    draw.text(
        (29, y + 4),
        text,
        font=font_normal,
        fill=(0, 0, 0),
    )

    y = y2


# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------

draw.rectangle(
    (
        1,
        height - footer_h,
        width - 2,
        height - 2,
    ),
    fill=(195, 195, 195),
)

draw.text(
    (
        12,
        height - footer_h + 6,
    ),
    "Indexes",
    font=font_bold,
    fill=(85, 85, 85),
)

img.save(
    OUTPUT,
    "PNG",
)

print("IMAGE CREATED:")
print(OUTPUT)
print("")
print("TABLE:", TABLE)
print("COLUMNS:", len(columns))
print("NO DATABASE DATA CHANGED")

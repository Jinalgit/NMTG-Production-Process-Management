from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from db import get_connection

SCHEMA = "jms_demo2"

OUTPUT_DIR = Path(
    r"D:\Het\db_backups\ER_tables"
)

# Already created and approved.
SKIP_TABLES = {
    "job_cards",
}


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


def text_width(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )
    return box[2] - box[0]


def create_table_image(table_name, columns):

    # ---------------------------------------------------------
    # Calculate width automatically
    # ---------------------------------------------------------

    test_img = Image.new(
        "RGB",
        (10, 10),
        "white",
    )

    test_draw = ImageDraw.Draw(test_img)

    longest_width = text_width(
        test_draw,
        table_name,
        font_header,
    )

    for col in columns:

        label = (
            f"{col['COLUMN_NAME']} "
            f"{str(col['COLUMN_TYPE']).upper()}"
        )

        longest_width = max(
            longest_width,
            text_width(
                test_draw,
                label,
                font_normal,
            ),
        )

    # Minimum same as approved job_cards image.
    # Expand automatically for long field names.
    width = max(
        440,
        longest_width + 70,
    )

    width = min(
        width,
        900,
    )

    header_h = 34
    row_h = 25
    footer_h = 30

    height = (
        header_h
        + len(columns) * row_h
        + footer_h
    )

    img = Image.new(
        "RGB",
        (width, height),
        "white",
    )

    draw = ImageDraw.Draw(img)

    # ---------------------------------------------------------
    # Outer table
    # ---------------------------------------------------------

    draw.rounded_rectangle(
        (
            0,
            0,
            width - 1,
            height - 1,
        ),
        radius=8,
        fill=(242, 242, 242),
        outline=(145, 145, 145),
        width=1,
    )

    # ---------------------------------------------------------
    # Header
    # ---------------------------------------------------------

    draw.rectangle(
        (
            1,
            1,
            width - 2,
            header_h,
        ),
        fill=(155, 199, 225),
    )

    # Table icon
    draw.rectangle(
        (
            10,
            9,
            24,
            23,
        ),
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
        table_name,
        font=font_header,
        fill=(0, 0, 0),
    )

    # Header triangle
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
            (
                1,
                y,
                width - 2,
                y2,
            ),
            fill=(250, 250, 250),
        )

        draw.line(
            (
                1,
                y2,
                width - 2,
                y2,
            ),
            fill=(225, 225, 225),
        )

        key_type = (
            col.get("COLUMN_KEY")
            or ""
        )

        icon_x = 15
        icon_y = (
            y
            + row_h // 2
        )

        # -----------------------------------------------------
        # Primary Key icon
        # -----------------------------------------------------

        if key_type == "PRI":

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

        # -----------------------------------------------------
        # Normal column icon
        # -----------------------------------------------------

        else:

            draw.polygon(
                [
                    (
                        icon_x,
                        icon_y - 4,
                    ),
                    (
                        icon_x + 4,
                        icon_y,
                    ),
                    (
                        icon_x,
                        icon_y + 4,
                    ),
                    (
                        icon_x - 4,
                        icon_y,
                    ),
                ],
                fill=(175, 225, 230),
                outline=(90, 170, 180),
            )

        label = (
            f"{col['COLUMN_NAME']} "
            f"{str(col['COLUMN_TYPE']).upper()}"
        )

        draw.text(
            (
                29,
                y + 4,
            ),
            label,
            font=font_normal,
            fill=(0, 0, 0),
        )

        y = y2

    # ---------------------------------------------------------
    # Index footer
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

    # ---------------------------------------------------------
    # Save image
    # ---------------------------------------------------------

    output_file = (
        OUTPUT_DIR
        / f"{table_name}.png"
    )

    img.save(
        output_file,
        "PNG",
    )

    return output_file


# =============================================================
# DATABASE READ
# =============================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

conn = get_connection()
cur = conn.cursor(
    dictionary=True
)

try:

    cur.execute(
        """
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s
          AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """,
        (SCHEMA,),
    )

    table_rows = (
        cur.fetchall()
        or []
    )

    table_names = [
        row["TABLE_NAME"]
        for row in table_rows
    ]

    print("=" * 70)
    print("NMTG ER TABLE IMAGE GENERATOR")
    print("=" * 70)

    print(
        "TOTAL TABLES FOUND:",
        len(table_names),
    )

    created = 0
    skipped = 0
    failed = 0

    for table_name in table_names:

        if table_name in SKIP_TABLES:

            print(
                f"SKIP    : {table_name}"
            )

            skipped += 1
            continue

        try:

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
                (
                    SCHEMA,
                    table_name,
                ),
            )

            columns = (
                cur.fetchall()
                or []
            )

            if not columns:

                print(
                    f"NO COLS : {table_name}"
                )

                failed += 1
                continue

            output_file = (
                create_table_image(
                    table_name,
                    columns,
                )
            )

            print(
                f"CREATED : "
                f"{table_name} "
                f"({len(columns)} columns)"
            )

            created += 1

        except Exception as exc:

            print(
                f"ERROR   : "
                f"{table_name} -> {exc}"
            )

            failed += 1

finally:

    cur.close()
    conn.close()


print("")
print("=" * 70)
print("COMPLETE")
print("=" * 70)

print(
    "Images created :",
    created,
)

print(
    "Skipped        :",
    skipped,
)

print(
    "Failed         :",
    failed,
)

print(
    "Output folder  :",
    OUTPUT_DIR,
)

print("")
print(
    "READ ONLY - NO DATABASE DATA CHANGED"
)

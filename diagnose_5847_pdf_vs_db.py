from pathlib import Path
import re

from pypdf import PdfReader
from db import get_connection

ROOT = Path(
    r"C:\Users\IT system\Desktop\JOBCARD\JOBCARD"
    r"\07.07.2024\030926\jobcard\aajna"
)

TARGET_JC = "0000115847"


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").replace("\xa0", " ")
    ).strip()


def extract_text(path):
    reader = PdfReader(str(path))
    output = []

    for page in reader.pages:
        try:
            value = page.extract_text(
                extraction_mode="layout"
            ) or ""
        except TypeError:
            value = page.extract_text() or ""

        output.append(value)

    return "\n".join(output)


def first(pattern, text):
    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE | re.MULTILINE
    )
    return clean(match.group(1)) if match else ""


target_file = None
target_text = ""

for path in sorted(ROOT.glob("*.pdf")):
    text = extract_text(path)

    jc_no = first(
        r"Job\s*Card\s*No\.?\s*:?\s*(\d{4,12})",
        text
    )

    if jc_no == TARGET_JC:
        target_file = path
        target_text = text
        break


if not target_file:
    raise SystemExit(
        f"JC {TARGET_JC} PDF not found."
    )


child_code = first(
    r"Item\s*Name\s*:?\s*"
    r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)",
    target_text
)

bom_no = first(
    r"BOM\s*No\.?\s*:?\s*([A-Z0-9/-]+)",
    target_text
)

rm_match = re.search(
    r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)"
    r"\s+"
    r"([A-Za-z.]+)"
    r"\s+"
    r"(\d+(?:\.\d+)?)"
    r"\s*\n"
    r"\s*([^\r\n]+)"
    r"\s*\n"
    r"\s*CUTTING\s*SIZE\s*[-:]\s*([^\r\n]+)",
    target_text,
    flags=re.IGNORECASE
)

if rm_match:
    rm_code = clean(rm_match.group(1))
    pdf_uom = clean(rm_match.group(2))
    pdf_qty = clean(rm_match.group(3))
    pdf_material = clean(rm_match.group(4))
    pdf_cutting = clean(rm_match.group(5))
else:
    rm_code = ""
    pdf_uom = ""
    pdf_qty = ""
    pdf_material = ""
    pdf_cutting = ""


print("=" * 78)
print("JC 0000115847 - PDF VS DATABASE DIAGNOSIS")
print("=" * 78)

print("")
print("[PDF]")
print("File          :", target_file.name)
print("JC            :", TARGET_JC)
print("BOM No        :", bom_no)
print("JC Child Code :", child_code)
print("RM Code       :", rm_code)
print("RM Description:", pdf_material)
print("RM UOM        :", pdf_uom)
print("RM Qty        :", pdf_qty)
print("Cutting Size  :", pdf_cutting)


conn = get_connection()
cursor = conn.cursor(dictionary=True)

try:
    print("")
    print("[DB ITEM - JC CHILD]")

    cursor.execute("""
        SELECT
            item_code,
            item_description,
            item_type,
            make_default,
            material,
            size,
            part_name
        FROM items
        WHERE item_code = %s
        LIMIT 1
    """, (child_code,))

    item = cursor.fetchone()

    print(item if item else "NOT FOUND")


    print("")
    print("[DB RAW MATERIAL ITEM]")

    cursor.execute("""
        SELECT
            item_code,
            item_description,
            item_type,
            make_default,
            material,
            size,
            part_name
        FROM items
        WHERE item_code = %s
        LIMIT 1
    """, (rm_code,))

    rm_item = cursor.fetchone()

    print(rm_item if rm_item else "NOT FOUND")


    print("")
    print("[DIRECT BOM LINK: JC CHILD -> PDF RAW MATERIAL]")

    cursor.execute("""
        SELECT
            id,
            bom_no,
            parent_code,
            child_code,
            make_buy,
            quantity,
            uom,
            cutting_size,
            is_alternate
        FROM bom_links
        WHERE parent_code = %s
          AND child_code = %s
        ORDER BY id
    """, (
        child_code,
        rm_code
    ))

    direct_links = cursor.fetchall() or []

    if direct_links:
        for row in direct_links:
            print(row)
    else:
        print("NOT FOUND")


    print("")
    print("[ALL BOM CHILDREN OF JC ITEM]")

    cursor.execute("""
        SELECT
            bl.id,
            bl.bom_no,
            bl.parent_code,
            bl.child_code,
            bl.make_buy,
            bl.quantity,
            bl.uom,
            bl.cutting_size,
            bl.is_alternate,
            i.item_description
        FROM bom_links bl
        LEFT JOIN items i
          ON i.item_code = bl.child_code
        WHERE bl.parent_code = %s
        ORDER BY bl.id
    """, (child_code,))

    children = cursor.fetchall() or []

    if children:
        for row in children:
            print(row)
    else:
        print("NO BOM CHILDREN FOUND")


    print("")
    print("=" * 78)
    print("COMPARISON")
    print("=" * 78)

    if not direct_links:
        print(
            "RESULT: PDF has raw material but the same direct "
            "BOM link is NOT FOUND in DB."
        )

    else:
        link = direct_links[0]

        db_uom = clean(link.get("uom"))
        db_cutting = clean(link.get("cutting_size"))
        db_qty = clean(link.get("quantity"))

        print(
            "PDF UOM         :",
            pdf_uom
        )
        print(
            "DB UOM          :",
            db_uom
        )

        print(
            "PDF Cutting Size:",
            pdf_cutting
        )
        print(
            "DB Cutting Size :",
            db_cutting
        )

        print(
            "PDF Qty         :",
            pdf_qty
        )
        print(
            "DB Qty          :",
            db_qty
        )

        if (
            pdf_cutting.lower()
            != db_cutting.lower()
        ):
            print(
                "MISMATCH: Cutting Size differs between "
                "PDF and BOM master."
            )

        if (
            pdf_uom.lower().rstrip(".")
            != db_uom.lower().rstrip(".")
        ):
            print(
                "MISMATCH: UOM differs between "
                "PDF and BOM master."
            )

finally:
    cursor.close()
    conn.close()

print("")
print("READ-ONLY DIAGNOSIS COMPLETE")
print("NO DATABASE DATA CHANGED")

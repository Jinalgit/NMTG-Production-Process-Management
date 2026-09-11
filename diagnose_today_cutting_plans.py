from pathlib import Path
import re

from pypdf import PdfReader
from db import get_connection

ROOT = Path(
    r"C:\Users\IT system\Desktop\JOBCARD\JOBCARD"
    r"\07.07.2024\030926\jobcard\aajna"
)


def clean(v):
    return re.sub(
        r"\s+",
        " ",
        str(v or "").replace("\xa0", " ")
    ).strip()


def pdf_text(path):
    reader = PdfReader(str(path))
    out = []

    for page in reader.pages:
        try:
            txt = page.extract_text(
                extraction_mode="layout"
            ) or ""
        except TypeError:
            txt = page.extract_text() or ""

        out.append(txt)

    return "\n".join(out)


def first(pattern, text):
    m = re.search(
        pattern,
        text,
        flags=re.IGNORECASE | re.MULTILINE
    )
    return clean(m.group(1)) if m else ""


def get_pdf_info(path):
    text = pdf_text(path)

    jc = first(
        r"Job\s*Card\s*No\.?\s*:?\s*(\d{4,12})",
        text
    )

    child = first(
        r"Item\s*Name\s*:?\s*"
        r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)",
        text
    )

    cut = first(
        r"CUTTING\s*SIZE\s*[-:]\s*([^\r\n]+)",
        text
    )

    material = ""

    m = re.search(
        r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)"
        r"\s+"
        r"(?:mm|kg\.?|nos\.?)"
        r"\s+"
        r"\d+(?:\.\d+)?"
        r"\s*[\r\n]+"
        r"\s*([^\r\n]+)",
        text,
        flags=re.IGNORECASE
    )

    if m:
        material = clean(m.group(2))

    return {
        "file": path.name,
        "jc": jc,
        "child": child,
        "material": material,
        "cutting": cut,
    }


pdf_records = []

for path in sorted(ROOT.glob("*.pdf")):
    info = get_pdf_info(path)

    if info["jc"]:
        pdf_records.append(info)


conn = get_connection()
cur = conn.cursor(dictionary=True)

print("=" * 100)
print("CUTTING PLAN CREATION DIAGNOSIS")
print("=" * 100)

seen = set()

for info in pdf_records:

    jc = info["jc"]

    if jc in seen:
        print()
        print(
            f"{info['file']} -> JC {jc} "
            "DUPLICATE PDF - already checked"
        )
        continue

    seen.add(jc)

    print()
    print("-" * 100)
    print(
        f"FILE {info['file']} | JC {jc}"
    )
    print("-" * 100)

    print("PDF Child Code :", info["child"])
    print("PDF Material   :", info["material"] or "-")
    print("PDF Cut Size   :", info["cutting"] or "-")

    # --------------------------------------------------
    # Process Master
    # --------------------------------------------------

    cur.execute("""
        SELECT
            ip.step_no,
            p.process_name
        FROM item_processes ip
        JOIN processes p
          ON p.id = ip.process_id
        WHERE ip.item_code = %s
        ORDER BY ip.step_no, ip.id
    """, (info["child"],))

    master_rows = cur.fetchall() or []

    master_processes = [
        clean(row["process_name"])
        for row in master_rows
    ]

    master_has_cutting = any(
        p.lower() == "cutting"
        for p in master_processes
    )

    print()
    print(
        "MASTER ROUTE    :",
        " -> ".join(master_processes)
        if master_processes
        else "NO ROUTE"
    )

    print(
        "MASTER CUTTING  :",
        "YES" if master_has_cutting else "NO"
    )

    # --------------------------------------------------
    # Actual JC timeline
    # --------------------------------------------------

    cur.execute("""
        SELECT process_name
        FROM job_card_process_days
        WHERE job_card_no = %s
        ORDER BY id
    """, (jc,))

    timeline = [
        clean(row["process_name"])
        for row in cur.fetchall()
    ]

    timeline_has_cutting = any(
        p.lower() == "cutting"
        for p in timeline
    )

    print(
        "JC TIMELINE     :",
        " -> ".join(timeline)
        if timeline
        else "JC NOT IMPORTED / NO TIMELINE"
    )

    print(
        "TIMELINE CUTTING:",
        "YES" if timeline_has_cutting else "NO"
    )

    # --------------------------------------------------
    # Cutting Plan table - dynamic column detection
    # --------------------------------------------------

    cur.execute("""
        SHOW COLUMNS FROM cutting_plans
    """)

    cp_columns = [
        row["Field"]
        for row in cur.fetchall()
    ]

    jc_column = None

    for candidate in (
        "source_job_card_no",
        "job_card_no",
    ):
        if candidate in cp_columns:
            jc_column = candidate
            break

    cp_rows = []

    if jc_column:
        wanted = [
            col for col in (
                "id",
                jc_column,
                "item_name",
                "material_spec",
                "material",
                "cut_size",
                "planned_qty",
                "status",
            )
            if col in cp_columns
        ]

        sql = (
            "SELECT "
            + ", ".join(wanted)
            + f" FROM cutting_plans "
            + f"WHERE {jc_column} = %s "
            + "ORDER BY id"
        )

        cur.execute(sql, (jc,))
        cp_rows = cur.fetchall() or []

    print(
        "CUTTING PLAN    :",
        f"YES ({len(cp_rows)} record)"
        if cp_rows
        else "NO"
    )

    for cp in cp_rows:
        print("PLAN DATA       :", cp)

    # --------------------------------------------------
    # Diagnosis
    # --------------------------------------------------

    print()

    if info["cutting"] and not master_has_cutting:
        print(
            "DIAGNOSIS       : PDF HAS CUTTING SIZE, "
            "BUT PROCESS MASTER HAS NO 'Cutting'."
        )
        print(
            "                   Current upload code therefore "
            "does NOT create a Cutting Plan."
        )

    elif master_has_cutting and not cp_rows:
        print(
            "DIAGNOSIS       : Process Master HAS Cutting, "
            "but Cutting Plan was NOT created."
        )
        print(
            "                   Next check should be "
            "_resolve_auto_source()."
        )

    elif master_has_cutting and cp_rows:
        print(
            "DIAGNOSIS       : Expected Cutting Plan exists."
        )

    else:
        print(
            "DIAGNOSIS       : No Cutting requirement detected "
            "from Process Master."
        )


print()
print("=" * 100)
print("SUMMARY")
print("=" * 100)
print("Unique JCs checked :", len(seen))

cur.close()
conn.close()

print("READ ONLY - NO DATABASE DATA CHANGED")

from pathlib import Path
import re
from pypdf import PdfReader

ROOT = Path(
    r"C:\Users\IT system\Desktop\JOBCARD\JOBCARD"
    r"\07.07.2024\030926\jobcard\aajna"
)

TARGET_JC = "0000115847"

REPORT_FILE = Path(
    r"D:\Het\demo2\jc_0000115847_pdf_diagnosis.txt"
)


def clean(value):
    value = str(value or "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", value)


def extract_pdf_text(pdf_path):
    reader = PdfReader(str(pdf_path))
    pages = []

    for page in reader.pages:
        try:
            text = page.extract_text(
                extraction_mode="layout"
            ) or ""
        except TypeError:
            text = page.extract_text() or ""

        pages.append(text)

    return "\n".join(pages)


def get_job_card_no(text):
    match = re.search(
        r"Job\s*Card\s*No\.?\s*:?\s*(\d{4,12})",
        text,
        flags=re.IGNORECASE,
    )

    return match.group(1) if match else ""


def current_parser_result(text):
    """
    Reproduce the important material/cutting-size logic
    currently used by LOCAL job_cards.py.
    """

    match = re.search(
        r"Raw\s*Material\s*\.*"
        r"(.*?)"
        r"(?:-+\s*Processes\s*-+|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    rm_block = match.group(1) if match else ""

    lines = [
        clean(line)
        for line in rm_block.splitlines()
        if clean(line)
    ]

    material_code = ""
    material_uom = ""
    material_qty = ""
    material_desc = ""

    for line_index, line in enumerate(lines):
        material_row = re.match(
            r"^"
            r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)"
            r"\s+"
            r"([A-Za-z.]+)"
            r"\s+"
            r"(\d+(?:\.\d+)?)"
            r"$",
            line,
            flags=re.IGNORECASE,
        )

        if not material_row:
            continue

        material_code = clean(material_row.group(1))
        material_uom = clean(material_row.group(2))
        material_qty = clean(material_row.group(3))

        for desc_line in lines[
            line_index + 1:
            line_index + 5
        ]:
            if re.search(
                r"CUTTING\s*SIZE",
                desc_line,
                flags=re.IGNORECASE,
            ):
                continue

            if desc_line:
                material_desc = desc_line
                break

        break

    cut_match = re.search(
        r"CUTTING\s*SIZE\s*[-:]\s*([^\r\n]+)",
        rm_block,
        flags=re.IGNORECASE,
    )

    cutting_size = clean(
        cut_match.group(1)
    ) if cut_match else ""

    return {
        "block": rm_block,
        "material_code": material_code,
        "material_uom": material_uom,
        "material_qty": material_qty,
        "material_desc": material_desc,
        "cutting_size": cutting_size,
    }


def wider_item_details_result(text):
    """
    Diagnostic parser looking at the actual Item Details area,
    including text BEFORE Raw Material ....
    """

    match = re.search(
        r"Item\s*Details"
        r"(.*?)"
        r"(?:-+\s*Processes\s*-+|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    block = match.group(1) if match else ""

    lines = [
        clean(line)
        for line in block.splitlines()
        if clean(line)
    ]

    material_code = ""
    material_uom = ""
    material_qty = ""
    material_desc = ""

    material_line_index = None

    for index, line in enumerate(lines):
        material_row = re.match(
            r"^"
            r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)"
            r"\s+"
            r"([A-Za-z.]+)"
            r"\s+"
            r"(\d+(?:\.\d+)?)"
            r"$",
            line,
            flags=re.IGNORECASE,
        )

        if material_row:
            material_code = clean(material_row.group(1))
            material_uom = clean(material_row.group(2))
            material_qty = clean(material_row.group(3))
            material_line_index = index
            break

    if material_line_index is not None:
        for line in lines[
            material_line_index + 1:
            material_line_index + 6
        ]:
            if re.search(
                r"CUTTING\s*SIZE",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            if re.fullmatch(
                r"Raw\s*Material\s*\.*",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            if line:
                material_desc = line
                break

    cut_match = re.search(
        r"CUTTING\s*SIZE\s*[-:]\s*([^\r\n]+)",
        block,
        flags=re.IGNORECASE,
    )

    cutting_size = clean(
        cut_match.group(1)
    ) if cut_match else ""

    return {
        "block": block,
        "lines": lines,
        "material_code": material_code,
        "material_uom": material_uom,
        "material_qty": material_qty,
        "material_desc": material_desc,
        "cutting_size": cutting_size,
    }


def keyword_positions(text):
    result = {}

    patterns = {
        "Item Details": r"Item\s*Details",
        "CUTTING SIZE": r"CUTTING\s*SIZE",
        "Raw Material": r"Raw\s*Material",
        "Processes": r"-+\s*Processes\s*-+",
    }

    for name, pattern in patterns.items():
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        result[name] = (
            match.start()
            if match
            else -1
        )

    return result


pdf_files = sorted(
    path
    for path in ROOT.rglob("*")
    if path.is_file()
    and path.suffix.lower() == ".pdf"
)

output = []

output.append("=" * 75)
output.append("NMTG PDF MATERIAL / CUTTING SIZE DIAGNOSIS")
output.append("=" * 75)
output.append(f"Folder : {ROOT}")
output.append(f"PDFs   : {len(pdf_files)}")
output.append(f"Target : {TARGET_JC}")
output.append("")

target_found = False

for pdf_path in pdf_files:
    try:
        text = extract_pdf_text(pdf_path)
    except Exception as exc:
        output.append(
            f"ERROR | {pdf_path.name} | {exc}"
        )
        continue

    jc_no = get_job_card_no(text)

    current = current_parser_result(text)
    wider = wider_item_details_result(text)
    positions = keyword_positions(text)

    if jc_no == TARGET_JC:
        target_found = True

    output.append("-" * 75)
    output.append(
        f"FILE: {pdf_path.name}"
    )
    output.append(
        f"JC  : {jc_no or 'NOT FOUND'}"
    )

    output.append(
        "CURRENT PARSER -> "
        f"Material=[{current['material_desc']}] "
        f"Cutting=[{current['cutting_size']}]"
    )

    output.append(
        "WIDER BLOCK    -> "
        f"Code=[{wider['material_code']}] "
        f"UOM=[{wider['material_uom']}] "
        f"Qty=[{wider['material_qty']}] "
        f"Material=[{wider['material_desc']}] "
        f"Cutting=[{wider['cutting_size']}]"
    )

    output.append(
        "POSITIONS       -> "
        f"ItemDetails={positions['Item Details']} | "
        f"CuttingSize={positions['CUTTING SIZE']} | "
        f"RawMaterial={positions['Raw Material']} | "
        f"Processes={positions['Processes']}"
    )

    cut_pos = positions["CUTTING SIZE"]
    rm_pos = positions["Raw Material"]

    if (
        cut_pos >= 0
        and rm_pos >= 0
        and cut_pos < rm_pos
    ):
        output.append(
            "DIAGNOSIS      -> CUTTING SIZE is BEFORE "
            "'Raw Material'. Current parser cannot see it."
        )

    if jc_no == TARGET_JC:
        output.append("")
        output.append(
            "TARGET JC ITEM DETAILS / RAW MATERIAL AREA:"
        )
        output.append("")

        for line_no, line in enumerate(
            wider["lines"],
            start=1,
        ):
            output.append(
                f"{line_no:02d}: {line}"
            )

        output.append("")
        output.append(
            "CURRENT PARSER BLOCK AFTER 'Raw Material':"
        )
        output.append("")

        current_lines = [
            clean(line)
            for line in current["block"].splitlines()
            if clean(line)
        ]

        if current_lines:
            for line_no, line in enumerate(
                current_lines,
                start=1,
            ):
                output.append(
                    f"{line_no:02d}: {line}"
                )
        else:
            output.append(
                "[EMPTY BLOCK]"
            )

output.append("")
output.append("=" * 75)

if target_found:
    output.append(
        f"TARGET JC {TARGET_JC}: FOUND"
    )
else:
    output.append(
        f"TARGET JC {TARGET_JC}: NOT FOUND"
    )

output.append("=" * 75)

report = "\n".join(output)

print(report)

REPORT_FILE.write_text(
    report,
    encoding="utf-8",
)

print("")
print(
    "REPORT SAVED TO:"
)
print(
    REPORT_FILE
)

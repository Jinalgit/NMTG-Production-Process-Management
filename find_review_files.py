import csv
import re
import shutil
import sys
from pathlib import Path

from db import get_connection

SOURCE_FOLDER = Path(
    r"C:\Users\IT system\Desktop\JOBCARD\JOBCARD\JOB CARD-REVIEW"
)

OUTPUT_FOLDER = SOURCE_FOLDER / "NEEDS-PROCESS-MASTER-REVIEW"
REPORT_FILE = SOURCE_FOLDER / "job_card_review_check.csv"


JOB_CARD_PATTERN = re.compile(
    r"Job\s*Card\s*No\.?\s*[^0-9]*(\d{4,12})",
    re.IGNORECASE,
)

CHILD_CODE_PATTERNS = [
    re.compile(
        r"Item\s*Name\s*[^A-Z0-9]*"
        r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:Item|Child)\s*Code\s*[^A-Z0-9]*"
        r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)",
        re.IGNORECASE,
    ),
]


def read_text(path):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except Exception:
            return None

    return None


def extract_job_cards(text):
    results = []

    matches = list(JOB_CARD_PATTERN.finditer(text))

    for index, match in enumerate(matches):
        job_card_no = match.group(1).strip()

        start = match.start()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        section = text[start:end]
        child_code = ""

        for pattern in CHILD_CODE_PATTERNS:
            child_match = pattern.search(section)

            if child_match:
                child_code = child_match.group(1).strip().upper()
                break

        results.append({
            "job_card_no": job_card_no,
            "child_code": child_code,
        })

    return results


def exists_in_job_cards(cursor, job_card_no):
    cursor.execute(
        """
        SELECT 1
        FROM job_cards
        WHERE job_card_no = %s
        LIMIT 1
        """,
        (job_card_no,),
    )

    return cursor.fetchone() is not None


def exists_in_items(cursor, child_code):
    if not child_code:
        return False

    cursor.execute(
        """
        SELECT 1
        FROM items
        WHERE item_code = %s
        LIMIT 1
        """,
        (child_code,),
    )

    return cursor.fetchone() is not None


def main():
    if not SOURCE_FOLDER.exists():
        print(f"ERROR: Folder not found:\n{SOURCE_FOLDER}")
        sys.exit(1)

    files = [
        path
        for path in SOURCE_FOLDER.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".csv", ".xlsx", ".xls"}
    ]

    if not files:
        print("No CSV or Excel files found.")
        return

    OUTPUT_FOLDER.mkdir(exist_ok=True)

    conn = None
    cursor = None
    report_rows = []
    copied_files = set()

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        for path in sorted(files):
            if path.suffix.lower() != ".csv":
                report_rows.append({
                    "file_name": path.name,
                    "job_card_no": "",
                    "child_code": "",
                    "job_card_exists": "",
                    "item_exists": "",
                    "status": "EXCEL_FILE_NOT_CHECKED",
                })
                continue

            text = read_text(path)

            if text is None:
                report_rows.append({
                    "file_name": path.name,
                    "job_card_no": "",
                    "child_code": "",
                    "job_card_exists": "",
                    "item_exists": "",
                    "status": "FILE_READ_ERROR",
                })
                continue

            records = extract_job_cards(text)

            if not records:
                report_rows.append({
                    "file_name": path.name,
                    "job_card_no": "",
                    "child_code": "",
                    "job_card_exists": "",
                    "item_exists": "",
                    "status": "JOB_CARD_NOT_FOUND_IN_FILE",
                })
                continue

            for record in records:
                job_card_no = record["job_card_no"]
                child_code = record["child_code"]

                job_card_exists = exists_in_job_cards(
                    cursor,
                    job_card_no,
                )

                item_exists = exists_in_items(
                    cursor,
                    child_code,
                )

                if job_card_exists:
                    status = "ALREADY_IMPORTED"

                elif not child_code:
                    status = "CHILD_CODE_NOT_FOUND"

                elif not item_exists:
                    status = "NEEDS_PROCESS_MASTER_REVIEW"

                    if path.name not in copied_files:
                        shutil.copy2(
                            path,
                            OUTPUT_FOLDER / path.name,
                        )
                        copied_files.add(path.name)

                else:
                    status = "FRESH_JOB_CARD_EXISTING_ITEM"

                report_rows.append({
                    "file_name": path.name,
                    "job_card_no": job_card_no,
                    "child_code": child_code,
                    "job_card_exists": "YES" if job_card_exists else "NO",
                    "item_exists": "YES" if item_exists else "NO",
                    "status": status,
                })

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

    with REPORT_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as report:
        writer = csv.DictWriter(
            report,
            fieldnames=[
                "file_name",
                "job_card_no",
                "child_code",
                "job_card_exists",
                "item_exists",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(report_rows)

    review_count = sum(
        1
        for row in report_rows
        if row["status"] == "NEEDS_PROCESS_MASTER_REVIEW"
    )

    fresh_existing_count = sum(
        1
        for row in report_rows
        if row["status"] == "FRESH_JOB_CARD_EXISTING_ITEM"
    )

    already_count = sum(
        1
        for row in report_rows
        if row["status"] == "ALREADY_IMPORTED"
    )

    print()
    print("=" * 70)
    print("JOB CARD REVIEW CHECK COMPLETED")
    print("=" * 70)
    print(
        f"Needs Process Master review : {review_count}"
    )
    print(
        f"Fresh JC, item already exists: {fresh_existing_count}"
    )
    print(
        f"Already imported             : {already_count}"
    )
    print()
    print(f"Review files copied to:\n{OUTPUT_FOLDER}")
    print()
    print(f"Full report created at:\n{REPORT_FILE}")


if __name__ == "__main__":
    main()

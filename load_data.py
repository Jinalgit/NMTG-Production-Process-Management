"""
Loads 5 actual job card records and process master data
into the jms_demo2 database.

Run once after db_setup.sql has been executed.
"""

import pandas as pd
import mysql.connector

PLANNING_FILE = r"D:\Het\Planning sheet 26-27-work for it-2.xlsx"
MASTER_FILE   = r"D:\Het\Master_Output.xlsx"

conn = mysql.connector.connect(
    host="127.0.0.1", port=3306, database="jms_demo2",
    user="root", password="admin@123",
    auth_plugin="mysql_native_password"
)
cursor = conn.cursor()

print("Reading planning data...")
df = pd.read_excel(PLANNING_FILE, sheet_name=0, header=None)
data = df.iloc[1:].reset_index(drop=True)

print("Reading process master...")
pm = pd.read_excel(MASTER_FILE, sheet_name="Process Wise Output")
pm.columns = pm.columns.str.strip()

# Best 5 row indices (0-based after skipping header row)
BEST_ROWS = [0, 1, 2, 3, 11]

def clean(val):
    if pd.isna(val): return None
    s = str(val).strip()
    return None if s in ["", "-", "nan"] else s

def clean_date(val):
    if pd.isna(val): return None
    if hasattr(val, "strftime"): return val.strftime("%Y-%m-%d")
    return None

def clean_int(val):
    if pd.isna(val): return None
    try: return int(float(str(val)))
    except: return None

# ── Insert 5 job cards ────────────────────────────────────────────────────────
print("\nInserting 5 job card records...")
for idx in BEST_ROWS:
    row       = data.iloc[idx]
    jc_no     = clean(row.iloc[5])
    so_no     = clean(row.iloc[3])
    so_date   = clean_date(row.iloc[4])
    jc_date   = clean_date(row.iloc[6])
    f_status  = clean(row.iloc[2]) or "Pending"
    erp_stat  = clean(row.iloc[46]) or "Open"
    item_name = clean(row.iloc[10])
    material  = clean(row.iloc[45])
    so_qty    = clean_int(row.iloc[12])
    jc_qty    = clean_int(row.iloc[15])
    wip_status= clean(row.iloc[16]) or "Pending"
    wip_days  = clean_int(row.iloc[17])
    tot_days  = clean_int(row.iloc[34])
    delivery  = clean_date(row.iloc[36])
    remarks   = clean(row.iloc[18])

    if not jc_no: continue

    cursor.execute("""
        INSERT IGNORE INTO job_cards
        (job_card_no, so_no, so_date, job_card_date, final_status, erp_status)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (jc_no, so_no, so_date, jc_date, f_status, erp_stat))

    cursor.execute("""
        INSERT INTO job_card_items
        (job_card_no, item_name, material, so_qty, job_card_qty,
         wip_status, wip_stage_days, total_days, delivery_date, remarks)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (jc_no, item_name, material, so_qty, jc_qty,
          wip_status, wip_days, tot_days, delivery, remarks))

    print(f"  ✓ JC {jc_no} — {item_name} — WIP: {wip_status}")

conn.commit()

# ── Insert process master (first 50 records) ─────────────────────────────────
print("\nInserting process master records...")
p_cols = ["P1","P2","P3","P4","P5","P6","P7","P8"]
inserted = 0
for _, r in pm.head(50).iterrows():
    model    = clean(r.get("Model name= item name"))
    material = clean(r.get("Material"))
    if not model: continue
    procs   = [clean(r.get(p)) for p in p_cols]
    num_ops = sum(1 for p in procs if p)
    cursor.execute("""
        INSERT INTO process_master
        (model_name, material, p1,p2,p3,p4,p5,p6,p7,p8,num_operations)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (model, material, *procs, num_ops))
    inserted += 1

conn.commit()
print(f"  ✓ {inserted} process master records inserted.")

cursor.close()
conn.close()

print("\n✅ Done! jms_demo2 database is ready.")
print("   Job Cards : 5")
print(f"   Process Master: {inserted}")
print("   Supervisors: 5 (inserted via db_setup.sql)")

# -*- End of file -*-
# import mysql.connector

# conn = mysql.connector.connect(
#     host="127.0.0.1", port=3306, database="jms_demo2",
#     user="root", password="admin@123",
#     auth_plugin="mysql_native_password"
# )
# cursor = conn.cursor()

# keep = "('108553','108565','108567','108568','108850')"

# cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
# cursor.execute(f"DELETE FROM audit_trail WHERE job_card_no NOT IN {keep}")
# cursor.execute(f"DELETE FROM quality_check_details WHERE quality_check_id IN (SELECT id FROM quality_checks WHERE job_card_no NOT IN {keep})")
# cursor.execute(f"DELETE FROM quality_checks WHERE job_card_no NOT IN {keep}")
# cursor.execute(f"DELETE FROM job_card_process_days WHERE job_card_no NOT IN {keep}")
# cursor.execute(f"DELETE FROM job_card_items WHERE job_card_no NOT IN {keep}")
# cursor.execute(f"DELETE FROM job_cards WHERE job_card_no NOT IN {keep}")
# cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

# cursor.execute("UPDATE job_card_items SET wip_status='Rough Turning', remaining_days=28 WHERE job_card_no='108553'")
# cursor.execute("UPDATE job_card_items SET wip_status='CNC Machining',  remaining_days=0  WHERE job_card_no='108565'")
# cursor.execute("UPDATE job_card_items SET wip_status='Pending',        remaining_days=51 WHERE job_card_no='108567'")
# cursor.execute("UPDATE job_card_items SET wip_status='Pending',        remaining_days=51 WHERE job_card_no='108568'")
# cursor.execute("UPDATE job_card_items SET wip_status='Store',          remaining_days=0  WHERE job_card_no='108850'")
# cursor.execute("UPDATE job_card_process_days SET is_completed=0, end_date=NULL WHERE job_card_no='108553' AND process_name IN ('Rough Turning','Heat Treatment','CNC Machining')")

# conn.commit()

# cursor.execute("SELECT job_card_no, wip_status, remaining_days FROM job_card_items ORDER BY job_card_no")
# rows = cursor.fetchall()
# print("\nFinal records:")
# for row in rows:
#     print(f"  {row[0]} | {row[1]} | {row[2]}")

# cursor.close()
# conn.close()
# print("\nDone!")
# -*- coding: utf-8 -*-
"""
Fix demo data issues + clean old records.
Save to: D:\\Het\\Junk\\New_demo_fix.py
Run:     python D:\\Het\\Junk\\New_demo_fix.py
"""

import mysql.connector
from datetime import date, datetime, timedelta

conn = mysql.connector.connect(
    host="127.0.0.1", port=3306, database="jms_demo2",
    user="root", password="admin@123",
    auth_plugin="mysql_native_password"
)
cursor = conn.cursor(dictionary=True)
TODAY = date.today()

print("=" * 65)
print("FIXING DEMO DATA")
print("=" * 65)

# ── Step 1: Delete ALL old 110001-110010 records ──────────────────────────────
OLD_JCS = ["110001","110002","110003","110004","110005",
           "110006","110007","110008","110009","110010","DEMO001",
           "D001","D002","D003","D004","D005",
           "D006","D007","D008","D009","D010"]

cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
for JC in OLD_JCS:
    cursor.execute("DELETE FROM audit_trail WHERE job_card_no=%s", (JC,))
    cursor.execute("""DELETE qd FROM quality_check_details qd
        JOIN quality_checks qc ON qd.quality_check_id=qc.id
        WHERE qc.job_card_no=%s""", (JC,))
    cursor.execute("DELETE FROM quality_checks WHERE job_card_no=%s", (JC,))
    cursor.execute("DELETE FROM job_card_process_days WHERE job_card_no=%s", (JC,))
    cursor.execute("DELETE FROM job_card_items WHERE job_card_no=%s", (JC,))
    cursor.execute("DELETE FROM job_cards WHERE job_card_no=%s", (JC,))
cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
print("✅ Deleted all old 110001-110010 and DEMO001 records")

# ── Step 2: Add all demo items to process_master ──────────────────────────────
items_to_add = [
    # (model_name, material, p1..p10)
    ("NHB20 - (OD 90)", "EN 9 Dia 90 x 210 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "Heat Treatment","CNC Machining",
     "Quality Check","Store","Assembly", None),

    ("NHB35 - 35x110x35", "EN 9 Dia 110 x 350 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "CNC Machining", None,
     "Quality Check","Store","Assembly", None),

    ("CLS - 40x175", "EN 24 Dia 130 x 400 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "Heat Treatment","CNC Machining",
     "Quality Check","Store","Assembly", None),

    ("CLS - 45x140x35", "EN 9 Dia 140 x 350 MM",
     "Drawing","Raw Material","Cutting","Forging",
     "Normalising","R/Turning",
     "Quality Check","Store","Assembly", None),

    ("NHB120H - (OD 290)", "EN 24 Dia 290 x 320 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "CNC Machining","Drilling & Tapping",
     "Quality Check","Store","Assembly", None),

    ("Coupling Hub - 169.9x285x375TL", "EN 24 Dia 285 x 375 MM",
     "Drawing","Raw Material","Cutting","Forging",
     "Normalising","R/Turning",
     "CNC Machining","Quality Check","Store","Assembly"),

    ("NHB120H - 70x290x80x80", "EN 9 Dia 290 x 200 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "Heat Treatment","CNC Machining",
     "Drilling & Tapping","Quality Check","Store","Assembly"),

    ("NHB120.SPC - 120x210x12.5TL", "EN 9 Dia 210 x 125 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "CNC Machining", None,
     "Quality Check","Store","Assembly", None),

    ("Clamping screw of M16x1.5Px84TL", "EN 24 Dia 75 x 87 MM",
     "Drawing","Raw Material","Cutting","Forging",
     "Conventional Machining","CNC Machining",
     "Quality Check","Store","Assembly", None),

    ("Clamping screw of M20x1.5Px140TL", "EN 24 Dia 75 x 39 MM",
     "Drawing","Raw Material","Cutting","R/Turning",
     "CNC Machining", None,
     "Quality Check","Store","Assembly", None),
]

for item in items_to_add:
    name = item[0]
    mat  = item[1]
    procs= list(item[2:])
    # Pad to 10
    while len(procs) < 10: procs.append(None)
    num_ops = sum(1 for p in procs if p)

    # Check if exists
    cursor.execute("SELECT id FROM process_master WHERE LOWER(TRIM(model_name))=LOWER(TRIM(%s))", (name,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE process_master
            SET material=%s,p1=%s,p2=%s,p3=%s,p4=%s,p5=%s,
                p6=%s,p7=%s,p8=%s,p9=%s,p10=%s,num_operations=%s
            WHERE id=%s
        """, (mat, *procs, num_ops, existing["id"]))
    else:
        cursor.execute("""
            INSERT INTO process_master
            (model_name,material,p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,num_operations)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (name, mat, *procs, num_ops))

print("✅ Process Master updated with all 10 demo items")

# ── Helper functions ──────────────────────────────────────────────────────────
cursor2 = conn.cursor()

def dt(days_offset, hour=9):
    d = TODAY + timedelta(days=days_offset)
    return datetime(d.year, d.month, d.day, hour, 0, 0)

def create_jc(jc_no, so_no, wo_no, so_date_offset, item_name,
              material, qty, wip_status, wip_stage_days,
              total_days, remaining_days, delivery_offset,
              final_status="Pending", remarks=""):
    d_so = TODAY + timedelta(days=so_date_offset)
    d_del= TODAY + timedelta(days=delivery_offset)
    cursor2.execute("""
        INSERT INTO job_cards
        (job_card_no,so_no,work_order_no,so_date,
         job_card_date,final_status,erp_status,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
    """, (jc_no,so_no,wo_no,d_so,d_so,final_status,"Open"))
    cursor2.execute("""
        INSERT INTO job_card_items
        (job_card_no,item_name,material,so_qty,actual_qty,
         wip_status,wip_stage_days,total_days,remaining_days,
         delivery_date,remarks)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (jc_no,item_name,material,qty,qty,
          wip_status,wip_stage_days,total_days,
          remaining_days,d_del,remarks))

def add_proc(jc_no, name, days_planned,
             in_off=None, out_off=None, is_comp=0,
             is_sub=0, vendor=None, lead_days=0,
             sub_start=None, sub_exp=None):
    in_t = dt(in_off)       if in_off  is not None else None
    out_t= dt(out_off, 17)  if out_off is not None else None
    act  = abs(out_off-in_off) if (in_off is not None and out_off is not None) else None
    s_s  = TODAY + timedelta(days=sub_start) if sub_start is not None else None
    s_e  = TODAY + timedelta(days=sub_exp)   if sub_exp   is not None else None
    cursor2.execute("""
        INSERT INTO job_card_process_days
        (job_card_no,process_name,days,is_completed,
         in_time,out_time,actual_days,
         is_subcontract,vendor_name,
         subcontract_lead_days,
         subcontract_start_date,
         subcontract_expected_date)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (jc_no,name,days_planned,is_comp,
          in_t,out_t,act,is_sub,vendor,
          lead_days,s_s,s_e))

def add_audit(jc_no, item, stages):
    for old,new,off in stages:
        cursor2.execute("""
            INSERT INTO audit_trail
            (job_card_no,item_name,old_stage,new_stage,changed_by,changed_at)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (jc_no,item,old,new,"Rajesh Patel",
              TODAY+timedelta(days=off)))

# ── Recreate all 10 demo records ──────────────────────────────────────────────

# D001 — Drawing (fresh, day 2)
create_jc("D001","S44001","WO4401",-2,
    "NHB20 - (OD 90)","EN 9 Dia 90 x 210 MM",
    10,"Drawing",2,35,33,33)
add_proc("D001","Drawing",2,-2,None,0)
add_proc("D001","Raw Material",3)
add_proc("D001","Cutting",5)
add_proc("D001","R/Turning",8)
add_proc("D001","Heat Treatment",5)
add_proc("D001","CNC Machining",7)
add_proc("D001","Quality Check",2)
add_proc("D001","Store",1)
add_proc("D001","Assembly",2)
print("✅ D001 — Drawing stage, Day 2")

# D002 — CNC Machining (on track)
create_jc("D002","S44002","WO4402",-20,
    "NHB35 - 35x110x35","EN 9 Dia 110 x 350 MM",
    6,"CNC Machining",4,35,18,22)
add_proc("D002","Drawing",2,-20,-18,1)
add_proc("D002","Raw Material",3,-18,-15,1)
add_proc("D002","Cutting",4,-15,-11,1)
add_proc("D002","R/Turning",7,-11,-4,1)
add_proc("D002","CNC Machining",8,-4,None,0)
add_proc("D002","Quality Check",2)
add_proc("D002","Store",1)
add_proc("D002","Assembly",2)
add_audit("D002","NHB35 - 35x110x35",[
    ("Pending","Drawing",-20),("Drawing","Raw Material",-18),
    ("Raw Material","Cutting",-15),("Cutting","R/Turning",-11),
    ("R/Turning","CNC Machining",-4)])
print("✅ D002 — CNC Machining, Day 4 (on track)")

# D003 — Heat Treatment subcontract ADVANCE
create_jc("D003","S44003","WO4403",-18,
    "CLS - 40x175","EN 24 Dia 130 x 400 MM",
    4,"Heat Treatment",5,45,22,25)
add_proc("D003","Drawing",2,-18,-16,1)
add_proc("D003","Raw Material",3,-16,-13,1)
add_proc("D003","Cutting",5,-13,-8,1)
add_proc("D003","R/Turning",8,-8,-5,1)
add_proc("D003","Heat Treatment",7,-5,None,0,1,
         "Sharma Heat Treatment Pvt. Ltd.",8,-5,3)
add_proc("D003","CNC Machining",7)
add_proc("D003","Quality Check",2)
add_proc("D003","Store",1)
add_proc("D003","Assembly",2)
add_audit("D003","CLS - 40x175",[
    ("Pending","Drawing",-18),("Drawing","Raw Material",-16),
    ("Raw Material","Cutting",-13),("Cutting","R/Turning",-8),
    ("R/Turning","Heat Treatment",-5)])
print("✅ D003 — Subcontract ADVANCE 🟢 (3d left)")

# D004 — Normalising subcontract ON TIME
create_jc("D004","S44004","WO4404",-22,
    "CLS - 45x140x35","EN 9 Dia 140 x 350 MM",
    8,"Normalising",6,40,14,16)
add_proc("D004","Drawing",2,-22,-20,1)
add_proc("D004","Raw Material",3,-20,-17,1)
add_proc("D004","Cutting",4,-17,-13,1)
add_proc("D004","Forging",5,-13,-8,1)
add_proc("D004","Normalising",6,-6,None,0,1,
         "Metro Heat Process Ltd.",6,-6,0)
add_proc("D004","R/Turning",7)
add_proc("D004","Quality Check",2)
add_proc("D004","Store",1)
add_proc("D004","Assembly",2)
add_audit("D004","CLS - 45x140x35",[
    ("Pending","Drawing",-22),("Drawing","Raw Material",-20),
    ("Raw Material","Cutting",-17),("Cutting","Forging",-13),
    ("Forging","Normalising",-6)])
print("✅ D004 — Subcontract ON TIME 🟡 (due today)")

# D005 — R/Turning subcontract OVERDUE
create_jc("D005","S44005","WO4405",-30,
    "NHB120H - (OD 290)","EN 24 Dia 290 x 320 MM",
    3,"R/Turning",18,50,8,10)
add_proc("D005","Drawing",2,-30,-28,1)
add_proc("D005","Raw Material",3,-28,-25,1)
add_proc("D005","Cutting",5,-25,-20,1)
add_proc("D005","R/Turning",8,-18,None,0,1,
         "Patel Machine Works",7,-18,-11)
add_proc("D005","CNC Machining",7)
add_proc("D005","Drilling & Tapping",4)
add_proc("D005","Quality Check",2)
add_proc("D005","Store",1)
add_proc("D005","Assembly",2)
add_audit("D005","NHB120H - (OD 290)",[
    ("Pending","Drawing",-30),("Drawing","Raw Material",-28),
    ("Raw Material","Cutting",-25),("Cutting","R/Turning",-18)])
print("✅ D005 — Subcontract OVERDUE 🔴 (11d late!)")

# D006 — CNC stuck 22d, only 5d to delivery
create_jc("D006","S44006","WO4406",-35,
    "Coupling Hub - 169.9x285x375TL",
    "EN 24 Dia 285 x 375 MM",
    2,"CNC Machining",22,60,5,7)
add_proc("D006","Drawing",2,-35,-33,1)
add_proc("D006","Raw Material",3,-33,-30,1)
add_proc("D006","Cutting",5,-30,-25,1)
add_proc("D006","Forging",6,-25,-19,1)
add_proc("D006","Normalising",4,-19,-15,1)
add_proc("D006","R/Turning",8,-15,-8,1)
add_proc("D006","CNC Machining",10,-22,None,0)
add_proc("D006","Quality Check",2)
add_proc("D006","Store",1)
add_proc("D006","Assembly",2)
add_audit("D006","Coupling Hub - 169.9x285x375TL",[
    ("Pending","Drawing",-35),("Drawing","Raw Material",-33),
    ("Raw Material","Cutting",-30),("Cutting","Forging",-25),
    ("Forging","Normalising",-19),("Normalising","R/Turning",-15),
    ("R/Turning","CNC Machining",-22)])
print("✅ D006 — Stuck CNC 22d, 7d to delivery ⚠️")

# D007 — Quality Check (almost done)
create_jc("D007","S44007","WO4407",-42,
    "NHB120H - 70x290x80x80","EN 9 Dia 290 x 200 MM",
    5,"Quality Check",1,42,3,5)
add_proc("D007","Drawing",2,-42,-40,1)
add_proc("D007","Raw Material",3,-40,-37,1)
add_proc("D007","Cutting",5,-37,-32,1)
add_proc("D007","R/Turning",8,-32,-24,1)
add_proc("D007","Heat Treatment",5,-24,-19,1)
add_proc("D007","CNC Machining",8,-19,-10,1)
add_proc("D007","Drilling & Tapping",4,-10,-6,1)
add_proc("D007","Quality Check",2,-1,None,0)
add_proc("D007","Store",1)
add_proc("D007","Assembly",2)
add_audit("D007","NHB120H - 70x290x80x80",[
    ("Pending","Drawing",-42),("Drawing","Raw Material",-40),
    ("Raw Material","Cutting",-37),("Cutting","R/Turning",-32),
    ("R/Turning","Heat Treatment",-24),
    ("Heat Treatment","CNC Machining",-19),
    ("CNC Machining","Drilling & Tapping",-10),
    ("Drilling & Tapping","Quality Check",-1)])
print("✅ D007 — Quality Check, 3d to delivery")

# D008 — Completed
create_jc("D008","S44008","WO4408",-50,
    "NHB120.SPC - 120x210x12.5TL",
    "EN 9 Dia 210 x 125 MM",
    12,"Assembly",0,35,0,-2,"Completed")
add_proc("D008","Drawing",2,-50,-48,1)
add_proc("D008","Raw Material",3,-48,-45,1)
add_proc("D008","Cutting",4,-45,-41,1)
add_proc("D008","R/Turning",6,-41,-35,1)
add_proc("D008","CNC Machining",7,-35,-28,1)
add_proc("D008","Quality Check",2,-28,-26,1)
add_proc("D008","Store",1,-26,-25,1)
add_proc("D008","Assembly",2,-25,-23,1)
print("✅ D008 — Completed ✅")

# D009 — 2 subcontracts
create_jc("D009","S44009","WO4409",-25,
    "Clamping screw of M16x1.5Px84TL",
    "EN 24 Dia 75 x 87 MM",
    15,"Conventional Machining",8,45,14,16)
add_proc("D009","Drawing",2,-25,-23,1)
add_proc("D009","Raw Material",3,-23,-20,1)
add_proc("D009","Cutting",4,-20,-16,1)
add_proc("D009","Forging",5,-16,-10,1,1,
         "Gujarat Forge Ltd.",5,-16,-11)
add_proc("D009","Conventional Machining",8,-8,None,0,1,
         "Shah Engineering Works",10,-8,2)
add_proc("D009","CNC Machining",6)
add_proc("D009","Quality Check",2)
add_proc("D009","Store",1)
add_proc("D009","Assembly",2)
add_audit("D009","Clamping screw of M16x1.5Px84TL",[
    ("Pending","Drawing",-25),("Drawing","Raw Material",-23),
    ("Raw Material","Cutting",-20),("Cutting","Forging",-16),
    ("Forging","Conventional Machining",-8)])
print("✅ D009 — 2 subcontracts (Forging done + Conv.Mach advance)")

# D010 — Pending (not started)
create_jc("D010","S44010","WO4410",-1,
    "Clamping screw of M20x1.5Px140TL",
    "EN 24 Dia 75 x 39 MM",
    20,"Pending",0,40,40,39)
add_proc("D010","Drawing",2)
add_proc("D010","Raw Material",3)
add_proc("D010","Cutting",5)
add_proc("D010","R/Turning",8)
add_proc("D010","CNC Machining",7)
add_proc("D010","Quality Check",2)
add_proc("D010","Store",1)
add_proc("D010","Assembly",2)
print("✅ D010 — Pending, not started yet")

conn.commit()
cursor.close()
cursor2.close()
conn.close()

print(f"""
{"="*65}
ALL FIXED! Summary:
{"="*65}
- Old records 110001-110010 and DEMO001 deleted
- Process Master updated with correct processes
- All 10 demo records recreated with correct stages
- Quality Check + Store + Assembly added to all items

Fetch these on Page 3 to demo:
  D003 → Heat Treatment yellow pill 🟢 ADVANCE
  D004 → Normalising yellow pill   🟡 ON TIME
  D005 → R/Turning yellow pill     🔴 OVERDUE (most critical)
  D006 → CNC stuck 22d, 7d left    ⚠️  URGENT
  D007 → Quality Check, almost done
  D008 → Completed order
{"="*65}
""")
# NMTG JMS — Session Handoff (2026-09-22)

## Who you are talking to
Jinal DipakKumar Prajapati, Executive Director at NMTG Mechtrans Techniques Pvt. Ltd.
Prefers direct, fast style. First propose a plan and wait for approval before doing work.
For code changes: give one step at a time, wait for confirmation. Never regenerate whole files, deliver find-and-replace patches.
All code runs on the SERVER (C:\Users\Admin\Desktop\Het\demo2) via PowerShell — not on his laptop, not in a terminal on cloud. He pastes commands into the server's PowerShell window.
Backend: Flask + MySQL 8.0. Database jms_demo2, user root, password admin@123, host 127.0.0.1.

## Big picture — what we've been doing today
1. Migrated the OEE module from D:\Het\demo2 (Het's laptop) to C:\Users\Admin\Desktop\Het\demo2 (server). Done.
2. Made OEE dashboards default to "Today" filter. Done.
3. Bypassed the -C child gate for OEE terminal completions so OEE entries don't get blocked. Done.
4. Wiped today's OEE test data. Done.
5. Restored login_activity + material planning modules from PRE_FULL_PUSH backup. Done.
6. Bulk-advanced ~227 job cards to specific stages from a customer Excel file (Pending_Export_JC_With_DPR_Production_1.xlsx). IN PROGRESS — 218 of 227 landed, 9 missing, some timestamps landed in the future.

## Current problem — the JC advancement is 96% done
- CSV had 283 rows, 250 matched to actual process names in job_card_process_days, 227 needed advancement (23 were already at target), 33 held for review.
- SQL script executed and advanced 218 distinct JCs. Missing 9.
- BIG BUG: some randomized timestamps landed on Sept 23 and Sept 24 (future dates). Today is Sept 22. Need to clamp all changed_at / in_time / out_time / end_date to <= today.
- audit_trail split: Abhishek 177, Parth 84. Roughly 2:1 (the random function skewed).

## What must happen next (in order)
### Step A: Clamp future-dated rows to today
Look for audit_trail rows where changed_by IN ('Abhishek','Parth') AND DATE(changed_at) > CURDATE() — set changed_at to a random time today.
Look for job_card_process_days rows where DATE(in_time) > CURDATE() or DATE(out_time) > CURDATE() or end_date > CURDATE() (for rows touched in the advancement window) — clamp them.

### Step B: Find and advance the missing 9 JCs
The MATCHED CSV is at C:\Users\Admin\Desktop\pending_MATCHED.csv on the server. It has 250 rows (columns: DATE, QTY, SETUP, JOB_CARD_NO). 227 needed advancement.
Query the 218 that already landed via audit_trail. Diff against the CSV to find the 9 missing JCs. Regenerate the delta SQL for just those 9 with timestamps <= today, run it.

### Step C: Verify
Spot check 5 JCs from the CSV — their wip_status in job_card_items must match the SETUP column.

### Step D: Then we go to OEE charts
Machine Losses (No JC) chart and Tooling Activity chart on the OEE Dashboard. Tool Room + Development chart in the next session.

## The advancement pattern (for reference)
For each JC + target-stage pair from CSV:
1. Look up target process id in job_card_process_days for that JC + process name.
2. UPDATE all job_card_process_days rows for that JC with id < target_id, set is_completed=1, out_time=random datetime, end_date=DATE(datetime). (Chain-complete preceding stages.)
3. UPDATE the target row: set in_time=random datetime near CSV DATE. Leave is_completed=0.
4. UPDATE job_card_items SET wip_status='<target process name>' WHERE job_card_no.
5. INSERT into audit_trail (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at) — changed_by random Abhishek or Parth, changed_at random near CSV DATE.

## Rules Jinal has stated
- JC numbers are stored 10-char with leading zeros (0000nnnnnn). Excel strips them — always Normalize-JC.
- Timestamps must be randomized across days near the CSV DATE (± 2 days), never all one moment. Hours 8-17. **NEVER future-dated — cap at today.**
- changed_by must be split between Abhishek and Parth, roughly 50/50 (currently skewed 68/32 — acceptable but the delta 9 should balance it).
- CHILD_C_GATE bypass for OEE completions is patched in quality_check.py line 2806.
- OEE dashboard + summary default to "Today".
- Zone logins (zonea..zonee) redirect to /oee-machine/operator after login.

## Server file paths
- App root: C:\Users\Admin\Desktop\Het\demo2
- MySQL: C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe
- Backup taken before advancement: C:\Users\Admin\Desktop\jms_demo2_BEFORE_JC_ADVANCE_<timestamp>.sql
- SQL script that ran: C:\Users\Admin\Desktop\advance_JCs.sql
- Matched CSV: C:\Users\Admin\Desktop\pending_MATCHED.csv
- Unmatched CSV: C:\Users\Admin\Desktop\pending_UNMATCHED.csv

## MySQL query pattern to give Jinal
Always this shape (he pastes it in server PowerShell):
```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' -h 127.0.0.1 -u root -padmin@123 -t jms_demo2 -e "SELECT ..."
```
For multi-statement scripts, write SQL to file and:
```powershell
Get-Content C:\Users\Admin\Desktop\file.sql -Raw | & 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' -h 127.0.0.1 -u root -padmin@123 --default-character-set=utf8mb4 jms_demo2
```

## People
- Het — lead developer at NMTG, whose laptop D:\Het\demo2 was the source.
- Abhishek and Parth — operators/entry users. Their user ids: Abhishek=11, Parth=13.

## Guardrails
- Never damage the DB. Backup before destructive changes.
- Never send whole-file rewrites. Only find-and-replace patches.
- Give ONE step at a time. Wait for confirmation.
- No em dashes. No "Certainly!" / "Absolutely!" openers.

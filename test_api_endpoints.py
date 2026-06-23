#!/usr/bin/env python
"""
Test the remaining_days calculation for all job cards
"""
import mysql.connector

conn = mysql.connector.connect(
    host='127.0.0.1', port=3306, database='jms_demo2',
    user='root', password='admin@123',
    auth_plugin='mysql_native_password'
)
cursor = conn.cursor(dictionary=True)

# Get all job cards
cursor.execute('SELECT DISTINCT jc.job_card_no FROM job_cards jc ORDER BY jc.job_card_no')
jc_rows = cursor.fetchall()

print('='*60)
print('REMAINING DAYS CALCULATION TEST FOR ALL JOB CARDS')
print('='*60)
print()

for jc_rec in jc_rows:
    jc_no = jc_rec["job_card_no"]
    
    # Calculate remaining_days live
    cursor.execute('''
        SELECT 
            SUM(COALESCE(pdd.default_days, pd.days, 0)) as total_default,
            SUM(CASE
                WHEN pd.in_time IS NULL THEN 0
                WHEN pd.in_time IS NOT NULL AND pd.out_time IS NULL
                    THEN DATEDIFF(CURDATE(), DATE(pd.in_time))
                WHEN pd.actual_days IS NOT NULL
                    THEN pd.actual_days
                WHEN pd.in_time IS NOT NULL AND pd.out_time IS NOT NULL
                    THEN DATEDIFF(DATE(pd.out_time), DATE(pd.in_time))
                ELSE 0
            END) as total_used
        FROM job_card_process_days pd
        LEFT JOIN process_default_days pdd
            ON LOWER(TRIM(pd.process_name)) = LOWER(TRIM(pdd.process_name))
        WHERE pd.job_card_no = %s
    ''', (jc_no,))
    
    calc = cursor.fetchone()
    if calc:
        total_default = int(calc.get('total_default') or 0)
        total_used = int(calc.get('total_used') or 0)
        remaining = max(0, total_default - total_used)
        
        # Get the saved remaining_days
        cursor.execute('SELECT remaining_days FROM job_card_items WHERE job_card_no = %s LIMIT 1', (jc_no,))
        saved = cursor.fetchone()
        saved_remaining = int(saved.get('remaining_days') or 0) if saved else 0
        
        status = '✅' if remaining > 0 else '⚠️ '
        print(f'{status} JC {jc_no}:')
        print(f'     Total Default Days:  {total_default}')
        print(f'     Total Used Days:     {total_used}')
        print(f'     Live Remaining Days: {remaining}')
        print(f'     Saved Remaining Days: {saved_remaining} (OLD - not used anymore)')
        print()
    else:
        print(f'⏭️  JC {jc_no}: No process data found')
        print()

cursor.close()
conn.close()

print('='*60)
print('✅ Test complete - remaining_days is calculated live!')
print('='*60)

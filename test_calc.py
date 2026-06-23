#!/usr/bin/env python
import mysql.connector

conn = mysql.connector.connect(
    host='127.0.0.1', port=3306, database='jms_demo2',
    user='root', password='admin@123',
    auth_plugin='mysql_native_password'
)
cursor = conn.cursor(dictionary=True)

# Get available job cards
cursor.execute('SELECT DISTINCT jc.job_card_no FROM job_cards jc ORDER BY jc.job_card_no')
rows = cursor.fetchall()
print('Available Job Cards:')
for r in rows:
    print(f'  {r["job_card_no"]}')

# Test calculation for the first job card
if rows:
    test_jc = rows[0]["job_card_no"]
    print(f'\nTesting calculation for {test_jc}:')
    
    cursor.execute('''
        SELECT 
            jc.job_card_no,
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
        FROM job_cards jc
        JOIN job_card_process_days pd ON jc.job_card_no = pd.job_card_no
        LEFT JOIN process_default_days pdd
            ON LOWER(TRIM(pd.process_name)) = LOWER(TRIM(pdd.process_name))
        WHERE jc.job_card_no = %s
        GROUP BY jc.job_card_no
    ''', (test_jc,))
    
    result = cursor.fetchone()
    if result:
        total_default = int(result.get('total_default') or 0)
        total_used = int(result.get('total_used') or 0)
        remaining = max(0, total_default - total_used)
        print(f'  Total Default Days: {total_default}')
        print(f'  Total Used Days: {total_used}')
        print(f'  Remaining Days: {remaining}')
    else:
        print(f'  No process data found for {test_jc}')

cursor.close()
conn.close()

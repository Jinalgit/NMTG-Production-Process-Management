-- ============================================================
-- Add process days table and remaining days column
-- Run this ONCE on jms_demo2 database
-- ============================================================

USE jms_demo2;

-- New table to store individual process days per job card
CREATE TABLE IF NOT EXISTS job_card_process_days (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    job_card_no VARCHAR(50) NOT NULL,
    process_name VARCHAR(100) NOT NULL,
    days        INT DEFAULT 0,
    is_completed TINYINT DEFAULT 0,
    FOREIGN KEY (job_card_no) REFERENCES job_cards(job_card_no)
);

-- Add remaining_days column to job_card_items
ALTER TABLE job_card_items
ADD COLUMN IF NOT EXISTS remaining_days INT DEFAULT 0;

-- ============================================================
-- Insert process days for 5 existing job cards
-- ============================================================

-- JC 108553 — SHAFT OF HYDRAULIC MOTOR — Total: 50
INSERT INTO job_card_process_days (job_card_no, process_name, days, is_completed) VALUES
('108553', 'Drawing',       18, 1),
('108553', 'RM',            10, 1),
('108553', 'Cutting',       22, 0),
('108553', 'R/Turning',      0, 0),
('108553', 'Heat Treatment', 0, 0),
('108553', 'CNC Machining',  0, 0);

UPDATE job_card_items SET remaining_days = 50 WHERE job_card_no = '108553';

-- JC 108565 — SHAFT OF OVERRUNNING CLUTCH — Total: 51
INSERT INTO job_card_process_days (job_card_no, process_name, days, is_completed) VALUES
('108565', 'Drawing',       18, 1),
('108565', 'RM',            10, 1),
('108565', 'Cutting',       23, 1),
('108565', 'R/Turning',      0, 0),
('108565', 'Heat Treatment', 0, 0),
('108565', 'CNC Machining',  0, 0);

-- CNC is current WIP so remaining = 51 - 18 - 10 - 23 = 0 (cutting done)
UPDATE job_card_items SET remaining_days = 0 WHERE job_card_no = '108565';

-- JC 108568 — FLANGE WITH INTERNAL SPLINE — Total: 51
INSERT INTO job_card_process_days (job_card_no, process_name, days, is_completed) VALUES
('108568', 'Drawing',   18, 0),
('108568', 'RM',        10, 0),
('108568', 'Cutting',   23, 0),
('108568', 'R/Turning',  0, 0),
('108568', 'CNC Machining', 0, 0);

UPDATE job_card_items SET remaining_days = 51 WHERE job_card_no = '108568';

-- JC 108567 — FLANGE BET HYD MOTOR — Total: 51
INSERT INTO job_card_process_days (job_card_no, process_name, days, is_completed) VALUES
('108567', 'Drawing',   18, 0),
('108567', 'RM',        10, 0),
('108567', 'Cutting',   23, 0),
('108567', 'R/Turning',  0, 0),
('108567', 'CNC Machining', 0, 0);

UPDATE job_card_items SET remaining_days = 51 WHERE job_card_no = '108567';

-- JC 108850 — SHRINK DISC — Total: 40
INSERT INTO job_card_process_days (job_card_no, process_name, days, is_completed) VALUES
('108850', 'Drawing',       17, 1),
('108850', 'Cutting',        2, 1),
('108850', 'Forging',        1, 1),
('108850', 'Normalising',   20, 1),
('108850', 'R/Turning',      0, 1),
('108850', 'Heat Treatment', 0, 1),
('108850', 'CNC Machining',  0, 1),
('108850', 'OD Grinding',    0, 1);

-- Store means all done, remaining = 0
UPDATE job_card_items SET remaining_days = 0 WHERE job_card_no = '108850';

SELECT 'Process days inserted successfully' AS status;

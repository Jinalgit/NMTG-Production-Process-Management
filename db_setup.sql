-- ============================================================
-- DEMO 2 — JOB CARD MANAGEMENT SYSTEM
-- Run this once to create the database and all tables
-- ============================================================

DROP DATABASE IF EXISTS jms_demo2;
CREATE DATABASE jms_demo2;
USE jms_demo2;

-- ============================================================
-- TABLE 1: process_master
-- Stores all items with their material and processes
-- ============================================================
CREATE TABLE process_master (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    model_name     VARCHAR(500) NOT NULL,
    material       VARCHAR(255),
    part_name      VARCHAR(255),
    p1  VARCHAR(100), p2  VARCHAR(100), p3  VARCHAR(100), p4  VARCHAR(100),
    p5  VARCHAR(100), p6  VARCHAR(100), p7  VARCHAR(100), p8  VARCHAR(100),
    num_operations INT DEFAULT 0,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 2: supervisors
-- ============================================================
CREATE TABLE supervisors (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

-- ============================================================
-- TABLE 3: job_cards
-- Main job card header — no prefixes on job_card_no
-- ============================================================
CREATE TABLE job_cards (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    job_card_no   VARCHAR(50) UNIQUE NOT NULL,
    so_no         VARCHAR(50),
    customer_name VARCHAR(255),
    work_order_no VARCHAR(50),
    parent_code   VARCHAR(50),
    so_date       DATE,
    job_card_date DATE,
    work_order_date DATE,
    child_code    VARCHAR(100),
    final_status  VARCHAR(50) DEFAULT 'Pending',
    erp_status    VARCHAR(50) DEFAULT 'Open',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 4: job_card_items
-- One row per item in a job card
-- ============================================================
CREATE TABLE job_card_items (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    job_card_no    VARCHAR(50) NOT NULL,
    item_name      VARCHAR(500) NOT NULL,
    material       VARCHAR(255),
    so_qty         INT,
    job_card_qty   INT,
    advance_stock  VARCHAR(100),
    actual_qty     INT DEFAULT 0,
    rejected_qty   INT NULL,
    wip_status     VARCHAR(100) DEFAULT 'Pending',
    wip_stage_days INT DEFAULT 0,
    total_days     INT DEFAULT 0,
    delivery_date  DATE NOT NULL,
    remarks        VARCHAR(500),
    FOREIGN KEY (job_card_no) REFERENCES job_cards(job_card_no)
);

-- ============================================================
-- TABLE 5: quality_checks
-- Header for each quality check session
-- ============================================================
CREATE TABLE quality_checks (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    job_card_no VARCHAR(50) NOT NULL,
    checked_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_card_no) REFERENCES job_cards(job_card_no)
);

-- ============================================================
-- TABLE 6: quality_check_details
-- One row per process checked per item
-- ============================================================
CREATE TABLE quality_check_details (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    quality_check_id  INT NOT NULL,
    item_name         VARCHAR(500),
    actual_qty        INT,
    rejected_qty      INT NULL,
    process_name      VARCHAR(100),
    quality_result    ENUM('OK', 'NOT OK'),
    supervisor        VARCHAR(100),
    FOREIGN KEY (quality_check_id) REFERENCES quality_checks(id)
);

-- ============================================================
-- TABLE 7: audit_trail
-- Logs every WIP stage change with supervisor and timestamp
-- ============================================================
CREATE TABLE audit_trail (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    job_card_no  VARCHAR(50) NOT NULL,
    item_name    VARCHAR(500),
    old_stage    VARCHAR(100),
    new_stage    VARCHAR(100),
    changed_by   VARCHAR(100),
    changed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SAMPLE DATA: supervisors
-- ============================================================
INSERT INTO supervisors (name) VALUES
    ('Rajesh Patel'),
    ('Suresh Shah'),
    ('Mahesh Mehta'),
    ('Dinesh Kumar'),
    ('Ramesh Joshi');

-- ============================================================
-- VERIFICATION
-- ============================================================
SELECT 'Tables created successfully' AS status;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'jms_demo2';

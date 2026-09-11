-- ============================================================================
-- NMTG BOM & Process Schema  ·  MySQL 8.0+
-- Run once on jms_demo2. Existing process_master table is NOT touched.
-- ============================================================================

-- 1. PROCESSES  ─  lookup table (~30 rows)
--    Single source of truth for process names. No typos, easy reporting.
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    process_name    VARCHAR(100)    NOT NULL,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_process_name (process_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 2. ITEMS  ─  master table for every part / assembly / raw material (~15,600 rows)
--    One row per item code. Description, type, material, size live here.
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS items (
    item_code       VARCHAR(30)     NOT NULL PRIMARY KEY,
    item_description VARCHAR(500)   NULL,
    item_type       ENUM('ASSEMBLY','PART','RAW_MATERIAL')  DEFAULT 'PART',
    make_default    ENUM('A','I')   NULL        COMMENT 'Default make/buy flag',
    material        VARCHAR(255)    NULL,
    size            VARCHAR(100)    NULL,
    part_name       VARCHAR(255)    NULL,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_item_desc (item_description(100)),
    INDEX idx_item_type (item_type),
    INDEX idx_item_material (material)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 3. BOM_LINKS  ─  every parent → child edge (~29,200 rows)
--    The entire tree lives here. One row per relationship.
--    make_buy is per-link (same part can be A for one parent, I for another).
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bom_links (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    parent_code     VARCHAR(30)     NOT NULL,
    child_code      VARCHAR(30)     NOT NULL,
    sr_no           INT             NULL        COMMENT 'Sequence within parent',
    make_buy        ENUM('A','I')   NULL        COMMENT 'Override per relationship',
    quantity        DECIMAL(10,3)   DEFAULT 1.000,
    uom             VARCHAR(20)     DEFAULT 'NOS',
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_parent_child (parent_code, child_code),
    INDEX idx_child (child_code),
    INDEX idx_parent (parent_code),

    CONSTRAINT fk_bom_parent FOREIGN KEY (parent_code) REFERENCES items(item_code)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_bom_child  FOREIGN KEY (child_code)  REFERENCES items(item_code)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 4. ITEM_PROCESSES  ─  normalized routing, one row per step (~45,000 rows)
--    Replaces p1–p25 columns. No column limit, easy to query by process.
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS item_processes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    item_code       VARCHAR(30)     NOT NULL,
    step_no         INT             NOT NULL    COMMENT '1, 2, 3… sequence',
    process_id      INT             NOT NULL,
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_item_step (item_code, step_no),
    INDEX idx_ip_process (process_id),

    CONSTRAINT fk_ip_item    FOREIGN KEY (item_code)  REFERENCES items(item_code)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ip_process FOREIGN KEY (process_id) REFERENCES processes(id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- USEFUL VIEWS  (optional but handy for quick queries)
-- ============================================================================

-- View: item with its processes as comma-separated string (like the old p1,p2… but dynamic)
CREATE OR REPLACE VIEW v_item_routing AS
SELECT
    i.item_code,
    i.item_description,
    i.item_type,
    i.material,
    i.size,
    GROUP_CONCAT(p.process_name ORDER BY ip.step_no SEPARATOR ' → ') AS routing
FROM items i
LEFT JOIN item_processes ip ON ip.item_code = i.item_code
LEFT JOIN processes p       ON p.id = ip.process_id
GROUP BY i.item_code, i.item_description, i.item_type, i.material, i.size;


-- View: top-level assemblies (items that are parents but never children)
CREATE OR REPLACE VIEW v_top_assemblies AS
SELECT i.*
FROM items i
WHERE i.item_code IN (SELECT DISTINCT parent_code FROM bom_links)
  AND i.item_code NOT IN (SELECT DISTINCT child_code FROM bom_links);


-- Example: recursive CTE to explode full BOM for any assembly
-- Usage: replace 'NAVDS0000001' with any parent code
--
-- WITH RECURSIVE bom_tree AS (
--     SELECT item_code, item_description, item_code AS root, 0 AS depth
--     FROM items WHERE item_code = 'NAVDS0000001'
--     UNION ALL
--     SELECT i.item_code, i.item_description, bt.root, bt.depth + 1
--     FROM bom_tree bt
--     JOIN bom_links bl ON bl.parent_code = bt.item_code
--     JOIN items i      ON i.item_code = bl.child_code
--     WHERE bt.depth < 15
-- )
-- SELECT * FROM bom_tree ORDER BY depth, item_code;
PAGE5_PPC = "page5_ppc"
PAGE3_TRACEABILITY = "page3_traceability"

PAGE5_BASE_FIELDS = {
    "job_card_no",
    "so_no",
    "customer_name",
    "work_order_no",
    "parent_code",
    "child_code",
    "item_name",
    "material",
    "so_qty",
}

PROCESS_FIELDS = {
    "actual_qty",
    "remarks",
    "vendor_name",
    "subcontractor_name",
}


def ensure_permission_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_field_permissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            page_name VARCHAR(100) NOT NULL,
            field_name VARCHAR(100) NOT NULL,
            can_view TINYINT DEFAULT 1,
            can_edit TINYINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_page_field (user_id, page_name, field_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_page_permissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            page_name VARCHAR(100) NOT NULL,
            can_access TINYINT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_page (user_id, page_name)
        )
    """)


def seed_default_permissions(cursor):
    supervisor_fields = [
        (PAGE3_TRACEABILITY, "actual_qty"),
        (PAGE3_TRACEABILITY, "remarks"),
        (PAGE3_TRACEABILITY, "vendor_name"),
        (PAGE5_PPC, "actual_qty"),
        (PAGE5_PPC, "remarks"),
        (PAGE5_PPC, "vendor_name"),
        (PAGE5_PPC, "subcontractor_name"),
    ]
    for page_name, field_name in supervisor_fields:
        cursor.execute("""
            INSERT IGNORE INTO user_field_permissions
                (user_id, page_name, field_name, can_view, can_edit)
            SELECT id, %s, %s, 1, 1
            FROM users
            WHERE role = 'supervisor'
        """, (page_name, field_name))

    for field_name in sorted(PAGE5_BASE_FIELDS):
        cursor.execute("""
            INSERT IGNORE INTO user_field_permissions
                (user_id, page_name, field_name, can_view, can_edit)
            SELECT id, %s, %s, 1, 1
            FROM users
            WHERE LOWER(TRIM(username)) = 'gaurang'
        """, (PAGE5_PPC, field_name))


def has_process_access(cursor, user_id, process_name):
    cursor.execute("""
        SELECT 1
        FROM supervisor_process_access
        WHERE user_id = %s
          AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
        LIMIT 1
    """, (user_id, process_name or ""))
    return cursor.fetchone() is not None


def has_field_edit_access(cursor, user_id, page_name, field_name):
    cursor.execute("""
        SELECT 1
        FROM user_field_permissions
        WHERE user_id = %s
          AND page_name = %s
          AND field_name = %s
          AND can_edit = 1
        LIMIT 1
    """, (user_id, page_name, field_name))
    return cursor.fetchone() is not None


def can_user_edit_field(cursor, role, user_id, page_name, field_name):
    role = (role or "").strip().lower()
    if role == "admin":
        return True
    if role == "operator":
        return False
    if role == "supervisor":
        return has_field_edit_access(cursor, user_id, page_name, field_name)
    return False

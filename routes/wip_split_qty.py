"""
Quantity-level WIP support.

SPLIT_QTY_WIP_V1

This module allows one Job Card item quantity to exist across
multiple process stages at the same time.

Example:
    JC Qty = 50

    CNC Machining 1st Side = 25
    CNC Machining 2nd Side = 25

The existing job_card_items.wip_status remains available for
legacy compatibility. Quantity-level stage state is maintained
separately.
"""


def ensure_split_qty_tables(cursor):
    """
    Create the quantity-level WIP tables when the feature is enabled.

    No table is created merely by importing this module.
    """

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS job_card_stage_qty (
            id BIGINT NOT NULL AUTO_INCREMENT,

            job_card_item_id INT NOT NULL,
            job_card_no VARCHAR(50) NOT NULL,
            process_name VARCHAR(100) NOT NULL,

            qty_available INT NOT NULL DEFAULT 0,
            qty_hold INT NOT NULL DEFAULT 0,
            qty_rejected INT NOT NULL DEFAULT 0,
            qty_moved_out INT NOT NULL DEFAULT 0,

            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL
                DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            PRIMARY KEY (id),

            UNIQUE KEY uq_jc_stage_qty (
                job_card_item_id,
                process_name
            ),

            INDEX idx_jc_stage_qty_job (
                job_card_no
            ),

            INDEX idx_jc_stage_qty_process (
                process_name,
                qty_available
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS job_card_qty_movements (
            id BIGINT NOT NULL AUTO_INCREMENT,

            job_card_item_id INT NOT NULL,
            job_card_no VARCHAR(50) NOT NULL,

            from_process VARCHAR(100) NOT NULL,
            to_process VARCHAR(100) NULL,

            qty_moved INT NOT NULL DEFAULT 0,
            qty_rejected INT NOT NULL DEFAULT 0,
            qty_hold INT NOT NULL DEFAULT 0,
            qty_pending_after INT NOT NULL DEFAULT 0,

            source_type VARCHAR(50) NULL,
            source_id BIGINT NULL,

            changed_by_user_id INT NULL,
            changed_by VARCHAR(100) NULL,
            remarks VARCHAR(500) NULL,

            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (id),

            INDEX idx_jc_qty_move_job (
                job_card_no,
                job_card_item_id
            ),

            INDEX idx_jc_qty_move_from (
                from_process
            ),

            INDEX idx_jc_qty_move_to (
                to_process
            ),

            INDEX idx_jc_qty_move_source (
                source_type,
                source_id
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
        """
    )


def get_stage_quantities(cursor, job_card_item_id):
    """
    Return quantity state for every process belonging to one JC item.
    """

    cursor.execute(
        """
        SELECT
            process_name,
            qty_available,
            qty_hold,
            qty_rejected,
            qty_moved_out
        FROM job_card_stage_qty
        WHERE job_card_item_id = %s
        ORDER BY id
        """,
        (job_card_item_id,),
    )

    rows = cursor.fetchall()

    return {
        str(row.get("process_name") or "").strip().lower(): row
        for row in rows
    }


def seed_stage_quantity(
    cursor,
    *,
    job_card_item_id,
    job_card_no,
    process_name,
    initial_qty,
):
    """
    Seed the first quantity balance for an existing JC.

    Safe to call repeatedly. Existing stage quantity is not reset.
    """

    initial_qty = int(initial_qty or 0)

    if initial_qty < 0:
        raise ValueError("Initial stage quantity cannot be negative.")

    cursor.execute(
        """
        INSERT INTO job_card_stage_qty
        (
            job_card_item_id,
            job_card_no,
            process_name,
            qty_available
        )
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            job_card_no = VALUES(job_card_no)
        """,
        (
            job_card_item_id,
            job_card_no,
            process_name,
            initial_qty,
        ),
    )


def move_stage_quantity(
    cursor,
    *,
    job_card_item_id,
    job_card_no,
    from_process,
    to_process,
    ok_qty,
    rejected_qty=0,
    hold_qty=0,
    reject_process=None,
    initial_available_qty=None,
    source_type=None,
    source_id=None,
    changed_by_user_id=None,
    changed_by=None,
    remarks=None,
):
    """
    Move only the submitted quantity to the next process.

    OK Qty      -> next process
    Rejected    -> removed from forward WIP, retained in history
    Hold        -> retained against current process
    Remaining   -> stays available at current process
    """

    ok_qty = int(ok_qty or 0)
    rejected_qty = int(rejected_qty or 0)
    hold_qty = int(hold_qty or 0)

    if min(ok_qty, rejected_qty, hold_qty) < 0:
        raise ValueError("Split quantities cannot be negative.")

    # REJECT_AT_PROCESS_V1
    # Combined Setup: rejected pieces belong to the operation
    # where they were actually scrapped, not to the operation
    # the run started at.
    #
    # reject_process=None reproduces the legacy behaviour.
    reject_target_process = (
        str(reject_process or "").strip()
        or str(from_process or "").strip()
    )

    reject_on_source = (
        reject_target_process.strip().lower()
        == str(from_process or "").strip().lower()
    )

    if initial_available_qty is not None:
        seed_stage_quantity(
            cursor,
            job_card_item_id=job_card_item_id,
            job_card_no=job_card_no,
            process_name=from_process,
            initial_qty=int(initial_available_qty or 0),
        )

    cursor.execute(
        """
        SELECT
            id,
            qty_available,
            qty_hold,
            qty_rejected,
            qty_moved_out
        FROM job_card_stage_qty
        WHERE job_card_item_id = %s
          AND LOWER(TRIM(process_name)) =
              LOWER(TRIM(%s))
        LIMIT 1
        FOR UPDATE
        """,
        (
            job_card_item_id,
            from_process,
        ),
    )

    source_row = cursor.fetchone()

    if not source_row:
        raise ValueError(
            "No quantity balance exists for the current process."
        )

    available_before = (
        int(source_row.get("qty_available") or 0)
        + int(source_row.get("qty_hold") or 0)
    )

    consumed_qty = (
        ok_qty
        + rejected_qty
        + hold_qty
    )

    if consumed_qty > available_before:
        raise ValueError(
            "Split quantity exceeds the quantity available "
            f"at '{from_process}'. "
            f"Available={available_before}, "
            f"submitted={consumed_qty}."
        )

    pending_after = (
        available_before
        - consumed_qty
    )

    cursor.execute(
        """
        UPDATE job_card_stage_qty
        SET qty_available = %s,
            qty_hold = %s,
            qty_rejected = qty_rejected + %s,
            qty_moved_out = qty_moved_out + %s
        WHERE id = %s
        """,
        (
            pending_after,
            hold_qty,
            (
                rejected_qty
                if reject_on_source
                else 0
            ),
            ok_qty,
            source_row["id"],
        ),
    )

    # REJECT_AT_PROCESS_V1_POST
    # Scrap reported against a later operation of the same
    # combined setup is booked on that operation's own row.
    if (
        rejected_qty > 0
        and not reject_on_source
    ):
        cursor.execute(
            """
            INSERT INTO job_card_stage_qty
            (
                job_card_item_id,
                job_card_no,
                process_name,
                qty_available,
                qty_rejected
            )
            VALUES (%s, %s, %s, 0, %s)
            ON DUPLICATE KEY UPDATE
                qty_rejected =
                    qty_rejected + VALUES(qty_rejected),
                job_card_no =
                    VALUES(job_card_no)
            """,
            (
                job_card_item_id,
                job_card_no,
                reject_target_process,
                rejected_qty,
            ),
        )

    if ok_qty > 0 and to_process:
        cursor.execute(
            """
            INSERT INTO job_card_stage_qty
            (
                job_card_item_id,
                job_card_no,
                process_name,
                qty_available
            )
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                qty_available =
                    qty_available + VALUES(qty_available),
                job_card_no =
                    VALUES(job_card_no)
            """,
            (
                job_card_item_id,
                job_card_no,
                to_process,
                ok_qty,
            ),
        )

    cursor.execute(
        """
        INSERT INTO job_card_qty_movements
        (
            job_card_item_id,
            job_card_no,
            from_process,
            to_process,
            reject_process,
            qty_moved,
            qty_rejected,
            qty_hold,
            qty_pending_after,
            source_type,
            source_id,
            changed_by_user_id,
            changed_by,
            remarks
        )
        VALUES
        (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        """,
        (
            job_card_item_id,
            job_card_no,
            from_process,
            to_process,
            (
                reject_target_process
                if rejected_qty > 0
                else None
            ),
            ok_qty,
            rejected_qty,
            hold_qty,
            pending_after,
            source_type,
            source_id,
            changed_by_user_id,
            changed_by,
            remarks,
        ),
    )

    return {
        "from_process": from_process,
        "to_process": to_process,
        "moved_qty": ok_qty,
        "rejected_qty": rejected_qty,
        "reject_process": (
            reject_target_process
            if rejected_qty > 0
            else None
        ),
        "hold_qty": hold_qty,
        "pending_qty": pending_after,
    }

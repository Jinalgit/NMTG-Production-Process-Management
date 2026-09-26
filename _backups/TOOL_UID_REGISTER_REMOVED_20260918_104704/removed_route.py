@quality_check_bp.route(
    "/oee-tool-uid-register",
    methods=["GET"]
)
def machine_oee_tool_uid_register_page_v115():

    if not _can_access_tool_uid_register():
        return ("Access denied: Tool UID Register is only available to CNC/VMC supervisors.", 403)
    from flask import render_template

    role = str(
        session.get("role")
        or ""
    ).strip().lower()


    if role not in (
        "admin",
        "supervisor",
        "plant_head",
    ):

        return (
            "This page is available only "
            "for Admin and Supervisor.",
            403
        )


    return render_template(
        "oee_tool_uid_register.html",
        active_page="oee_tool_uid_register",
    )


# OEE_TOOL_UID_REGISTER_PAGE_V115_END


# =========================================================
# OEE_TOOL_MASTER_LIST_API_V126
# Read-only listing of oee_tool_master rows for Admin/Supervisor.
# =========================================================


from functools import wraps
from flask import jsonify, redirect, session, url_for
from permission_utils import is_gaurang_special_user


PAGE_ACCESS = {
    "page1": {
        "admin": "full",
        "supervisor": "full",
        "operator": "create",
    },
    "page2": {
        "admin": "full",
        "supervisor": "full",
        "operator": "full",
    },
    "page3": {
        "admin": "full",
        "supervisor": "full",
        "operator": "read",
    },
    "page4": {
        "admin": "full",
        "supervisor": "full",
    },
    "page5": {
        "admin": "full",
        "supervisor": "read",
    },
    "operator_dashboard": {
        "operator": "full",
    },
    "supervisor_dashboard": {
        "supervisor": "full",
    },
    "admin_dashboard": {
        "admin": "full",
    },
    "user_management": {
        "admin": "full",
    },
}

GAURANG_OPERATIONAL_PAGES = {
    "supervisor_dashboard",
    "page1",
    "page2",
    "page3",
    "page4",
    "page5",
}

GAURANG_EXCLUDED_PAGES = {
    "admin_dashboard",
    "user_management",
}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper


def page_required(page_name):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))

            access = current_access(page_name)
            if not access:
                return redirect(url_for("auth.login"))

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def api_required(page_name, allowed_modes=("full",)):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return jsonify({"success": False, "error": "Login required"}), 401

            access = current_access(page_name)
            if access not in allowed_modes:
                return jsonify({"success": False, "error": "Unauthorized access"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_access(page_name):
    # Special operational access for gaurang user_id=5; excludes user management.
    if is_gaurang_special_user():
        if page_name in GAURANG_EXCLUDED_PAGES:
            return None
        if page_name in GAURANG_OPERATIONAL_PAGES:
            return "full"

    role = session.get("role")
    return PAGE_ACCESS.get(page_name, {}).get(role)


def allowed_pages(role):
    pages = {
        page_name: access
        for page_name, role_access in PAGE_ACCESS.items()
        for role_name, access in role_access.items()
        if role_name == role
    }
    if is_gaurang_special_user():
        pages = {k: v for k, v in pages.items() if k not in GAURANG_EXCLUDED_PAGES}
        pages.update({page_name: "full" for page_name in GAURANG_OPERATIONAL_PAGES})
    return pages

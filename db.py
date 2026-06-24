"""
Database connection helper for Demo 2.
All route blueprints import get_connection() from this module.
"""

import os
import mysql.connector

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "database": os.environ.get("DB_NAME", "jms_demo2"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ["DB_PASSWORD"],
    "connection_timeout": 10,
    "auth_plugin": "mysql_native_password",
}


def get_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn

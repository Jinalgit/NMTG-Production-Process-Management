"""
Database connection helper for Demo 2.
All route blueprints import get_connection() from this module.
"""

import mysql.connector

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "database": "jms_demo2",
    "user": "root",
    "password": "admin@123",
    "connection_timeout": 10,
    "auth_plugin": "mysql_native_password",
}


def get_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn

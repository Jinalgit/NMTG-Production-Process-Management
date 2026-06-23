# from getpass import getpass
# from werkzeug.security import generate_password_hash
# from db import get_connection


# CREATE_USERS_SQL = """
# CREATE TABLE IF NOT EXISTS users (
#     id INT AUTO_INCREMENT PRIMARY KEY,
#     username VARCHAR(50) NOT NULL UNIQUE,
#     password_hash VARCHAR(255) NOT NULL,
#     role ENUM('admin','supervisor','operator') NOT NULL,
#     full_name VARCHAR(100),
#     is_active TINYINT(1) DEFAULT 1,
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# )
# """


# def create_or_update_admin():
#     username = input("Admin username [admin]: ").strip() or "admin"
#     full_name = input("Full name [Admin]: ").strip() or "Admin"
#     password = getpass("Admin password: ")

#     if not password:
#         raise SystemExit("Password is required.")

#     password_hash = generate_password_hash(password)

#     conn = get_connection()
#     cursor = conn.cursor()
#     cursor.execute(CREATE_USERS_SQL)
#     cursor.execute(
#         """
#         INSERT INTO users (username, password_hash, role, full_name, is_active)
#         VALUES (%s, %s, 'admin', %s, 1)
#         ON DUPLICATE KEY UPDATE
#             password_hash = VALUES(password_hash),
#             role = 'admin',
#             full_name = VALUES(full_name),
#             is_active = 1
#         """,
#         (username, password_hash, full_name),
#     )
#     conn.commit()
#     cursor.close()
#     conn.close()
#     print(f"Admin user '{username}' is ready.")


# if __name__ == "__main__":
#     create_or_update_admin()

from werkzeug.security import generate_password_hash
from db import get_connection

users = [
    {
        "username": "supervisor",
        "password": "supervisor123",
        "role": "supervisor",
        "full_name": "Supervisor"
    },
    {
        "username": "operator",
        "password": "operator123",
        "role": "operator",
        "full_name": "Operator"
    }
]

conn = get_connection()
cursor = conn.cursor()

for user in users:
    password_hash = generate_password_hash(user["password"])

    cursor.execute("""
        INSERT INTO users (username, password_hash, role, full_name, is_active)
        VALUES (%s, %s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
            password_hash = VALUES(password_hash),
            role = VALUES(role),
            full_name = VALUES(full_name),
            is_active = 1
    """, (
        user["username"],
        password_hash,
        user["role"],
        user["full_name"]
    ))

conn.commit()
cursor.close()
conn.close()

print("Supervisor and Operator users created successfully")
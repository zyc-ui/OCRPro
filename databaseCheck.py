"""
databaseCheck.py
查看 database_data.db 中所有表的列名和基本信息
"""

import sqlite3
import os

DB_PATH = "database_data.db"


def check_database(db_path=DB_PATH):
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {os.path.abspath(db_path)}")
        return

    print(f"✅ 数据库路径: {os.path.abspath(db_path)}")
    print(f"   文件大小: {os.path.getsize(db_path) / 1024:.1f} KB\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        print("⚠️  数据库中没有任何表")
        conn.close()
        return

    print(f"共找到 {len(tables)} 个表:\n")

    for table in tables:
        # 获取列信息
        cursor.execute(f"PRAGMA table_info('{table}')")
        columns = cursor.fetchall()

        # 获取行数
        cursor.execute(f"SELECT COUNT(*) FROM '{table}'")
        row_count = cursor.fetchone()[0]

        print(f"┌─ 表名: {table}")
        print(f"│  行数: {row_count}")
        print(f"│  列数: {len(columns)}")
        print(f"│  列名:")
        for col in columns:
            cid, name, col_type, notnull, default, pk = col
            print(f"│    [{cid:2d}] {name}  ({col_type or 'TEXT'})")
        print(f"└{'─' * 50}\n")

    conn.close()


if __name__ == "__main__":
    check_database()

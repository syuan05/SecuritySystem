# db_utils.py
# 資料庫連線管理
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "ssl_disabled": False,
    "charset": "utf8mb4"
}

def get_db_connection():
    """建立資料庫連線並自動設為台灣時區"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SET time_zone = '+08:00';")  # ✅ 強制使用台灣時區
    cur.close()
    return conn

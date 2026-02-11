from flask import g
from sqlalchemy import create_engine
import pymysql
import ssl
import os

# 데이터베이스 설정
DB_CONFIG = {
    'host': 'localhost',
    'user': 'mbc',
    'password': '1234',
    'db': 'lms',
    'port': 3306,
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

TEACHERS_DB_CONFIG = {
    'host': '192.168.0.150',
    'user': 'mbc320',
    'password': '1234',
    'db': 'lms',
    'port': 3306,
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

CLOUD_DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', 4000)),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
    'ssl': {
        "check_hostname": False,
        "verify_mode": ssl.CERT_NONE
    }
}

CURRENT_DB_CONFIG = CLOUD_DB_CONFIG

DB_URL = f"mysql+pymysql://{CURRENT_DB_CONFIG['user']}:{CURRENT_DB_CONFIG['password']}@{CURRENT_DB_CONFIG['host']}:{CURRENT_DB_CONFIG['port']}/{CURRENT_DB_CONFIG['db']}"

engine = create_engine(
    DB_URL,
    pool_size=10,        # 기본으로 유지할 연결 개수
    max_overflow=20,     # 사람이 몰리면 임시로 더 만들 연결 개수
    pool_recycle=500,    # 500초마다 연결을 새로고침 (TiDB 끊김 방지)
    connect_args={
        "ssl": {
            "check_hostname": False,
            "verify_mode": "cert_none"  # SSL 에러 방지용
        }
    }
)

def get_db():
    """
    Flask의 g 객체를 사용하여 요청당 하나의 DB 연결을 재사용합니다.
    """
    if 'db' not in g:
        # 1. 엔진에서 '순정' 연결(raw_connection)을 하나 빌려옵니다.
        conn = engine.raw_connection()

        # 2. 기존의 cursor() 함수를 따로 저장해둡니다.
        original_cursor_func = conn.cursor

        # 3. 팀원들이 호출할 새로운 cursor 함수를 만듭니다.
        #    팀원이 cursor()를 호출하면 -> 자동으로 DictCursor를 넣어줍니다.
        def cursor_with_dict_default(cursor=pymysql.cursors.DictCursor):
            return original_cursor_func(cursor)

        # 4. 연결 객체의 cursor 함수를 우리가 만든 함수로 바꿔치기합니다. (Monkey Patching)
        conn.cursor = cursor_with_dict_default

        # 5. g 객체에 저장 (요청이 끝날 때까지 유지)
        g.db = conn

    return g.db

def execute_query(sql, args=()):
    """
    INSERT, UPDATE, DELETE 쿼리 실행 전용
    자동으로 commit 하고, 에러 발생 시 rollback 합니다.
    반환값: 영향받은 행의 수 (rowcount)
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            rows = cursor.execute(sql, args)
            conn.commit()
            return rows
    except Exception as e:
        conn.rollback() # 에러 나면 되돌리기
        raise e # 에러를 호출한 곳으로 다시 던져서 알림

def fetch_query(sql, args=(), one=False):
    """
    SELECT 쿼리 실행 전용
    one=True이면 fetchone(), False이면 fetchall()
    """
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(sql, args)
        if one:
            return cursor.fetchone()
        return cursor.fetchall()

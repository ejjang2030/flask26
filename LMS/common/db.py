from flask import g
import pymysql

# 데이터베이스 설정
DB_CONFIG = {
    'host': 'localhost',
    'user': 'mbc',
    'password': '1234',
    'db': 'lms',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

TEACHERS_DB_CONFIG = {
    'host': '192.168.0.150',
    'user': 'mbc320',
    'password': '1234',
    'db': 'lms',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 1. DB 연결 관리 함수 (g 객체 사용)
def get_db():
    if 'db' not in g:
        # 연결이 없으면 새로 생성하여 g.db에 저장
        g.db = pymysql.connect(**TEACHERS_DB_CONFIG)
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

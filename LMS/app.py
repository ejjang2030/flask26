from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
import os
from LMS.common.db import fetch_query, execute_query

app = Flask(__name__)

load_dotenv()
FLASK_APP_KEY = os.getenv('FLASK_APP_KEY')
app.secret_key = FLASK_APP_KEY

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('로그인이 필요한 서비스입니다.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('main.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    uid = request.form.get('uid')
    upw = request.form.get('upw')

    # [개선] SELECT 로직이 한 줄로 줄어듦
    user = fetch_query("SELECT * FROM members WHERE uid = %s", (uid,), one=True)

    if user and check_password_hash(user['password'], upw):
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        return redirect(url_for('index'))
    else:
        return "<script>alert('로그인 실패');history.back();</script>"


@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃 되었습니다.')
    return redirect(url_for('login'))


@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    uid = request.form.get('uid')
    password = request.form.get('password')
    name = request.form.get('name')

    try:
        # 1. 중복 체크 (SELECT)
        exist = fetch_query("SELECT id FROM members WHERE uid = %s", (uid,), one=True)
        if exist:
            return '<script>alert("이미 존재하는 아이디입니다.");history.back();</script>'

        # 2. 회원 가입 (INSERT - DML)
        # [개선] 복잡한 conn, cursor, commit 코드가 사라지고 함수 호출만 남음
        hashed_pw = generate_password_hash(password)
        execute_query("INSERT INTO members (uid, password, name) VALUES (%s, %s, %s)", (uid, hashed_pw, name))

        return '<script>alert("가입 완료!"); location.href="/login";</script>'

    except Exception as e:
        print(f"가입 에러: {e}")
        return '가입 중 오류 발생'

@app.route('/mypage')
@login_required
def mypage():
    user = fetch_query("SELECT * FROM members WHERE id = %s", (session['user_id'],), one=True)

    # COUNT 쿼리도 간단하게 처리 (결과가 없을 수 있으므로 예외처리 살짝 필요하거나 쿼리 수정)
    board_data = fetch_query("SELECT COUNT(*) as cnt FROM boards WHERE member_id = %s", (session['user_id'],), one=True)
    board_count = board_data['cnt'] if board_data else 0

    return render_template('mypage.html', user=user, board_count=board_count)

@app.route('/member/edit', methods=['GET', 'POST'])
@login_required
def member_edit():
    if request.method == 'GET':
        user = fetch_query("SELECT * FROM members WHERE id = %s", (session['user_id'],), one=True)
        return render_template('member_edit.html', user=user)

    # POST 요청 (정보 수정)
    new_name = request.form.get('name')
    new_pw = request.form.get('password')

    try:
        if new_pw:
            hashed_pw = generate_password_hash(new_pw)
            # [개선] UPDATE 실행
            execute_query(
                "UPDATE members SET name = %s, password = %s WHERE id = %s",
                (new_name, hashed_pw, session['user_id'])
            )
        else:
            execute_query(
                "UPDATE members SET name = %s WHERE id = %s",
                (new_name, session['user_id'])
            )

        session['user_name'] = new_name
        return "<script>alert('수정 완료');location.href='/mypage';</script>"

    except Exception as e:
        print(f"수정 에러: {e}")
        return "수정 중 오류 발생"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
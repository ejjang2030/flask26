from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
import os
from LMS.common.db import fetch_query, execute_query
from LMS.common.session import Session
from LMS.domain import Board
from math import ceil

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    uid = request.form.get('uid')
    upw = request.form.get('upw')

    # [개선] SELECT 로직이 한 줄로 줄어듦
    user = fetch_query("SELECT * FROM members WHERE uid = %s", (uid,), one=True)

    if user and user['password'] == upw:
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
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
        hashed_pw = password
        execute_query("INSERT INTO members (uid, password, name) VALUES (%s, %s, %s)", (uid, hashed_pw, name))

        return '<script>alert("가입 완료!"); location.href="/login";</script>'

    except Exception as e:
        print(f"가입 에러: {e}")
        return '가입 중 오류 발생'

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
            hashed_pw = new_pw
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

@app.route('/mypage')
@login_required
def mypage():
    user = fetch_query("SELECT * FROM members WHERE id = %s", (session['user_id'],), one=True)

    # COUNT 쿼리도 간단하게 처리 (결과가 없을 수 있으므로 예외처리 살짝 필요하거나 쿼리 수정)
    board_data = fetch_query("SELECT COUNT(*) as cnt FROM boards WHERE member_id = %s", (session['user_id'],), one=True)
    board_count = board_data['cnt'] if board_data else 0

    return render_template('mypage.html', user=user, board_count=board_count)

@app.route('/board/write', methods=['GET', 'POST']) # http://localhost:5000/board/write
def board_write():
    # 1. 사용자가 '글쓰기' 버튼을 눌러서 들어왔을 때 (화면 보여주기)
    if request.method == 'GET':
        # 로그인 체크 (로그인 안 했으면 글 못 쓰게)
        if 'user_id' not in session:
            return '<script>alert("로그인 후 이용 가능합니다."); location.href="/login";</script>'
        return render_template('board_write.html')

    # 2. 사용자가 '등록하기' 버튼을 눌러서 데이터를 보냈을 때(DB 저장)
    elif request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        # 세션에 저장된 로그인 유지의 id (member_id)
        member_id = session.get('user_id')
        try:
            execute_query(
                "INSERT INTO boards (member_id, title, content) VALUES (%s, %s, %s)", (member_id, title, content))
            return redirect(url_for('board_list'))
        except Exception as e:
            print(e)

@app.route('/board')
def board_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    # 전체 개수 구하기
    count_sql = "SELECT COUNT(*) as cnt FROM boards"
    total_count = fetch_query(count_sql)[0]['cnt']
    total_pages = ceil(total_count / per_page)

    # 데이터 가져오기
    sql = f"""SELECT b.*, m.name as writer_name
        FROM boards b
        JOIN members m ON b.member_id = m.id
        ORDER BY b.id DESC
        LIMIT {per_page} OFFSET {offset}""" # 기존 SQL 쿼리
    rows = fetch_query(sql)
    boards = [Board.from_db(row) for row in rows]

    # HTML이 기대하는 'pagination' 변수를 가짜로 만들어서 넘겨줍니다.
    pagination = {
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }

    return render_template('board_list.html',
                           boards=boards,
                           pagination=pagination) # 여기서 pagination을 넘겨줍니다!

@app.route('/board/view/<int:board_id>') # http://localhost:5000/board/view/99(게시물번호)
def board_view(board_id):
    sql = """
        SELECT b.*, m.name as writer_name, m.uid as writer_uid
        FROM boards b
        JOIN members m ON b.member_id = m.id
        WHERE b.id = %s
    """
    row = fetch_query(sql, (board_id,), one=True)
    if not row:
        return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'
    board = Board.from_db(row)
    return render_template('board_view.html', board=board)

@app.route('/board/edit/<int:board_id>', methods=['GET', 'POST'])
def board_edit(board_id):
    if request.method == 'GET':
        sql = "SELECT * FROM boards WHERE id = %s"
        row = fetch_query(sql, (board_id,), one=True)
        if not row:
            return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'

        if row['member_id'] != session.get('user_id'):
            return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
        board = Board.from_db(row)
        return render_template('board_edit.html', board=board)
    elif request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')

        sql = "UPDATE boards SET title = %s, content = %s WHERE id = %s"
        try:
            execute_query(sql, (title, content, board_id))
            return redirect(url_for('board_view', board_id=board_id))
        except Exception as e:
            print(e)
    return None


@app.route('/board/delete/<int:board_id>')
def board_delete(board_id):
    board_sql = 'SELECT * FROM boards WHERE id = %s'
    row = fetch_query(board_sql, (board_id,), one=True)
    if not row:
        return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'
    if row['member_id'] != session.get('user_id'):
        return '<script>alert("삭제할 권한이 없습니다."); history.back();</script>'
    try:
        sql = "DELETE FROM boards WHERE id = %s"
        execute_query(sql, (board_id,))
        return redirect(url_for('board_list'))
    except Exception as e:
        print(e)

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
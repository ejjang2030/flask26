

from ssl import socket_error

import os
from dotenv import load_dotenv
from flask import send_from_directory
from werkzeug.utils import secure_filename

import uuid
load_dotenv()
import requests
import traceback
from math import ceil
from functools import wraps
from bs4 import BeautifulSoup
from flask_caching import Cache
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from LMS.common.db import fetch_query, execute_query
from LMS.common.session import Session
from LMS.domain import Board, Score
from LMS.service import PostService
from LMS.common.session import Session
from datetime import datetime, timedelta
from LMS.common.db import fetch_query, execute_query
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify

app = Flask(__name__)

cache = Cache(config={'CACHE_TYPE': 'simple'})
cache.init_app(app)

FLASK_APP_KEY = os.getenv('FLASK_APP_KEY')
app.secret_key = FLASK_APP_KEY

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ----------------------------------------------------------------------------------------------------------------------
#                                                 회원 CRUD
# ----------------------------------------------------------------------------------------------------------------------

# 로그인 후 이용 가능합니다.
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('로그인이 필요한 서비스입니다.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 로그인
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

# 로그아웃
@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃 되었습니다.')
    return redirect(url_for('login'))

# 회원가입
@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    if request.method == 'GET':
        # 현재 연도를 구해서 템플릿으로 전달합니다.
        today_year = date.today().year
        return render_template('join.html', year_now=today_year)

    uid = request.form.get('uid')
    password = request.form.get('password')
    name = request.form.get('name')
    #회원가입 시 생년월일 추가(만 14세 이상만 가입 가능)
    # [추가] 따로 입력받은 년, 월, 일을 가져옴
    b_year = request.form.get('birth_year')
    b_month = request.form.get('birth_month')
    b_day = request.form.get('birth_day')

    try:
        # [추가] 만 나이 계산 및 14세 체크
        if b_year and b_month and b_day:
            birth_date = date(int(b_year), int(b_month), int(b_day))
            today = date.today()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

            if age < 14:
                return '<script>alert("만 14세 이상만 가입 가능합니다.");history.back();</script>'

            # DB에 저장할 날짜 형식 (YYYY-MM-DD)
            birthdate_str = birth_date.strftime('%Y-%m-%d')
        else:
            return '<script>alert("생년월일을 모두 입력해주세요.");history.back();</script>'

        # 1. 중복 체크 (SELECT)
        exist = fetch_query("SELECT id FROM members WHERE uid = %s", (uid,), one=True)
        if exist:
            return '<script>alert("이미 존재하는 아이디입니다.");history.back();</script>'

        # 2. 회원 가입 (INSERT - DML)
        # [개선] 복잡한 conn, cursor, commit 코드가 사라지고 함수 호출만 남음
        hashed_pw = password
        execute_query("INSERT INTO members (uid, password, name, birthdate) VALUES (%s, %s, %s, %s)", (uid, hashed_pw, name, birthdate_str))

        return '<script>alert("가입 완료!"); location.href="/login";</script>'

    except Exception as e:
        print(f"가입 에러: {e}")
        return '가입 중 오류 발생'

# 회원 정보 수정
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

# 마이페이지
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 1. 유저 정보 가져오기
    user = fetch_query("SELECT * FROM members WHERE id = %s", (session['user_id'],), one=True)

    # 2. [수정] 신고 1개 이상이면 차단된 것으로 간주
    sql_count = """
        SELECT 
            COUNT(*) as total_cnt,
            COUNT(CASE WHEN (SELECT COUNT(*) FROM reports WHERE board_id = b.id) >= 1 THEN 1 END) as reported_cnt
        FROM boards b
        WHERE b.member_id = %s AND b.active = 1
    """
    count_data = fetch_query(sql_count, (session['user_id'],), one=True)

    board_count = count_data['total_cnt'] if count_data else 0
    reported_count = count_data['reported_cnt'] if count_data else 0

    return render_template('mypage.html',
                           user=user,
                           board_count=board_count,
                           reported_count=reported_count)

# 마이페이지 - 성적 확인
@app.route('/score/my')
def score_my():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM scores WHERE member_id = %s"
            cursor.execute(sql, (session['user_id'],))
            row = cursor.fetchone()

            score = Score.from_db(row) if row else None
            return render_template('score_my.html', score=score)
    finally:
        conn.close()

# 마이페이지 - 프로필 사진
@app.route('/profile/upload', methods=['POST'])
def profile_upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if 'profile_img' not in request.files:
        return "<script>alert('파일이 없습니다.');history.back();</script>"

    file = request.files['profile_img']
    if file.filename == '':
        return "<script>alert('선택된 파일이 없습니다.');history.back();</script>"

    if file:
        # 확장자 체크 및 파일명 생성 (유저 고유 ID 사용)
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif']:
            return "<script>alert('이미지 파일만 업로드 가능합니다.');history.back();</script>"

        # 파일명: profile_유저ID.png (기존 사진 덮어쓰기 위해 고정)
        filename = f"profile_{session['user_id']}{ext}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        file.save(save_path)

        # DB의 members 테이블에 프로필 이미지 파일명 저장 (이미 컬럼이 있다면)
        try:
            sql = "UPDATE members SET profile_img = %s WHERE id = %s"
            execute_query(sql, (filename, session['user_id']))
            return "<script>alert('프로필 사진이 변경되었습니다.');location.href='/mypage';</script>"
        except Exception as e:
            print(f"프로필 DB 업데이트 에러: {e}")
            return "<script>alert('DB 업데이트 중 오류 발생');history.back();</script>"

# 마이페이지 - 작성한 게시물 조회
@app.route('/board/my')  # http://localhost:5000/board/my
def my_board_list() :
    if 'user_id' not in session :
        return redirect(url_for('login'))

    conn = Session.get_connection()

    try :
        with conn.cursor() as cursor :

            # 내가 쓴 글만 조회 (작성자 이름 포함)
            sql = """
                  SELECT b.*, m.name as writer_name
                  FROM boards b
                  JOIN members m ON b.member_id = m.id
                  WHERE b.member_id = %s
                  ORDER BY b.id DESC
                  """
            cursor.execute(sql, (session['user_id'],))
            rows = cursor.fetchall()

            # 기존 Board 도메인 객체 활용
            boards = [Board.from_db(row) for row in rows]

            # 기존 board_list.html을 재사용하거나 전용 페이지를 만듭니다.
            # 여기서는 '내 글 관리'라는 느낌을 주도록 새로운 제목과 함께 보냅니다.
            return render_template('board_list.html', boards=boards, list_title="내가 작성한 게시물")

    finally :
        conn.close()

# ----------------------------------------------------------------------------------------------------------------------
#                                                 게시판 CRUD
# ----------------------------------------------------------------------------------------------------------------------

# 게시물 작성
@app.route('/board/write', methods=['GET', 'POST']) # http://localhost:5000/board/write
def board_write():
    # 1. 사용자가 '글쓰기' 버튼을 눌러서 들어왔을 때 (화면 보여주기)
    if request.method == 'GET':
        # 로그인 체크 (로그인 안 했으면 글 못 쓰게)
        if 'user_id' not in session:
            return '<script>alert("로그인 후 이용 가능합니다."); location.href="/login";</script>'

        # 관리자 여부를 템플릿에 전달
        is_admin = (session.get('user_role') == "admin")
        return render_template('board_write.html', is_admin=is_admin)

    # 2. 사용자가 '등록하기' 버튼을 눌러서 데이터를 보냈을 때(DB 저장)
    elif request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        # 세션에 저장된 로그인 유지의 id (member_id)
        member_id = session.get('user_id')

        #소현
        # 1. 공지사항 고정 여부 확인 (관리자만 가능)
        is_pinned = 0
        if session.get('user_role') == "admin":
            if request.form.get('is_pinned') == 'on':
                is_pinned = 1

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                # 2. 공지사항(is_pinned=1)인 경우에만 개수 체크
                if is_pinned == 1:
                    count_sql = "SELECT COUNT(*) AS c FROM boards WHERE is_pinned = 1"
                    cursor.execute(count_sql)
                    pinned_count = cursor.fetchone()['c'] # 튜플이나 딕셔너리 형태에 따라 적절히 추출
                    print(pinned_count)

                    if pinned_count >= 10:
                        return "<script>alert('공지사항은 최대 10개까지만 등록 가능합니다.');history.back();</script>"

                # 3. DB 저장 (is_pinned 컬럼 포함)
                sql = "INSERT INTO boards (member_id, title, content, is_pinned) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (member_id, title, content, is_pinned))
                conn.commit()

            return redirect(url_for('board_list'))  # 저장 후 목록으로 이동

        except Exception as e:
            print(f"글쓰기 에러: {e}")
            return "저장 중 에러가 발생했습니다."

        finally:
            conn.close()

        # try:
        #     execute_query(
        #         "INSERT INTO boards (member_id, title, content) VALUES (%s, %s, %s)", (member_id, title, content))
        #     return redirect(url_for('board_list'))
        # except Exception as e:
        #     print(e)

# 게시물 목록
@app.route('/board')
def board_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    # 1. 권한에 따른 WHERE 절 생성
    # 관리자는 삭제된 글(active=0)도 보고, 유저는 정상 글(active=1)만 봄
    if session.get('user_role') == 'admin':
        where_clause = "WHERE 1=1" # 모든 글 보기
    else:
        where_clause = "WHERE b.active = 1" # 정상 글만 보기

    # 2. 전체 개수 구하기 (권한 필터 적용)
    count_sql = f"SELECT COUNT(*) as cnt FROM boards b {where_clause}"
    count_res = fetch_query(count_sql, one=True)
    total_count = count_res['cnt'] if count_res else 0
    total_pages = ceil(total_count / per_page)

    # 3. 메인 쿼리 (좋아요, 싫어요, 댓글수 + [추가] 신고수)
    sql = f"""
        SELECT 
            b.*, 
            m.name as writer_name,
            (SELECT COUNT(*) FROM board_likes WHERE board_id = b.id) as like_count,
            (SELECT COUNT(*) FROM board_dislikes WHERE board_id = b.id) as dislike_count,
            (SELECT COUNT(*) FROM board_comments WHERE board_id = b.id) as comment_count,
            (SELECT COUNT(*) FROM reports WHERE board_id = b.id) as report_count
        FROM boards b
        JOIN members m ON b.member_id = m.id
        {where_clause}
        ORDER BY b.is_pinned DESC, b.id DESC
        LIMIT {per_page} OFFSET {offset}
    """
    rows = fetch_query(sql)

    boards = []
    for row in rows:
        board = Board.from_db(row)
        board.like_count = row['like_count']
        board.dislike_count = row['dislike_count']
        board.comment_count = row['comment_count']
        board.report_count = row['report_count'] # [추가] 신고 수 주입
        board.is_pinned = row.get('is_pinned', 0)
        boards.append(board)

    pagination = {
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }

    return render_template('board_list.html', boards=boards, pagination=pagination)

# 게시물 자세히 보기
@app.route('/board/view/<int:board_id>')
def board_view(board_id):
    # 1. 조회수 증가
    try:
        execute_query("UPDATE boards SET visits = visits + 1 WHERE id = %s", (board_id,))
    except Exception as e:
        print(f"조회수 증가 오류: {e}")

    # 2. 게시글 상세 정보 가져오기 (신고 수 서브쿼리 추가)
    sql = """
        SELECT b.*, m.name as writer_name, m.uid as writer_uid,
               (SELECT COUNT(*) FROM reports WHERE board_id = b.id) as report_count
        FROM boards b
        JOIN members m ON b.member_id = m.id
        WHERE b.id = %s
    """
    row = fetch_query(sql, (board_id,), one=True)
    if not row:
        return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'

    # 🚩 [신규 추가] 신고 1개 이상 차단 로직 (관리자는 통과)
    if row['report_count'] >= 1:
        if session.get('user_role') != 'admin':
            return "<script>alert('신고 접수된 게시글임으로 조회가 불가능합니다.'); history.back();</script>"

    # 3. 좋아요 & 싫어요 정보 조회
    like_count = fetch_query("SELECT COUNT(*) as cnt FROM board_likes WHERE board_id = %s", (board_id,), one=True)[
        'cnt']
    dislike_count = \
    fetch_query("SELECT COUNT(*) as cnt FROM board_dislikes WHERE board_id = %s", (board_id,), one=True)['cnt']

    user_liked = False
    user_disliked = False

    if 'user_id' in session:
        # 이미 세션에 member_id(PK)가 저장되어 있다고 가정 (로그인 시 id를 저장했다면)
        member_pk = session['user_id']

        if fetch_query("SELECT 1 FROM board_likes WHERE board_id = %s AND member_id = %s", (board_id, member_pk),
                       one=True):
            user_liked = True
        if fetch_query("SELECT 1 FROM board_dislikes WHERE board_id = %s AND member_id = %s", (board_id, member_pk),
                       one=True):
            user_disliked = True

    # 4. 댓글 및 대댓글 목록 가져오기 (기존 팀원 코드 유지)
    comment_sql = """
            SELECT c.*, m.name as writer_name, m.uid as writer_uid
            FROM board_comments c
            JOIN members m ON c.member_id = m.id
            WHERE c.board_id = %s
            ORDER BY c.created_at ASC
        """
    all_comments = fetch_query(comment_sql, (board_id,))

    comment_dict = {c['id']: {**c, 'children': []} for c in all_comments}
    root_comments = []

    for c_id, c_data in comment_dict.items():
        parent_id = c_data['parent_id']
        if parent_id and parent_id in comment_dict:
            comment_dict[parent_id]['children'].append(c_data)
        else:
            root_comments.append(c_data)

    # 5. Board 객체 생성 및 데이터 주입
    board = Board.from_db(row)
    board.likes = like_count
    board.dislikes = dislike_count
    board.report_count = row['report_count']  # 혹시 화면에 신고수 띄울까봐 추가

    return render_template('board_view.html',
                           board=board,
                           user_liked=user_liked,
                           user_disliked=user_disliked,
                           comments=root_comments)

# 게시물 수정
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


# 게시물 삭제 (관리자 영구삭제 vs 유저 소프트삭제)
@app.route('/board/delete/<int:board_id>')
def board_delete(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 1. 게시글 존재 여부 및 정보 확인
    board_sql = 'SELECT * FROM boards WHERE id = %s'
    row = fetch_query(board_sql, (board_id,), one=True)

    if not row:
        return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'

    try:
        # 2. 관리자(admin)인 경우: DB에서 아예 행을 삭제 (Hard Delete)
        if session.get('user_role') == 'admin':
            sql = "DELETE FROM boards WHERE id = %s"
            execute_query(sql, (board_id,))
            msg = "관리자 권한으로 게시글을 영구 삭제했습니다."

        # 3. 일반 유저인 경우: 본인 글일 때만 active를 0으로 수정 (Soft Delete)
        else:
            # 본인 글인지 먼저 체크
            if row['member_id'] != session.get('user_id'):
                return '<script>alert("삭제할 권한이 없습니다."); history.back();</script>'

            # active 상태만 0으로 바꿔서 목록에서 숨김
            sql = "UPDATE boards SET active = 0 WHERE id = %s AND member_id = %s"
            execute_query(sql, (board_id, session['user_id']))
            msg = "게시글이 삭제되었습니다."

        return f"<script>alert('{msg}'); location.href='/board';</script>"

    except Exception as e:
        print(f'삭제 에러: {e}')
        return "<script>alert('처리 중 오류가 발생했습니다.'); history.back();</script>"

# 좋아요
@app.route('/board/like/<int:board_id>', methods=['POST'])
def board_like_toggle(board_id):
    # 1. 로그인 체크
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401

    try:
        # 2. 게시글 존재 확인
        board = fetch_query("SELECT id FROM boards WHERE id = %s", (board_id,), one=True)
        if not board:
            return jsonify({'success': False, 'message': '존재하지 않는 게시글입니다.'}), 404

        # 3. 좋아요 상태 확인
        check_sql = "SELECT id FROM board_likes WHERE board_id = %s AND member_id = %s"
        # session['user_id']가 DB의 members.id(PK, 숫자)와 일치하는지 꼭 확인하세요!
        already_liked = fetch_query(check_sql, (board_id, session['user_id']), one=True)

        if already_liked:
            execute_query("DELETE FROM board_likes WHERE board_id = %s AND member_id = %s",
                          (board_id, session['user_id']))
            is_liked = False
        else:
            execute_query("INSERT INTO board_likes (board_id, member_id) VALUES (%s, %s)",
                          (board_id, session['user_id']))
            is_liked = True

        # 4. 개수 집계
        count_res = fetch_query("SELECT COUNT(*) as cnt FROM board_likes WHERE board_id = %s", (board_id,), one=True)
        like_count = count_res['cnt'] if count_res else 0

        return jsonify({
            'success': True,
            'is_liked': is_liked,
            'like_count': like_count
        })

    except Exception as e:
        # 이 부분이 중요합니다! 에러가 나더라도 클라이언트에게 JSON을 돌려줘야 합니다.
        print(f"Database Error: {e}")
        return jsonify({
            'success': False,
            'message': f"데이터베이스 오류가 발생했습니다: {str(e)}"
        }), 500

# 싫어요
@app.route('/board/dislike/<int:board_id>', methods=['POST'])
def board_dislike_toggle(board_id):
    # 1. 로그인 체크
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401

    try:
        # 2. 게시글 존재 확인
        board = fetch_query("SELECT id FROM boards WHERE id = %s", (board_id,), one=True)
        if not board:
            return jsonify({'success': False, 'message': '존재하지 않는 게시글입니다.'}), 404

        # 3. 싫어요 상태 확인
        check_sql = "SELECT id FROM board_dislikes WHERE board_id = %s AND member_id = %s"

        # session['user_id']가 DB의 members.id(PK)와 일치한다고 가정합니다.
        # (만약 session에 문자열 ID가 들어있다면, 여기서 member_id를 조회하는 로직이 추가로 필요할 수 있습니다)
        already_disliked = fetch_query(check_sql, (board_id, session['user_id']), one=True)

        if already_disliked:
            # 이미 싫어요를 눌렀다면 -> 삭제 (취소)
            execute_query("DELETE FROM board_dislikes WHERE board_id = %s AND member_id = %s",
                          (board_id, session['user_id']))
            is_disliked = False
        else:
            # 안 눌렀다면 -> 추가 (싫어요)
            execute_query("INSERT INTO board_dislikes (board_id, member_id) VALUES (%s, %s)",
                          (board_id, session['user_id']))
            is_disliked = True

        # 4. 개수 집계 (board_dislikes 테이블 카운트)
        count_res = fetch_query("SELECT COUNT(*) as cnt FROM board_dislikes WHERE board_id = %s", (board_id,), one=True)
        dislike_count = count_res['cnt'] if count_res else 0

        return jsonify({
            'success': True,
            'is_disliked': is_disliked,
            'dislike_count': dislike_count
        })

    except Exception as e:
        # 에러 발생 시 JSON 응답 반환
        print(f"Database Error: {e}")
        return jsonify({
            'success': False,
            'message': f"데이터베이스 오류가 발생했습니다: {str(e)}"
        }), 500

# 댓글
@app.route('/board/comment/<int:board_id>', methods=['POST'])
def add_comment(board_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401

    data = request.get_json()
    content = data.get('content')
    parent_id = data.get('parent_id')  # 대댓글일 경우 부모 ID가 넘어옴

    sql = "INSERT INTO board_comments (board_id, member_id, parent_id, content) VALUES (%s, %s, %s, %s)"
    execute_query(sql, (board_id, session['user_id'], parent_id, content))

    return jsonify({'success': True})


# 게시물 신고 기능
@app.route('/board/report/<int:board_id>', methods=['POST'])
def board_report(board_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401

    # 프론트에서 JSON으로 보냈다면 request.get_json()을 써야 할 수도 있습니다.
    # 만약 기존처럼 Form으로 보냈다면 그대로 유지하세요.
    data = request.get_json()
    reason = data.get('reason')
    reporter_id = session['user_id']

    try:
        board = fetch_query("SELECT member_id FROM boards WHERE id = %s", (board_id,), one=True)
        if board and board['member_id'] == reporter_id:
            return jsonify({'success': False, 'message': '본인 글은 신고할 수 없습니다.'})
        check_sql = "SELECT id FROM reports WHERE board_id = %s AND reporter_id = %s"
        if fetch_query(check_sql, (board_id, reporter_id), one=True):
            return jsonify({'success': False, 'message': '이미 신고한 글입니다.'})

        insert_sql = "INSERT INTO reports (board_id, reporter_id, reason) VALUES (%s, %s, %s)"
        execute_query(insert_sql, (board_id, reporter_id, reason))
        return jsonify({'success': True, 'message': '신고가 접수되었습니다.'})

    except Exception as e:
        print(f"Database Error: {e}")
        return jsonify({'success': False, 'message': '서버 오류 발생'}), 500


# 관리자 전용: 신고 내역 초기화 (게시글 복구)
@app.route('/admin/clear_reports/<int:board_id>')
def clear_reports(board_id):
    # 1. 권한 체크 (세션의 role이 admin인지 확인)
    if session.get('user_role') != 'admin':
        return "<script>alert('관리자만 접근 가능합니다.'); history.back();</script>"

    try:
        # 2. execute_query를 사용하여 해당 게시글의 모든 신고 삭제
        # 신고가 삭제되면 report_count가 0이 되어 다시 일반 유저에게 노출됩니다.
        sql = "DELETE FROM reports WHERE board_id = %s"
        execute_query(sql, (board_id,))

        return "<script>alert('신고가 초기화되었습니다. 게시글이 다시 공개됩니다.'); location.href='/board';</script>"

    except Exception as e:
        print(f"신고 초기화 에러: {e}")
        return f"<script>alert('처리 중 오류가 발생했습니다.'); history.back();</script>"

# ----------------------------------------------------------------------------------------------------------------------
#                                                 성적 CRUD
# ----------------------------------------------------------------------------------------------------------------------

# 성적 입력
@app.route('/score/add') # http://localhost:5000/score/add?uid=test1&name=test1
def score_add():
    if session.get('user_role') not in ('admin', 'manager'):
        return '<script>alert("권한이 없습니다."); history.back();</script>'

    # request.args는 url을 통해서 넘어오는 값 주소뒤에 ?K=V&K=V ......
    target_uid = request.args.get('uid')
    target_name = request.args.get('name')

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM members WHERE uid = %s', (target_uid,))
            student = cursor.fetchone()

            existing_score = None
            if student:
                cursor.execute('SELECT * FROM scores WHERE member_id = %s', (student['id'],))
                row = cursor.fetchone()
                if row:
                    existing_score = Score.from_db(row)

            return render_template('score_form.html', target_uid=target_uid, target_name=target_name, score=existing_score)
    finally:
        conn.close()

# 성적 저장
@app.route('/score/save', methods=['POST'])
def score_save():
    if session.get('user_role') not in ('admin', 'manager'):
        return "권한 오류", 403

    target_uid = request.form.get('target_uid')
    kor = int(request.form.get('korean', 0))
    eng = int(request.form.get('english', 0))
    math = int(request.form.get('math', 0))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM members WHERE uid = %s', (target_uid,))
            student = cursor.fetchone()
            print(student) # 학번 출력
            if not student:
                return "<script>alert('존재하지 않는 학생입니다.'); history.back();</script>"

            temp_score = Score(member_id=student['id'], kor=kor, eng=eng, math=math)
            #              __init__.py

            cursor.execute('SELECT id FROM scores WHERE member_id = %s', (student['id'],))
            is_exist = cursor.fetchone() # 성적이 있으면 id가 나오고 없으면 None

            if is_exist:
                sql = """
                    UPDATE scores SET korean = %s, english = %s, math = %s, total = %s, average = %s, grade = %s WHERE member_id = %s
                """
                cursor.execute(sql, (temp_score.kor, temp_score.eng, temp_score.math, temp_score.total, temp_score.avg, temp_score.grade, student['id']))
            else:
                sql = """
                    INSERT INTO scores (member_id, korean, english, math, total, average, grade)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (student['id'], temp_score.kor, temp_score.eng, temp_score.math, temp_score.total, temp_score.avg, temp_score.grade))
            conn.commit()
            return f"<script>alert('{target_uid} 학생 성적 저장 완료!'); location.href = '/score/list';</script>"
    finally:
        conn.close()

# 성적 목록
@app.route('/score/list') # http://localhost:5000/score/list -> get
def score_list():
    if session.get('user_role') not in ('admin', 'manager'):
        return "<script>alert('권한이 없습니다.'); history.back();</script>"

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT m.name, m.uid, s.* FROM scores s
                JOIN members m ON s.member_id = m.id
                ORDER BY s.total DESC
            """
            cursor.execute(sql)
            datas = cursor.fetchall()
            print(f'sql 결과 : {datas}')

            score_objects = []
            for data in datas:
                s = Score.from_db(data) # 직렬화 dict -> 객체로 만들어)
                s.name = data['name']
                s.uid = data['uid']
                score_objects.append(s) # 객체를 리스트에 넣음

            return render_template('score_list.html', scores=score_objects)
            #                          프론트화면 ui에                    성적이 담긴 리스트 객체를 전달함!!
    finally:
        conn.close()

# 성적 입력 (member 테이블 기반)
@app.route('/score/members')
def score_members():
    if session.get('user_role') not in ('admin', 'manager'):
        return "<script>alert('권한이 없습니다.'); history.back();</script>"

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT m.id, m.uid, m.name, s.id AS score_id
                FROM members m
                LEFT JOIN scores s ON m.id = s.member_id
                WHERE m.role = 'user'
                ORDER BY m.name ASC
            """
            cursor.execute(sql)
            members = cursor.fetchall()
            return render_template('score_member_list.html', members=members)
    finally:
        conn.close()

# ----------------------------------------------------------------------------------------------------------------------
#                                               자료실 (파일 업로드)
# ----------------------------------------------------------------------------------------------------------------------

# 파일 처리 경로
UPLOAD_FOLDER = 'uploads/'
# 폴더 부재 시 자동 생성
if not os.path.exists(UPLOAD_FOLDER) : # 'import os' 상단에 추가
    os.makedirs(UPLOAD_FOLDER) # os.makedirs(경로) : 폴더 생성용 코드

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 최대 용량 제한 (e.g. 16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 파일 게시판 - 작성
@app.route('/filesboard/write', methods = ['GET', 'POST'])
def filesboard_write() :
    if 'user_id' not in session :
        return redirect(url_for('login'))

    if request.method == 'POST' :

        title = request.form.get('title')
        content = request.form.get('content')
        files = request.files.getlist('files') # getlist : 리스트 형태로 가져온다.

        if PostService.save_post(session['user_id'], title, content, files) :
            return "<script>alert('게시물이 등록되었습니다.');location.href='/filesboard';</script>"

        else :
            return "<script>alert('등록 실패');history.back();</script>"

    return render_template('filesboard_write.html')

# 파일 게시판 - 목록
@app.route('/filesboard')
def filesboard_list() :
    posts = PostService.get_posts()
    return render_template('filesboard_list.html', posts=posts)

# 파일 게시판 - 자세히 보기
@app.route('/filesboard/view/<int:post_id>')
def filesboard_view(post_id) :
    post, files = PostService.get_post_detail(post_id)

    if not post :
        return "<script>alert('해당 게시글이 없습니다.'); location.href='/filesboard';</script>"

    return render_template('filesboard_view.html', post=post, files=files)

# 파일 게시판 - 자료 다운로드
@app.route('/download/<path:filename>')
def download_file(filename) :
    # 파일이 저장된 폴더(uploads)에서 파일을 찾아 전송한다.
    # 프론트 '<a href="{{ url_for('download_file', filename=file.save_name) }}" ...>' 처리용
    # filename : 서버에 저장된 save_name
    # 브라우저가 다운로드할 때 보여줄 원본 이름을 쿼리 스트링으로 받거나 DB에서 가져와야 한다.

    origin_name = request.args.get('origin_name')
    return send_from_directory('uploads/', filename, as_attachment = True, download_name = origin_name)
    # from flask import send_from_directory 필수

    #   return send_from_directory('uploads/', filename) : 브라우저에서 바로 열어버린다.
    #   as_attachment=True : 파일 다운로드 창
    #   저장할 파일명 : download_name=origin_name

# ----------------------------------------------------------------------------------------------------------------------
#                                         오늘의 운세 / 내일의 운세 (띠별)
# ----------------------------------------------------------------------------------------------------------------------

# 띠별 운세 확인
@app.route('/fortune', methods=['GET', 'POST'])
def fortune():
    if not session.get('user_id'):
        return "<script>alert('로그인 후 이용 가능합니다.'); location.href='/login';</script>"

    data = None

    if request.method == 'POST':
        try:
            year = int(request.form.get('year'))
            month = int(request.form.get('month'))
            day = int(request.form.get('day'))

            # 1. 띠 계산
            zodiacs = ["원숭이띠", "닭띠", "개띠", "돼지띠", "쥐띠", "소띠", "호랑이띠", "토끼띠", "용띠", "뱀띠", "말띠", "양띠"]
            user_zodiac = zodiacs[year % 12]

            # 2. 나이 계산 (현재 2026년 기준)
            age = 2026 - year + 1

            # 3. 오늘/내일 날짜 설정
            today_date = datetime.now().date()
            tomorrow_date = today_date + timedelta(days=1)

            # 4. DB/크롤링 연동 로직 호출
            today_content = get_db_fortune(user_zodiac, today_date)
            tomorrow_content = get_db_fortune(user_zodiac, tomorrow_date)

            data = {
                'birth': f"{year}년 {month}월 {day}일",
                'zodiac': user_zodiac,
                'age': age,
                'today': today_content,
                'tomorrow': tomorrow_content
            }
        except Exception as e:
            print(f"운세 페이지 로직 에러: {e}")


    return render_template('fortune.html', data=data)

# 네이버 운세
def crawl_naver_fortune(zodiac_name, is_tomorrow=False):
    target = "내일" if is_tomorrow else "오늘"
    # 네이버 운세 검색 URL (더 정확한 경로로 수정)
    url = f"https://search.naver.com/search.naver?query={zodiac_name}+{target}+운세"

    # 실제 브라우저처럼 보이게 하는 필수 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.naver.com'
    }

    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()  # 연결 실패 시 에러 발생
        soup = BeautifulSoup(res.text, 'html.parser')

        # 네이버 운세 텍스트 박스 선택 (여러 경우의 수 대비)
        fortune_box = soup.select_one(".text._content") or soup.select_one(".infothumb .detail")

        if fortune_box:
            return fortune_box.get_text().strip()
        else:
            return f"현재 {zodiac_name} {target} 운세 정보를 찾을 수 없습니다. (네이버 UI 변경 가능성)"

    except Exception as e:
        print(f"에러 발생: {e}")
        return "네이버 서버 연결에 실패했습니다. 잠시 후 다시 시도해주세요."

# 운세 DB
def get_db_fortune(zodiac_name, target_date):
    conn = None
    try:
        conn = Session.get_connection()
        with conn.cursor() as cursor:
            # 1. DB 조회
            sql = "SELECT content FROM fortunes WHERE zodiac_name = %s AND target_date = %s"
            cursor.execute(sql, (zodiac_name, target_date))
            result = cursor.fetchone()

            if result:
                # 튜플/딕셔너리 모든 환경 대응
                return result['content'] if isinstance(result, dict) else result[0]

            # 2. DB에 없으면 크롤링
            is_tomorrow = target_date > datetime.now().date()
            content = crawl_naver_fortune(zodiac_name, is_tomorrow)

            # 3. 크롤링한 내용이 정상일 때만 DB 저장
            if "실패" not in content and "없습니다" not in content:
                insert_sql = "INSERT INTO fortunes (zodiac_name, target_date, content) VALUES (%s, %s, %s)"
                cursor.execute(insert_sql, (zodiac_name, target_date, content))
                conn.commit()

            return content

    except Exception:
        # ❗ 터미널에 아주 상세한 에러 로그를 찍어줍니다. 이걸 확인해야 합니다.
        print("DB/로직 상세 에러 로그 발생!")
        traceback.print_exc()
        return "운세 로직 처리 중 내부 오류가 발생했습니다."
    finally:
        if conn:
            conn.close()

# ----------------------------------------------------------------------------------------------------------------------
#                                                  랜덤 채팅
# ----------------------------------------------------------------------------------------------------------------------

# 대기열: 접속해서 매칭을 기다리는 유저들의 request.sid(고유ID) 저장
socketio = SocketIO(app)
waiting_users = []

# 메인 화면
@app.route('/chat')
def chat():
    return render_template("chat.html")

# 랜덤 매칭
@socketio.on("random_match")
def handle_random_match():
    global waiting_users
    sid = request.sid

# @socketio.on('join')
# def on_join():
#     user_id = request.sid
#
#     if sid in waiting_users:
#         print("이미 대기 중:", sid)
#         return
#
#     if waiting_users:
#         partner_sid = waiting_users.pop(0)
#
#         if partner_sid == sid:
#             waiting_users.append(sid)
#             return
#
#         room_id = str(uuid.uuid4())
#
#         join_room(room_id)
#         socketio.server.enter_room(partner_sid, room_id)
#
#         # 두 명 모두에게 매칭 알림
#         socketio.emit("matched", {"room": room_id}, room=room_id)
#
#         print("매칭 완료:", room_id)
#
#     else:
#         waiting_users.append(request.sid)
#         print("대기열 추가:", request.sid)

# 메시지 전송
@socketio.on('send_message')
def handle_send_message(data):
    room = data.get("room")
    message = data.get("message")

    if not room:
        return

    socketio.emit("receive_message", {
        "user": "상대방",
        "message": message
    }, room=room, include_self=False)

# 퇴장 메세지
@socketio.on("leave_room")
def handle_leave(data):
    room = data.get("room")
    leave_room(room)

    socketio.emit("receive_message", {
        "user": "📢 시스템",
        "message": "상대방이 나갔습니다."
    }, room=room)

# 대기열 제거
@socketio.on("disconnect")
def handle_disconnect():

    sid = request.sid

    if sid in waiting_users:
        waiting_users.remove(sid)
        print("대기열에서 제거:", sid)

@socketio.on('disconnect')
def on_disconnect():

    user_id = request.sid

    if user_id in waiting_users:
        waiting_users.remove(user_id)
    print(f"접속 종료: {user_id}")

# ----------------------------------------------------------------------------------------------------------------------
#                                                 메모장
# ----------------------------------------------------------------------------------------------------------------------
# 메모장 메인 (목록 조회)
@app.route('/memo')
def memo_list():
    if 'user_id' not in session:
        flash('로그인이 필요한 서비스입니다.')
        return redirect(url_for('login'))

    # 팀 프로젝트 규칙: session['user_id']에 PK가 들어있음
    current_user_pk = session.get('user_id')

    memos = fetch_query(
        "SELECT * FROM memos WHERE member_id = %s ORDER BY updated_at DESC",
        (current_user_pk,)
    )
    return render_template('memo_list.html', memos=memos)

# 메모 저장 (신규 / 수정)
@app.route('/memo/save', methods=['POST'])
def memo_save():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '로그인이 필요합니다.'})

        data = request.get_json()
        # [수정] user_pk 대신 세션에 저장된 user_id를 가져옴
        current_user_pk = session.get('user_id')

        # 디버깅용 출력 (변수명 일치시킴)
        print(f"--- 저장 시도 중: user_pk={current_user_pk}, data={data} ---")

        if current_user_pk is None:
            return jsonify({'success': False, 'message': '유저 정보가 없습니다. 다시 로그인하세요.'})

        title = data.get('title') or '제목 없는 메모'
        content = data.get('content', '')
        memo_id = data.get('id')

        if memo_id:
            execute_query("UPDATE memos SET title=%s, content=%s WHERE id=%s AND member_id=%s",
                          (title, content, memo_id, current_user_pk))
        else:
            execute_query("INSERT INTO memos (member_id, title, content) VALUES (%s, %s, %s)",
                          (current_user_pk, title, content))

        return jsonify({'success': True})

    except Exception as e:
        print(f"서버 에러 발생: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 메모 삭제
@app.route('/memo/delete/<int:memo_id>', methods=['POST'])
def memo_delete(memo_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '권한이 없습니다.'})

    # [수정] 여기도 통일
    current_user_pk = session.get('user_id')

    execute_query(
        "DELETE FROM memos WHERE id=%s AND member_id=%s",
        (memo_id, current_user_pk)
    )
    return jsonify({'success': True})

# ----------------------------------------------------------------------------------------------------------------------
#                                                플라스크 실행
# ----------------------------------------------------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('FLASK_APP_PORT', 5000)),
        debug=True,
        allow_unsafe_werkzeug=True
    )
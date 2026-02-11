
from datetime import datetime

from ssl import socket_error


from dotenv import load_dotenv
from flask import send_from_directory
from werkzeug.utils import secure_filename

load_dotenv()

import traceback
import requests
from bs4 import BeautifulSoup
from flask_caching import Cache
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from LMS.common.db import fetch_query, execute_query
from LMS.common.session import Session
from LMS.domain import Board, Score
from math import ceil



app = Flask(__name__)

# 띠별 운세 확인 시 필요
# 캐시 설정 (하루 24시간 동안 보관)
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
@login_required
def mypage():
    user = fetch_query("SELECT * FROM members WHERE id = %s", (session['user_id'],), one=True)

    # COUNT 쿼리도 간단하게 처리 (결과가 없을 수 있으므로 예외처리 살짝 필요하거나 쿼리 수정)
    board_data = fetch_query("SELECT COUNT(*) as cnt FROM boards WHERE member_id = %s", (session['user_id'],), one=True)
    board_count = board_data['cnt'] if board_data else 0

    return render_template('mypage.html', user=user, board_count=board_count)

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


@app.route('/board')
def board_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    # 전체 개수 구하기
    count_sql = "SELECT COUNT(*) as cnt FROM boards"
    total_count = fetch_query(count_sql)[0]['cnt']
    total_pages = ceil(total_count / per_page)

    # [수정] 싫어요(dislike_count) 서브쿼리 추가
    sql = f"""
        SELECT 
            b.*, 
            m.name as writer_name,
            (SELECT COUNT(*) FROM board_likes WHERE board_id = b.id) as like_count,
            (SELECT COUNT(*) FROM board_dislikes WHERE board_id = b.id) as dislike_count,
            (SELECT COUNT(*) FROM board_comments WHERE board_id = b.id) as comment_count
        FROM boards b
        JOIN members m ON b.member_id = m.id
        ORDER BY b.is_pinned DESC, b.id DESC
        LIMIT {per_page} OFFSET {offset}
    """
    rows = fetch_query(sql)

    boards = []
    for row in rows:
        board = Board.from_db(row)
        board.like_count = row['like_count']
        board.dislike_count = row['dislike_count']  # [추가] 싫어요 수 할당
        board.comment_count = row['comment_count']

        # Board 객체에 is_pinned 속성이 없어서 추가
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

    # 2. 게시글 상세 정보 가져오기
    sql = """
        SELECT b.*, m.name as writer_name, m.uid as writer_uid
        FROM boards b
        JOIN members m ON b.member_id = m.id
        WHERE b.id = %s
    """
    row = fetch_query(sql, (board_id,), one=True)
    if not row:
        return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'

    # 3. [수정] 좋아요 & 싫어요 정보 조회
    # 3-1. 전체 카운트 조회
    like_count = fetch_query("SELECT COUNT(*) as cnt FROM board_likes WHERE board_id = %s", (board_id,), one=True)[
        'cnt']
    dislike_count = \
    fetch_query("SELECT COUNT(*) as cnt FROM board_dislikes WHERE board_id = %s", (board_id,), one=True)['cnt']

    # 3-2. 현재 로그인한 사용자의 클릭 여부 확인
    user_liked = False
    user_disliked = False

    if 'user_id' in session:
        # DB의 member_id(PK)를 정확히 알기 위해 user_id(문자열)로 조회
        member_info = fetch_query("SELECT id FROM members WHERE id = %s", (session['user_id'],), one=True)

        if member_info:
            member_pk = member_info['id']

            # 좋아요 여부 체크
            if fetch_query("SELECT 1 FROM board_likes WHERE board_id = %s AND member_id = %s", (board_id, member_pk),
                           one=True):
                user_liked = True

            # 싫어요 여부 체크 (추가됨)
            if fetch_query("SELECT 1 FROM board_dislikes WHERE board_id = %s AND member_id = %s", (board_id, member_pk),
                           one=True):
                user_disliked = True

    # 4. 댓글 및 대댓글 목록 가져오기 (계층형 구조)
    comment_sql = """
            SELECT c.*, m.name as writer_name, m.uid as writer_uid
            FROM board_comments c
            JOIN members m ON c.member_id = m.id
            WHERE c.board_id = %s
            ORDER BY c.created_at ASC
        """
    all_comments = fetch_query(comment_sql, (board_id,))

    # 딕셔너리를 활용해 트리 구조로 변환
    comment_dict = {c['id']: {**c, 'children': []} for c in all_comments}
    root_comments = []

    for c_id, c_data in comment_dict.items():
        parent_id = c_data['parent_id']
        if parent_id and parent_id in comment_dict:
            # 부모가 있다면 부모의 children 리스트에 추가
            comment_dict[parent_id]['children'].append(c_data)
        else:
            # 부모가 없다면 최상위(Root) 댓글
            root_comments.append(c_data)

    # 5. Board 객체 생성 및 데이터 주입
    board = Board.from_db(row)
    board.likes = like_count  # 좋아요 수 주입
    board.dislikes = dislike_count  # [추가] 싫어요 수 주입 (Board 클래스에 필드가 없어도 파이썬이라 들어갑니다)

    return render_template('board_view.html',
                           board=board,
                           user_liked=user_liked,
                           user_disliked=user_disliked,  # [추가] 템플릿으로 전달
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

# 게시물 삭제
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

# 파일 저장 경로 설정
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 자료실 목록
@app.route('/library')
def library_list():
    if 'user_id' not in session:
        return "<script>alert('로그인 후 이용 가능합니다.');location.href='/login';</script>"

    # fetch_query를 사용하면 dictionary=True 문제를 피하면서 깔끔하게 데이터를 가져올 수 있습니다.
    sql = """
        SELECT l.*, m.name as user_name 
        FROM library l 
        JOIN members m ON l.member_id = m.id 
        ORDER BY l.id DESC
    """
    files = fetch_query(sql)  # 프로젝트 공통 함수 활용
    return render_template('library.html', files=files)

# 파일 업로드
@app.route('/library/upload', methods=['POST'])
def library_upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if 'file' not in request.files:
        return "<script>alert('파일이 없습니다.');history.back();</script>"

    file = request.files['file']
    if file.filename == '':
        return "<script>alert('선택된 파일이 없습니다.');history.back();</script>"

    if file:
        original_name = file.filename
        ext = os.path.splitext(original_name)[1]
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')  # 밀리초까지 추가하여 중복 방지
        # 파일명을 유저ID_시간.확장자 형태로 안전하게 생성
        filename = f"{session['user_id']}_{timestamp}{ext}"

        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)  # 서버 저장

        try:
            sql = "INSERT INTO library (member_id, filename, original_name) VALUES (%s, %s, %s)"
            execute_query(sql, (session['user_id'], filename, original_name))
            return f"<script>alert('업로드 완료!');location.href='/library';</script>"
        except Exception as e:
            print(f"DB 저장 에러: {e}")
            return "<script>alert('DB 저장 실패');history.back();</script>"

# 파일 다운로드
@app.route('/library/download/<int:file_id>')
def library_download(file_id):
    # DB에서 파일명 조회
    sql = "SELECT filename, original_name FROM library WHERE id = %s"
    file_data = fetch_query(sql, (file_id,), one=True)

    if not file_data:
        return "<script>alert('DB에 파일 정보가 없습니다.');history.back();</script>"

    filename = file_data['filename']
    original_name = file_data['original_name']

    # 실제 서버 폴더에 파일이 있는지 확인
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    print(f"다운로드 시도 경로: {file_path}")  # 터미널에서 확인용

    if not os.path.exists(file_path):
        return f"<script>alert('서버에 실제 파일이 없습니다. (파일명: {filename})');history.back();</script>"

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=original_name  # 원래 이름으로 다운로드
    )

# 파일 삭제
@app.route('/library/delete/<int:file_id>', methods=['POST'])
def library_delete(file_id):
    if 'user_id' not in session:
        return "<script>alert('로그인이 필요합니다.');history.back();</script>"

    file_info = fetch_query("SELECT filename, member_id FROM library WHERE id = %s", (file_id,), one=True)

    if not file_info:
        return "<script>alert('파일 정보를 찾을 수 없습니다.');history.back();</script>"

    # 본인 확인
    if file_info['member_id'] != session['user_id']:
        return "<script>alert('본인만 삭제 가능합니다.');history.back();</script>"

    try:
        # 실제 파일 삭제
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_info['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)

        # DB 삭제
        execute_query("DELETE FROM library WHERE id = %s", (file_id,))
        return "<script>alert('삭제 완료');location.href='/library';</script>"
    except Exception as e:
        print(f"삭제 에러: {e}")
        return "<script>alert('삭제 처리 중 오류 발생');history.back();</script>"

<<<<<<< Updated upstream
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
#                                                플라스크 실행
# ----------------------------------------------------------------------------------------------------------------------
=======

#--------------------------------------------------
#               랜덤챗
#--------------------------------------------------
import uuid
from flask_socketio import SocketIO, join_room, leave_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # 세션/보안용 키 (필수)
socketio = SocketIO(app)

# -----------------------------------------------------------------------
#                               랜덤 채팅 로직
# -----------------------------------------------------------------------

# 대기열: 접속해서 매칭을 기다리는 유저들의 request.sid(고유ID) 저장
waiting_users = []
>>>>>>> Stashed changes


@app.route('/chat')
def chat():
    return render_template('chat.html')


@socketio.on('join')
def on_join():
    user_id = request.sid

    # 대기열에 본인이 이미 있다면 중복 추가 방지
    if user_id in waiting_users:
        return

    if waiting_users:
        # 대기자가 있으면 첫 번째 대기자와 매칭
        peer_id = waiting_users.pop(0)
        room_id = str(uuid.uuid4())  # 랜덤 방 ID 생성

        # 두 유저를 같은 방으로 입장시킴
        join_room(room_id, sid=user_id)
        join_room(room_id, sid=peer_id)

        # 두 유저에게 매칭 성공과 방 번호를 알림
        emit('matched', {'room': room_id}, room=room_id)
        print(f"매칭 성공! 방 번호: {room_id}")
    else:
        # 대기자가 없으면 대기열에 추가
        waiting_users.append(user_id)
        emit('waiting', {'msg': '상대방을 기다리는 중...'})
        print(f"대기열 추가: {user_id}")


@socketio.on('send_message')
def handle_send_message(data):
    room = data.get('room')
    msg = data.get('msg')
    # 내가 보낸 메시지를 해당 방에 있는 모든 사람(나 포함)에게 전달
    emit('receive_message', {'msg': msg, 'sender': request.sid}, room=room)


@socketio.on('disconnect')
def on_disconnect():
    user_id = request.sid
    # 대기 중에 나갔다면 대기열에서 제거
    if user_id in waiting_users:
        waiting_users.remove(user_id)
    print(f"접속 종료: {user_id}")


# -----------------------------------------------------------------------
#                               플라스크 실행
# -----------------------------------------------------------------------

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
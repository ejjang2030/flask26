from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from LMS.common.db import fetch_query, execute_query
from LMS.common.session import Session
from LMS.domain import Board, Score
from math import ceil

app = Flask(__name__)

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
        print("2",is_pinned)
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

    # 소현
    # 2. SQL 수정: ORDER BY 절에 b.is_pinned DESC 추가
    # is_pinned가 1(고정)인 데이터가 0(일반)보다 먼저 정렬됩니다.
    #

    # [개선] 좋아요 수와 댓글 수를 각각 집계하기 위해 DISTINCT 또는 서브쿼리 사용
    sql = f"""
        SELECT 
            b.*, 
            m.name as writer_name,
            (SELECT COUNT(*) FROM board_likes WHERE board_id = b.id) as like_count,
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
        board.comment_count = row['comment_count'] # 댓글 수 할당
        #Board 객체에 is_pinned 속성이 없어서 추가
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
    # 1. 조회수 증가 (기존 동일)
    try:
        execute_query("UPDATE boards SET visits = visits + 1 WHERE id = %s", (board_id,))
    except Exception as e: print(e)

    # 2. 게시글 상세 정보 (기존 동일)
    sql = """
        SELECT b.*, m.name as writer_name, m.uid as writer_uid
        FROM boards b
        JOIN members m ON b.member_id = m.id
        WHERE b.id = %s
    """
    row = fetch_query(sql, (board_id,), one=True)
    if not row:
        return '<script>alert("존재하지 않는 게시글입니다."); history.back();</script>'

    # 3. 좋아요 정보 조회 (기존 동일)
    like_count = fetch_query("SELECT COUNT(*) as cnt FROM board_likes WHERE board_id = %s", (board_id,), one=True)['cnt']
    user_liked = False
    if 'user_id' in session:
        if fetch_query("SELECT 1 FROM board_likes WHERE board_id = %s AND member_id = %s", (board_id, session['user_id']), one=True):
            user_liked = True

    # 4. [추가] 댓글 및 대댓글 목록 가져오기
    # 정렬 핵심: 부모 댓글 id 순서로 묶되, 그 안에서 생성일 순으로 정렬
    comment_sql = """
            SELECT c.*, m.name as writer_name, m.uid as writer_uid
            FROM board_comments c
            JOIN members m ON c.member_id = m.id
            WHERE c.board_id = %s
            ORDER BY c.created_at ASC
        """
    all_comments = fetch_query(comment_sql, (board_id,))

    # 2. 계층형 트리 구조로 가공
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

    board = Board.from_db(row)
    board.likes = like_count

    return render_template('board_view.html',
                           board=board,
                           user_liked=user_liked,
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
#                                              자료실 (파일 업로드)
# ----------------------------------------------------------------------------------------------------------------------

# 파일 저장 경로 설정 (static 폴더 안)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

# 폴더가 없으면 자동 생성 (OS 오류 방지)
if not os.path.exists(UPLOAD_FOLDER) :
    os.makedirs(UPLOAD_FOLDER, exist_ok = True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 자료실 메인 화면 (서브 메뉴 전용 경로)
@app.route('/library')
def library_list() :
    if 'user_id' not in session :
        return "<script>alert('로그인 후 이용 가능합니다.');location.href='/login';</script>"

    # 폴더 내 파일 목록 읽기
    try :
        files = os.listdir(app.config['UPLOAD_FOLDER'])

    except Exception as e :
        print(f"파일 읽기 오류: {e}")

        files = []

    return render_template('library.html', files=files)

# 파일 업로드
@app.route('/library/upload', methods=['POST'])
def library_upload() :
    if 'file' not in request.files :
        return "<script>alert('파일이 존재하지 않습니다.');history.back();</script>"

    file = request.files['file']
    if file.filename == '' :
        return "<script>alert('선택된 파일이 없습니다.');history.back();</script>"

    if file :

        # 안전한 파일명으로 변경 후 저장
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        return f"<script>alert('{filename} 업로드가 완료되었습니다.');location.href='/library';</script>"

# 파일 삭제
@app.route('/library/delete/<filename>', methods=['POST'])
def library_delete(filename) :
    if 'user_id' not in session :
        return "<script>alert('권한이 없습니다.');history.back();</script>"

    # 보안을 위해 파일명 정제 (중요!)
    filename = secure_filename(filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try :

        if os.path.exists(file_path) :
            os.remove(file_path)  # 실제 파일 삭제
            return f"<script>alert('{filename} 삭제가 완료되었습니다.');location.href='/library';</script>"

        else :
            return "<script>alert('파일을 찾을 수 없습니다.');history.back();</script>"

    except Exception as e :
        print(f"파일 삭제 에러: {e}")
        return "<script>alert('파일 삭제 도중 오류가 발생했습니다.');history.back();</script>"

# ----------------------------------------------------------------------------------------------------------------------
#                                                플라스크 실행
# ----------------------------------------------------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.getenv('FLASK_APP_PORT'), debug=True)
from flask import Flask, render_template, request, redirect, url_for, session
from common import Session
from domain import Board

app = Flask(__name__)
app.secret_key = 'sibaaaaaaaaar'

# ----------------------------------------------- 회원 CRUD -----------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    uid = request.form['uid']
    upw = request.form['upw']
    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:
            sql = 'SELECT id, name, uid, role FROM members WHERE uid = %s AND password = %s'
            cursor.execute(sql, (uid, upw))
            user = cursor.fetchone()

            if user:
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_uid'] = user['uid']
                session['user_role'] = user['role']
                return redirect(url_for('index'))
            else:
                return '<script>alert("아이디나 비번이 틀렸습니다"); history.back();</script>'
    finally:
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    uid = request.form['uid']
    password = request.form['password']
    name = request.form['name']

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM members WHERE uid = %s', (uid,))
            if cursor.fetchone():
                return '<script>alert("이미 존재하는 아이디입니다."); history.back();</script>'

            sql = 'INSERT INTO members (uid, password, name) VALUES (%s, %s, %s)'
            cursor.execute(sql, (uid, password, name))
            conn.commit()
            return '<script>alert("가입 완료"); location.href="/login";</script>'
    except Exception as e:
        print(f'회원가입 에러: {e}')
        return '가입 중 오류 발생. join()을 확인하세요.'
    finally:
        conn.close()

@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                cursor.execute('SELECT * FROM members WHERE id = %s', (session['user_id'],))
                user_info = cursor.fetchone()
                return render_template('members_edit.html', user=user_info)

            # POST 요청 처리
            new_name = request.form.get('new_name')
            new_pw = request.form.get('new_pw')

            if new_pw:
                sql = 'UPDATE members SET name = %s, password = %s WHERE id = %s'
                cursor.execute(sql, (new_name, new_pw, session['user_id']))
            else:
                sql = 'UPDATE members SET name = %s WHERE id = %s'
                cursor.execute(sql, (new_name, session['user_id']))

            conn.commit()
            session['user_name'] = new_name
            return "<script>alert('정보 수정 완료'); location.href='/mypage';</script>"
    except Exception as e:
        print(f'회원수정 에러: {e}')
        return f'수정 중 오류 발생: {e}'
    finally:
        conn.close()


@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 유저 정보 가져오기
            cursor.execute('SELECT * FROM members WHERE id = %s', (session['user_id'],))
            user_info = cursor.fetchone()

            # 💡 수정된 부분: active = 1 인 글만 숫자로 셉니다.
            sql = 'SELECT count(*) AS board_count FROM boards WHERE member_id = %s AND active = 1'
            cursor.execute(sql, (session['user_id'],))

            board_count = cursor.fetchone()['board_count']
            return render_template('mypage.html', user=user_info, board_count=board_count)
    finally:
        conn.close()

# ----------------------------------------------- 게시판 CRUD -----------------------------------------------
@app.route('/board')
def board_list():
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 💡 핵심: 관리자면 전체, 유저면 active=1만 가져오도록 조건을 만듭니다.
            if session.get('user_role') == 'admin':
                where_clause = ""  # 관리자는 조건 없음 (전체 노출)
            else:
                where_clause = "WHERE b.active = 1" # 유저는 활성글만

            sql = f"""
                SELECT b.*, m.name AS writer_name,
                       (SELECT COUNT(*) FROM reports WHERE board_id = b.id) AS report_count
                FROM boards b
                JOIN members m ON b.member_id = m.id
                {where_clause}
                ORDER BY b.id DESC
            """
            cursor.execute(sql)
            rows = cursor.fetchall()
            boards = [Board.from_db(row) for row in rows]
            return render_template('board_list.html', boards=boards)
    finally:
        conn.close()

@app.route('/board/write', methods=['GET', 'POST'])
def board_write():
    if 'user_id' not in session:
        return "<script>alert('로그인 후 이용 가능합니다.'); location.href='/login';</script>"

    if request.method == 'GET':
        return render_template('board_write.html')

    # POST 요청: .get[] -> .get() 으로 수정
    title = request.form.get('title')
    content = request.form.get('content')
    member_id = session.get('user_id')

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = 'INSERT INTO boards (member_id, title, content) VALUES (%s, %s, %s)'
            cursor.execute(sql, (member_id, title, content))
            conn.commit()
        return redirect(url_for('board_list'))
    except Exception as e:
        print(f'글쓰기 에러: {e}')
        return '저장 중 에러 발생'
    finally:
        conn.close()

@app.route('/board/view/<int:board_id>')
def board_view(board_id):
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT b.*, m.name AS writer_name, m.uid AS writer_uid,
                       (SELECT COUNT(*) FROM reports WHERE board_id = b.id) AS report_count
                FROM boards b
                JOIN members m ON b.member_id = m.id
                WHERE b.id = %s
            """
            cursor.execute(sql, (board_id,))
            row = cursor.fetchone()

            if not row:
                return "<script>alert('존재하지 않는 게시글입니다.'); history.back();</script>"

            # --- 이 부분을 아래와 같이 수정하세요 ---
            if row['report_count'] >= 1:
                # 신고가 1개 이상이라도, 세션의 role이 'admin'이면 통과!
                if session.get('user_role') != 'admin':
                    return "<script>alert('신고 접수된 게시글임으로 조회가 불가능합니다.'); history.back();</script>"
            # --------------------------------------

            board = Board.from_db(row)
            return render_template('board_view.html', board=board)
    except Exception as e:
        print(f"상세보기 에러: {e}")
        return "페이지를 불러오는 중 오류가 발생했습니다."
    finally:
        conn.close()

@app.route('/board/edit/<int:board_id>', methods=['GET', 'POST'])
def board_edit(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                sql = "SELECT * FROM boards WHERE id = %s"
                cursor.execute(sql, (board_id,))
                row = cursor.fetchone()

                if not row:
                    return "<script>alert('존재하지 않는 게시글입니다.'); history.back();</script>"

                if row['member_id'] != session.get('user_id'):
                    return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"

                board = Board.from_db(row)
                return render_template('board_edit.html', board=board)

            # POST 처리
            title = request.form.get('title')
            content = request.form.get('content')

            sql = "UPDATE boards SET title = %s, content = %s WHERE id = %s"
            cursor.execute(sql, (title, content, board_id))
            conn.commit()
            return redirect(url_for('board_view', board_id=board_id))
    finally:
        conn.close()


@app.route('/board/delete/<int:board_id>')
def board_delete(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 관리자(admin)인 경우: DB에서 아예 행을 삭제 (Hard Delete)
            if session.get('user_role') == 'admin':
                sql = "DELETE FROM boards WHERE id = %s"
                cursor.execute(sql, (board_id,))
                msg = "관리자 권한으로 게시글을 영구 삭제했습니다."

            # 2. 일반 유저인 경우: 본인 글일 때만 active를 0으로 수정 (Soft Delete)
            else:
                # 본인 확인을 위해 WHERE 절에 member_id를 함께 체크합니다.
                sql = "UPDATE boards SET active = 0 WHERE id = %s AND member_id = %s"
                cursor.execute(sql, (board_id, session['user_id']))

                # 만약 내 글이 아니거나 이미 처리된 글이라서 영향받은 행이 없다면?
                if cursor.rowcount == 0:
                    return "<script>alert('삭제 권한이 없거나 존재하지 않는 게시글입니다.'); history.back();</script>"
                msg = "게시글이 삭제되었습니다."

            conn.commit()
            return f"<script>alert('{msg}'); location.href='/board';</script>"
    except Exception as e:
        print(f'삭제 에러: {e}')
        return "처리 중 오류 발생"
    finally:
        conn.close()


@app.route('/board/report/<int:board_id>', methods=['POST'])
def board_report(board_id):
    if 'user_id' not in session:
        return "<script>alert('로그인 후 신고가 가능합니다.'); history.back();</script>"

    reason = request.form.get('reason')  # 사용자가 선택한 신고 사유
    reporter_id = session['user_id']

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 같은 글을 중복 신고하는지 체크 (선택 사항)
            cursor.execute("SELECT id FROM reports WHERE board_id=%s AND reporter_id=%s", (board_id, reporter_id))
            if cursor.fetchone():
                return "<script>alert('이미 신고한 게시글입니다.'); history.back();</script>"

            # 신고 데이터 삽입
            sql = "INSERT INTO reports (board_id, reporter_id, reason) VALUES (%s, %s, %s)"
            cursor.execute(sql, (board_id, reporter_id, reason))
            conn.commit()

            # (꿀팁) 신고가 5개 이상 쌓이면 게시글을 자동으로 비활성화(active=0) 하는 로직을 여기 넣을 수도 있음!

        return "<script>alert('신고가 접수되었습니다.'); history.back();</script>"
    finally:
        conn.close()


@app.route('/admin/clear_reports/<int:board_id>')
def clear_reports(board_id):
    # 1. 보안 체크: 관리자 세션이 없거나 admin이 아니면 입구컷
    if session.get('user_role') != 'admin':
        return "<script>alert('관리자만 접근 가능합니다.'); history.back();</script>"

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 2. reports 테이블에서 해당 게시글 번호(board_id)와 연결된 모든 신고 삭제
            sql = "DELETE FROM reports WHERE board_id = %s"
            cursor.execute(sql, (board_id,))

            # 3. DB에 반영
            conn.commit()

        return "<script>alert('신고가 초기화되었습니다. 이제 모든 사용자가 게시글을 볼 수 있습니다.'); location.href='/board';</script>"
    except Exception as e:
        print(f"복구 에러 발생: {e}")
        return f"오류가 발생했습니다: {e}"
    finally:
        conn.close()

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
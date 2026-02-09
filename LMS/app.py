# pip install flask
# 플라스크란?
# 파이썬으로 만든  db연동 콘솔프로그램으 웹으로 연결하는 프레임워크임
# 프레임워크 : 미리 만들어 놓은 틀 안에서 작업하는 공간
# app.py = 플라스크로 서버를 동작하기 위한 파일명(기본파일)
# static, templates 폴더 필수 (프론튼용 타일 모이는 곳)
# static 정적파일을 모아놓음 (html, css, javascript)
# templates 동적파일을 모아 놓음 (crud 화면, 레이아웃, index 등....)
from flask import Flask, render_template, request, redirect, url_for, session

from LMS.common import Session

#                팔라스크 프론트연결        요청시 응답, 주소전달  주소생성   상태저장소

app = Flask(__name__)
app.secret_key = 'dfskwdfjsdkfwljfsdlfjsldlsjdf'
# 세션을 사용하기 위해 보안키 설정 (아무 문자열이나 입력)
# RuntimeError: The session is unavailable because no secret key was set.
# Set the secret_key on the application to something unique and secret.

@app.route('/login', methods=['GET', 'POST'])
#    methods는 웹에 동작을 관여한다.
#    GET : URL 주소로 데이터를 처리(보안성 좋지 않음, 빠른)
#    POST : body영역에서 데이터를 처리(보안상 좋음, 대용량에서 많아 사용함)
#    대부분 처음에 화면(HTML 렌더)을 요청할 떄는 GET  방식으로 처리
#    화면에 있는 내용을 백엔드로 전달할 떄는 POST 방식으로 처리
def login(): #http://localhost.5000/login
    if request.method == 'GET': # 처음접속하면 GET 방식으로 화면 출력용
        return render_template('login.html')
        # get방식으로 요청하면 login.htmlㅇ 화면이 나옴
    # login.html에서 action="/login" method="POST"처리 용 코드
    # login.html에서 넘어온 폼 데이터는 uid / upw
    uid = request.form.get('uid') # 요청한 폼내용을 가져옴
    upw = request.form.get('upw') # request  form get
    # print('/login에서 넘어온 폼데이터 출력테스트')
    # print(uid, upw)
    # print('====================================')

    conn = Session.get_connection() # 교사용 db에 접속용 객체
    try: # 예외발생 가능성 있음
        with conn.cursor() as cursor:
            # 1회원 정보 조회
            sql = "SELECT id, name, uid, role FROM members WHERE uid = %s AND password = %s"
            #                                                    uid가 동일 & pwd가 동일
            #           id, name, uid, role 가져온다.
            cursor.execute(sql, (uid, upw)) # 쿼리문 실행
            user = cursor.fetchone() # 쿼리 결과 1개를 가져와 user 변수에 넣음

            if user:
                # 찾은 계정이 있으면 브라우저의 세션영역에 보관한다.
                session['user_id'] = user['id'] # 계정일련번호(회원번호)
                session['user_name'] = user['name'] # 계정이름
                session['user_uid'] = user['uid'] # 계정로그인명
                session['user_role'] = user['role'] # 계정권한
                # 세션에 저장 완료
                # 브라우저에서 f12번 누르고 애플리케이션 탭에서 쿠키 항목에 가면 session 객체가 보임
                # 이것을 삭제하면 로그아웃 처리 됨
                return redirect(url_for('index'))
                # 처리후 이동하는 경로 http://localhost:5000/index로 갑(get 메서드 방식)
            else:
                # 찾은 계정이 없다
                return "<script>alert('아이디나 비번이 틀렸습니다.');history.back();</script>"
                #               경고창발생                       뒤로가기
    finally:
        conn.close() # db 연결 종료

@app.route('/logout') # 기본동작이 get방식이라, methods=['GET'] 생략가능
def logout():
    session.clear() # 세션 비우기
    return redirect(url_for('login')) # http://localhost:5000/login (get방식)

@app.route('/join', methods=['GET', 'POST']) # 회원가입용 함수
def join(): # http://localhost:5000/ get메서드(화면출력) post(화면폼처리용)
    if request.method == 'GET':
        return render_template('join.html') # 로그인화면용 프론트로 보냄

    # POST 메서드 인 경우 (폼으로 데이터가 넘어올때 처리)
    uid = request.form.get('uid')
    password = request.form.get('password')
    name = request.form.get('name') # 폼에서 넘어온 값을 변수에 넣음

    conn = Session.get_connection() # db에 연결
    try: # 예외발생 가능성이 있는 코드
        with conn.cursor() as cursor:
            # 아이디 중복 확인
            cursor.execute('SELECT id FROM members WHERE uid = %s', (uid,))
            if cursor.fetchone():
                return '<script>alert("이미 존재하는 아이디입니다.");history.back();</script>'

            # 회원 정보 저장 (role, active는 기본값이 들어감)
            sql = 'INSERT INTO members (uid, password, name) VALUES (%s, %s, %s)'
            cursor.execute(sql, (uid, password, name))
            conn.commit()
            return '<script>alert("회원가입이 완료되었습니다!"); location.href="/login";</script>'
    except Exception as e: # 예외발생시 실행문
        print(f'회원가입 에러 : {e}')
        return '가입 중 오류가 발생했습니다. \n join()메서드를 확인하세요!!!'

    finally: # 항상 실행문
        conn.close()

@app.route('/member/edit', methods=['GET','POST'])
def member_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    #있으면 db연결 시작
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                #기존 정보 불러오기
                cursor.execute("SELECT * FROM members WHERE id = %s", (session['user_id'],))
                user_info = cursor.fetchone()
                return render_template('member_edit.html', user=user_info)
                #가장 중요한 포인트 : get요청시 페이지(member_edit.html), 객체 전달용 코드(user=user_info)

            #POST 요청 : 정보 업데이트
            new_name = request.form.get('name')
            new_pw = request.form.get('password')

            if new_pw:  #비밀번호 입력시에만 변경
                sql = "UPDATE members SET name = %s, password = %s WHERE id = %s"
                cursor.execute(sql, (new_name, new_pw, session['user_id']))

            else:  #이름만 변경
                sql = "UPDATE members SET name = %s WHERE id = %s"
                cursor.execute(sql, (new_name, session['user_id']))

            conn.commit()
            session['user_name'] = new_name  #세션 이름 정보도 갱신
            return "<script>alert('정보가 수정되었습니다.');location.href='/mypage';</script>"


    except Exception as e:
        print(f"정보 수정 에러:{e}")
        return "수정 중 오류가 발생했습니다.\n member_edit()메서드를 확인하세요."

    finally:
        conn.close()

@app.route('/mypage') # http://localhost:5000/mypage get요청시 처리됨
def mypage():
    if 'user_id' not in session: # 로그인상태인지 확인
        return redirect(url_for('login')) # 로그인아니면 http://localhost:5000/login login으로 보냄

    conn = Session.get_connection() # db연결
    try:
        with conn.cursor() as cursor:
            # 1. 내 상세 정보 조회
            cursor.execute('SELECT * FROM members WHERE id = %s', (session['user_id'],))
            # 로그인한 정보를 가지고 db에서 찾아옴
            user_info = cursor.fetchone() # 찾아온값1개를 user_info에 담음 (dict)

            # 2. 내가 쓴 게시글 개수 조회 (작성하신 boards 테이블 활용)
            cursor.execute('SELECT COUNT(*) AS board_count FROM boards WHERE member_id = %s', (session['user_id'],))
            #                                                   boards 테이블에 조건 member_id 값을 가지고 찾아옴
            #                     개수를 세어 fetchone()에 넣음 -> board_count 이름으로 개수를 가지고 있음
            board_count = cursor.fetchone()['board_count']

            return render_template('mypage.html', user=user_info, board_count=board_count)
            # 결과를 리턴한다.                           mypage.html 에게 user객체와 board_count객체를 담아 보냄
            # 프론트에서 사용하려면 {{ user.???? }} {{ board_count }}
    finally:
        conn.close()

@app.route('/') # url 생성용 코드 http://localhost:5000/ or http://192.168.0.168:5000
def index():
    return render_template('main.html')




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    # host='0.0.0.0' 누가요청하던 응답해라
    # port=5000 플라스크에서 사용하는 포트번호
    # debug=True 콘솔에서 디버그를 보겠다.
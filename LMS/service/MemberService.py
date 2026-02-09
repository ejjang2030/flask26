# Member객체에 curd를 담당, 메뉴용 메서드 등...
from LMS.common import Session
from LMS.domain import Member

class MemberService:
    # 여기는 주소가 아닌 cls로 활용함 -> __init__가 없다.

    @classmethod
    def load(cls): # db에 연결 테스트 목적으로 생성
        conn = Session.get_connection() # lms db를 가져와서 conn에 넣음
        # 예외발생가능 있음
        try :
            with conn.cursor() as cursor: # db에서 가져온 객체 1줄을 cursor라고 함
                cursor.execute("select count(*) as cnt from members")
                #               Member 테이블에서 개수나온 것을 cnt변수에 넣어라
                # cursor.execute() sql문 실행용
                count = cursor.fetchone()['cnt'] # dict 타입으로 나옴 cnt : 5
                #             .fetchone() 1개의 결과가 나올때 readone
                #             .fetchall() 여러개의 결과가 나올때 readall
                #             .fetchmany(3) 3개의 결과만 보고 싶을 때 (최상위3개)
                print(f"시스템에 현재 등록된 회원수는 {count}명 입니다. ")

        except : # 예외발생 문구
            print("MemberServie.load()메서드 오류발생....")

        finally: # 항상 출력되는 코드
            print("데이터베이스 접속 종료됨....")
            conn.close()

    @classmethod
    def login(cls):
        print("\n[로그인]")
        uid = input("아이디: ")
        pw = input("비밀번호: ")

        conn = Session.get_connection()
        # print("Session.get_connection()" + conn)

        try:
            with conn.cursor() as cursor:
                # 1. 아이디와 비밀번호가 일치하는 회원 조회
                sql = "SELECT * FROM members WHERE uid = %s AND password = %s"
                print("sql = " + sql)
                cursor.execute(sql, (uid, pw))
                row = cursor.fetchone()
                # print("row" + row[0])

                if row:
                    member = Member.from_db(row)
                    # 2. 계정 활성화 여부 체크
                    if not member.active:
                        print("비활성화된 계정입니다. 관리자에게 문의하세요.")
                        return

                    Session.login(member)
                    print(f"{member.name}님 로그인 성공 ({member.role})")
                else:
                    print("아이디 또는 비밀번호가 틀렸습니다.")
        except : # 예외발생 문구
            print("MemberServie.login()메서드 오류발생....")
        finally:
            conn.close()

    @classmethod
    def logout(cls):
        # 1. 먼저 세션에 로그인 정보가 있는지 확인
        if not Session.is_login():
            print("\n[알림] 현재 로그인 상태가 아닙니다.")
            return

        # 2. 세션의 로그인 정보 삭제
        Session.logout()
        print("\n[성공] 로그아웃 되었습니다. 안녕히 가세요!")

    @classmethod
    def signup(cls):
        print("\n[회원가입]")
        uid = input("아이디: ")

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. 중복 체크
                check_sql = "SELECT id FROM members WHERE uid = %s"
                cursor.execute(check_sql, (uid,)) # 튜플은 1개여도 쉼표 필수!!!
                # print("cursor.fetchone() : " + cursor.fetchone()[0])
                # SQL 쿼리 결과에서 단 한 개의 행(row)만 튜플(tuple) 형태로 반환합니다.
                # 호출할 때마다 다음 행으로 넘어가며, 더 이상 행이 없으면 None을 반환합니다.
                # 딕셔너리 커서 사용 시 딕셔너리 형태로도 출력됩니다
                if cursor.fetchone():
                    print("이미 존재하는 아이디입니다.")
                    return

                pw = input("비밀번호: ")
                name = input("이름: ")

                # 2. 데이터 삽입
                insert_sql = "INSERT INTO members (uid, password, name) VALUES (%s, %s, %s)"
                cursor.execute(insert_sql, (uid, pw, name))
                conn.commit()
                print("회원가입 완료! 로그인해 주세요.")
        except Exception as e:
            conn.rollback()
            # 트랜젝션 : with안쪽에 2개이상의 sql문이 둘다 true일때는 commit()
            #                    2중 한개라도 오류가 발생하면 rollback()
            print(f"회원가입 오류: {e}")
        finally:
            conn.close()

    @classmethod
    def modify(cls): # 회원 수정 메서드
        if not Session.is_login():
            print("로그인 후 이용 가능합니다.")
            return


        member = Session.login_member
        print(f"내정보확인 : {member}") # Member.__str__()
        print("\n[내 정보 수정]\n1. 이름 변경  2. 비밀번호 변경 3. 계정비활성 및 탈퇴 0. 취소")
        sel = input("선택: ")

        new_name = member.name
        new_pw = member.pw

        if sel == "1":
            new_name = input("새 이름: ")
        elif sel == "2":
            new_pw = input("새 비밀번호: ")
        elif sel == "3":
            print("회원 중지 및 탈퇴를 진행합니다.")
            cls.delete()
        else:
            return

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE members SET name = %s, password = %s WHERE id = %s"
                cursor.execute(sql, (new_name, new_pw, member.id))
                conn.commit()

                # 메모리(세션) 정보도 동기화
                member.name = new_name
                member.pw = new_pw
                print("정보 수정 완료")
        finally:
            conn.close()

    @classmethod
    def delete(cls):
        if not Session.is_login(): return
        member = Session.login_member

        print("\n[회원 탈퇴]\n1. 완전 탈퇴  2. 계정 비활성화")
        sel = input("선택: ")

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                if sel == "1":
                    sql = "DELETE FROM members WHERE id = %s"
                    cursor.execute(sql, (member.id,))
                    print("회원 탈퇴 완료")
                elif sel == "2":
                    sql = "UPDATE members SET active = FALSE WHERE id = %s"
                    cursor.execute(sql, (member.id,))
                    print("계정 비활성화 완료")

                conn.commit()
                Session.logout()
        finally:
            conn.close()
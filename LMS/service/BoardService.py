from LMS.common.session import Session # 로그인정보, db정보
from LMS.domain.Board import Board # oop Board 객체

class BoardService:

    @classmethod
    def run(cls):
        if not Session.is_login():
            print("로그인 후 이용 가능합니다.")
            return

        while True: # board 주메뉴
            print(f"\n====== MBC 게시판 ({Session.login_member.name}접속중.) ======")
            cls.list_board()
            print("1. 글 쓰기")
            print("2. 글 상세 보기 (수정/삭제 가능)")
            print("0. 뒤로가기")

            sel = input(">>> ")
            if sel == "1":
                cls.write_board()
            elif sel == "2":
                cls.view_detail()

            elif sel == "0":
                break

    @classmethod
    def list_board(cls):
        print("\n" + "=" * 60)
        print(f"{'번호':<5} | {'제목':<25} | {'작성자':<10} | {'작성일'}")
        print("-" * 60)

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # members 테이블과 JOIN하여 작성자 이름(name)을 가져옵니다.
                sql = """
                         SELECT b.*, m.name FROM boards b
                         JOIN members m ON b.member_id = m.id
                         ORDER BY b.id DESC \
                         """
                cursor.execute(sql)
                datas = cursor.fetchall()
                for data in datas:
                    # 날짜 형식 처리 (YYYY-MM-DD 형식으로 출력)
                    date_str = data['created_at'].strftime('%Y-%m-%d')
                    print(f"{data['id']:<5} | {data['title']:<25} | {data['name']:<10} | {date_str}")
        finally:
            conn.close()
        print("=" * 60)

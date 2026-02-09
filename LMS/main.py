# 주 실행코드 (메인메뉴등을 관리한다.)
from LMS.service import *
from LMS.common.session import Session


def main():
    # 프로그램 시작용 코드
    MemberService.load()

    run = True
    while run:
        print("""
        ==========================
         MBC 아카데미 관리 시스템
        ==========================
        1. 회원가입  2. 로그인 3. 로그아웃
        4. 회원관리  
        5. 게시판  6. 성적관리 7. 상품몰
        9. 종료
        """)
        member = Session.login_member # None
        if member is None:
            print("현재 로그인 상태가 아닙니다.")
        else:
            print(f"{member.name}님 환영합니다.")

        sel = input(">>>")
        if sel == "1":
            print("회원가입 서비스로 진입합니다.")
            MemberService.signup()
        elif sel == "2":
            print("로그인 서비스로 진입합니다.")
            MemberService.login()
        elif sel == "3":
            print("로그아웃을 진행합니다.")
            MemberService.logout()
        elif sel == "4":
            print("회원관리 서비스로 진입합니다.")
            MemberService.modify()
        elif sel == "5":
            print("게시판 서비스로 진입합니다.")
            BoardService.run()
        elif sel == "6":
            print("성적관리 서비스로 진입합니다.")
            ScoreService.run()
        elif sel == "9":
            print("LMS 서비스를 종료합니다.")
            run = False
# main() 종료

if __name__ == "__main__":
    main()

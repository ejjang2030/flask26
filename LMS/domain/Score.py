class Score:
    def __init__(self, member_id, kor, eng, math, id=None):
        self.id = id  # scores 테이블의 PK
        self.member_id = member_id  # members 테이블의 id와 연결된 FK
        self.kor = kor
        self.eng = eng
        self.math = math

    # 파이썬 계산 프로퍼티 (메서드지만 변수처럼 써먹는다.)
    @property
    def total(self):  # Score.total -> 계산됨
        return self.kor + self.eng + self.math

    @property
    def avg(self):
        return round(self.total / 3, 2)

    @property
    def grade(self):
        avg = self.avg
        if avg >= 90:
            return "A"
        elif avg >= 80:
            return "B"
        elif avg >= 70:
            return "C"
        else:
            return "F"

    @classmethod
    def from_db(cls, row: dict):
        """DB 딕셔너리에서 member_id 기반으로 객체 생성"""
        if not row:
            return None

        return cls(
            id=row.get('id'),
            member_id=row.get('member_id'),  # uid 대신 member_id 사용
            kor=int(row.get('korean', 0)),
            eng=int(row.get('english', 0)),
            math=int(row.get('math', 0))
        )
class Board:
    def __init__(
            self,
            id,
            title,
            content,
            member_id,
            active=True,
            writer_name=None,
            created_at=None,
            writer_uid=None,
            visits=0,
            likes=0,
            report_count=0
    ):
        self.id = id  # DB의 PK
        self.title = title
        self.content = content
        self.member_id = member_id  # 작성자의 고유 번호(FK)
        self.active = active  # 삭제 여부 (boolean 1/0)

        # JOIN을 통해 가져올 추가 정보들 (선택 사항)
        self.writer_name = writer_name
        self.created_at = created_at
        self.writer_uid = writer_uid
        self.visits = visits
        self.likes = likes
        self.report_count = report_count

    @classmethod
    def from_db(cls, row: dict):
        if not row: return None
        # db에 있ㄴ느 내용의 1줄을 dict 타입으로 가져와 객체로 만듬.
        return cls(
            id=row.get('id'),
            title=row.get('title'),
            content=row.get('content'),
            member_id=row.get('member_id'),
            active=bool(row.get('active')), # 현재 미구현!
            # JOIN 쿼리 시 사용할 이름과 아이디
            writer_name=row.get('writer_name'),
            created_at=row.get('created_at'),
            writer_uid=row.get('writer_uid'),
            visits=row.get('visits'),
            report_count=row.get('report_count', 0)
        )
import os
import sys

# 1. 현재 파일(app.py)이 있는 루트 경로를 파이썬 경로에 강제로 등록
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 2. 이제 파이썬이 루트를 알고 있으므로 LMS 폴더를 찾아갈 수 있습니다.
try:
    from LMS.app import socketio
except ImportError as e:
    # 만약 에러가 나면 로그에서 정확한 이유를 볼 수 있게 출력
    print(f"Import failed: {e}")
    raise e

# Vercel이 실행할 변수
app = socketio
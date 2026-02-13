import sys
import os

# 현재 폴더 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# [수정] socketio가 아니라 진짜 Flask 객체인 'app'을 가져옵니다.
from LMS.app import app

# Vercel이 실행할 객체임을 명시
app = app
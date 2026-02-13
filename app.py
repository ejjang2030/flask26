import sys
import os

# 현재 폴더 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 진짜 Flask 앱 가져오기
from LMS.app import app

# Vercel용 변수
app = app
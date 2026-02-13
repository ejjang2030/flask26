import os
import sys

# 현재 위치(api 폴더)의 부모(루트)를 경로에 추가해서 LMS 폴더를 찾을 수 있게 함
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# LMS 폴더 안의 app.py에서 flask 객체(app)를 가져옴
from LMS.app import app

# Vercel은 이 'app' 객체를 찾아서 실행합니다.
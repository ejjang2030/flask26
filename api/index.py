from flask import Flask
import sys
import os

# 현재 위치(api)의 부모 폴더(루트)를 경로에 추가
# 그래야 옆방에 있는 LMS 폴더를 찾을 수 있음
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# LMS 폴더 안의 app.py에서 'app' 객체 가져오기
from LMS.app import app

# Vercel은 이 파일 안에 있는 'app' 변수를 찾아서 실행합니다.
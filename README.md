# 📘 Communa LMS Project

**Communa LMS** 프로젝트를 위한 개발 환경 설정 가이드입니다.
Flask와 TiDB(MySQL)를 사용하며, 팀원들이 쉽게 개발할 수 있도록 환경이 세팅되어 있습니다.

아래 순서대로 따라오시면 **5분 안에 실행** 가능합니다! 🚀

---

## 🛠️ 1. 설치 및 세팅 (Installation)

### 1-1. 프로젝트 클론

```bash
git clone https://github.com/ejjang2030/flask26.git
cd communa
```

---

## 💻 2. OS별 환경설정

### 🍎 Mac / Linux

#### 2-1. 가상환경 생성

```bash
python3 -m venv .venv
```

#### 2-2. 가상환경 활성화

```bash
source .venv/bin/activate
```

---

### 🪟 Windows

#### 2-1. 가상환경 생성

```bash
python -m venv .venv
```

#### 2-2. 가상환경 활성화

```bash
.venv\Scripts\Activate.ps1
```

---

## 📦 3. 라이브러리 설치

```bash
pip install -r requirements.txt
```

---

## 🔐 4. 환경변수 설정

`.env` 파일을 **루트 디렉터리**에 위치시켜 주세요.

```
communa/
 ├─ app/
 ├─ .venv/
 ├─ requirements.txt
 ├─ .env   ← 여기에 위치
 └─ README.md
```

---

## ✅ 실행 준비 완료

이제 Flask 서버 실행만 하면 바로 개발을 시작할 수 있습니다! 🎉

@echo off
echo Starting Pharma Data Integrity Inspector...
echo.

REM Start Backend
echo Starting Backend on http://localhost:8000
start "Backend" cmd /k "cd backend && .\.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --reload"

REM Wait for backend to start
timeout /t 5 /nobreak >nul

REM Start Frontend
echo Starting Frontend on http://localhost:5173
start "Frontend" cmd /k "cd frontend && npx vite --host 0.0.0.0 --port 5173"

echo.
echo Servers starting...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Press any key to exit this window...
pause >nul

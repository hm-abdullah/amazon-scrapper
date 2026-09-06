import sys
import subprocess
from pathlib import Path

root_dir = Path(__file__).resolve().parent
backend_venv_python = root_dir / "backend" / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

if not backend_venv_python.exists():
    print(f"Error: Backend virtualenv not found at {backend_venv_python}")
    sys.exit(1)

cmd = [str(backend_venv_python), "-m", "uvicorn", "backend.app.main:app", "--reload", "--port", "8000"]
print("Starting FastAPI Backend server at http://localhost:8000...")
subprocess.run(cmd, cwd=root_dir)

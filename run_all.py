"""
Single-command startup: launches the FastAPI backend and the React frontend
together, so you don't need two separate terminals for local development.

Usage:
    python run_all.py

Requires:
    - backend/venv already created with dependencies installed (see README)
    - frontend/node_modules already installed (npm install)
    - Postgres + Redis already running (docker compose up postgres redis -d)
"""
import subprocess
import sys
import os
import signal
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
FRONTEND_DIR = os.path.join(ROOT, "frontend")

processes = []


def kill_ports(ports=(8000, 5173)):
    """Clean up any leftover processes on target ports before launching."""
    if os.name == "nt":
        for port in ports:
            try:
                out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
                for line in out.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and "LISTENING" in parts:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != os.getpid():
                            subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        time.sleep(1)


def start(cmd, cwd, name, env=None):
    print(f"[run_all] starting {name}: {' '.join(cmd)}")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.Popen(cmd, cwd=cwd, env=full_env)
    processes.append((name, proc))
    return proc


def shutdown(*_):
    print("\n[run_all] stopping all services...")
    for name, proc in processes:
        print(f"  stopping {name}")
        try:
            if os.name == "nt":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    kill_ports((8000, 5173))

    # Ensure Docker CLI path is available in environment
    for p in [
        os.path.expanduser(r"~\AppData\Local\Programs\DockerDesktop\resources\bin"),
        r"C:\Program Files\Docker\Docker\resources\bin",
    ]:
        if os.path.exists(p) and p not in os.environ.get("PATH", ""):
            os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]

    # Attempt to start postgres & redis containers via docker compose
    try:
        print("[run_all] checking and starting database & redis via docker compose...")
        res = subprocess.run(["docker", "compose", "up", "postgres", "redis", "-d"], cwd=ROOT, capture_output=True, text=True)
        if res.returncode == 0:
            print("[run_all] PostgreSQL (pgvector) and Redis containers are running.")
        else:
            print("[run_all] Notice: Docker Compose could not start containers automatically.")
            print("[run_all] Please make sure Docker Desktop is running.")
    except Exception as exc:
        print(f"[run_all] Notice: Could not run docker command ({exc}).")

    venv_python = (
        os.path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join(BACKEND_DIR, ".venv", "bin", "python")
    )
    if not os.path.exists(venv_python):
        venv_python = (
            os.path.join(BACKEND_DIR, "venv", "Scripts", "python.exe")
            if os.name == "nt"
            else os.path.join(BACKEND_DIR, "venv", "bin", "python")
        )
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    backend_env = {"PYTHONPATH": BACKEND_DIR}
    start(
        [python_exe, "-m", "uvicorn", "app.main:app", "--app-dir", BACKEND_DIR, "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=BACKEND_DIR,
        name="backend (FastAPI)",
        env=backend_env,
    )
    time.sleep(2)  # give the backend a head start before the frontend proxies to it

    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    start([npm_cmd, "run", "dev"], cwd=FRONTEND_DIR, name="frontend (Vite)")

    print("\n[run_all] Backend:  http://localhost:8000/docs")
    print("[run_all] Frontend: http://localhost:5173")
    print("[run_all] Press Ctrl+C to stop both.\n")

    # keep the main thread alive while the child processes run
    try:
        while True:
            time.sleep(1)
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"[run_all] {name} exited unexpectedly (code {proc.returncode})")
                    shutdown()
    except KeyboardInterrupt:
        shutdown()

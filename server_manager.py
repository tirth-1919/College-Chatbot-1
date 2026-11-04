"""server_manager.py

Robust, independent and unified process manager for the AI FAQ College Chat Bot.
Powers user.py and admin.py with live Uvicorn ("Unicorn") and Next.js log streaming in terminal.
Supports running Admin Side, User Side, or All Services unified with zero process interference.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
LOGS_DIR = ROOT / "logs"

# Ensure UTF-8 output and enable ANSI colors on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        hOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(hOut, ctypes.byref(mode)):
            kernel32.SetConsoleMode(hOut, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass

# Terminal ANSI color constants
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_DIM = "\033[90m"
CLR_CYAN = "\033[36m"
CLR_GREEN = "\033[32m"
CLR_MAGENTA = "\033[35m"
CLR_YELLOW = "\033[33m"
CLR_RED = "\033[31m"
CLR_BLUE = "\033[34m"


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is actively being LISTENED on (ignores TIME_WAIT connections)."""
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                f"netstat -ano | findstr :{port}",
                shell=True, text=True, stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 4 and "LISTENING" in parts:
                    return True
            return False
        except Exception:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def get_pid_using_port(port: int) -> int | None:
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                f"netstat -ano | findstr :{port}",
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        return int(pid)
        except Exception:
            return None
    return None


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                f'tasklist /FI "PID eq {pid}" /NH',
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return str(pid) in out
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def kill_process_tree(pid: int) -> None:
    """Kill a process and all its children safely."""
    if not pid or not is_pid_running(pid):
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def check_http_health(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HealthChecker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status < 400
    except Exception:
        return False


def wait_for_health(url: str, timeout: float = 30.0, interval: float = 0.5) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if check_http_health(url):
            return True
        time.sleep(interval)
    return False


def wait_for_backend(proc: subprocess.Popen, url: str, timeout: float = 30.0, interval: float = 0.5) -> bool:
    """Wait for an HTTP response, while failing promptly if Uvicorn exits."""
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False
        if check_http_health(url):
            return True
        time.sleep(interval)
    return False


def configure_task_broker(env: dict[str, str]) -> dict[str, str]:
    """Use a project-local Celery queue in development when Redis is absent."""
    redis_url = env.get("REDIS_URL", "")
    app_env = env.get("APP_ENV", "")
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key.strip() == "REDIS_URL" and not redis_url:
                redis_url = value.strip().strip("\"'")
            elif key.strip() == "APP_ENV" and not app_env:
                app_env = value.strip().strip("\"'")
    app_env = (app_env or "development").lower()
    if redis_url.startswith(("redis://", "rediss://")) and app_env == "development":
        parsed = urlparse(redis_url)
        try:
            with socket.create_connection((parsed.hostname or "localhost", parsed.port or 6379), timeout=0.4):
                pass
        except OSError:
            env["REDIS_URL"] = "filesystem://"
    elif not redis_url and app_env == "development":
        env["REDIS_URL"] = "filesystem://"
    return env


class ServiceManager:
    def __init__(self, side: str):
        assert side in ("user", "admin"), "side must be 'user' or 'admin'"
        self.side = side
        self.side_upper = side.upper()
        self.backend_port = 8000 if side == "user" else 8001
        self.frontend_port = 3000 if side == "user" else 3001
        self.frontend_dir = FRONTEND_DIR / ("user-app" if side == "user" else "admin-app")
        self.backend_health_url = f"http://127.0.0.1:{self.backend_port}/health"
        self.frontend_url = f"http://localhost:{self.frontend_port}"

        self.side_log_dir = LOGS_DIR / side
        self.side_log_dir.mkdir(parents=True, exist_ok=True)
        self.pids_file = self.side_log_dir / "pids.json"
        self.stop_flag_file = self.side_log_dir / "stop.flag"
        self.backend_log_file = self.side_log_dir / "backend.log"
        self.frontend_log_file = self.side_log_dir / "frontend.log"
        self.worker_log_file = self.side_log_dir / "worker.log"
        self.launcher_log_file = self.side_log_dir / "launcher.log"

        self.backend_proc: subprocess.Popen | None = None
        self.frontend_proc: subprocess.Popen | None = None
        self.worker_proc: subprocess.Popen | None = None
        self._shutting_down = False
        self._ready = False

        # Color tags for terminal streaming
        if self.side == "admin":
            self.backend_tag = f"{CLR_CYAN}[ADMIN-BACKEND]{CLR_RESET}"
            self.frontend_tag = f"{CLR_MAGENTA}[ADMIN-FRONTEND]{CLR_RESET}"
        else:
            self.backend_tag = f"{CLR_GREEN}[USER-BACKEND]{CLR_RESET}"
            self.frontend_tag = f"{CLR_YELLOW}[USER-FRONTEND]{CLR_RESET}"

    def log(self, message: str) -> None:
        timestamp = get_timestamp()
        line = f"[{timestamp}] [{self.side_upper}] {message}\n"
        try:
            with open(self.launcher_log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def load_pids(self) -> dict[str, int]:
        if not self.pids_file.exists():
            return {}
        try:
            return json.loads(self.pids_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_pids(self, pids: dict[str, int]) -> None:
        data = {
            **pids,
            "side": self.side,
            "updated_at": get_timestamp(),
        }
        self.pids_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear_pids(self) -> None:
        if self.pids_file.exists():
            try:
                self.pids_file.unlink()
            except OSError:
                pass

    def is_running(self) -> bool:
        pids = self.load_pids()
        b_pid = pids.get("backend")
        f_pid = pids.get("frontend")
        b_running = b_pid and is_pid_running(b_pid) and is_port_in_use(self.backend_port)
        f_running = f_pid and is_pid_running(f_pid) and is_port_in_use(self.frontend_port)
        w_pid = pids.get("worker")
        w_running = self.side == "admin" and w_pid and is_pid_running(w_pid)
        return bool(b_running or f_running or w_running)

    def check_ports_available(self) -> tuple[bool, str]:
        pids = self.load_pids()
        # Backend port check
        if is_port_in_use(self.backend_port):
            occupant_pid = get_pid_using_port(self.backend_port)
            if occupant_pid and occupant_pid == pids.get("backend"):
                return False, f"{self.side_upper} Backend is already running (PID {occupant_pid})."
            return False, f"Port {self.backend_port} is occupied by PID {occupant_pid or 'unknown'} (not managed by {self.side} launcher)."

        # Frontend port check
        if is_port_in_use(self.frontend_port):
            occupant_pid = get_pid_using_port(self.frontend_port)
            if occupant_pid and occupant_pid == pids.get("frontend"):
                return False, f"{self.side_upper} Frontend is already running (PID {occupant_pid})."
            return False, f"Port {self.frontend_port} is occupied by PID {occupant_pid or 'unknown'} (not managed by {self.side} launcher)."

        return True, ""

    def start_backend(self) -> subprocess.Popen:
        self.log(f"Starting Backend on port {self.backend_port}")

        # On Windows, wait up to 15 s for TIME_WAIT sockets to clear before binding
        if sys.platform == "win32":
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind(("127.0.0.1", self.backend_port))
                    break  # bind succeeded — port is usable
                except OSError:
                    print(f"[WAITING]  Port {self.backend_port} in TIME_WAIT, retrying...", flush=True)
                    time.sleep(2)

        env = os.environ.copy()
        env["APP_SIDE"] = self.side
        env["PORT"] = str(self.backend_port)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        configure_task_broker(env)

        # Start uvicorn with access logging and info level so unicorn logs show in terminal
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            f"app.{self.side}_main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.backend_port),
            "--access-log",
            "--log-level",
            "info",
            "--timeout-graceful-shutdown",
            "0",
        ]

        backend_log = open(self.backend_log_file, "a", encoding="utf-8")
        backend_log.write(f"\n--- Starting {self.side_upper} Backend at {get_timestamp()} ---\n")
        backend_log.flush()

        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd,
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            text=True,
            bufsize=1,
        )
        self.backend_proc = proc
        self.log(f"Backend started with PID {proc.pid}")

        # Stream all Uvicorn ("unicorn") and backend logs directly to terminal
        def stream_backend_output():
            for line in iter(proc.stdout.readline, ""):
                if line:
                    backend_log.write(line)
                    backend_log.flush()
                    clean = line.rstrip("\r\n")
                    if not clean.strip():
                        continue
                    # Live terminal display of Uvicorn and FastAPI logs
                    print(f"{self.backend_tag} {clean}", flush=True)

        threading.Thread(target=stream_backend_output, daemon=True).start()
        return proc

    def start_worker(self) -> subprocess.Popen:
        """Start one shared Celery worker from the Admin Side launcher."""
        self.log("Starting Celery worker")
        env = configure_task_broker(os.environ.copy())
        env["APP_SIDE"] = "admin"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        with open(self.worker_log_file, "a", encoding="utf-8") as worker_log:
            worker_log.write(f"\n--- Starting worker at {get_timestamp()} ---\n")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "app.worker:celery", "worker", "--pool=solo", "--loglevel=INFO"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            text=True,
            bufsize=1,
        )
        self.worker_proc = proc
        self.log(f"Celery worker started with PID {proc.pid}")

        def stream_worker_output():
            with open(self.worker_log_file, "a", encoding="utf-8") as worker_log:
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        worker_log.write(line)
                        worker_log.flush()
                        print(f"{self.backend_tag} [WORKER] {line.rstrip()}", flush=True)

        threading.Thread(target=stream_worker_output, daemon=True).start()
        return proc

    def start_frontend(self) -> subprocess.Popen:
        self.log(f"Starting Frontend on port {self.frontend_port}")
        env = os.environ.copy()
        env["PORT"] = str(self.frontend_port)
        env["NEXT_PUBLIC_APP_SIDE"] = self.side
        env["NEXT_DIST_DIR"] = f".next-{self.side}"
        # Keep frontend and API on the same hostname so SameSite=Lax auth cookies
        # are sent on cross-origin fetches (localhost:3000 -> localhost:8000).
        env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{self.backend_port}/api/v1"
        if self.side == "admin":
            env["NEXT_PUBLIC_ADMIN_API_URL"] = f"http://localhost:{self.backend_port}/api/v1"

        frontend_log = open(self.frontend_log_file, "a", encoding="utf-8")
        frontend_log.write(f"\n--- Starting {self.side_upper} Frontend at {get_timestamp()} ---\n")
        frontend_log.flush()

        next_bin = FRONTEND_DIR / "node_modules" / "next" / "dist" / "bin" / "next"
        if next_bin.exists():
            cmd = ["node", str(next_bin), "dev", "-p", str(self.frontend_port), "-H", "0.0.0.0"]
        else:
            cmd = ["npm", "run", "dev", "--", "-p", str(self.frontend_port), "-H", "0.0.0.0"]

        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        use_shell = not next_bin.exists() and sys.platform == "win32"
        proc = subprocess.Popen(
            cmd,
            cwd=self.frontend_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=use_shell,
            creationflags=flags,
            text=True,
            bufsize=1,
        )
        self.frontend_proc = proc
        self.log(f"Frontend started with PID {proc.pid}")

        # Stream Next.js and frontend logs directly to terminal
        def stream_frontend_output():
            for line in iter(proc.stdout.readline, ""):
                if line:
                    frontend_log.write(line)
                    frontend_log.flush()
                    clean = line.rstrip("\r\n")
                    if not clean.strip():
                        continue
                    # Skip heavy static webpack chunk requests but show everything else
                    if any(x in clean for x in ("_next/static/webpack", "favicon.ico")):
                        continue
                    print(f"{self.frontend_tag} {clean}", flush=True)

        threading.Thread(target=stream_frontend_output, daemon=True).start()
        return proc

    def stop(self) -> None:
        self._shutting_down = True
        self._ready = False
        try:
            self.stop_flag_file.write_text(get_timestamp(), encoding="utf-8")
        except Exception:
            pass

        self.log(f"Stopping {self.side_upper} Side services...")
        pids = self.load_pids()

        # 1. Kill launcher first if called from external CLI
        l_pid = pids.get("launcher")
        current_pid = os.getpid()
        if l_pid and l_pid != current_pid:
            self.log(f"Stopping Launcher PID {l_pid}")
            kill_process_tree(l_pid)

        # 2. Kill Frontend
        f_pid = (self.frontend_proc.pid if self.frontend_proc else None) or pids.get("frontend")
        if f_pid:
            self.log(f"Stopping Frontend PID {f_pid}")
            kill_process_tree(f_pid)

        # 3. Kill Backend
        b_pid = (self.backend_proc.pid if self.backend_proc else None) or pids.get("backend")
        if b_pid:
            self.log(f"Stopping Backend PID {b_pid}")
            kill_process_tree(b_pid)

        w_pid = (self.worker_proc.pid if self.worker_proc else None) or pids.get("worker")
        if w_pid:
            self.log(f"Stopping Worker PID {w_pid}")
            kill_process_tree(w_pid)

        # 4. Clean any lingering process holding the ports
        occ_b = get_pid_using_port(self.backend_port)
        if occ_b and occ_b != current_pid:
            kill_process_tree(occ_b)
        occ_f = get_pid_using_port(self.frontend_port)
        if occ_f and occ_f != current_pid:
            kill_process_tree(occ_f)

        # Clear tracked pids
        self.clear_pids()
        if self.stop_flag_file.exists():
            try:
                self.stop_flag_file.unlink()
            except OSError:
                pass
        self.log(f"{self.side_upper} Side services stopped.")

    def run(self) -> int:
        print("=" * 55)
        print("            AI FAQ COLLEGE CHAT BOT")
        print(f"                 {self.side_upper} SIDE")
        print("    🦄 FastAPI + Uvicorn ('Unicorn') ASGI Server")
        print("    ▲  Next.js Frontend Development Server")
        print("=" * 55)
        print()

        if self.stop_flag_file.exists():
            try:
                self.stop_flag_file.unlink()
            except OSError:
                pass

        # Check if already running or if ports are occupied
        available, reason = self.check_ports_available()
        if not available:
            print(f"[CONFLICT] {reason}")
            print(f"Tip: Run 'python admin.py stop' to terminate existing services.")
            self.log(f"Port conflict / already running: {reason}")
            return 1

        # 1. Start Backend (Uvicorn)
        print(f"[STARTING] {self.side.capitalize()} Backend (FastAPI on Uvicorn)...")
        self.start_backend()
        print(f"[CHECKING] Backend Health ({self.backend_health_url})...")
        if not wait_for_backend(self.backend_proc, self.backend_health_url, timeout=90.0):
            print(f"[ERROR] {self.side.capitalize()} Backend did not become available on {self.backend_health_url}")
            if self.backend_proc.poll() is not None:
                print(f"[ERROR] Backend process exited with code {self.backend_proc.returncode}.")
            print(f"[TIP]   See log for details: {self.backend_log_file}")
            self.log("Backend failed health check.")
            self.stop()
            return 1
        print(f"[HEALTHY]  {self.side.capitalize()} Backend - Port {self.backend_port} (PID {self.backend_proc.pid})")
        print()

        if self.side == "admin":
            print("[STARTING] Admin task worker (Celery)...")
            self.start_worker()
            time.sleep(1.0)
            if self.worker_proc.poll() is not None:
                print(f"[ERROR] Admin task worker exited with code {self.worker_proc.returncode}; see {self.worker_log_file}")
                self.stop()
                return 1
            print(f"[HEALTHY]  Admin task worker (PID {self.worker_proc.pid})")
            print()

        # 2. Start Frontend (Next.js)
        print(f"[STARTING] {self.side.capitalize()} Frontend (Next.js dev)...")
        self.start_frontend()
        print(f"[CHECKING] Frontend Readiness ({self.frontend_url})...")
        if wait_for_health(self.frontend_url, timeout=30.0):
            print(f"[HEALTHY]  {self.side.capitalize()} Frontend - Port {self.frontend_port} (PID {self.frontend_proc.pid})")
        else:
            print(f"[RUNNING]  {self.side.capitalize()} Frontend - Port {self.frontend_port} (PID {self.frontend_proc.pid})")
        print()

        # Save active PIDs including launcher PID
        pids = {
            "launcher": os.getpid(),
            "backend": self.backend_proc.pid,
            "frontend": self.frontend_proc.pid,
        }
        if self.worker_proc:
            pids["worker"] = self.worker_proc.pid
        self.save_pids(pids)

        # 3. Ready Banner
        print("=" * 55)
        print(f"               {self.side_upper} SIDE READY")
        print("=" * 55)
        print()
        print(f"  • Frontend:    {self.frontend_url}")
        print(f"  • Backend:     http://localhost:{self.backend_port}")
        print(f"  • API Docs:    http://localhost:{self.backend_port}/docs")
        print(f"  • Health:      {self.backend_health_url}")
        print()
        print("-" * 55)
        print("    LIVE TERMINAL OUTPUT (UVICORN & NEXT.JS LOGS)")
        print("-" * 55)
        print(f"Press CTRL+C to stop {self.side.capitalize()} Side cleanly.")
        print()

        self._ready = True

        # 4. Monitor and Crash Recovery
        restart_counts: dict[str, list[float]] = {"backend": [], "frontend": [], "worker": []}
        MAX_RESTARTS_IN_WINDOW = 3
        WINDOW_SECONDS = 60.0

        try:
            while not self._shutting_down:
                if self.stop_flag_file.exists():
                    self.log("Stop flag detected; exiting monitor loop.")
                    break
                now = time.time()
                # Check backend
                if self.backend_proc and self.backend_proc.poll() is not None:
                    code = self.backend_proc.returncode
                    self.log(f"Backend stopped with exit code {code}")
                    print(f"\n[ALERT] {self.side.capitalize()} Backend stopped (exit code {code})")

                    if self.stop_flag_file.exists() or self._shutting_down:
                        break

                    restart_counts["backend"] = [t for t in restart_counts["backend"] if now - t < WINDOW_SECONDS]
                    if len(restart_counts["backend"]) < MAX_RESTARTS_IN_WINDOW:
                        restart_counts["backend"].append(now)
                        print(f"[RECOVERY] Restarting {self.side.capitalize()} Backend (attempt {len(restart_counts['backend'])}/{MAX_RESTARTS_IN_WINDOW})...")
                        self.log("Attempting backend restart")
                        self.start_backend()
                        if wait_for_health(self.backend_health_url, timeout=15.0):
                            print(f"[HEALTHY] {self.side.capitalize()} Backend restarted successfully.")
                            pids = {"launcher": os.getpid(), "backend": self.backend_proc.pid, "frontend": self.frontend_proc.pid}
                            if self.worker_proc:
                                pids["worker"] = self.worker_proc.pid
                            self.save_pids(pids)
                        else:
                            print(f"[ERROR] {self.side.capitalize()} Backend failed health check after restart.")
                            break
                    else:
                        print(f"[FATAL] {self.side.capitalize()} Backend exceeded maximum restart attempts. Stopping.")
                        break

                # Check frontend
                if self.frontend_proc and self.frontend_proc.poll() is not None:
                    code = self.frontend_proc.returncode
                    self.log(f"Frontend stopped with exit code {code}")
                    print(f"\n[ALERT] {self.side.capitalize()} Frontend stopped (exit code {code})")

                    if self.stop_flag_file.exists() or self._shutting_down:
                        break

                    restart_counts["frontend"] = [t for t in restart_counts["frontend"] if now - t < WINDOW_SECONDS]
                    if len(restart_counts["frontend"]) < MAX_RESTARTS_IN_WINDOW:
                        restart_counts["frontend"].append(now)
                        print(f"[RECOVERY] Restarting {self.side.capitalize()} Frontend (attempt {len(restart_counts['frontend'])}/{MAX_RESTARTS_IN_WINDOW})...")
                        self.log("Attempting frontend restart")
                        self.start_frontend()
                        pids = {"launcher": os.getpid(), "backend": self.backend_proc.pid, "frontend": self.frontend_proc.pid}
                        if self.worker_proc:
                            pids["worker"] = self.worker_proc.pid
                        self.save_pids(pids)
                    else:
                        print(f"[FATAL] {self.side.capitalize()} Frontend exceeded maximum restart attempts. Stopping.")
                        break

                if self.worker_proc and self.worker_proc.poll() is not None:
                    code = self.worker_proc.returncode
                    self.log(f"Worker stopped with exit code {code}")
                    print(f"\n[ALERT] Admin worker stopped (exit code {code})")
                    if self.stop_flag_file.exists() or self._shutting_down:
                        break
                    restart_counts["worker"] = [t for t in restart_counts["worker"] if now - t < WINDOW_SECONDS]
                    if len(restart_counts["worker"]) < MAX_RESTARTS_IN_WINDOW:
                        restart_counts["worker"].append(now)
                        print(f"[RECOVERY] Restarting Admin worker (attempt {len(restart_counts['worker'])}/{MAX_RESTARTS_IN_WINDOW})...")
                        self.start_worker()
                        pids = {"launcher": os.getpid(), "backend": self.backend_proc.pid, "frontend": self.frontend_proc.pid}
                        pids["worker"] = self.worker_proc.pid
                        self.save_pids(pids)
                    else:
                        print("[FATAL] Admin worker exceeded maximum restart attempts. Stopping.")
                        break

                time.sleep(1.0)
        except KeyboardInterrupt:
            print(f"\n[SHUTDOWN] Stopping {self.side.capitalize()} Side...")
        finally:
            self.stop()
            print(f"{self.side.capitalize()} Side stopped cleanly.")

        return 0

    def print_status(self) -> None:
        pids = self.load_pids()
        b_pid = pids.get("backend") or get_pid_using_port(self.backend_port)
        f_pid = pids.get("frontend") or get_pid_using_port(self.frontend_port)
        w_pid = pids.get("worker")

        b_running = bool(b_pid and is_pid_running(b_pid) and is_port_in_use(self.backend_port))
        b_healthy = check_http_health(self.backend_health_url) if b_running else False

        f_running = bool(f_pid and is_pid_running(f_pid) and is_port_in_use(self.frontend_port))
        f_healthy = check_http_health(self.frontend_url) if f_running else False
        w_running = bool(self.side == "admin" and w_pid and is_pid_running(w_pid))

        b_pid_display = str(b_pid) if b_running else "N/A"
        f_pid_display = str(f_pid) if f_running else "N/A"

        print(f"[{self.side_upper} SIDE STATUS]")
        print(f"  Backend:  {'RUNNING' if b_running else 'STOPPED':<8} (Port {self.backend_port}, PID: {b_pid_display}, Health: {'HEALTHY' if b_healthy else 'UNHEALTHY'})")
        print(f"  Frontend: {'RUNNING' if f_running else 'STOPPED':<8} (Port {self.frontend_port}, PID: {f_pid_display}, Health: {'HEALTHY' if f_healthy else 'UNHEALTHY'})")
        if self.side == "admin":
            print(f"  Worker:   {'RUNNING' if w_running else 'STOPPED':<8} (PID: {w_pid if w_running else 'N/A'})")
        print()


class UnifiedManager:
    """Manages all services: Admin Side (8001, 3001) + User Side (8000, 3000) simultaneously."""

    def __init__(self):
        self.admin = ServiceManager("admin")
        self.user = ServiceManager("user")
        self._shutting_down = False

    def check_ports_available(self) -> tuple[bool, str]:
        ok_a, reason_a = self.admin.check_ports_available()
        if not ok_a:
            return False, reason_a
        ok_u, reason_u = self.user.check_ports_available()
        if not ok_u:
            return False, reason_u
        # On Windows, sockets in TIME_WAIT can still block bind() even though nothing
        # is LISTENING. Wait up to 10 s for such transient states to clear.
        if sys.platform == "win32":
            for port in (self.backend_port, self.frontend_port):
                deadline = time.time() + 10
                while time.time() < deadline:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            s.bind(("127.0.0.1", port))
                        break  # bind succeeded — port is usable
                    except OSError:
                        time.sleep(1)

        # On Windows, sockets in TIME_WAIT can still block bind() even though nothing
        # is LISTENING. Wait up to 10 s for such transient states to clear.
        if sys.platform == "win32":
            for port in (self.backend_port, self.frontend_port):
                deadline = time.time() + 10
                while time.time() < deadline:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            s.bind(("127.0.0.1", port))
                        break  # bind succeeded — port is usable
                    except OSError:
                        time.sleep(1)

        # On Windows, sockets in TIME_WAIT can still block bind() even though nothing
        # is LISTENING. Wait up to 10 s for such transient states to clear.
        if sys.platform == "win32":
            for port in (self.backend_port, self.frontend_port):
                deadline = time.time() + 10
                while time.time() < deadline:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            s.bind(("127.0.0.1", port))
                        break  # bind succeeded — port is usable
                    except OSError:
                        time.sleep(1)

        return True, ""

    def run(self) -> int:
        print("=" * 60)
        print("            AI FAQ COLLEGE CHAT BOT (ALL SERVICES)")
        print("       Admin Side (:8001, :3001) + User Side (:8000, :3000)")
        print("    🦄 FastAPI + Uvicorn ('Unicorn') ASGI Engines (Ports 8000, 8001)")
        print("    ▲  Next.js Frontend Dev Servers (Ports 3000, 3001)")
        print("=" * 60)
        print()

        # Clean existing stop flags
        for mgr in (self.admin, self.user):
            if mgr.stop_flag_file.exists():
                try:
                    mgr.stop_flag_file.unlink()
                except OSError:
                    pass

        # Check port conflicts
        available, reason = self.check_ports_available()
        if not available:
            print(f"[CONFLICT] {reason}")
            print(f"Tip: Run 'python admin.py stop' to terminate any lingering processes.")
            return 1

        # 1. Start Backends (FastAPI + Uvicorn)
        print(f"[1/4] Starting Admin Backend (FastAPI / Uvicorn on port 8001)...")
        self.admin.start_backend()

        print(f"[2/4] Starting User Backend (FastAPI / Uvicorn on port 8000)...")
        self.user.start_backend()

        # Check Backend health
        print(f"[CHECKING] Admin Backend Health (http://127.0.0.1:8001/health)...")
        if not wait_for_backend(self.admin.backend_proc, self.admin.backend_health_url, timeout=90.0):
            print(f"[ERROR] Admin Backend did not become healthy.")
            self.stop()
            return 1
        print(f"[HEALTHY]  Admin Backend - Port 8001 (PID {self.admin.backend_proc.pid})")

        print(f"[CHECKING] User Backend Health (http://127.0.0.1:8000/health)...")
        if not wait_for_backend(self.user.backend_proc, self.user.backend_health_url, timeout=90.0):
            print(f"[ERROR] User Backend did not become healthy.")
            self.stop()
            return 1
        print(f"[HEALTHY]  User Backend - Port 8000 (PID {self.user.backend_proc.pid})")
        print()

        print("[WORKER] Starting shared Admin Celery worker...")
        self.admin.start_worker()
        time.sleep(1.0)
        if self.admin.worker_proc.poll() is not None:
            print(f"[ERROR] Admin worker exited with code {self.admin.worker_proc.returncode}; see {self.admin.worker_log_file}")
            self.stop()
            return 1
        print(f"[HEALTHY]  Admin worker (PID {self.admin.worker_proc.pid})")
        print()

        # 2. Start Frontends (Next.js)
        print(f"[3/4] Starting Admin Frontend (Next.js dev on port 3001)...")
        self.admin.start_frontend()

        print(f"[4/4] Starting User Frontend (Next.js dev on port 3000)...")
        self.user.start_frontend()

        # Check Frontend readiness
        print(f"[CHECKING] Frontend Readiness...")
        if wait_for_health(self.admin.frontend_url, timeout=30.0):
            print(f"[HEALTHY]  Admin Frontend - Port 3001 (PID {self.admin.frontend_proc.pid})")
        else:
            print(f"[RUNNING]  Admin Frontend - Port 3001 (PID {self.admin.frontend_proc.pid})")

        if wait_for_health(self.user.frontend_url, timeout=30.0):
            print(f"[HEALTHY]  User Frontend - Port 3000 (PID {self.user.frontend_proc.pid})")
        else:
            print(f"[RUNNING]  User Frontend - Port 3000 (PID {self.user.frontend_proc.pid})")
        print()

        # Save PIDs
        launcher_pid = os.getpid()
        self.admin.save_pids({
            "launcher": launcher_pid,
            "backend": self.admin.backend_proc.pid,
            "frontend": self.admin.frontend_proc.pid,
            "worker": self.admin.worker_proc.pid,
        })
        self.user.save_pids({
            "launcher": launcher_pid,
            "backend": self.user.backend_proc.pid,
            "frontend": self.user.frontend_proc.pid,
        })

        # 3. Unified Ready Banner
        print("=" * 60)
        print("               ALL SERVICES RUNNING & READY")
        print("=" * 60)
        print()
        print("  [ADMIN SIDE]")
        print("  • Admin Frontend:  http://localhost:3001")
        print("  • Admin Backend:   http://localhost:8001")
        print("  • Admin API Docs:  http://localhost:8001/docs")
        print("  • Admin Health:    http://localhost:8001/health")
        print()
        print("  [USER SIDE]")
        print("  • User Frontend:   http://localhost:3000")
        print("  • User Backend:    http://localhost:8000")
        print("  • User API Docs:   http://localhost:8000/docs")
        print("  • User Health:     http://localhost:8000/health")
        print()
        print("-" * 60)
        print("    LIVE TERMINAL OUTPUT (UVICORN & NEXT.JS LOGS)")
        print("-" * 60)
        print("Press CTRL+C to stop all services cleanly.")
        print()

        self.admin._ready = True
        self.user._ready = True

        # 4. Monitor loop with auto-recovery for all 4 services
        procs = [
            ("admin", "backend", self.admin, "backend_proc", self.admin.backend_port, self.admin.backend_health_url, self.admin.start_backend),
            ("admin", "frontend", self.admin, "frontend_proc", self.admin.frontend_port, self.admin.frontend_url, self.admin.start_frontend),
            ("admin", "worker", self.admin, "worker_proc", 0, "", self.admin.start_worker),
            ("user", "backend", self.user, "backend_proc", self.user.backend_port, self.user.backend_health_url, self.user.start_backend),
            ("user", "frontend", self.user, "frontend_proc", self.user.frontend_port, self.user.frontend_url, self.user.start_frontend),
        ]
        restarts: dict[str, list[float]] = {f"{s}_{t}": [] for s, t, *_ in procs}

        try:
            while not self._shutting_down:
                if self.admin.stop_flag_file.exists() or self.user.stop_flag_file.exists():
                    break
                now = time.time()
                for side, stype, mgr, attr, port, health_url, starter in procs:
                    proc: subprocess.Popen | None = getattr(mgr, attr)
                    if proc and proc.poll() is not None:
                        code = proc.returncode
                        key = f"{side}_{stype}"
                        print(f"\n[ALERT] {side.capitalize()} {stype.capitalize()} stopped (code {code})")
                        if self._shutting_down:
                            break
                        restarts[key] = [t for t in restarts[key] if now - t < 60.0]
                        if len(restarts[key]) < 3:
                            restarts[key].append(now)
                            print(f"[RECOVERY] Restarting {side.capitalize()} {stype.capitalize()} (attempt {len(restarts[key])}/3)...")
                            starter()
                            setattr(mgr, attr, getattr(mgr, attr))
                            if stype == "backend":
                                wait_for_health(health_url, timeout=15.0)
                        else:
                            print(f"[FATAL] {side.capitalize()} {stype.capitalize()} exceeded restart limit. Stopping all.")
                            return 1
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Stopping all services...")
        finally:
            self.stop()
            print("All services stopped cleanly.")

        return 0

    def stop(self) -> None:
        self._shutting_down = True
        self.admin.stop()
        self.user.stop()

        # Extra safety check: kill any lingering processes on ports 8000, 8001, 3000, 3001
        current_pid = os.getpid()
        for port in (8000, 8001, 3000, 3001):
            pid = get_pid_using_port(port)
            if pid and pid != current_pid:
                kill_process_tree(pid)

    def print_status(self) -> None:
        print("=" * 60)
        print("           AI FAQ COLLEGE CHAT BOT STATUS")
        print("=" * 60)
        print()
        self.admin.print_status()
        self.user.print_status()

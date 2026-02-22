"""Trade Control — Desktop service manager for Trade Agent.

Manages:
  1. FastAPI backend  (port 8000)
  2. Vite dashboard   (port 5173)

Features: system tray, health monitoring, auto-restart, auto-start on boot.
"""

import ctypes
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from enum import Enum
from logging.handlers import RotatingFileHandler
from tkinter import scrolledtext
from typing import Optional
from urllib.request import Request, urlopen

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    pystray = None

# ---------------------------------------------------------------------------
# Paths & Constants
# ---------------------------------------------------------------------------

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboard")
LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "trade_control.log")
ICON_FILE = os.path.join(APP_DIR, "trade_icon.ico")

INSTANCE_PORT = 48081  # Single-instance lock port

PYTHON_EXE = sys.executable
NODE_EXE = "node"
NPM_CMD = "npm.cmd" if sys.platform == "win32" else "npm"

# ---------------------------------------------------------------------------
# Colors (dark trading theme)
# ---------------------------------------------------------------------------

BG = "#0d1117"
BG_CARD = "#161b22"
BG_INPUT = "#1c2333"
BRAND = "#58a6ff"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d29922"
DIM = "#8b949e"
WHITE = "#e6edf3"
FONT = "Consolas"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("TradeControl")
logger.setLevel(logging.DEBUG)

_file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_console_handler)


# ---------------------------------------------------------------------------
# Service definitions
# ---------------------------------------------------------------------------

class ServiceState(Enum):
    STOPPED = "Stopped"
    STARTING = "Starting"
    RUNNING = "Running"
    ERROR = "Error"
    STOPPING = "Stopping"


class ServiceConfig:
    def __init__(self, name, command, port, health_url, cwd=None, startup_delay=2.0):
        self.name = name
        self.command = command
        self.port = port
        self.health_url = health_url
        self.cwd = cwd or PROJECT_ROOT
        self.startup_delay = startup_delay


SERVICES = {
    "backend": ServiceConfig(
        name="FastAPI Backend",
        command=[PYTHON_EXE, "-m", "agent.main"],
        port=8000,
        health_url="http://localhost:8000/api/health",
        cwd=PROJECT_ROOT,
        startup_delay=3.0,
    ),
    "dashboard": ServiceConfig(
        name="Vite Dashboard",
        command=[NPM_CMD, "run", "dev"],
        port=5173,
        health_url="http://localhost:5173",
        cwd=DASHBOARD_DIR,
        startup_delay=4.0,
    ),
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: float = 3.0) -> Optional[str]:
    try:
        req = Request(url)
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def port_in_use(port: int) -> bool:
    # Check both IPv4 and IPv6
    for family, addr in [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")]:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex((addr, port)) == 0:
                    return True
        except Exception:
            pass
    return False


def kill_port(port: int):
    """Kill whatever process is using *port* (IPv4 or IPv6)."""
    if not psutil:
        return
    killed_pids = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr.port == port and conn.pid and conn.pid not in killed_pids:
            if conn.status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid)
                    logger.info(f"Killing PID {conn.pid} ({proc.name()}) on port {port}")
                    proc.terminate()
                    proc.wait(timeout=3)
                    killed_pids.add(conn.pid)
                except Exception as e:
                    logger.warning(f"Failed to kill PID {conn.pid}: {e}")


_instance_socket = None

def acquire_instance_lock() -> bool:
    global _instance_socket
    try:
        _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _instance_socket.bind(("127.0.0.1", INSTANCE_PORT))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Service Manager
# ---------------------------------------------------------------------------

class ServiceManager:
    def __init__(self, key: str, config: ServiceConfig):
        self.key = key
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.state = ServiceState.STOPPED
        self.started_at: Optional[datetime] = None
        self.last_healthy = False
        self.fail_count = 0
        self._reader_thread: Optional[threading.Thread] = None

    def start(self):
        if self.state in (ServiceState.RUNNING, ServiceState.STARTING):
            return
        self.state = ServiceState.STARTING
        logger.info(f"[{self.config.name}] Starting...")

        # Clean up port
        if port_in_use(self.config.port):
            logger.warning(f"[{self.config.name}] Port {self.config.port} in use, killing...")
            kill_port(self.config.port)
            time.sleep(0.5)

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.process = subprocess.Popen(
                self.config.command,
                cwd=self.config.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
            self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self._reader_thread.start()

            # Wait for health
            time.sleep(self.config.startup_delay)
            if self.check_health():
                self.state = ServiceState.RUNNING
                self.started_at = datetime.now()
                self.fail_count = 0
                logger.info(f"[{self.config.name}] Running (PID {self.process.pid})")
            else:
                # Give it more time
                for _ in range(5):
                    time.sleep(1)
                    if self.check_health():
                        self.state = ServiceState.RUNNING
                        self.started_at = datetime.now()
                        self.fail_count = 0
                        logger.info(f"[{self.config.name}] Running (PID {self.process.pid})")
                        return
                self.state = ServiceState.ERROR
                logger.error(f"[{self.config.name}] Failed health check after start")
        except Exception as e:
            self.state = ServiceState.ERROR
            logger.error(f"[{self.config.name}] Start failed: {e}")

    def stop(self):
        if self.state == ServiceState.STOPPED:
            return
        self.state = ServiceState.STOPPING
        logger.info(f"[{self.config.name}] Stopping...")

        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            except Exception as e:
                logger.warning(f"[{self.config.name}] Stop error: {e}")
            self.process = None

        # Also kill by port in case orphaned
        if port_in_use(self.config.port):
            kill_port(self.config.port)

        self.state = ServiceState.STOPPED
        self.started_at = None
        self.last_healthy = False
        self.fail_count = 0
        logger.info(f"[{self.config.name}] Stopped")

    def restart(self):
        self.stop()
        time.sleep(1)
        self.start()

    def check_health(self) -> bool:
        healthy = http_get(self.config.health_url) is not None
        self.last_healthy = healthy
        return healthy

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def get_uptime(self) -> str:
        if not self.started_at:
            return "--"
        delta = datetime.now() - self.started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s"

    def _read_output(self):
        try:
            for line in iter(self.process.stdout.readline, b""):
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.debug(f"[{self.config.name}] {text}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Health Monitor
# ---------------------------------------------------------------------------

class HealthMonitor:
    def __init__(self, managers: dict[str, ServiceManager]):
        self.managers = managers
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            for key, mgr in self.managers.items():
                if mgr.state == ServiceState.RUNNING:
                    alive = mgr.is_alive()
                    healthy = mgr.check_health() if alive else False

                    if not alive or not healthy:
                        mgr.fail_count += 1
                        logger.warning(
                            f"[{mgr.config.name}] Health fail #{mgr.fail_count} "
                            f"(alive={alive}, healthy={healthy})"
                        )
                        if mgr.fail_count >= 3:
                            logger.info(f"[{mgr.config.name}] Auto-restarting...")
                            threading.Thread(target=mgr.restart, daemon=True).start()
                            mgr.fail_count = 0
                    else:
                        mgr.fail_count = 0
                elif mgr.state == ServiceState.ERROR:
                    # Try to recover from error state
                    mgr.fail_count += 1
                    if mgr.fail_count >= 3:
                        logger.info(f"[{mgr.config.name}] Attempting recovery...")
                        threading.Thread(target=mgr.start, daemon=True).start()
                        mgr.fail_count = 0

            time.sleep(10)


# ---------------------------------------------------------------------------
# Tray Manager
# ---------------------------------------------------------------------------

class TrayManager:
    def __init__(self, app: "TradeControlApp"):
        self.app = app
        self.icon = None
        self._last_color = None

    def start(self):
        if not pystray:
            return
        image = self._make_icon(GREEN)
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._on_show, default=True),
            pystray.MenuItem("Start All", self._on_start_all),
            pystray.MenuItem("Stop All", self._on_stop_all),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self.icon = pystray.Icon("TradeControl", image, "Trade Control", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def update_color(self, color: str):
        if color != self._last_color and self.icon:
            self._last_color = color
            self.icon.icon = self._make_icon(color)

    def _make_icon(self, color: str) -> "Image.Image":
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw a chart-like icon
        r, g, b = self._hex_to_rgb(color)

        # Background circle
        draw.ellipse([4, 4, size - 4, size - 4], fill=(r, g, b, 200))

        # "T" letter for Trade
        draw.text((size // 2 - 8, size // 2 - 12), "T", fill=(255, 255, 255, 255))

        return img

    @staticmethod
    def _hex_to_rgb(hex_color: str):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _on_show(self, icon=None, item=None):
        self.app.after(0, self.app.deiconify)
        self.app.after(0, self.app.lift)

    def _on_start_all(self, icon=None, item=None):
        threading.Thread(target=self.app.start_all, daemon=True).start()

    def _on_stop_all(self, icon=None, item=None):
        threading.Thread(target=self.app.stop_all, daemon=True).start()

    def _on_quit(self, icon=None, item=None):
        self.app.after(0, self.app.quit_app)


# ---------------------------------------------------------------------------
# GUI Text Handler (routes logs to the text widget)
# ---------------------------------------------------------------------------

class TextHandler(logging.Handler):
    def __init__(self, widget: scrolledtext.ScrolledText):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        msg = self.format(record) + "\n"
        try:
            self.widget.after(0, self._append, msg)
        except Exception:
            pass

    def _append(self, msg):
        self.widget.configure(state="normal")
        self.widget.insert("end", msg)
        # Limit to 500 lines
        lines = int(self.widget.index("end-1c").split(".")[0])
        if lines > 500:
            self.widget.delete("1.0", f"{lines - 500}.0")
        self.widget.see("end")
        self.widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class TradeControlApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Trade Control")
        self.geometry("680x720")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(600, 600)

        # Load icon if exists
        if os.path.exists(ICON_FILE):
            try:
                self.iconbitmap(ICON_FILE)
            except Exception:
                pass

        # Service managers
        self.managers: dict[str, ServiceManager] = {}
        for key, config in SERVICES.items():
            self.managers[key] = ServiceManager(key, config)

        # Health monitor
        self.monitor = HealthMonitor(self.managers)

        # Tray
        self.tray = TrayManager(self)

        # GUI refs
        self._cards: dict[str, dict] = {}

        self._build_gui()

        # Wire log handler to text widget
        text_handler = TextHandler(self._log_text)
        text_handler.setLevel(logging.INFO)
        text_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(text_handler)

        # Protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start systems
        self.tray.start()
        self.monitor.start()

        # Auto-start services after 500ms
        self.after(500, lambda: threading.Thread(target=self.start_all, daemon=True).start())

        # Periodic GUI update
        self._update_loop()

    # ---- GUI ----

    def _build_gui(self):
        # Title
        title_frame = tk.Frame(self, bg=BG)
        title_frame.pack(fill="x", padx=16, pady=(12, 0))

        tk.Label(
            title_frame, text="TRADE CONTROL",
            font=(FONT, 16, "bold"), fg=BRAND, bg=BG,
        ).pack(side="left")

        self._status_label = tk.Label(
            title_frame, text="Starting...",
            font=(FONT, 10), fg=DIM, bg=BG,
        )
        self._status_label.pack(side="right")

        # Master button
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=16, pady=(8, 4))

        self._master_btn = tk.Button(
            btn_frame, text="STOP ALL SERVICES",
            font=(FONT, 10, "bold"), fg=WHITE, bg="#b62324",
            activebackground="#d63031", activeforeground=WHITE,
            bd=0, padx=16, pady=6, cursor="hand2",
            command=lambda: threading.Thread(target=self._toggle_all, daemon=True).start(),
        )
        self._master_btn.pack(fill="x")

        # Service cards
        cards_frame = tk.Frame(self, bg=BG)
        cards_frame.pack(fill="x", padx=16, pady=4)

        for key in ["backend", "dashboard"]:
            self._cards[key] = self._build_service_card(cards_frame, key)

        # MT5 info card
        self._build_mt5_card(cards_frame)

        # Open buttons row
        action_frame = tk.Frame(self, bg=BG)
        action_frame.pack(fill="x", padx=16, pady=4)

        for label, cmd in [
            ("Open Dashboard", self._open_dashboard),
            ("Open API Docs", self._open_api_docs),
            ("Open Project", self._open_project),
            ("Open Logs", self._open_logs),
        ]:
            tk.Button(
                action_frame, text=label,
                font=(FONT, 9), fg=WHITE, bg=BG_INPUT,
                activebackground=BG_CARD, activeforeground=BRAND,
                bd=0, padx=10, pady=4, cursor="hand2",
                command=cmd,
            ).pack(side="left", padx=2, expand=True, fill="x")

        # Log console
        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        tk.Label(
            log_frame, text="Log Output",
            font=(FONT, 9, "bold"), fg=DIM, bg=BG, anchor="w",
        ).pack(fill="x")

        self._log_text = scrolledtext.ScrolledText(
            log_frame, wrap="word", font=(FONT, 8),
            bg=BG_INPUT, fg=WHITE, insertbackground=WHITE,
            bd=0, height=10,
        )
        self._log_text.configure(state="disabled")
        self._log_text.pack(fill="both", expand=True, pady=(2, 0))

    def _build_service_card(self, parent, key: str) -> dict:
        config = SERVICES[key]
        card = tk.Frame(parent, bg=BG_CARD, bd=0, highlightthickness=1, highlightbackground="#30363d")
        card.pack(fill="x", pady=3)

        # Row 1: indicator + name + status
        row1 = tk.Frame(card, bg=BG_CARD)
        row1.pack(fill="x", padx=10, pady=(8, 2))

        indicator = tk.Label(row1, text="\u25cf", font=(FONT, 14), fg=DIM, bg=BG_CARD)
        indicator.pack(side="left")

        tk.Label(
            row1, text=config.name,
            font=(FONT, 11, "bold"), fg=WHITE, bg=BG_CARD,
        ).pack(side="left", padx=(6, 0))

        status_label = tk.Label(row1, text="Stopped", font=(FONT, 9), fg=DIM, bg=BG_CARD)
        status_label.pack(side="right")

        # Row 2: port, pid, uptime, health
        row2 = tk.Frame(card, bg=BG_CARD)
        row2.pack(fill="x", padx=10, pady=(0, 2))

        port_label = tk.Label(row2, text=f"Port: {config.port}", font=(FONT, 8), fg=DIM, bg=BG_CARD)
        port_label.pack(side="left")

        pid_label = tk.Label(row2, text="PID: --", font=(FONT, 8), fg=DIM, bg=BG_CARD)
        pid_label.pack(side="left", padx=(12, 0))

        uptime_label = tk.Label(row2, text="Uptime: --", font=(FONT, 8), fg=DIM, bg=BG_CARD)
        uptime_label.pack(side="left", padx=(12, 0))

        health_label = tk.Label(row2, text="Health: --", font=(FONT, 8), fg=DIM, bg=BG_CARD)
        health_label.pack(side="right")

        # Row 3: buttons
        row3 = tk.Frame(card, bg=BG_CARD)
        row3.pack(fill="x", padx=10, pady=(0, 8))

        restart_btn = tk.Button(
            row3, text="Restart", font=(FONT, 8), fg=WHITE, bg=BG_INPUT,
            bd=0, padx=8, pady=2, cursor="hand2",
            command=lambda k=key: threading.Thread(
                target=self.managers[k].restart, daemon=True
            ).start(),
        )
        restart_btn.pack(side="left", padx=(0, 4))

        stop_btn = tk.Button(
            row3, text="Stop", font=(FONT, 8), fg=RED, bg=BG_INPUT,
            bd=0, padx=8, pady=2, cursor="hand2",
            command=lambda k=key: threading.Thread(
                target=self.managers[k].stop, daemon=True
            ).start(),
        )
        stop_btn.pack(side="left")

        return {
            "indicator": indicator,
            "status": status_label,
            "pid": pid_label,
            "uptime": uptime_label,
            "health": health_label,
        }

    def _build_mt5_card(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, bd=0, highlightthickness=1, highlightbackground="#30363d")
        card.pack(fill="x", pady=3)

        row = tk.Frame(card, bg=BG_CARD)
        row.pack(fill="x", padx=10, pady=8)

        self._mt5_indicator = tk.Label(row, text="\u25cf", font=(FONT, 14), fg=DIM, bg=BG_CARD)
        self._mt5_indicator.pack(side="left")

        tk.Label(
            row, text="MetaTrader 5",
            font=(FONT, 11, "bold"), fg=WHITE, bg=BG_CARD,
        ).pack(side="left", padx=(6, 0))

        self._mt5_status = tk.Label(row, text="Not detected", font=(FONT, 9), fg=DIM, bg=BG_CARD)
        self._mt5_status.pack(side="right")

    # ---- Actions ----

    def start_all(self):
        logger.info("Starting all services...")
        for key in ["backend", "dashboard"]:
            self.managers[key].start()
            time.sleep(1)
        logger.info("All services started")

    def stop_all(self):
        logger.info("Stopping all services...")
        for key in ["dashboard", "backend"]:
            self.managers[key].stop()
        logger.info("All services stopped")

    def _toggle_all(self):
        all_running = all(m.state == ServiceState.RUNNING for m in self.managers.values())
        if all_running:
            self.stop_all()
        else:
            self.start_all()

    def _open_dashboard(self):
        import webbrowser
        webbrowser.open("http://localhost:5173")

    def _open_api_docs(self):
        import webbrowser
        webbrowser.open("http://localhost:8000/docs")

    def _open_project(self):
        os.startfile(PROJECT_ROOT)

    def _open_logs(self):
        os.startfile(LOG_DIR)

    # ---- GUI Update Loop ----

    def _update_loop(self):
        all_running = True

        for key, mgr in self.managers.items():
            card = self._cards[key]
            state = mgr.state

            # Indicator color
            color = {
                ServiceState.RUNNING: GREEN,
                ServiceState.STARTING: YELLOW,
                ServiceState.STOPPING: YELLOW,
                ServiceState.ERROR: RED,
                ServiceState.STOPPED: DIM,
            }.get(state, DIM)

            card["indicator"].configure(fg=color)
            card["status"].configure(text=state.value, fg=color)

            pid = mgr.process.pid if mgr.process and mgr.is_alive() else "--"
            card["pid"].configure(text=f"PID: {pid}")
            card["uptime"].configure(text=f"Uptime: {mgr.get_uptime()}")

            health_str = "OK" if mgr.last_healthy else "--"
            health_color = GREEN if mgr.last_healthy else DIM
            card["health"].configure(text=f"Health: {health_str}", fg=health_color)

            if state != ServiceState.RUNNING:
                all_running = False

        # Master button
        if all_running:
            self._master_btn.configure(text="STOP ALL SERVICES", bg="#b62324")
            self._status_label.configure(text="All Running", fg=GREEN)
        else:
            self._master_btn.configure(text="START ALL SERVICES", bg="#238636")
            states = [m.state.value for m in self.managers.values()]
            self._status_label.configure(text=" | ".join(states), fg=YELLOW)

        # MT5 detection
        mt5_running = False
        mt5_pid = None
        if psutil:
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    name = proc.info["name"].lower()
                    if name in ("terminal.exe", "terminal64.exe", "metatrader.exe"):
                        mt5_running = True
                        mt5_pid = proc.info["pid"]
                        break
                except Exception:
                    pass

        if mt5_running:
            self._mt5_indicator.configure(fg=GREEN)
            self._mt5_status.configure(text=f"Running (PID {mt5_pid})", fg=GREEN)
        else:
            self._mt5_indicator.configure(fg=DIM)
            self._mt5_status.configure(text="Not detected", fg=DIM)

        # Tray icon
        tray_color = GREEN if all_running else (RED if any(
            m.state == ServiceState.ERROR for m in self.managers.values()
        ) else YELLOW)
        self.tray.update_color(tray_color)

        self.after(2000, self._update_loop)

    # ---- Lifecycle ----

    def _on_close(self):
        """Minimize to tray instead of closing."""
        if pystray:
            self.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        logger.info("Shutting down Trade Control...")
        self.monitor.stop()
        for mgr in self.managers.values():
            mgr.stop()
        self.tray.stop()
        self.destroy()


# ---------------------------------------------------------------------------
# Console hiding (Windows)
# ---------------------------------------------------------------------------

def _hide_console():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _hide_console()

    if not acquire_instance_lock():
        logger.error("Trade Control is already running!")
        try:
            root = tk.Tk()
            root.withdraw()
            from tkinter import messagebox
            messagebox.showwarning("Trade Control", "Trade Control is already running.")
            root.destroy()
        except Exception:
            pass
        return

    logger.info("Trade Control starting...")
    app = TradeControlApp()
    app.mainloop()


if __name__ == "__main__":
    main()

import sys
import time
import threading
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Try to reconfigure stdout to UTF-8 if supported (Python 3.7+)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Dynamic Encoding Detection
try:
    # Probe the actual glyphs we use so Windows code pages fall back cleanly.
    "".join(["?", "-", "?", "?", "?", "?"]).encode(sys.stdout.encoding or "utf-8")
    supports_unicode = True
except Exception:
    supports_unicode = False

# Set Glyphs based on terminal capabilities
if supports_unicode:
    SPINNER_CHARS = ["?", "?", "?", "?", "?", "?", "?", "?", "?", "?"]
    LINE_CHAR = "-"
    SUCCESS_ICON = "?"
    WARNING_ICON = "?"
    ERROR_ICON = "?"
    INFO_ICON = "?"
else:
    SPINNER_CHARS = ["|", "/", "-", "\\"]
    LINE_CHAR = "-"
    SUCCESS_ICON = "[OK]"
    WARNING_ICON = "[!]"
    ERROR_ICON = "[X]"
    INFO_ICON = "[i]"

class Spinner:
    """A terminal loading spinner running on a background thread."""
    def __init__(self, message="Processing..."):
        self.message = message
        self.stop_event = threading.Event()
        self.thread = None
        self.chars = SPINNER_CHARS

    def _spin(self):
        idx = 0
        while not self.stop_event.is_set():
            sys.stdout.write(f"\r{Fore.CYAN}{self.chars[idx]} {Fore.WHITE}{self.message}")
            sys.stdout.flush()
            idx = (idx + 1) % len(self.chars)
            time.sleep(0.08)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def __enter__(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread:
            self.thread.join()

def type_print(text, delay=0.015, color=Fore.WHITE):
    """Prints text with a typewriter effect to mimic Claude Code agent typing."""
    sys.stdout.write(color)
    for char in text:
        try:
            sys.stdout.write(char)
        except Exception:
            # Fallback for unicode chars inside strings if print fails
            sys.stdout.write("?")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(Style.RESET_ALL)
    print()

def print_banner():
    """Prints a premium, scanable brand banner for AegisCode."""
    banner = f"""
{Fore.MAGENTA}{Style.BRIGHT}    ___                       ______          __   
{Fore.MAGENTA}{Style.BRIGHT}   /   |  ___  ____ _(_)____ / ____/___  ____/ /__ 
{Fore.MAGENTA}{Style.BRIGHT}  / /| | / _ \\/ __ `/ / ___// /   / __ \\/ __  / _ \\
{Fore.MAGENTA}{Style.BRIGHT} / ___ |/  __/ /_/ / (__  )/ /___/ /_/ / /_/ /  __/
{Fore.MAGENTA}{Style.BRIGHT}/_/  |_|\\___/\\__, /_/____/ \\____/\\____/\\__,_/\\___/ 
{Fore.MAGENTA}{Style.BRIGHT}            /____/                                 
{Fore.CYAN}            [AI-Age Code Integrity & Vetting Agent]
"""
    print(banner)

def print_section(title):
    """Prints a clear, clean section header for visual spacing."""
    divider = LINE_CHAR * (50 - len(title) - 6)
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{LINE_CHAR * 3} {title} {divider}")

def print_success(message):
    print(f"{Fore.GREEN}{SUCCESS_ICON} {Fore.WHITE}{message}")

def print_warning(message):
    print(f"{Fore.YELLOW}{WARNING_ICON} {Fore.WHITE}{message}")

def print_error(message):
    print(f"{Fore.RED}{ERROR_ICON} {Fore.WHITE}{message}")

def print_info(message):
    print(f"{Fore.BLUE}{INFO_ICON} {Fore.WHITE}{message}")


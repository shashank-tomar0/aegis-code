import csv
import os
import threading
import webbrowser
from typing import ClassVar

from rich.text import Text
from rich.panel import Panel
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, ProgressBar, RichLog, Static

# --- CSS Design System ---
CSS = """
Screen {
    background: #0d0e12;
}

/* App Header styling */
#header-panel {
    height: 6;
    background: #0d0e12;
    border-bottom: solid #1f2229;
    padding: 1 2;
}

#traffic-lights {
    width: 6;
    content-align: left top;
}

#header-title {
    width: 1fr;
    content-align: left top;
    text-style: bold;
}

#header-stats {
    width: auto;
    color: #a1a1aa;
    text-align: right;
    content-align: right top;
}

/* Main Layout */
#body {
    height: 1fr;
    background: #0d0e12;
}

#table-container {
    width: 65%;
    border-right: solid #1f2229;
    background: #0d0e12;
}

#detail-container {
    width: 35%;
    padding: 1 2;
    background: #0d0e12;
}

/* Data Table Customization */
DataTable {
    background: #0d0e12;
    color: #e4e4e7;
}

DataTable > .datatable--header {
    background: #0d0e12;
    color: #52525b;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1f2229;
    color: #ffffff;
    text-style: bold;
    border-left: vkey #9d6fff;
}

DataTable > .datatable--hover {
    background: #16181d;
}

/* Detail Panel / Dossier */
#detail {
    height: 1fr;
    background: #0d0e12;
    color: #d4d4d8;
    padding: 0 1;
}

/* Progress & Logs */
#bottom-container {
    height: 12;
    border-top: solid #1f2229;
    background: #0d0e12;
}

#progress-panel {
    height: 3;
    padding: 1 2;
    background: #16181d;
}

#progress-label {
    height: 1;
    color: #a1a1aa;
    text-style: bold;
}

#log {
    height: 1fr;
    background: #0d0e12;
    color: #8b949e;
    border: none;
    padding: 0 2;
}

Footer {
    background: #16181d;
    color: #52525b;
}

Footer > .footer--key {
    color: #00d4c8;
    background: #1f2229;
}
"""

# --- UI Helper Functions ---
def _make_badge(text: str, color_hex: str) -> Text:
    """Minimalist dot indicator instead of block background."""
    return Text(f"● {text}", style=f"bold {color_hex}")

def _mini_bar(percentage: float, width: int = 10, color: str = "#9d6fff") -> Text:
    """Minimalist thin horizontal bar."""
    filled = int((percentage / 100.0) * width)
    empty = width - filled
    bar_text = ("━" * filled) + ("╌" * empty)
    return Text(f"{bar_text} {percentage:.1f}%", style=color)

def _match_column(value: str) -> Text:
    text = str(value or "0.0%")
    try:
        pct = float(text.split("%")[0])
    except (TypeError, ValueError, IndexError):
        return Text(text, style="dim white")
    color = "#ff007f" if pct >= 70 else "#ffb703" if pct >= 40 else "#00d4c8"
    return _mini_bar(pct, width=8, color=color)

def _grade_badge(value: str) -> Text:
    try:
        grade = float(value)
    except (TypeError, ValueError):
        return _make_badge(str(value or "-"), "#52525b")
    color = "#00e676" if grade >= 80 else "#ffb703" if grade >= 50 else "#ff007f"
    return _make_badge(f"{grade:.1f}%", color)

def _status_badge(stage: str) -> Text:
    palette = {
        "queued": "#52525b",
        "scanning": "#ffb703",
        "scanned": "#00d4c8",
        "comparing": "#9d6fff",
        "grading": "#ffb703",
        "graded": "#00e676",
        "error": "#ff007f",
    }
    return _make_badge(stage.upper(), palette.get(stage, "#52525b"))

def _bool_badge(val: str, ok_val: str, warn_val: str = None) -> Text:
    val = str(val).upper()
    if val == ok_val:
        return _make_badge(val, "#00e676")
    elif warn_val and val == warn_val:
        return _make_badge(val, "#ffb703")
    else:
        return _make_badge(val, "#ff007f")

# --- Main Application ---
class AegisTUI(App):
    CSS = CSS
    TITLE = "AegisCode"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("a", "run_audit", "Run Audit"),
        Binding("r", "refresh", "Reload"),
        Binding("w", "open_web", "Web UI"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, submissions_dir: str = "test_submissions", config: dict | None = None, test_command: str | None = None, rubric_path: str = "rubric.md"):
        super().__init__()
        self.submissions_dir = submissions_dir
        self.config = config or {}
        self.test_command = test_command
        self.rubric_path = rubric_path
        self.student_rows: dict[str, dict] = {}
        self.selected_student: str | None = None
        self.is_auditing = False
        self._web_thread_started = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-panel"):
            yield Static("[#ff5f56]●[/] [#ffbd2e]●[/] [#27c93f]●[/]", id="traffic-lights")
            
            ascii_logo = (
                r"[bold #00d4c8]   __ _  ___  ___ _(_)__[/]  [bold #9d6fff]/ ___/___  ___/ /__[/]" + "\n"
                r"[bold #00d4c8]  / _` |/ -_)/ _ `/ /(_-<[/][bold #9d6fff]/ /__ / _ \/ _  // -_)[/]" + "\n"
                r"[bold #00d4c8]  \_,_| \__/ \_, /_//___/[/][bold #9d6fff]\___/ \___/\_,_/ \__/[/]" + "\n"
                r"[bold #00d4c8]            /___/        [/]"
            )
            yield Static(ascii_logo, id="header-title", markup=True)
            yield Static("STATS WAITING...", id="header-stats")
            
        with Horizontal(id="body"):
            with Vertical(id="table-container"):
                yield DataTable(id="students", cursor_type="row", zebra_stripes=False)
            with Vertical(id="detail-container"):
                yield Static("Select a student to inspect details.", id="detail", markup=True)
                
        with Vertical(id="bottom-container"):
            with Horizontal(id="progress-panel"):
                yield Static("SYSTEM IDLE", id="progress-label")
                yield ProgressBar(id="progress", total=1, show_eta=False)
            yield RichLog(id="log", markup=True, wrap=True)
            
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#students", DataTable)
        table.add_columns("STUDENT", "STAGE", "MATCH", "GIT", "FUZZ", "INTEGRITY", "GRADE")
        self.load_existing_results()
        self.log_message("\n[bold #00d4c8]AEGIS[/][bold #9d6fff]CODE[/] [dim]Forensics Engine Initialized[/]\n[dim]Ready for command payload...[/]")

    def load_existing_results(self) -> None:
        rows = []
        if os.path.exists("grades.csv"):
            with open("grades.csv", "r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.student_rows = {}
        for row in rows:
            name = row.get("Student", "unknown")
            self.student_rows[name] = {**row, "Stage": "graded"}
        self.refresh_table()
        if rows:
            self.log_message(f"[bold #00e676]✓[/] [dim]Loaded {len(rows)} students from database.[/]")
        else:
            self.log_message("[bold #ffb703]![/] [dim]No grades.csv found. Press 'A' to execute Audit Protocol.[/]")

    def refresh_table(self) -> None:
        table = self.query_one("#students", DataTable)
        table.clear()
        for name in sorted(self.student_rows):
            row = self.student_rows[name]
            
            initials = name[:2].upper() if name else "??"
            avatar = f"[#1f2229 on #00d4c8] {initials} [/]"
            
            git_val = str(row.get("Git Forensic Anomaly", "-"))
            fuzz_val = str(row.get("Fuzz/Gaming Anomaly", "-"))
            flag_val = str(row.get("Integrity Flag", "-"))

            table.add_row(
                Text.from_markup(f"{avatar} [bold white]{name}[/]"),
                _status_badge(row.get("Stage", "queued")),
                _match_column(row.get("Max Plagiarism Match", "0.0%")),
                _bool_badge(git_val, "NO", "NO_REPO"),
                _bool_badge(fuzz_val, "PASSED", "WARNING"),
                _bool_badge(flag_val, "CLEAN"),
                _grade_badge(row.get("Adjusted Grade %", "0")),
                key=name,
            )
        self.refresh_summary()
        if self.selected_student and self.selected_student in self.student_rows:
            self.render_detail(self.selected_student)
        elif self.student_rows:
            first = sorted(self.student_rows)[0]
            self.selected_student = first
            self.render_detail(first)

    def refresh_summary(self) -> None:
        total = len(self.student_rows)
        flagged = sum(1 for row in self.student_rows.values() if row.get("Integrity Flag") == "FLAGGED")
        grades = []
        for row in self.student_rows.values():
            try:
                grades.append(float(row.get("Adjusted Grade %", 0)))
            except (TypeError, ValueError):
                pass
        avg = f"{sum(grades) / len(grades):.1f}%" if grades else "-"
        status = "[bold #00e676]ACTIVE[/]" if self.is_auditing else "[bold #a1a1aa]STANDBY[/]"
        
        stats_text = (
            f"[dim]STATUS:[/] {status}  "
            f"[dim]TARGETS:[/] [bold white]{total}[/]  "
            f"[dim]FLAGGED:[/] [bold #ff007f]{flagged}[/]  "
            f"[dim]AVG GRADE:[/] [bold #00d4c8]{avg}[/]"
        )
        self.query_one("#header-stats", Static).update(stats_text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.selected_student = str(event.row_key.value)
        self.render_detail(self.selected_student)

    def render_detail(self, student: str) -> None:
        row = self.student_rows.get(student)
        if not row:
            return
            
        ai_match = row.get("AI Baseline Match", "0.0%")
        llm_flag = row.get("LLM Rewrite Flag", "-")
        git_anomaly = row.get("Git Forensic Anomaly", "-")
        fuzz = row.get("Fuzz/Gaming Anomaly", "-")
        integrity = row.get("Integrity Flag", "-")
        
        c_flag = "#ff007f" if integrity == "FLAGGED" else "#00e676"
        c_llm = "#ff007f" if llm_flag == "YES" else "#00e676"
        c_git = "#00e676" if git_anomaly == "NO" else "#ff007f"
        c_fuzz = "#00e676" if fuzz == "PASSED" else "#ff007f"
        
        try:
            plag_float = float(row.get("Max Plagiarism Match", "0").split("%")[0])
        except:
            plag_float = 0.0
        
        try:
            ai_float = float(ai_match.split("%")[0])
        except:
            ai_float = 0.0

        dossier = (
            f"[bold white]TARGET:[/] [bold #00d4c8]{student}[/]\n"
            f"[bold white]STAGE:[/] {row.get('Stage', '-').upper()}\n\n"
            
            f"[dim #52525b]━━ CODE METRICS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
            f"LOC: [white]{row.get('Lines of Code', '-')}[/]  |  FILES: [white]{row.get('Files Scanned', '-')}[/]\n"
            f"TESTS: [bold white]{row.get('Test Score %', '-')}%[/] ({row.get('Tests Passed', '-')} / {row.get('Total Tests', '-')})\n\n"
            
            f"[dim #52525b]━━ FORENSIC ANALYSIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
            f"PLAGIARISM MATCH: [bold {'#ff007f' if plag_float > 50 else '#00d4c8'}]{row.get('Max Plagiarism Match', '-')}[/]\n"
            f"AI BASELINE MATCH: [bold {'#ff007f' if ai_float > 50 else '#00d4c8'}]{ai_match}[/]\n"
            f"LLM REWRITE FLAG: [bold {c_llm}]{llm_flag}[/]\n"
            f"GIT FORENSICS: [bold {c_git}]{git_anomaly}[/]\n"
            f"FUZZER STATUS: [bold {c_fuzz}]{fuzz}[/]\n"
            f"VIVA VOCE SCORE: [bold white]{row.get('Viva Ownership Score', '-')}[/]\n\n"
        )

        if row.get("Git Notes"):
            dossier += f"[dim]GIT NOTES:[/] [white]{row['Git Notes']}[/]\n\n"

        border_c = "#ff007f" if integrity == "FLAGGED" else "#00e676"
        verdict_text = (
            f"  [bold white]FINAL VERDICT[/]\n"
            f"  ADJUSTED GRADE: [bold #00d4c8]{row.get('Adjusted Grade %', '-')}%[/]\n"
            f"  INTEGRITY OVERALL: [bold {c_flag}]{integrity}[/]\n"
        )

        full_panel = Panel(
            dossier + verdict_text,
            title=f"[bold #9d6fff]■ DOSSIER: {student}[/]",
            border_style=border_c,
            padding=(1, 2)
        )
        self.query_one("#detail", Static).update(full_panel)

    def action_refresh(self) -> None:
        if self.is_auditing:
            self.log_message("[bold #ffb703]![/] Audit sequence locked.")
            return
        self.load_existing_results()

    def action_run_audit(self) -> None:
        if self.is_auditing:
            self.log_message("[bold #ffb703]![/] Audit sequence already in progress.")
            return
        self.run_audit_worker()

    @work(thread=True)
    def run_audit_worker(self) -> None:
        from aegis.grading import execute_grading_pipeline
        self.is_auditing = True
        self.call_from_thread(self.refresh_summary)
        self.call_from_thread(self.set_progress, 0, 1, f"INITIALIZING AUDIT ON {self.submissions_dir.upper()}")

        def callback(event: str, payload: dict) -> None:
            self.call_from_thread(self.handle_progress, event, payload)

        try:
            execute_grading_pipeline(
                self.config,
                self.submissions_dir,
                test_command=self.test_command or self.config.get("test_command"),
                rubric_path=self.rubric_path,
                progress_callback=callback,
            )
        except Exception as exc:
            self.call_from_thread(self.log_message, f"[bold #ff007f]FATAL ERROR:[/] {exc}")
        finally:
            self.is_auditing = False
            self.call_from_thread(self.refresh_summary)

    def handle_progress(self, event: str, payload: dict) -> None:
        if event == "pipeline_started":
            total = payload.get("total_students", 0)
            for name in sorted(os.listdir(self.submissions_dir)):
                full_path = os.path.join(self.submissions_dir, name)
                if os.path.isdir(full_path):
                    self.student_rows[name] = {"Student": name, "Stage": "queued"}
            self.refresh_table()
            self.set_progress(0, max(total, 1), f"TARGET ACQUISITION: {total} HOSTS")
            self.log_message(f"[bold #00d4c8]>[/] Target acquisition complete: {total} directories locked.")
            return

        if event == "student_scan_started":
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row["Stage"] = "scanning"
            self.refresh_table()
            self.set_progress(payload["index"] - 1, payload["total"], f"STATIC ANALYSIS: {payload['student'].upper()}")
            return

        if event == "student_scan_completed":
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row.update({
                "Files Scanned": payload.get("files_scanned", "-"),
                "Lines of Code": payload.get("lines_of_code", "-"),
                "Fuzz/Gaming Anomaly": payload.get("fuzz_anomaly", "-"),
                "Viva Verified": "YES" if payload.get("viva_verified") else "NO",
                "Viva Ownership Score": f"{payload.get('viva_score', 0)}%",
                "Git Forensic Anomaly": "NO" if payload.get("git_repo") else "NO_REPO",
                "Stage": "scanned",
            })
            self.refresh_table()
            self.log_message(f"[bold #9d6fff]>[/] Static scan complete: [white]{payload['student']}[/]")
            return

        if event == "similarity_pair_completed":
            pair_index = payload.get("pair_index", 0)
            total_pairs = payload.get("total_pairs", 1)
            student_a = payload.get("student_a")
            student_b = payload.get("student_b")
            for name in [student_a, student_b]:
                row = self.student_rows.setdefault(name, {"Student": name})
                row["Stage"] = "comparing"
            self.refresh_table()
            self.set_progress(pair_index, total_pairs, f"CROSS-MATCHING: {student_a} ↔ {student_b}")
            return

        if event == "student_grade_started":
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row["Stage"] = "grading"
            self.refresh_table()
            self.set_progress(payload["index"] - 1, payload["total"], f"FUZZING & LLM ANALYSIS: {payload['student'].upper()}")
            return

        if event == "student_grade_completed":
            result = payload.get("result", {})
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row.update(result)
            row["Stage"] = "graded"
            self.refresh_table()
            self.set_progress(payload["index"], payload["total"], f"DOSSIER FINALIZED: {payload['student'].upper()}")
            self.log_message(f"[bold #00e676]>[/] Dossier finalized for [white]{payload['student']}[/]: Grade {result.get('Adjusted Grade %', '-')}%.")
            return

        if event == "pipeline_completed":
            total = payload.get("total_students", 0)
            self.set_progress(total, max(total, 1), "AUDIT SEQUENCE COMPLETE")
            self.log_message(f"\n[bold #00e676]★[/] [white]Audit sequence completed for {total} hosts.[/]")
            return

        if event == "error":
            self.log_message(f"[bold #ff007f]ERROR:[/] {payload.get('message', 'Unknown fault')}")

    def set_progress(self, current: int, total: int, label: str) -> None:
        bar = self.query_one("#progress", ProgressBar)
        bar.update(total=max(total, 1), progress=max(0, current))
        self.query_one("#progress-label", Static).update(label)

    def log_message(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def action_open_web(self) -> None:
        if not self._web_thread_started:
            from aegis.web_server import start_server
            thread = threading.Thread(
                target=start_server,
                kwargs={"config": self.config, "submissions_dir": self.submissions_dir, "port": 8000},
                daemon=True,
            )
            thread.start()
            self._web_thread_started = True
        webbrowser.open("http://localhost:8000")
        self.log_message("[bold #00d4c8]>[/] Dashboard telemetry initialized on localhost:8000")

def launch_tui(submissions_dir: str = "test_submissions", config: dict | None = None, test_command: str | None = None, rubric_path: str = "rubric.md"):
    app = AegisTUI(submissions_dir=submissions_dir, config=config or {}, test_command=test_command, rubric_path=rubric_path)
    app.run()

import csv
import os
import threading
import webbrowser
from typing import ClassVar

from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import DataTable, Footer, ProgressBar, RichLog, Static


CSS = """
Screen {
    background: #09090b;
}

/* Custom Header styling */
#header-panel {
    height: 6;
    background: #09090b;
    border-bottom: heavy #00f0ff;
    padding: 1 2;
}

#header-title {
    color: #9d4edd;
    text-style: bold;
    content-align: left middle;
}

#header-stats {
    color: #a1a1aa;
    text-align: right;
    content-align: right middle;
}

/* Main Layout */
#body {
    height: 1fr;
    background: #09090b;
}

#table-container {
    width: 65%;
    border-right: vkey #27272a;
    background: #09090b;
}

#detail-container {
    width: 35%;
    padding: 1 2;
    background: #050505;
}

/* Data Table */
DataTable {
    background: #09090b;
    color: #e4e4e7;
}

DataTable > .datatable--header {
    background: #18181b;
    color: #00f0ff;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #9d4edd 30%;
    color: #ffffff;
    text-style: bold;
}

/* Detail Panel */
#detail {
    height: 1fr;
    background: #050505;
    color: #d4d4d8;
    border: ascii #00f0ff;
    padding: 1 2;
}

/* Progress & Logs */
#bottom-container {
    height: 14;
    border-top: heavy #00f0ff;
    background: #09090b;
}

#progress-panel {
    height: 3;
    padding: 1 2;
    background: #18181b;
}

#progress-label {
    height: 1;
    color: #00f0ff;
    text-style: bold;
}

#log {
    height: 1fr;
    background: #000000;
    color: #a1a1aa;
    border: none;
    padding: 0 1;
}

Footer {
    background: #18181b;
    color: #00e676;
}
"""


def _grade_text(value: str) -> Text:
    try:
        grade = float(value)
    except (TypeError, ValueError):
        return Text(str(value or "-"), style="dim white")
    color = "#00e676" if grade >= 80 else "#ffb703" if grade >= 50 else "#ff007f"
    return Text(f" {grade:.1f}% ", style=f"bold {color}")


def _match_text(value: str) -> Text:
    text = str(value or "0.0%")
    try:
        pct = float(text.split("%")[0])
    except (TypeError, ValueError, IndexError):
        return Text(text, style="dim white")
    color = "#ff007f" if pct >= 70 else "#ffb703" if pct >= 40 else "#00f0ff"
    return Text(f" {text} ", style=f"bold {color}")


def _status_text(stage: str) -> Text:
    palette = {
        "queued": "#71717a",
        "scanning": "#ffb703",
        "scanned": "#00f0ff",
        "comparing": "#9d4edd",
        "grading": "#ffb703",
        "graded": "#00e676",
        "error": "#ff007f",
    }
    return Text(f" ◉ {stage.upper()} ", style=f"bold {palette.get(stage, '#ffffff')}")


class AegisTUI(App):
    CSS = CSS
    TITLE = "AegisCode"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("a", "run_audit", "🚀 Run Audit"),
        Binding("r", "refresh", "🔄 Reload CSV"),
        Binding("w", "open_web", "🌐 Open Web UI"),
        Binding("q", "quit", "❌ Quit"),
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
            yield Static(
                "█████╗ ███████╗ ██████╗ ██╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗\n"
                "██╔══██╗██╔════╝██╔════╝ ██║██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝\n"
                "███████║█████╗  ██║  ███╗██║███████╗██║     ██║   ██║██║  ██║█████╗  \n"
                "██╔══██║██╔══╝  ██║   ██║██║╚════██║██║     ██║   ██║██║  ██║██╔══╝  \n"
                "██║  ██║███████╗╚██████╔╝██║███████║╚██████╗╚██████╔╝██████╔╝███████╗\n"
                "╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝",
                id="header-title"
            )
            yield Static("STATS WAITING...", id="header-stats")
            
        with Horizontal(id="body"):
            with Vertical(id="table-container"):
                yield DataTable(id="students", cursor_type="row", zebra_stripes=True)
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
        self.log_message("\n[bold #00f0ff]AegisCode Forensics Engine Initialized[/]\n[dim]Ready for command payload...[/]")

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
            self.log_message(f"[bold #00e676]✓[/] [white]Loaded {len(rows)} students from database.[/]")
        else:
            self.log_message("[bold #ffb703]![/] [white]No grades.csv found. Press 'A' to execute Audit Protocol.[/]")

    def refresh_table(self) -> None:
        table = self.query_one("#students", DataTable)
        table.clear()
        for name in sorted(self.student_rows):
            row = self.student_rows[name]
            
            git_val = str(row.get("Git Forensic Anomaly", "-"))
            git_fmt = f"[#00e676]{git_val}[/]" if git_val == "NO" else f"[bold #ff007f]{git_val}[/]"
            
            fuzz_val = str(row.get("Fuzz/Gaming Anomaly", "-"))
            fuzz_fmt = f"[#00e676]{fuzz_val}[/]" if fuzz_val == "PASSED" else f"[bold #ff007f]{fuzz_val}[/]"
            
            flag_val = str(row.get("Integrity Flag", "-"))
            flag_fmt = f"[bold #ff007f]⚠ {flag_val}[/]" if flag_val == "FLAGGED" else f"[bold #00e676]✓ {flag_val}[/]"

            table.add_row(
                Text(f" {name} ", style="bold #ffffff"),
                _status_text(row.get("Stage", "queued")),
                _match_text(row.get("Max Plagiarism Match", "0.0%")),
                Text.from_markup(git_fmt),
                Text.from_markup(fuzz_fmt),
                Text.from_markup(flag_fmt),
                _grade_text(row.get("Adjusted Grade %", "0")),
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
        status = "[bold #00e676]ACTIVE[/]" if self.is_auditing else "[bold #00f0ff]STANDBY[/]"
        
        stats_text = (
            f"[dim]SYSTEM STATUS:[/] {status}\n"
            f"[dim]TARGETS SCANNED:[/] [bold white]{total}[/]\n"
            f"[dim]INTEGRITY VIOLATIONS:[/] [bold #ff007f]{flagged}[/]\n"
            f"[dim]MEAN ACCURACY:[/] [bold #00f0ff]{avg}[/]"
        )
        self.query_one("#header-stats", Static).update(stats_text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.selected_student = str(event.row_key.value)
        self.render_detail(self.selected_student)

    def render_detail(self, student: str) -> None:
        row = self.student_rows.get(student)
        if not row:
            return
            
        ai_match = row.get("AI Baseline Match", "-")
        llm_flag = row.get("LLM Rewrite Flag", "-")
        git_anomaly = row.get("Git Forensic Anomaly", "-")
        fuzz = row.get("Fuzz/Gaming Anomaly", "-")
        integrity = row.get("Integrity Flag", "-")
        
        c_flag = "#ff007f" if integrity == "FLAGGED" else "#00e676"
        c_ai = "#ff007f" if row.get("AI Flagged") == "YES" else "#00e676"
        c_llm = "#ff007f" if llm_flag == "YES" else "#00e676"
        c_git = "#00e676" if git_anomaly == "NO" else "#ff007f"
        c_fuzz = "#00e676" if fuzz == "PASSED" else "#ff007f"
        
        panel_content = (
            f"[bold #ffffff]TARGET:[/] [bold #00f0ff]{student.upper()}[/]\n"
            f"[bold #ffffff]STAGE:[/] {row.get('Stage', '-').upper()}\n\n"
            f"[bold #9d4edd]─── CODE METRICS ───────────────────────[/]\n"
            f"[dim]LOC:[/] [white]{row.get('Lines of Code', '-')}[/]  |  [dim]FILES:[/] [white]{row.get('Files Scanned', '-')}[/]\n"
            f"[dim]TESTS:[/] [white]{row.get('Test Score %', '-')}%[/] ({row.get('Tests Passed', '-')} / {row.get('Total Tests', '-')})\n\n"
            f"[bold #9d4edd]─── FORENSIC ANALYSIS ──────────────────[/]\n"
            f"[dim]PLAGIARISM MATCH:[/] [bold white]{row.get('Max Plagiarism Match', '-')}[/]\n"
            f"[dim]AI BASELINE MATCH:[/] [bold {c_ai}]{ai_match}[/]\n"
            f"[dim]LLM REWRITE FLAG:[/] [bold {c_llm}]{llm_flag}[/]\n"
            f"[dim]GIT FORENSICS:[/] [bold {c_git}]{git_anomaly}[/]\n"
            f"[dim]FUZZER STATUS:[/] [bold {c_fuzz}]{fuzz}[/]\n"
            f"[dim]VIVA VOCE SCORE:[/] [bold white]{row.get('Viva Ownership Score', '-')}[/]\n\n"
            f"[bold #9d4edd]─── FINAL VERDICT ──────────────────────[/]\n"
            f"[dim]ADJUSTED GRADE:[/] [bold #00f0ff]{row.get('Adjusted Grade %', '-')}%[/]\n"
            f"[dim]INTEGRITY OVERALL:[/] [bold {c_flag}]{integrity}[/]\n"
        )
        
        if row.get("Git Notes"):
            panel_content += f"\n[dim]GIT NOTES:[/] [white]{row['Git Notes']}[/]"

        self.query_one("#detail", Static).update(Panel(
            panel_content,
            title=f"[bold #00f0ff]▤ DOSSIER: {student}[/]",
            border_style="#9d4edd",
            box=getattr(import_rich_box(), "SQUARE", None)
        ))

    def action_refresh(self) -> None:
        if self.is_auditing:
            self.log_message("[bold #ffb703]![/] Audit sequence locked. Cannot refresh.")
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
            self.log_message(f"[bold #00f0ff]>[/] Target acquisition complete: {total} directories locked.")
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
            self.log_message(f"[bold #9d4edd]>[/] Static scan complete: [white]{payload['student']}[/]")
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
        self.log_message("[bold #00f0ff]>[/] Dashboard telemetry initialized on localhost:8000")


def import_rich_box():
    import rich.box
    return rich.box

def launch_tui(submissions_dir: str = "test_submissions", config: dict | None = None, test_command: str | None = None, rubric_path: str = "rubric.md"):
    app = AegisTUI(submissions_dir=submissions_dir, config=config or {}, test_command=test_command, rubric_path=rubric_path)
    app.run()

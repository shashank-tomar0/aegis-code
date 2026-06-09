import csv
import os
import threading
import webbrowser
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, ProgressBar, RichLog, Static


CSS = """
Screen {
    background: #111318;
}

#summary {
    height: 3;
    padding: 0 1;
    color: #d7dae0;
    background: #1a1f29;
    border-bottom: solid #2d3442;
}

#body {
    height: 1fr;
}

#table-panel {
    width: 58;
    border-right: solid #2d3442;
}

#detail-panel {
    width: 1fr;
    padding: 1 2;
}

#detail {
    height: 1fr;
    border: round #2d3442;
    padding: 1 1;
}

#progress-panel {
    height: 4;
    padding: 0 1;
    background: #1a1f29;
    border-top: solid #2d3442;
}

#progress-label {
    height: 1;
    color: #d7dae0;
}

#log {
    height: 10;
    border-top: solid #2d3442;
}
"""


def _grade_text(value: str) -> Text:
    try:
        grade = float(value)
    except (TypeError, ValueError):
        return Text(str(value or "-"))
    color = "green" if grade >= 80 else "yellow" if grade >= 50 else "red"
    return Text(f"{grade:.1f}%", style=f"bold {color}")


def _match_text(value: str) -> Text:
    text = str(value or "0.0%")
    try:
        pct = float(text.split("%")[0])
    except (TypeError, ValueError, IndexError):
        return Text(text)
    color = "red" if pct >= 70 else "yellow" if pct >= 40 else "cyan"
    return Text(text, style=color)


def _status_text(stage: str) -> Text:
    palette = {
        "queued": "white",
        "scanning": "yellow",
        "scanned": "cyan",
        "comparing": "magenta",
        "grading": "yellow",
        "graded": "green",
        "error": "red",
    }
    return Text(stage.upper(), style=f"bold {palette.get(stage, 'white')}")


class AegisTUI(App):
    CSS = CSS
    TITLE = "AegisCode"
    SUB_TITLE = "Live audit dashboard"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("a", "run_audit", "Run Audit"),
        Binding("r", "refresh", "Reload CSV"),
        Binding("w", "open_web", "Open Web"),
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
        yield Header(show_clock=True)
        yield Static("Waiting for audit data.", id="summary")
        with Horizontal(id="body"):
            with Vertical(id="table-panel"):
                yield DataTable(id="students", cursor_type="row", zebra_stripes=True)
            with Vertical(id="detail-panel"):
                yield Static("Select a student to inspect details.", id="detail")
        with Vertical(id="progress-panel"):
            yield Static("Idle", id="progress-label")
            yield ProgressBar(id="progress", total=1, show_eta=False)
        yield RichLog(id="log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#students", DataTable)
        table.add_columns("Student", "Stage", "Match", "Git", "Fuzz", "Integrity", "Grade")
        self.load_existing_results()

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
            self.log_message(f"[green]Loaded {len(rows)} students from grades.csv[/]")
        else:
            self.log_message("[yellow]No grades.csv found yet. Press 'a' to run an audit.[/]")

    def refresh_table(self) -> None:
        table = self.query_one("#students", DataTable)
        table.clear()
        for name in sorted(self.student_rows):
            row = self.student_rows[name]
            table.add_row(
                Text(name, style="bold white"),
                _status_text(row.get("Stage", "queued")),
                _match_text(row.get("Max Plagiarism Match", "0.0%")),
                Text(str(row.get("Git Forensic Anomaly", "-"))),
                Text(str(row.get("Fuzz/Gaming Anomaly", "-"))),
                Text(str(row.get("Integrity Flag", "-"))),
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
        status = "Audit running" if self.is_auditing else "Ready"
        self.query_one("#summary", Static).update(
            f"Students: {total}    Flagged: {flagged}    Avg grade: {avg}    Status: {status}"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.selected_student = str(event.row_key.value)
        self.render_detail(self.selected_student)

    def render_detail(self, student: str) -> None:
        row = self.student_rows.get(student)
        if not row:
            return
        details = [
            f"[b]{student}[/b]",
            "",
            f"Stage: {row.get('Stage', '-')}",
            f"Integrity: {row.get('Integrity Flag', '-')}",
            f"Adjusted grade: {row.get('Adjusted Grade %', '-')}%",
            f"Test score: {row.get('Test Score %', '-')}% ({row.get('Tests Passed', '-')} / {row.get('Total Tests', '-')})",
            f"Plagiarism: {row.get('Max Plagiarism Match', '-')}",
            f"Git anomaly: {row.get('Git Forensic Anomaly', '-')}",
            f"Fuzz anomaly: {row.get('Fuzz/Gaming Anomaly', '-')}",
            f"Viva verified: {row.get('Viva Verified', '-')}",
            f"Viva ownership: {row.get('Viva Ownership Score', '-')}",
            f"Files scanned: {row.get('Files Scanned', '-')}",
            f"Lines of code: {row.get('Lines of Code', '-')}",
        ]
        if row.get("Git Notes"):
            details.extend(["", "Git notes:", str(row["Git Notes"])])
        if row.get("Last Event"):
            details.extend(["", "Last event:", str(row["Last Event"])])
        self.query_one("#detail", Static).update("\n".join(details))

    def action_refresh(self) -> None:
        if self.is_auditing:
            self.log_message("[yellow]Audit is already running.[/]")
            return
        self.load_existing_results()

    def action_run_audit(self) -> None:
        if self.is_auditing:
            self.log_message("[yellow]Audit is already running.[/]")
            return
        self.run_audit_worker()

    @work(thread=True)
    def run_audit_worker(self) -> None:
        from aegis.grading import execute_grading_pipeline

        self.is_auditing = True
        self.call_from_thread(self.refresh_summary)
        self.call_from_thread(self.set_progress, 0, 1, f"Starting audit for {self.submissions_dir}")

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
            self.call_from_thread(self.log_message, f"[red]Audit failed: {exc}[/]")
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
            self.set_progress(0, max(total, 1), f"Discovered {total} submissions")
            self.log_message(f"[cyan]Discovered {total} student folders in {self.submissions_dir}[/]")
            return

        if event == "student_scan_started":
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row["Stage"] = "scanning"
            row["Last Event"] = "Scanning repository"
            self.refresh_table()
            self.set_progress(payload["index"] - 1, payload["total"], f"Scanning {payload['student']}")
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
                "Git Notes": "; ".join(payload.get("git_anomalies", [])),
                "Stage": "scanned",
                "Last Event": "Static analysis complete",
            })
            self.refresh_table()
            self.log_message(f"[cyan]Scanned {payload['student']}[/]")
            return

        if event == "similarity_pair_completed":
            pair_index = payload.get("pair_index", 0)
            total_pairs = payload.get("total_pairs", 1)
            student_a = payload.get("student_a")
            student_b = payload.get("student_b")
            for name in [student_a, student_b]:
                row = self.student_rows.setdefault(name, {"Student": name})
                row["Stage"] = "comparing"
                row["Last Event"] = f"Compared with {student_b if name == student_a else student_a}"
            self.refresh_table()
            self.set_progress(pair_index, total_pairs, f"Similarity {pair_index}/{total_pairs}: {student_a} vs {student_b}")
            return

        if event == "student_grade_started":
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row["Stage"] = "grading"
            row["Last Event"] = "Running tests and generating feedback"
            self.refresh_table()
            self.set_progress(payload["index"] - 1, payload["total"], f"Grading {payload['student']}")
            return

        if event == "student_grade_completed":
            result = payload.get("result", {})
            row = self.student_rows.setdefault(payload["student"], {"Student": payload["student"]})
            row.update(result)
            row["Stage"] = "graded"
            row["Last Event"] = "Grade finalized"
            self.refresh_table()
            self.set_progress(payload["index"], payload["total"], f"Graded {payload['student']}")
            self.log_message(f"[green]Graded {payload['student']} -> {result.get('Adjusted Grade %', '-')}%[/]")
            return

        if event == "pipeline_completed":
            total = payload.get("total_students", 0)
            self.set_progress(total, max(total, 1), f"Audit complete. Wrote {payload.get('csv_file', 'grades.csv')}")
            self.log_message(f"[green]Audit complete for {total} students[/]")
            return

        if event == "error":
            self.log_message(f"[red]{payload.get('message', 'Unknown error')}[/]")

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
        self.log_message("[cyan]Opened web dashboard at http://localhost:8000[/]")


def launch_tui(submissions_dir: str = "test_submissions", config: dict | None = None, test_command: str | None = None, rubric_path: str = "rubric.md"):
    app = AegisTUI(submissions_dir=submissions_dir, config=config or {}, test_command=test_command, rubric_path=rubric_path)
    app.run()

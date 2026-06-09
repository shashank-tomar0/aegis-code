import os
import json
import csv
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from colorama import Fore, Style
from aegis.grading import scan_student_code
from aegis.git_forensics import analyze_git_history
from aegis.winnowing import get_file_fingerprints, compute_similarity

class AegisDashboardHandler(BaseHTTPRequestHandler):
    submissions_dir = "test_submissions"
    config = {}

    def log_message(self, format, *args):
        # Suppress request logging in the terminal to keep it clean
        return

    def _set_headers(self, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def do_GET(self):
        # 1. Serve static Dashboard HTML
        if self.path == "/" or self.path == "/index.html":
            self._set_headers("text/html")
            # Load dashboard.html relative to this file
            html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            except Exception as e:
                self.wfile.write(f"<h1>Error loading dashboard template: {e}</h1>".encode("utf-8"))
            return

        # 2. API: Summary
        elif self.path == "/api/summary":
            self._set_headers()
            results = []
            csv_path = "grades.csv"
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            results.append(row)
                except Exception as e:
                    results = {"error": f"Failed to read grades.csv: {e}"}
            else:
                results = {"error": "grades.csv has not been generated. Run 'aegis audit' first."}
            self.wfile.write(json.dumps(results).encode("utf-8"))
            return

        # 3. API: Student Detail
        elif self.path.startswith("/api/student/"):
            student_name = self.path.split("/")[-1]
            student_dir = os.path.join(self.submissions_dir, student_name)
            
            if not os.path.exists(student_dir):
                self.send_error(404, f"Student {student_name} not found")
                return

            self._set_headers()
            
            # Read files and functions
            code_report = scan_student_code(student_dir)
            git_report = analyze_git_history(student_dir)
            
            # Extract code file contents
            files_content = {}
            for file_path in code_report["files_scanned"]:
                rel_path = os.path.relpath(file_path, student_dir)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        files_content[rel_path] = f.read()
                except Exception:
                    files_content[rel_path] = "# Could not read file contents"

            # Read feedback report if available
            feedback = ""
            feedback_path = os.path.join(student_dir, "feedback.md")
            if os.path.exists(feedback_path):
                try:
                    with open(feedback_path, "r", encoding="utf-8") as f:
                        feedback = f.read()
                except Exception:
                    pass

            response_data = {
                "name": student_name,
                "lines_count": code_report["lines_count"],
                "functions": [
                    {
                        "name": f["name"],
                        "complexity": f["complexity"],
                        "source_code": f["source_code"]
                    } for f in code_report["functions"]
                ],
                "files": files_content,
                "git": {
                    "is_repo": git_report["is_git_repo"],
                    "commit_count": git_report["commit_count"],
                    "authors": git_report["authors"],
                    "emails": git_report["emails"],
                    "step_churn_anomaly": git_report["step_churn_anomaly"],
                    "time_anomaly": git_report["time_anomaly"],
                    "anomalies": git_report["anomalies"],
                    "commits": [
                        {
                            "hash": c["hash"],
                            "message": c["message"],
                            "author": c["author"],
                            "timestamp": c["timestamp"],
                            "additions": c["additions"],
                            "deletions": c["deletions"]
                        } for c in git_report["commits"]
                    ]
                },
                "feedback": feedback
            }
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # 4. API: Compare logic for plagiarism
        elif self.path.startswith("/api/compare/"):
            # Format: /api/compare/student1/student2
            parts = self.path.split("/")
            if len(parts) < 5:
                self.send_error(400, "Invalid compare parameters")
                return
                
            s1, s2 = parts[-2], parts[-1]
            dir1 = os.path.join(self.submissions_dir, s1)
            dir2 = os.path.join(self.submissions_dir, s2)
            
            if not os.path.exists(dir1) or not os.path.exists(dir2):
                self.send_error(404, "One or both students not found")
                return

            self._set_headers()
            
            # Scan both
            rep1 = scan_student_code(dir1)
            rep2 = scan_student_code(dir2)
            
            fp1 = get_file_fingerprints(rep1["tokens"], self.config.get("k_gram", 5), self.config.get("window_size", 4))
            fp2 = get_file_fingerprints(rep2["tokens"], self.config.get("k_gram", 5), self.config.get("window_size", 4))
            
            sim = compute_similarity(fp1, fp2)
            
            # Read first solution file (assuming single main solution file for comparison simplicity)
            code1 = ""
            if rep1["files_scanned"]:
                try:
                    with open(rep1["files_scanned"][0], "r", encoding="utf-8") as f:
                        code1 = f.read()
                except Exception:
                    pass
                    
            code2 = ""
            if rep2["files_scanned"]:
                try:
                    with open(rep2["files_scanned"][0], "r", encoding="utf-8") as f:
                        code2 = f.read()
                except Exception:
                    pass

            response_data = {
                "student1": s1,
                "student2": s2,
                "jaccard": f"{sim['jaccard']*100:.1f}%",
                "containment": f"{sim['containment']*100:.1f}%",
                "code1": code1,
                "code2": code2
            }
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        else:
            self.send_error(404, "API Endpoint not found")

def start_server(config, submissions_dir="test_submissions", port=8000):
    """Starts the HTTP server and opens the web browser automatically."""
    AegisDashboardHandler.submissions_dir = submissions_dir
    AegisDashboardHandler.config = config
    
    server_address = ("", port)
    httpd = HTTPServer(server_address, AegisDashboardHandler)
    
    url = f"http://localhost:{port}"
    print(f"\n{Fore.GREEN}{Style.BRIGHT}AegisCode Report Dashboard running at {url}")
    print(f"{Fore.CYAN}Press Ctrl+C to stop the web server.\n")
    
    # Auto-open browser
    webbrowser.open(url)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Stopping AegisCode report dashboard...")
        httpd.server_close()

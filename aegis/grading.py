import os
import csv
import json
import subprocess
from aegis.ast_analyzer import analyze_file
from aegis.winnowing import get_file_fingerprints, compute_similarity
from aegis.git_forensics import analyze_git_history
from aegis.viva_agent import verify_receipt, get_gemini_client
from colorama import Fore, Style
from aegis.ui import Spinner, print_success, print_warning, print_error, print_info
from aegis.fuzzer import inspect_hardcoding, dynamic_fuzz_test


def _emit_progress(progress_callback, event, **payload):
    if progress_callback:
        progress_callback(event, payload)


def scan_student_code(student_dir):
    """Scans all Python files in a student's folder and aggregates AST tokens and functions."""
    all_tokens = []
    all_functions = []
    total_lines = 0
    python_files = []

    for root, _, files in os.walk(student_dir):
        # Exclude hidden files, virtualenvs, and test directories
        if any(p in root for p in [".git", "venv", "__pycache__", "env"]):
            continue
        for file in files:
            if file.endswith(".py") and not file.startswith("test_"):
                filepath = os.path.join(root, file)
                python_files.append(filepath)
                try:
                    res = analyze_file(filepath)
                    all_tokens.extend(res["tokens"])
                    all_functions.extend(res["functions"])
                    total_lines += res["lines_count"]
                except Exception as e:
                    # Log parsing errors but keep going
                    pass

    return {
        "tokens": all_tokens,
        "functions": all_functions,
        "lines_count": total_lines,
        "files_scanned": python_files
    }

def run_student_tests(student_dir, test_command):
    """Runs tests in the student directory and parses pass/fail rates."""
    if not test_command:
        return {"run": False, "passed": 0, "total": 0, "output": "No test command configured."}
        
    try:
        # Run the test command in student dir
        result = subprocess.run(
            test_command.split(),
            cwd=student_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30
        )
        
        output = result.stdout + "\n" + result.stderr
        
        # Simple parser for pytest or unittest outputs
        # Look for "X passed, Y failed" or "Ran X tests"
        passed = 0
        total = 0
        
        # Pytest matching
        pytest_match = re.search(r"=(\d+)\s+passed(?:,\s+(\d+)\s+failed)?", output)
        if pytest_match:
            passed = int(pytest_match.group(1))
            failed = int(pytest_match.group(2)) if pytest_match.group(2) else 0
            total = passed + failed
        else:
            # Unittest matching: "Ran 5 tests..." and "OK" or "FAILED (failures=1)"
            ran_match = re.search(r"Ran\s+(\d+)\s+tests", output)
            if ran_match:
                total = int(ran_match.group(1))
                if "OK" in output:
                    passed = total
                else:
                    fail_match = re.search(r"failures=(\d+)", output)
                    errors_match = re.search(r"errors=(\d+)", output)
                    fails = int(fail_match.group(1)) if fail_match else 0
                    errors = int(errors_match.group(1)) if errors_match else 0
                    passed = total - (fails + errors)
                    
        return {
            "run": True,
            "passed": passed,
            "total": total,
            "success": result.returncode == 0,
            "output": output
        }
    except subprocess.TimeoutExpired:
        return {"run": True, "passed": 0, "total": 0, "output": "Test execution timed out (30s limit)."}
    except Exception as e:
        return {"run": True, "passed": 0, "total": 0, "output": f"Failed to execute tests: {e}"}

import re

def generate_ai_feedback(config, student_name, code_report, test_report, rubric_path):
    """Uses Gemini to generate detailed rubric-based feedback for a student."""
    rubric_content = ""
    if os.path.exists(rubric_path):
        try:
            with open(rubric_path, "r", encoding="utf-8") as f:
                rubric_content = f.read()
        except Exception:
            pass

    # Extract clean overview of functions to show AI
    fn_summaries = []
    for fn in code_report["functions"]:
        fn_summaries.append(f"Function: {fn['name']} (Complexity: {fn['complexity']})\nSource:\n{fn['source_code']}\n")
        
    code_summary = "\n".join(fn_summaries)
    
    prompt = f"""
You are an expert computer science TA. Write a comprehensive, supportive, and detailed feedback report for a student named '{student_name}'.

Evaluate their submission using this rubric:
{rubric_content if rubric_content else "Check for code functionality, formatting, logic, and complexity."}

Student Code Details:
Total Files Scanned: {len(code_report['files_scanned'])}
Total lines of code: {code_report['lines_count']}
Functions analyzed:
{code_summary}

Test Run Output:
Passed: {test_report.get('passed', 0)} / {test_report.get('total', 0)}
Details:
{test_report.get('output', '')[:800]} # Truncate if too long

Generate a feedback report in Markdown format. Outline:
1. Grade Score / Evaluation Table
2. Code Structure & Design Review (highlight good practices and areas for improvement)
3. Complexity & Algorithmic Design suggestions
4. Next Steps for learning.
Keep the tone encouraging yet rigorous.
"""
    if not config.get("api_key"):
        return f"# Feedback for {student_name}\n\nGemini API key is not configured, so AI feedback was skipped."

    try:
        client = get_gemini_client(config["api_key"])
        model = client.GenerativeModel(config["model_name"])
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"# Feedback for {student_name}\n\nFailed to generate AI feedback: {e}"

def execute_grading_pipeline(config, submissions_dir, test_command=None, rubric_path="rubric.md", progress_callback=None):
    """Runs the full grading, similarity matching, git forensics, and receipt checking pipeline."""
    if not os.path.exists(submissions_dir):
        print_error(f"Submissions directory '{submissions_dir}' does not exist.")
        _emit_progress(progress_callback, "error", message=f"Submissions directory '{submissions_dir}' does not exist.")
        return False
        
    students = [d for d in os.listdir(submissions_dir) if os.path.isdir(os.path.join(submissions_dir, d))]
    
    if not students:
        print_warning(f"No student subdirectories found in '{submissions_dir}'.")
        _emit_progress(progress_callback, "error", message=f"No student subdirectories found in '{submissions_dir}'.")
        return False

    _emit_progress(progress_callback, "pipeline_started", total_students=len(students), submissions_dir=submissions_dir)

    student_data = {}
    with Spinner("Scanning student repositories & mining Git history..."):
        for index, student in enumerate(students, start=1):
            student_dir = os.path.join(submissions_dir, student)
            _emit_progress(progress_callback, "student_scan_started", student=student, index=index, total=len(students))
            code_report = scan_student_code(student_dir)
            git_report = analyze_git_history(student_dir)
            
            # Winnowing fingerprints
            fp = get_file_fingerprints(code_report["tokens"], config["k_gram"], config["window_size"])
            
            # Check for receipt
            receipt_path = os.path.join(student_dir, ".aegis_vet_receipt")
            viva_verified, viva_msg = verify_receipt(receipt_path)
            
            # Load score from receipt if verified
            viva_score = 100
            if viva_verified:
                try:
                    with open(receipt_path, "r") as f:
                        receipt_data = json.load(f)
                        viva_score = int(receipt_data.get("ownership_score", 100))
                except Exception:
                    pass
            
            # Run Fuzzer Checks
            hardcode_count = 0
            constants_checked = []
            fuzz_passed = True
            fuzz_message = "Passed"
            
            for file_path in code_report["files_scanned"]:
                hc_cnt, consts = inspect_hardcoding(file_path)
                hardcode_count += hc_cnt
                constants_checked.extend(consts)
                
                passed, msg = dynamic_fuzz_test(file_path, "search")
                if not passed:
                    fuzz_passed = False
                    fuzz_message = msg

            if hardcode_count > 0 and not fuzz_passed:
                fuzz_anomaly = "BOTH_FAILED"
            elif hardcode_count > 0:
                fuzz_anomaly = "HARDCODED_CHEAT"
            elif not fuzz_passed:
                fuzz_anomaly = "FUZZ_FAILED"
            else:
                fuzz_anomaly = "PASSED"

            student_data[student] = {
                "dir": student_dir,
                "code": code_report,
                "git": git_report,
                "fingerprints": fp,
                "viva_verified": viva_verified,
                "viva_score": viva_score,
                "viva_msg": viva_msg,
                "fuzz_anomaly": fuzz_anomaly,
                "fuzz_message": fuzz_message,
                "hardcode_count": hardcode_count,
                "constants_checked": constants_checked
            }
            _emit_progress(
                progress_callback,
                "student_scan_completed",
                student=student,
                index=index,
                total=len(students),
                files_scanned=len(code_report["files_scanned"]),
                lines_of_code=code_report["lines_count"],
                fuzz_anomaly=fuzz_anomaly,
                git_repo=git_report["is_git_repo"],
                git_anomalies=list(git_report["anomalies"]),
                viva_verified=viva_verified,
                viva_score=viva_score,
            )

    # Cross-match students for plagiarism
    with Spinner("Computing AST Winnowing similarity matrix..."):
        similarity_matrix = {}
        total_pairs = max(len(students) * (len(students) - 1) // 2, 1)
        pair_index = 0
        for i, s1 in enumerate(students):
            similarity_matrix[s1] = {"max_jaccard": 0.0, "match_partner": None, "max_containment": 0.0}
            for s2 in students[i + 1:]:
                pair_index += 1
                sim = compute_similarity(student_data[s1]["fingerprints"], student_data[s2]["fingerprints"])
                if sim["jaccard"] > similarity_matrix[s1]["max_jaccard"]:
                    similarity_matrix[s1]["max_jaccard"] = sim["jaccard"]
                    similarity_matrix[s1]["max_containment"] = sim["containment"]
                    similarity_matrix[s1]["match_partner"] = s2
                similarity_matrix.setdefault(s2, {"max_jaccard": 0.0, "match_partner": None, "max_containment": 0.0})
                if sim["jaccard"] > similarity_matrix[s2]["max_jaccard"]:
                    similarity_matrix[s2]["max_jaccard"] = sim["jaccard"]
                    similarity_matrix[s2]["max_containment"] = sim["containment"]
                    similarity_matrix[s2]["match_partner"] = s1
                _emit_progress(
                    progress_callback,
                    "similarity_pair_completed",
                    student_a=s1,
                    student_b=s2,
                    similarity=sim["jaccard"],
                    pair_index=pair_index,
                    total_pairs=total_pairs,
                )

    # Run tests and write feedback
    results = []
    for index, student in enumerate(students, start=1):
        data = student_data[student]
        _emit_progress(progress_callback, "student_grade_started", student=student, index=index, total=len(students))
        
        with Spinner(f"Grading {Fore.CYAN}{student}{Fore.WHITE} (running tests & generating feedback)..."):
            # Run tests
            test_report = run_student_tests(data["dir"], test_command)
            
            # Run AI feedback
            feedback = generate_ai_feedback(config, student, data["code"], test_report, rubric_path)
            
            # Write feedback file inside student's directory
            feedback_file = os.path.join(data["dir"], "feedback.md")
            try:
                with open(feedback_file, "w", encoding="utf-8") as f:
                    f.write(feedback)
            except Exception as e:
                print_error(f"Failed to write feedback for {student}: {e}")

        # Compute grade details
        max_sim = similarity_matrix[student]
        
        # Calculate test grade
        test_pct = 0.0
        if test_report["run"] and test_report["total"] > 0:
            test_pct = (test_report["passed"] / test_report["total"]) * 100
        elif not test_report["run"]:
            test_pct = 100.0 # Default if no tests configured
            
        # Vetting grade factor: Grade is penalized if ownership is low
        viva_factor = data["viva_score"] / 100.0
        final_grade = test_pct * viva_factor
        
        # Determine Integrity Flags
        plagiarism_flag = max_sim["max_jaccard"] >= config["similarity_threshold"]
        git_flag = (not data["git"]["is_git_repo"]) or data["git"]["step_churn_anomaly"] or data["git"]["time_anomaly"]
        viva_flag = (not data["viva_verified"]) or (data["viva_score"] < 50)
        fuzz_flag = data["fuzz_anomaly"] != "PASSED"
        
        integrity_flag = plagiarism_flag or git_flag or viva_flag or fuzz_flag
        
        git_anomaly_str = "NO"
        if not data["git"]["is_git_repo"]:
            git_anomaly_str = "NO_REPO"
        elif data["git"]["step_churn_anomaly"]:
            git_anomaly_str = "CHURN"
        elif data["git"]["time_anomaly"]:
            git_anomaly_str = "SPEED"
            
        results.append({
            "Student": student,
            "Files Scanned": len(data["code"]["files_scanned"]),
            "Lines of Code": data["code"]["lines_count"],
            "Tests Passed": test_report.get("passed", 0),
            "Total Tests": test_report.get("total", 0),
            "Test Score %": f"{test_pct:.1f}",
            "Max Plagiarism Match": f"{max_sim['max_jaccard']*100:.1f}% ({max_sim['match_partner']})",
            "Git Forensic Anomaly": git_anomaly_str,
            "Fuzz/Gaming Anomaly": data["fuzz_anomaly"],
            "Viva Verified": "YES" if data["viva_verified"] else "NO",
            "Viva Ownership Score": f"{data['viva_score']}%",
            "Integrity Flag": "FLAGGED" if integrity_flag else "CLEAN",
            "Adjusted Grade %": f"{final_grade:.1f}"
        })
        _emit_progress(
            progress_callback,
            "student_grade_completed",
            student=student,
            index=index,
            total=len(students),
            result=results[-1],
            test_output=test_report.get("output", ""),
            feedback_path=feedback_file,
        )

    # Output grades.csv
    csv_file = "grades.csv"
    try:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print_success(f"Unified Grade Sheet compiled successfully to {Fore.GREEN}{csv_file}")
    except Exception as e:
        print_error(f"Failed to write {csv_file}: {e}")
        _emit_progress(progress_callback, "error", message=f"Failed to write {csv_file}: {e}")

    _emit_progress(progress_callback, "pipeline_completed", total_students=len(results), results=results, csv_file=csv_file)
    return results

import os
import sys
import argparse
import json
from colorama import Fore, Style, init

from aegis.config import load_config, save_config, DEFAULT_CONFIG
from aegis.ast_analyzer import analyze_file
from aegis.viva_agent import run_interactive_viva
from aegis.grading import execute_grading_pipeline, scan_student_code
from aegis.ui import print_banner, print_section, print_success, print_warning, print_error, print_info, Spinner

# Initialize colorama
init(autoreset=True)

DEFAULT_RUBRIC = """# Homework Rubric

## 1. Functionality (60%)
- All automated unit tests pass.
- Edge cases are handled gracefully (e.g. empty lists, negative integers).

## 2. Code Quality & Architecture (20%)
- Clean variable names.
- Logical function division.
- Proper scoping and DRY principles.

## 3. Algorithmic Efficiency & Complexity (20%)
- Optimal time complexity (e.g. no unnecessary nested loops).
- Proper space complexity management.
"""

def init_command(args):
    """Initializes the local aegis.json configuration and rubric.md template."""
    print_banner()
    print_section("INITIALIZING WORKSPACE")
    
    # Save default config if not exists
    if not os.path.exists("aegis.json"):
        save_config(DEFAULT_CONFIG)
        print_success("Created configuration file: aegis.json")
    else:
        print_warning("aegis.json already exists. Skipping.")
        
    # Save default rubric if not exists
    if not os.path.exists("rubric.md"):
        try:
            with open("rubric.md", "w", encoding="utf-8") as f:
                f.write(DEFAULT_RUBRIC)
            print_success("Created grading rubric template: rubric.md")
        except Exception as e:
            print_error(f"Failed to create rubric.md: {e}")
    else:
        print_warning("rubric.md already exists. Skipping.")
        
    print(f"\n{Fore.GREEN}{Style.BRIGHT}✔ Workspace initialized! Adjust settings in aegis.json and rubric.md.")

def vet_command(args):
    """Runs the interactive Viva Voce vetting interview in the student's repository."""
    print_banner()
    config = load_config()
    
    if not config.get("api_key"):
        print_error("Gemini API Key is missing.")
        print_warning("Please set the GEMINI_API_KEY environment variable or write it to aegis.json.")
        sys.exit(1)

    target_dir = args.dir or "."
    
    # Prompt for student name if not provided
    student_name = args.student
    if not student_name:
        sys.stdout.write(f"{Fore.CYAN}Please enter your Full Name: {Style.RESET_ALL}")
        sys.stdout.flush()
        student_name = input().strip()
        if not student_name:
            print_error("Student name cannot be empty.")
            sys.exit(1)

    # Scan python files
    with Spinner("Scanning files for coding structures..."):
        code_report = scan_student_code(target_dir)
    
    if not code_report["functions"]:
        print_error(f"No functions found to analyze in {target_dir}.")
        print_info("Please ensure your Python source files contain function definitions.")
        sys.exit(1)

    # Run the interactive Viva
    receipt = run_interactive_viva(config, student_name, code_report["functions"], target_dir)
    
    if receipt:
        # Save receipt locally
        receipt_path = os.path.join(target_dir, ".aegis_vet_receipt")
        try:
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=4)
            print_success(f"Vetting Complete! Signed receipt generated at {receipt_path}")
            print_info("Ensure this receipt file is included in your final submission.")
        except Exception as e:
            print_error(f"Failed to save receipt file: {e}")
    else:
        print_error("Vetting failed. No receipt generated.")

def audit_command(args):
    """Runs the teacher grading and plagiarism audit on submissions."""
    print_banner()
    config = load_config()
    
    # Setup test runner command
    test_command = args.tests
    if not test_command and "test_command" in config:
        test_command = config["test_command"]
        
    rubric_path = args.rubric or "rubric.md"
    submissions_dir = args.submissions_dir
    
    if not submissions_dir:
        print_error("Submissions directory is required.")
        sys.exit(1)
        
    print_section("AUDIT & GRADING PIPELINE")
    
    results = execute_grading_pipeline(config, submissions_dir, test_command, rubric_path)
    
    if results:
        # Display summary table
        try:
            from tabulate import tabulate
            use_tabulate = True
        except ImportError:
            use_tabulate = False

        summary_rows = []
        for r in results:
            summary_rows.append([
                r["Student"], 
                r["Test Score %"], 
                r["Max Plagiarism Match"], 
                r["Git Forensic Anomaly"], 
                r["Fuzz/Gaming Anomaly"],
                r["Viva Verified"], 
                r["Viva Ownership Score"], 
                r["Integrity Flag"], 
                r["Adjusted Grade %"]
            ])
            
        headers = [
            "Student", "Tests %", "Max Match", "Git Churn", "Fuzz/Game", "Viva Ok", "Ownership", "Integrity", "Final Grade %"
        ]
        
        if use_tabulate:
            print("\n" + tabulate(summary_rows, headers=headers, tablefmt="fancy_grid") + "\n")
        else:
            # Fallback simple text table formatter
            all_cols = [headers] + summary_rows
            col_widths = [max(len(str(item)) for item in col) for col in zip(*all_cols)]
            border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
            
            lines = [border]
            header_line = "|" + "|".join(f" {str(h).ljust(w)} " for h, w in zip(headers, col_widths)) + "|"
            lines.append(header_line)
            lines.append(border)
            
            for row in summary_rows:
                row_line = "|" + "|".join(f" {str(item).ljust(w)} " for item, w in zip(row, col_widths)) + "|"
                lines.append(row_line)
                
            lines.append(border)
            print("\n" + "\n".join(lines) + "\n")

def web_command(args):
    """Starts the local web report server."""
    config = load_config()
    submissions_dir = args.submissions_dir or "test_submissions"
    port = args.port or 8000
    
    from aegis.web_server import start_server
    start_server(config, submissions_dir, port)

def tui_command(args):
    """Launches the rich interactive Terminal UI dashboard."""
    config = load_config()
    submissions_dir = args.submissions_dir or "test_submissions"
    
    try:
        from aegis.tui import launch_tui
        launch_tui(
            submissions_dir=submissions_dir,
            config=config,
            test_command=args.tests or config.get("test_command"),
            rubric_path=args.rubric or "rubric.md",
        )
    except ImportError as e:
        print_error(f"TUI dependencies missing. Run: pip install textual rich")
        print_error(f"Details: {e}")
        sys.exit(1)

def clone_command(args):
    """Bulk clones student repositories from a list of URLs or a single URL."""
    import subprocess
    print_banner()
    print_section("BULK CLONING STUDENT REPOSITORIES")
    
    # 1. Gather URLs
    urls = []
    
    if args.classroom:
        from aegis.classroom import extract_assignment_id, fetch_classroom_repos
        assignment_id = extract_assignment_id(args.classroom)
        config = load_config()
        # Fallback to env var if not in aegis.json
        gh_token = config.get("github_token") or os.environ.get("GITHUB_TOKEN", "")
        
        fetched_urls = fetch_classroom_repos(assignment_id, gh_token)
        if not fetched_urls:
            print_error("Failed to fetch classroom repositories.")
            sys.exit(1)
        urls.extend(fetched_urls)
    else:
        source = args.repo_source
        if not source:
            print_error("Must provide either repo_source or --classroom.")
            sys.exit(1)
            
        if os.path.exists(source):
            try:
                with open(source, "r", encoding="utf-8") as f:
                    for line in f:
                        u = line.strip()
                        if u and not u.startswith("#"):
                            urls.append(u)
                print_info(f"Loaded {len(urls)} URLs from file: {source}")
            except Exception as e:
                print_error(f"Failed to read file {source}: {e}")
                sys.exit(1)
        else:
            if source.startswith(("http://", "https://", "git@", "ssh://")):
                urls.append(source)
                print_info(f"Using single repository URL: {source}")
            else:
                if "," in source:
                    urls = [u.strip() for u in source.split(",") if u.strip()]
                    print_info(f"Using {len(urls)} comma-separated repository URLs")
                else:
                    print_error(f"Source '{source}' is neither an existing file nor a valid Git URL.")
                    sys.exit(1)
                
    if not urls:
        print_warning("No URLs found to clone.")
        return

    dest_dir = args.dest
    os.makedirs(dest_dir, exist_ok=True)
    
    # 2. Clone each
    success_count = 0
    for idx, url in enumerate(urls, 1):
        print(f"\n{Fore.CYAN}[{idx}/{len(urls)}] Processing repository: {url}")
        
        # Extract student name from URL
        repo_name = url.split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
            
        student_name = repo_name
        if student_name.startswith("assignment-"):
            student_name = student_name[len("assignment-"):]
            
        student_folder = os.path.join(dest_dir, student_name)
        
        if os.path.exists(student_folder):
            print_warning(f"Destination folder '{student_folder}' already exists. Skipping clone.")
            continue
            
        try:
            with Spinner(f"Cloning into {student_folder}..."):
                res = subprocess.run(
                    ["git", "clone", url, student_folder],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=60
                )
            if res.returncode == 0:
                print_success(f"Successfully cloned student submission for: {Fore.GREEN}{student_name}")
                success_count += 1
            else:
                print_error(f"Failed to clone {url}: {res.stderr.strip()}")
        except subprocess.TimeoutExpired:
            print_error(f"Clone timed out for {url}")
        except Exception as e:
            print_error(f"Git execution error: {e}")
            
    print(f"\n{Fore.GREEN}{Style.BRIGHT}✔ Bulk cloning complete! {success_count}/{len(urls)} repositories successfully cloned.")

    # 3. Optional post-clone audit
    if args.audit:
        print("\n" + "="*60)
        config = load_config()
        test_command = config.get("test_command")
        rubric_path = "rubric.md"
        print_section("AUTOMATIC AUDIT PIPELINE RUN")
        results = execute_grading_pipeline(config, dest_dir, test_command, rubric_path)
        if results:
            summary_rows = []
            for r in results:
                summary_rows.append([
                    r["Student"], 
                    r["Test Score %"], 
                    r["Max Plagiarism Match"], 
                    r["Git Forensic Anomaly"], 
                    r["Fuzz/Gaming Anomaly"],
                    r["Viva Verified"], 
                    r["Viva Ownership Score"], 
                    r["Integrity Flag"], 
                    r["Adjusted Grade %"]
                ])
                
            headers = [
                "Student", "Tests %", "Max Match", "Git Churn", "Fuzz/Game", "Viva Ok", "Ownership", "Integrity", "Final Grade %"
            ]
            
            try:
                from tabulate import tabulate
                use_tabulate = True
            except ImportError:
                use_tabulate = False
                
            if use_tabulate:
                print("\n" + tabulate(summary_rows, headers=headers, tablefmt="fancy_grid") + "\n")
            else:
                all_cols = [headers] + summary_rows
                col_widths = [max(len(str(item)) for item in col) for col in zip(*all_cols)]
                border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
                lines = [border]
                header_line = "|" + "|".join(f" {str(h).ljust(w)} " for h, w in zip(headers, col_widths)) + "|"
                lines.append(header_line)
                lines.append(border)
                for row in summary_rows:
                    row_line = "|" + "|".join(f" {str(item).ljust(w)} " for item, w in zip(row, col_widths)) + "|"
                    lines.append(row_line)
                lines.append(border)
                print("\n" + "\n".join(lines) + "\n")

def baseline_command(args):
    """Generate or list AI plagiarism baseline banks."""
    config = load_config()
    print_banner()

    from aegis.baseline import generate_baselines, list_baselines

    action = args.baseline_action

    if action == "generate":
        prompt = args.prompt
        count = args.count
        lang = args.lang
        print_section("GENERATING AI BASELINE BANK")
        print_info(f"Prompt: {prompt}")
        print_info(f"Generating {count} variations in {lang}...")

        from aegis.ui import Spinner
        with Spinner(f"Calling Gemini API ({count} variations)..."):
            result = generate_baselines(config, prompt, count=count, lang=lang)

        if "error" in result:
            print_error(result["error"])
            sys.exit(1)

        ok = sum(1 for s in result["solutions"] if "code" in s)
        print_success(f"Generated {ok}/{count} solutions. Fingerprint union: {len(result['union_fingerprints'])} hashes.")
        print_info(f"Saved to .aegis_baselines/{result['key']}.json")

    elif action == "list":
        print_section("SAVED AI BASELINE BANKS")
        banks = list_baselines()
        if not banks:
            print_warning("No baseline banks found. Run 'aegis baseline generate' first.")
            return
        for b in banks:
            print(f"  {Fore.CYAN}{b['key']}{Style.RESET_ALL}  |  "
                  f"{Fore.WHITE}{b['variations']} variations{Style.RESET_ALL}  |  "
                  f"{b['lang']}  |  "
                  f"{Fore.YELLOW}{b['prompt'][:60]}...{Style.RESET_ALL}")
    else:
        print_error(f"Unknown baseline action: {action}")

def main():
    parser = argparse.ArgumentParser(
        description="AegisCode: AI-Age Code Integrity & Vetting Agent"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="AegisCode commands")
    
    # Init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize workspace configurations")
    
    # Vet subcommand
    vet_parser = subparsers.add_parser("vet", help="Run interactive Viva Voce vetting (Student)")
    vet_parser.add_argument("--student", type=str, help="Student name")
    vet_parser.add_argument("--dir", type=str, help="Student project directory")
    
    # Audit subcommand
    audit_parser = subparsers.add_parser("audit", help="Run grading and code integrity audit (Teacher)")
    audit_parser.add_argument("submissions_dir", type=str, help="Directory containing student folders")
    audit_parser.add_argument("--tests", type=str, help="Command to run tests (e.g. 'pytest')")
    audit_parser.add_argument("--rubric", type=str, help="Path to rubric file")
    
    # Web subcommand
    web_parser = subparsers.add_parser("web", help="Launch local reports dashboard")
    web_parser.add_argument("--submissions_dir", type=str, default="test_submissions", help="Directory containing student folders")
    web_parser.add_argument("--port", type=int, default=8000, help="Local port to run the server on")
    
    # TUI subcommand
    tui_parser = subparsers.add_parser("tui", help="Launch the rich interactive terminal dashboard")
    tui_parser.add_argument("--submissions_dir", type=str, default="test_submissions", help="Directory containing student folders")
    tui_parser.add_argument("--tests", type=str, help="Command to run tests (e.g. 'pytest')")
    tui_parser.add_argument("--rubric", type=str, help="Path to rubric file")

    # Clone subcommand
    clone_parser = subparsers.add_parser("clone", help="Bulk clone student repositories")
    clone_parser.add_argument("repo_source", type=str, nargs="?", help="Path to file containing GitHub URLs, or a single repository URL")
    clone_parser.add_argument("--classroom", type=str, help="GitHub Classroom assignment URL or ID to auto-fetch repos")
    clone_parser.add_argument("--dest", type=str, default="test_submissions", help="Directory to clone repositories into")
    clone_parser.add_argument("--audit", action="store_true", help="Automatically run audit on cloned repositories")

    # Baseline subcommand
    baseline_parser = subparsers.add_parser("baseline", help="Manage AI plagiarism baseline banks")
    baseline_sub = baseline_parser.add_subparsers(dest="baseline_action")
    gen_p = baseline_sub.add_parser("generate", help="Generate AI solution baselines for an assignment")
    gen_p.add_argument("prompt", type=str, help="Assignment description / problem statement")
    gen_p.add_argument("--count", type=int, default=8, help="Number of Gemini solution variations to generate")
    gen_p.add_argument("--lang", type=str, default="python", help="Programming language (default: python)")
    baseline_sub.add_parser("list", help="List all saved baseline banks")
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_command(args)
    elif args.command == "vet":
        vet_command(args)
    elif args.command == "audit":
        audit_command(args)
    elif args.command == "web":
        web_command(args)
    elif args.command == "tui":
        tui_command(args)
    elif args.command == "clone":
        clone_command(args)
    elif args.command == "baseline":
        baseline_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

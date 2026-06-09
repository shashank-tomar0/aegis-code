import os
import sys
import argparse
import json
from colorama import Fore, Style, init

from aegis.config import load_config, save_config, DEFAULT_CONFIG
from aegis.ast_analyzer import analyze_file
from aegis.viva_agent import run_interactive_viva
from aegis.grading import execute_grading_pipeline, scan_student_code

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
    print(f"{Fore.CYAN}Initializing AegisCode workspace...")
    
    # Save default config if not exists
    if not os.path.exists("aegis.json"):
        save_config(DEFAULT_CONFIG)
        print(f"Created configuration file: {Fore.GREEN}aegis.json")
    else:
        print(f"{Fore.YELLOW}aegis.json already exists. Skipping.")
        
    # Save default rubric if not exists
    if not os.path.exists("rubric.md"):
        try:
            with open("rubric.md", "w", encoding="utf-8") as f:
                f.write(DEFAULT_RUBRIC)
            print(f"Created grading rubric template: {Fore.GREEN}rubric.md")
        except Exception as e:
            print(f"{Fore.RED}Failed to create rubric.md: {e}")
    else:
        print(f"{Fore.YELLOW}rubric.md already exists. Skipping.")
        
    print(f"\n{Fore.GREEN}{Style.BRIGHT}Workspace initialized! Adjust settings in aegis.json and rubric.md.")

def vet_command(args):
    """Runs the interactive Viva Voce vetting interview in the student's repository."""
    config = load_config()
    
    if not config.get("api_key"):
        print(f"{Fore.RED}Error: Gemini API Key is missing.")
        print(f"{Fore.YELLOW}Please set the GEMINI_API_KEY environment variable or write it to aegis.json.")
        sys.exit(1)

    target_dir = args.dir or "."
    
    # Prompt for student name if not provided
    student_name = args.student
    if not student_name:
        print(f"{Fore.CYAN}Please enter your Full Name: ", end="", flush=True)
        student_name = input().strip()
        if not student_name:
            print(f"{Fore.RED}Student name cannot be empty.")
            sys.exit(1)

    # Scan python files
    print(f"{Fore.BLUE}Scanning files for coding structures in {os.path.abspath(target_dir)}...")
    code_report = scan_student_code(target_dir)
    
    if not code_report["functions"]:
        print(f"{Fore.RED}Error: No functions found to analyze in {target_dir}.")
        print("Please ensure your Python source files contain function definitions.")
        sys.exit(1)

    # Run the interactive Viva
    receipt = run_interactive_viva(config, student_name, code_report["functions"], target_dir)
    
    if receipt:
        # Save receipt locally
        receipt_path = os.path.join(target_dir, ".aegis_vet_receipt")
        try:
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=4)
            print(f"{Fore.GREEN}{Style.BRIGHT}Vetting Complete! signed receipt generated at {receipt_path}")
            print(f"Ensure this receipt file is included in your submission.")
        except Exception as e:
            print(f"{Fore.RED}Failed to save receipt file: {e}")
    else:
        print(f"{Fore.RED}Vetting failed. No receipt generated.")

def audit_command(args):
    """Runs the teacher grading and plagiarism audit on submissions."""
    config = load_config()
    
    # Setup test runner command
    test_command = args.tests
    if not test_command and "test_command" in config:
        test_command = config["test_command"]
        
    rubric_path = args.rubric or "rubric.md"
    submissions_dir = args.submissions_dir
    
    if not submissions_dir:
        print(f"{Fore.RED}Error: Submissions directory is required.")
        sys.exit(1)
        
    print(f"{Fore.CYAN}{Style.BRIGHT}==========================================")
    print(f"{Fore.CYAN}{Style.BRIGHT}     AEGISCODE GRADING & AUDIT PIPELINE   ")
    print(f"{Fore.CYAN}{Style.BRIGHT}==========================================\n")
    
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
                r["Viva Verified"], 
                r["Viva Ownership Score"], 
                r["Integrity Flag"], 
                r["Adjusted Grade %"]
            ])
            
        headers = [
            "Student", "Tests %", "Max Match", "Git Churn", "Viva Ok", "Ownership", "Integrity", "Final Grade %"
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
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_command(args)
    elif args.command == "vet":
        vet_command(args)
    elif args.command == "audit":
        audit_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

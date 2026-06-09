import subprocess
import os
import re
from datetime import datetime

def run_git_command(args, cwd):
    """Executes a git command in the specified directory and returns stdout."""
    try:
        # On Windows, we should pass shell=True if the command relies on shell extensions, 
        # but here running direct executable is safer.
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Git command failed or not a git repo
        return None
    except FileNotFoundError:
        # Git is not installed on the system PATH
        return None

def analyze_git_history(repo_path):
    """
    Performs forensic analysis on the git repository history.
    Returns a dictionary of metrics, anomalies, and logs.
    """
    report = {
        "is_git_repo": False,
        "commit_count": 0,
        "authors": set(),
        "step_churn_anomaly": False,
        "time_anomaly": False,
        "max_single_commit_addition": 0,
        "total_additions": 0,
        "churn_ratio": 0.0,
        "anomalies": [],
        "commits": []
    }

    # 1. Check if .git folder exists
    if not os.path.exists(os.path.join(repo_path, ".git")):
        report["anomalies"].append("Missing .git directory. No version history present.")
        return report

    report["is_git_repo"] = True

    # 2. Get commit list
    # Format: hash | author | email | timestamp | subject
    log_data = run_git_command(["log", "--pretty=format:%h|%an|%ae|%ct|%s"], repo_path)
    if not log_data:
        report["anomalies"].append("Git repository is initialized but has no commits.")
        return report

    commit_lines = log_data.split("\n")
    report["commit_count"] = len(commit_lines)

    commits = []
    authors = set()
    emails = set()

    for line in commit_lines:
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        h, name, email, ts, msg = parts
        try:
            dt = datetime.fromtimestamp(int(ts))
        except ValueError:
            dt = datetime.now()
        
        authors.add(name)
        emails.add(email)
        commits.append({
            "hash": h,
            "author": name,
            "email": email,
            "datetime": dt,
            "timestamp": int(ts),
            "message": msg,
            "additions": 0,
            "deletions": 0
        })

    report["authors"] = list(authors)
    report["emails"] = list(emails)

    # 3. Code Churn Analysis per Commit
    total_additions = 0
    total_deletions = 0
    max_addition = 0
    max_addition_hash = None

    for commit in commits:
        # Get lines added/deleted for this commit
        # git show --numstat <hash> returns lines: "added deleted filename"
        stat_data = run_git_command(["show", "--numstat", "--pretty=format:", commit["hash"]], repo_path)
        if stat_data:
            adds = 0
            dels = 0
            for stat_line in stat_data.split("\n"):
                stat_line = stat_line.strip()
                if not stat_line:
                    continue
                match = re.match(r"^(\d+)\s+(\d+)\s+", stat_line)
                if match:
                    adds += int(match.group(1))
                    dels += int(match.group(2))
            commit["additions"] = adds
            commit["deletions"] = dels
            
            total_additions += adds
            total_deletions += dels
            
            if adds > max_addition:
                max_addition = adds
                max_addition_hash = commit["hash"]

    report["total_additions"] = total_additions
    report["max_single_commit_addition"] = max_addition
    report["commits"] = commits

    # Calculate churn ratio (deletions / additions)
    # Human refactoring usually results in some deletions. AI dumping is purely additive.
    if total_additions > 0:
        report["churn_ratio"] = total_deletions / total_additions
        
        # Check for Step-Churn Anomaly: If a single commit added > 85% of all code in a multi-commit repo
        if len(commits) > 1 and (max_addition / total_additions) > 0.85 and total_additions > 150:
            report["step_churn_anomaly"] = True
            report["anomalies"].append(
                f"Step-Churn Anomaly detected: Commit {max_addition_hash} added {max_addition} lines "
                f"({(max_addition/total_additions)*100:.1f}% of total codebase additions)."
            )
        elif len(commits) == 1:
            # Single commit accounts for 100% of code, which is a step-churn anomaly for assignments
            report["step_churn_anomaly"] = True
            report["anomalies"].append(
                "Single-Commit Anomaly: Repository contains only 1 commit. No incremental development history."
            )
    else:
        report["churn_ratio"] = 0.0

    # 4. Check for Time/Speed Anomalies
    # If the time between two adjacent commits is less than 30 seconds, and they added > 30 lines of code,
    # it indicates automated scripting or copy-paste-commit sequence.
    if len(commits) > 1:
        # Commits are returned newest first, reverse to trace chronologically
        chrono_commits = list(reversed(commits))
        for i in range(1, len(chrono_commits)):
            t1 = chrono_commits[i-1]["timestamp"]
            t2 = chrono_commits[i]["timestamp"]
            time_diff = t2 - t1
            added_lines = chrono_commits[i]["additions"]
            
            if 0 < time_diff < 30 and added_lines > 40:
                report["time_anomaly"] = True
                report["anomalies"].append(
                    f"Temporal Anomaly: Commit {chrono_commits[i]['hash']} occurred {time_diff}s after "
                    f"{chrono_commits[i-1]['hash']} and added {added_lines} lines of code."
                )

    # 5. Check Author Anomalies
    # If there are multiple different author names or emails (indicating copying from different sources)
    if len(authors) > 2:
         report["anomalies"].append(
             f"Multi-Author Anomaly: Found {len(authors)} distinct authors in commit history: {', '.join(authors)}"
         )

    return report

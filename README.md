<div align="center">
  <h1>🛡️ AegisCode</h1>
  <p><b>The Next-Generation AI & Plagiarism Forensics Engine for CS Grading</b></p>

  <p>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform">
  </p>
</div>

---

## 🚀 Overview

**AegisCode** is an advanced, automated grading and academic integrity platform designed for the AI era. Traditional plagiarism detectors fail against students using ChatGPT or Copilot to rewrite code. AegisCode fights back with **AST Winnowing Fingerprinting**, **LLM Rewrite Detection**, **Dynamic Fuzzing**, and **Git Forensics**.

It doesn't just check if code works; it proves the student actually wrote it.

---

## ✨ Features

- 🧠 **LLM Rewrite Detector**: Uses Shannon entropy, identifier variance, and comment density heuristics to flag code that looks "too clean" (a common signature of AI variable-renaming).
- 🧬 **AI Plagiarism Baseline Bank**: Generates canonical Gemini-authored solutions for your assignment, then cross-matches student submissions against the AI's structural fingerprints to catch cheating.
- 🌳 **AST Winnowing Plagiarism Detection**: Tokenizes code into Abstract Syntax Trees (AST) and uses the Winnowing algorithm to detect structural plagiarism, ignoring variable renaming or whitespace changes.
- 🌍 **Multi-Language Support**: Parses Python, JavaScript, Java, and C/C++ natively using `tree-sitter`.
- 🕵️ **Git Forensics Engine**: Analyzes commit velocity, timestamp anomalies, and massive single-commit code dumps to catch last-minute copy-pasting.
- 🛡️ **Anti-Gaming Fuzzer**: Detects hardcoded test answers and bypasses by injecting chaotic fuzzing inputs directly into student functions dynamically.
- 🧑‍🏫 **Viva Voce AI Agent**: Automates a simulated oral exam. Students paste a receipt token proving they discussed their code with our Gemini-powered interrogation agent.
- 📊 **Cyberpunk TUI & Glassmorphic Web Dashboard**: Monitor the audit matrix in real-time via an aggressive neon Terminal UI or a rich local Web Dashboard.
- 📥 **GitHub Classroom Integration**: Auto-fetch and bulk-clone every student repository instantly via the GitHub REST API.
- 📄 **PDF Audit Reports**: Automatically generates a 1-page forensic dossier per student.

---

## ⚙️ Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/shashank-tomar0/aegis-code.git
   cd aegis-code
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up API Keys**:
   Create an `aegis.json` file in the root directory:
   ```json
   {
     "gemini_api_key": "YOUR_GEMINI_API_KEY",
     "github_token": "YOUR_GITHUB_PAT",
     "baseline_dir": ".aegis_baselines"
   }
   ```
   *(Ensure `aegis.json` is in your `.gitignore` to keep your keys secure!)*

---

## 📖 Quickstart Guide

AegisCode provides a sleek CLI for all operations.

### 1. Auto-Fetch Student Repositories
Connect to your GitHub Classroom assignment and clone all accepted submissions:
```bash
python -m aegis.cli clone --classroom <assignment_id_or_url> --dest test_submissions
```

### 2. Generate the AI Baseline Bank
Before auditing, let AegisCode generate multiple AI solutions to the assignment prompt to use as plagiarism baselines:
```bash
python -m aegis.cli baseline generate "Write a python function to perform binary search" --count 5
```

### 3. Run the Forensic Audit
Run tests, Git forensics, AST Winnowing, and the LLM Rewrite detector on all student submissions:
```bash
python -m aegis.cli audit test_submissions
```
*Results are saved to `grades.csv`, and a per-student `audit_report.pdf` is generated in their respective folders.*

### 4. Launch the Interfaces
**Neon Terminal UI (TUI):**
```bash
python -m aegis.cli tui
```
**Glassmorphic Web Dashboard:**
```bash
python -m aegis.cli web
```
*(Runs on `http://localhost:8000`)*

---

## 🏗️ Architecture

AegisCode is modular by design:
- `aegis/winnowing.py`: Core structural plagiarism engine (K-Grams + Hashes).
- `aegis/ast_analyzer.py` / `multi_lang_ast.py`: Code tokenizer.
- `aegis/rewrite_detector.py`: Heuristics for catching sanitized LLM output.
- `aegis/git_forensics.py`: Commit timeline analysis.
- `aegis/viva_agent.py`: Gemini-powered code interrogation module.
- `aegis/baseline.py`: AI cross-matching engine.
- `aegis/fuzzer.py`: Hardcoding / gaming defense.
- `aegis/pdf_report.py`: `fpdf2` report generation.

---

<div align="center">
  <p>Built for the future of computer science education. 🛡️</p>
</div>

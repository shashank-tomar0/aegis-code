import os
import json
import hashlib
from datetime import datetime
import google.generativeai as genai
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Secret key used for signing receipts (teachers can change this in config)
SIGNING_SECRET = "AEGIS_SECURE_VERIFICATION_KEY_2026"

def get_gemini_client(api_key):
    """Configures and returns the genai module client."""
    if not api_key:
        raise ValueError(
            "Gemini API Key is missing. Set the GEMINI_API_KEY environment variable "
            "or configure it in aegis.json."
        )
    genai.configure(api_key=api_key)
    return genai

def generate_viva_questions(client, model_name, fn_name, source_code):
    """Uses Gemini to generate 2 deep conceptual questions about the specified function."""
    prompt = f"""
You are AegisCode's Vetting Agent. Your job is to inspect the student's Python code below and generate 2 highly targeted, conceptual questions about their implementation.

The questions must test if the student actually wrote the code or understands its logic.
Guidelines:
- Do NOT ask simple syntax questions (e.g. "What does 'def' mean?").
- Ask about decision paths, choice of data structures, algorithm efficiency, how edge cases are handled, or why a specific line was written in a certain way.
- Avoid obvious questions. Go deep into their logic.
- Keep each question under 2 sentences.

Function Name: {fn_name}
Source Code:
```python
{source_code}
```

Format your output strictly as a JSON array of strings:
[
  "Question 1...",
  "Question 2..."
]
Do not include markdown tags like ```json in the response. Return raw JSON.
"""
    model = client.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    
    text = response.text.strip()
    
    # Strip potential markdown formatting if returned
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
        
    try:
        questions = json.loads(text)
        if isinstance(questions, list) and len(questions) >= 2:
            return questions[:2]
    except Exception:
        # Fallback if JSON parsing fails
        pass
        
    # Manual backup questions
    return [
        f"Can you explain the main objective of the '{fn_name}' function and how the loops/branches accomplish it?",
        f"What is the time complexity of '{fn_name}' and how would it behave with empty or negative inputs?"
    ]

def evaluate_viva_answers(client, model_name, fn_name, source_code, qas):
    """Uses Gemini to grade the student's understanding based on the Q&A transcript."""
    qa_block = ""
    for idx, (q, a) in enumerate(qas, 1):
        qa_block += f"Question {idx}: {q}\nStudent Answer: {a}\n\n"
        
    prompt = f"""
You are AegisCode's Vetting Agent. Below is the source code of a student's function, followed by 2 conceptual questions and the student's typed answers.
Evaluate the student's conceptual ownership of the code.

Assign an Ownership Score between 0 and 100, where:
- 90-100: Student has absolute conceptual ownership (they understand exactly how the code works, its constraints, and why choices were made).
- 70-89: Student has reasonable ownership but misses some fine details or gave slightly incomplete answers.
- 40-69: Student shows weak understanding, likely copied the code and has only a superficial grasp of the logic.
- 0-39: Student shows zero understanding, does not know how the logic runs, or answered nonsense/evasively.

Function Name: {fn_name}
Source Code:
```python
{source_code}
```

Student Q&A:
{qa_block}

Format your output strictly as a JSON object with 'score' (integer) and 'justification' (short string) keys:
{{
  "score": 85,
  "justification": "Student correctly explained the recursion base case but was unsure about the O(N log N) runtime complexity."
}}
Do not include markdown tags like ```json. Return raw JSON.
"""
    model = client.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    
    text = response.text.strip()
    
    # Strip potential markdown formatting if returned
    import re
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
        
    try:
        res = json.loads(text)
        return int(res.get("score", 0)), res.get("justification", "No justification provided.")
    except Exception:
        return 50, "Failed to parse AI evaluation. Defaulting to median pass score."

def generate_signed_receipt(student_name, score, justification, repo_path):
    """Generates a JSON receipt with a SHA-256 HMAC-like signature to prevent tampering."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    receipt_data = {
        "student_name": student_name,
        "ownership_score": score,
        "justification": justification,
        "timestamp": timestamp,
        "repo_path": os.path.abspath(repo_path)
    }
    
    # Calculate cryptographic signature
    serialized = f"{student_name}|{score}|{timestamp}|{receipt_data['repo_path']}|{SIGNING_SECRET}"
    signature = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    
    receipt_data["signature"] = signature
    return receipt_data

def verify_receipt(receipt_path):
    """Verifies the cryptographic signature of an aegis receipt file."""
    if not os.path.exists(receipt_path):
        return False, "Receipt file does not exist."
        
    try:
        with open(receipt_path, "r") as f:
            data = json.load(f)
            
        required = ["student_name", "ownership_score", "timestamp", "repo_path", "signature"]
        if not all(k in data for k in required):
            return False, "Receipt format is invalid or missing attributes."
            
        serialized = f"{data['student_name']}|{data['ownership_score']}|{data['timestamp']}|{data['repo_path']}|{SIGNING_SECRET}"
        expected = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        
        if data["signature"] == expected:
            return True, f"Verified! Score: {data['ownership_score']}% for {data['student_name']}"
        else:
            return False, "Receipt signature mismatch! The file has been modified or forged."
            
    except Exception as e:
        return False, f"Failed to read/verify receipt: {e}"

def run_interactive_viva(config, student_name, fn_list, repo_path):
    """Runs the terminal-based Q&A loop with the student."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==========================================")
    print(f"{Fore.CYAN}{Style.BRIGHT}    AEGISCODE INTERACTIVE VIVA-VOCE       ")
    print(f"{Fore.CYAN}{Style.BRIGHT}==========================================\n")
    
    if not fn_list:
        print(f"{Fore.YELLOW}Warning: No functions detected in your source files to vet.")
        return None

    # Filter out functions with very low complexity
    fn_list = [f for f in fn_list if f["complexity"] >= 2]
    if not fn_list:
        print(f"{Fore.YELLOW}All functions in the submission are low-complexity. Skipping Viva.")
        # Return a auto-pass receipt
        receipt = generate_signed_receipt(student_name, 100, "Automatic pass due to simple code structure.", repo_path)
        return receipt
        
    # Pick the highest complexity function
    target_fn = fn_list[0]
    
    print(f"Candidate Function identified for Vetting: {Fore.GREEN}{target_fn['name']}")
    print(f"Cyclomatic Complexity Index: {Fore.YELLOW}{target_fn['complexity']}\n")
    
    try:
        client = get_gemini_client(config["api_key"])
    except ValueError as e:
        print(f"{Fore.RED}Error: {e}")
        return None

    print(f"{Fore.BLUE}Contacting Aegis Vetting Agent to generate questions...")
    questions = generate_viva_questions(client, config["model_name"], target_fn["name"], target_fn["source_code"])
    
    qas = []
    print(f"\n{Fore.GREEN}Vetting Agent: Hello {student_name}. I have analyzed your code.")
    print("Please answer the following conceptual questions about your implementation.\n")
    
    for idx, q in enumerate(questions, 1):
        print(f"{Fore.WHITE}{Style.BRIGHT}[Question {idx}/2] {q}")
        print(f"{Fore.CYAN}Your Answer: ", end="", flush=True)
        answer = input()
        qas.append((q, answer))
        print()
        
    print(f"{Fore.BLUE}Evaluating answers with Vetting Agent...")
    score, justification = evaluate_viva_answers(client, config["model_name"], target_fn["name"], target_fn["source_code"], qas)
    
    print(f"\n{Fore.CYAN}{Style.BRIGHT}==========================================")
    print(f"{Fore.GREEN}{Style.BRIGHT}VIVA EVALUATION COMPLETE")
    print(f"{Fore.CYAN}Ownership Score: {Fore.YELLOW}{Style.BRIGHT}{score}%")
    print(f"{Fore.CYAN}Evaluation: {Fore.WHITE}{justification}")
    print(f"{Fore.CYAN}{Style.BRIGHT}==========================================\n")
    
    receipt = generate_signed_receipt(student_name, score, justification, repo_path)
    return receipt

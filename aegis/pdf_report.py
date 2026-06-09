"""
aegis/pdf_report.py — PDF Audit Report Export

Generates a one-page PDF Audit Report for a student, summarizing
their forensic flags, test scores, metrics, and AI feedback.
"""

from fpdf import FPDF
import os

class AegisPDFReport(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 16)
        self.set_text_color(157, 78, 221) # Purple brand color
        self.cell(0, 10, 'AegisCode Audit Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_student_pdf(student_name: str, result_data: dict, out_dir: str):
    pdf = AegisPDFReport()
    pdf.add_page()
    pdf.set_font('helvetica', '', 12)
    
    # Title section
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, f"Student: {student_name}", 0, 1, 'L')
    
    # Final Grade and Integrity Flag
    grade = result_data.get("Adjusted Grade %", "0")
    flag = result_data.get("Integrity Flag", "UNKNOWN")
    
    pdf.set_font('helvetica', '', 12)
    pdf.cell(50, 10, "Final Grade:", 0, 0)
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 10, f"{grade}%", 0, 1)
    
    pdf.set_font('helvetica', '', 12)
    pdf.cell(50, 10, "Integrity Status:", 0, 0)
    if flag == "FLAGGED":
        pdf.set_text_color(255, 0, 127) # Red/Pink
    else:
        pdf.set_text_color(0, 200, 83) # Green
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 10, flag, 0, 1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    
    # Details Table
    pdf.set_font('helvetica', 'B', 12)
    pdf.cell(0, 10, "Audit Details", 0, 1)
    
    details = [
        ("Test Score", f"{result_data.get('Test Score %', '0')}% ({result_data.get('Tests Passed', '0')}/{result_data.get('Total Tests', '0')})"),
        ("Plagiarism Match", result_data.get("Max Plagiarism Match", "0.0%")),
        ("AI Baseline Match", result_data.get("AI Baseline Match", "0.0%")),
        ("LLM Rewrite Flag", result_data.get("LLM Rewrite Flag", "NO")),
        ("Git Anomaly", result_data.get("Git Forensic Anomaly", "NO")),
        ("Anti-Gaming Fuzzer", result_data.get("Fuzz/Gaming Anomaly", "PASSED")),
        ("Viva Verified", result_data.get("Viva Verified", "NO")),
        ("Viva Ownership Score", result_data.get("Viva Ownership Score", "0%")),
        ("Files Scanned", str(result_data.get("Files Scanned", "0"))),
        ("Lines of Code", str(result_data.get("Lines of Code", "0")))
    ]
    
    for key, value in details:
        pdf.set_font('helvetica', 'B', 10)
        pdf.cell(60, 8, key, border=1)
        pdf.set_font('helvetica', '', 10)
        # Using built-in helvetica which doesn't support fancy unicode, so we sanitize
        safe_value = str(value).encode('ascii', 'replace').decode('ascii')
        pdf.cell(130, 8, safe_value, border=1, ln=1)
        
    pdf.ln(10)
    pdf.set_font('helvetica', 'I', 9)
    pdf.multi_cell(0, 5, "This report was generated automatically by AegisCode. "
                         "Integrity flags are based on static analysis, git forensics, "
                         "fuzzing heuristics, and AI cross-matching, and should be reviewed by an instructor.")
                         
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "audit_report.pdf")
    try:
        pdf.output(pdf_path)
    except Exception as e:
        print(f"Error saving PDF for {student_name}: {e}")
        
    return pdf_path

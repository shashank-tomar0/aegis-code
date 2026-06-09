"""
aegis/baseline.py — AI Plagiarism Baseline Bank

Generates Gemini-authored canonical solutions for a given assignment prompt,
fingerprints them using the Winnowing algorithm, and saves them to disk.
During audit, student code is cross-matched against this baseline bank to
detect AI-generated submissions.
"""

import os
import json
import hashlib
from aegis.ast_analyzer import analyze_file_from_source
from aegis.winnowing import get_file_fingerprints, compute_similarity


BASELINE_DIR = ".aegis_baselines"


def _baseline_key(prompt: str) -> str:
    """Create a filesystem-safe key from a prompt string."""
    return hashlib.md5(prompt.encode()).hexdigest()[:12]


def generate_baselines(config: dict, prompt: str, count: int = 10, lang: str = "python") -> dict:
    """
    Uses Gemini to generate `count` canonical solutions for the given prompt.
    Saves fingerprints to .aegis_baselines/<key>.json and returns the result.
    """
    from aegis.viva_agent import get_gemini_client

    api_key = config.get("api_key", "")
    if not api_key:
        return {"error": "Gemini API key not configured."}

    client = get_gemini_client(api_key)
    model_name = config.get("model_name", "gemini-1.5-flash")
    model = client.GenerativeModel(model_name)

    solutions = []
    fingerprints_union: set = set()

    system_prompt = (
        f"You are an expert {lang} programmer. Write a complete, correct, clean solution "
        f"to the following assignment problem. Output ONLY runnable code, no explanation, "
        f"no markdown fences.\n\nProblem: {prompt}"
    )

    for i in range(count):
        variation_prompt = (
            f"{system_prompt}\n\n"
            f"Use a slightly different variable naming style and code structure for variation #{i+1}. "
            f"This should be a completely independent solution."
        )
        try:
            response = model.generate_content(variation_prompt)
            code = response.text.strip()
            # Strip markdown code fences if present
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            tokens, _ = analyze_file_from_source(code)
            fp = get_file_fingerprints(tokens, config.get("k_gram", 5), config.get("window_size", 4))

            # Store hash values only (not position indices) for portability
            fp_hashes = [h for h, _ in fp]
            fingerprints_union.update(fp_hashes)

            solutions.append({
                "variation": i + 1,
                "code": code,
                "fingerprint_count": len(fp_hashes),
            })
        except Exception as e:
            solutions.append({"variation": i + 1, "error": str(e)})

    # Save to disk
    os.makedirs(BASELINE_DIR, exist_ok=True)
    key = _baseline_key(prompt)
    baseline_data = {
        "prompt": prompt,
        "lang": lang,
        "count": count,
        "key": key,
        "solutions": solutions,
        "union_fingerprints": list(fingerprints_union),
    }
    out_path = os.path.join(BASELINE_DIR, f"{key}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2)

    return baseline_data


def load_baselines(baseline_dir: str = BASELINE_DIR) -> list[dict]:
    """Load all saved baseline fingerprint sets from disk."""
    baselines = []
    if not os.path.exists(baseline_dir):
        return baselines
    for fname in os.listdir(baseline_dir):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(baseline_dir, fname), "r", encoding="utf-8") as f:
                    baselines.append(json.load(f))
            except Exception:
                pass
    return baselines


def check_against_baselines(student_fingerprints: set, baseline_dir: str = BASELINE_DIR) -> dict:
    """
    Cross-match a student's fingerprint set against all saved baseline banks.
    Returns the highest AI similarity found across all baselines.

    Args:
        student_fingerprints: set of (hash, index) tuples from winnowing
        baseline_dir: directory containing baseline JSON files

    Returns:
        dict with keys: max_ai_similarity, matched_baseline, ai_flagged
    """
    baselines = load_baselines(baseline_dir)
    if not baselines:
        return {"max_ai_similarity": 0.0, "matched_baseline": None, "ai_flagged": False}

    student_hashes = {h for h, _ in student_fingerprints}
    max_sim = 0.0
    matched_prompt = None

    for baseline in baselines:
        baseline_hashes = set(baseline.get("union_fingerprints", []))
        if not baseline_hashes:
            continue

        intersection = student_hashes & baseline_hashes
        union = student_hashes | baseline_hashes

        if union:
            jaccard = len(intersection) / len(union)
            # Also check containment (student code ⊆ AI code)
            containment = len(intersection) / len(student_hashes) if student_hashes else 0.0
            # Use max of both metrics as the signal
            sim = max(jaccard, containment * 0.8)

            if sim > max_sim:
                max_sim = sim
                matched_prompt = baseline.get("prompt", "Unknown")

    threshold = 0.35  # Lower threshold than human plagiarism (AI code is varied)
    return {
        "max_ai_similarity": round(max_sim, 4),
        "matched_baseline": matched_prompt,
        "ai_flagged": max_sim >= threshold,
    }


def list_baselines(baseline_dir: str = BASELINE_DIR) -> list[dict]:
    """Return summary of all saved baseline banks."""
    baselines = load_baselines(baseline_dir)
    return [
        {
            "key": b.get("key"),
            "prompt": b.get("prompt", "")[:80],
            "lang": b.get("lang", "python"),
            "variations": b.get("count", 0),
            "fingerprint_count": len(b.get("union_fingerprints", [])),
        }
        for b in baselines
    ]

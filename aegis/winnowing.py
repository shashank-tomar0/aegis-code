import hashlib

def get_kgrams(tokens, k):
    """Slices a token list into k-grams of size k."""
    if len(tokens) < k:
        return []
    return [tuple(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]

def hash_kgram(kgram):
    """Computes a deterministic 32-bit integer hash for a k-gram tuple."""
    kgram_str = ",".join(kgram)
    # Using SHA-256 and masking to 32 bits for portability and speed
    h = hashlib.sha256(kgram_str.encode('utf-8')).hexdigest()
    return int(h, 16) & 0xFFFFFFFF

def winnow(hashes, w):
    """
    Implements the Winnowing algorithm for document fingerprinting.
    Selects a representative subset of hashes using a sliding window.
    Handles ties by selecting the rightmost minimum.
    
    Returns a set of tuples: (hash_value, index)
    """
    fingerprints = set()
    n = len(hashes)
    
    if n == 0:
        return fingerprints
        
    if n < w:
        # If total hashes are smaller than the window size, select the absolute minimum
        min_val = min(hashes)
        # Rightmost index of the minimum
        min_idx = n - 1 - hashes[::-1].index(min_val)
        fingerprints.add((min_val, min_idx))
        return fingerprints

    for i in range(n - w + 1):
        window = hashes[i : i + w]
        min_val = min(window)
        # Rightmost index of min_val inside this window
        min_idx_in_window = w - 1 - window[::-1].index(min_val)
        min_pos = i + min_idx_in_window
        fingerprints.add((min_val, min_pos))

    return fingerprints

def compute_similarity(fp1, fp2):
    """
    Computes similarity metrics between two sets of fingerprints.
    Compares hash values, ignoring position indices.
    
    Returns a dict with:
    - jaccard: Jaccard similarity coefficient (intersection / union)
    - containment: Containment coefficient (intersection / size of smaller set)
    - intersection_count: Number of matching fingerprints
    """
    hashes1 = {h for h, _ in fp1}
    hashes2 = {h for h, _ in fp2}
    
    if not hashes1 or not hashes2:
        return {"jaccard": 0.0, "containment": 0.0, "intersection_count": 0}
        
    intersection = hashes1.intersection(hashes2)
    union = hashes1.union(hashes2)
    
    jaccard = len(intersection) / len(union)
    containment = len(intersection) / min(len(hashes1), len(hashes2))
    
    return {
        "jaccard": jaccard,
        "containment": containment,
        "intersection_count": len(intersection)
    }

def get_file_fingerprints(tokens, k=5, w=4):
    """Helper that converts a raw token list into a set of winnowed fingerprints."""
    kgrams = get_kgrams(tokens, k)
    hashes = [hash_kgram(kg) for kg in kgrams]
    return winnow(hashes, w)

import pytest
from aegis.winnowing import get_kgrams, hash_kgram, winnow, compute_similarity, get_file_fingerprints

def test_get_kgrams():
    tokens = ["a", "b", "c", "d", "e"]
    kgrams = get_kgrams(tokens, 3)
    assert kgrams == [("a", "b", "c"), ("b", "c", "d"), ("c", "d", "e")]

    kgrams_small = get_kgrams(["a", "b"], 3)
    assert kgrams_small == []

def test_hash_kgram():
    kgram = ("a", "b", "c")
    h = hash_kgram(kgram)
    assert isinstance(h, int)
    # The hash should be deterministic
    assert h == hash_kgram(("a", "b", "c"))
    assert h != hash_kgram(("a", "b", "d"))

def test_winnow():
    hashes = [77, 72, 42, 17, 98, 50, 17, 98, 8, 88, 67, 39, 77, 72, 42, 17, 98]
    w = 4
    fingerprints = winnow(hashes, w)
    
    # 17 should be selected as minimums in multiple windows
    selected_hashes = [h for h, idx in fingerprints]
    assert 17 in selected_hashes
    assert 8 in selected_hashes
    assert 39 in selected_hashes

def test_compute_similarity():
    fp1 = {(10, 0), (20, 1), (30, 2)}
    fp2 = {(20, 5), (30, 6), (40, 7)}
    
    sim = compute_similarity(fp1, fp2)
    # intersection: 20, 30 (size 2)
    # union: 10, 20, 30, 40 (size 4)
    # jaccard = 2/4 = 0.5
    # containment = 2/3 = 0.666...
    assert sim["intersection_count"] == 2
    assert sim["jaccard"] == 0.5
    assert abs(sim["containment"] - 0.6666) < 0.001

def test_get_file_fingerprints():
    tokens = ["token1", "token2", "token3", "token4", "token5", "token6"]
    fps = get_file_fingerprints(tokens, k=3, w=2)
    assert len(fps) > 0
    for val, idx in fps:
        assert isinstance(val, int)
        assert isinstance(idx, int)

#!/usr/bin/env python3
"""Cheap-and-cheerful ranker that mirrors HeliBoard's typing scoring for the
*exact-match* path: given a HeliBoard binary dict (v202 or v203) and an input
string, finds every word in the dict that is the same string up to case /
accent, then ranks them with the same formula as
`typing_scoring.h::calculateFinalScore`. Lets us answer 'why does typing
kawałków give Kawałków' offline without flashing an APK.

We deliberately ignore spatial/edit-distance scoring — it doesn't matter for
the exact-match cases we care about here. Everything else (EXACT_MATCH_PROMOTION,
CASE_ERROR_PENALTY_FOR_EXACT_MATCH, ACCENT_ERROR_PENALTY_FOR_EXACT_MATCH /
MISSING_ACCENT_PROMOTION_BOOST in the nopopup fork, freq) is straight from the
engine source.
"""
import sys
import unicodedata
from collections import defaultdict

# Ripped verbatim from app/src/main/jni/src/suggest/policyimpl/typing/scoring_params.cpp
EXACT_MATCH_PROMOTION = 1.10
CASE_ERROR_PENALTY = 0.01
# nopopup fork: was 0.02 penalty for missing-accent, flipped to +boost (tuned
# to break ties without overriding a clear freq advantage; mirror of the value
# in scoring_params.cpp).
MISSING_ACCENT_PROMOTION_BOOST = 0.003
TYPING_BASE_OUTPUT_SCORE = 1.0
SUGGEST_INTERFACE_OUTPUT_SCALE = 1_000_000.0  # see defines.h

# Polish base-letter map (mirror of char_utils.cpp BASE_CHARS for Polish letters).
BASE = {
    'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
}

def to_base(ch):
    if ch in BASE:
        return BASE[ch]
    # fallback: NFKD strip combining marks
    s = unicodedata.normalize('NFKD', ch)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s if s else ch

def base_lower(s):
    return ''.join(to_base(c) for c in s).lower()

def classify(input_str, candidate):
    """Return one of: 'exact', 'case_only', 'accent_only', 'case_and_accent',
    'no_match'. Same input length as candidate is required (we only look at
    exact matches, no edit distance)."""
    if len(input_str) != len(candidate):
        return 'no_match'
    if input_str == candidate:
        return 'exact'
    if input_str.lower() == candidate.lower():
        return 'case_only'
    if base_lower(input_str) == base_lower(candidate):
        # accents differ; check if case also differs
        if input_str.lower() == candidate.lower():
            return 'accent_only'  # unreachable — covered above
        # Determine: did user supply base letters where candidate had accents?
        # Treat as missing-accent if every diff is candidate-has-accent-input-doesnt
        missing_accent_only = True
        for ic, cc in zip(input_str, candidate):
            if ic == cc:
                continue
            if to_base(cc) == ic.lower() or to_base(cc).lower() == ic.lower():
                continue
            missing_accent_only = False
            break
        return 'accent_only' if missing_accent_only else 'case_and_accent'
    return 'no_match'

def score(freq, kind):
    """Mirror calculateFinalScore for the boostExactMatches=true, hasProbabilityZero=false branch."""
    # compoundDistance is ~0 for an exact char-for-char match, so the
    # base-score term is ~TYPING_BASE_OUTPUT_SCORE. The frequency contributes
    # via probability-cost in compoundDistance — we approximate that as
    # -(freq_norm) where freq_norm = (255 - freq) * tiny_const so higher freq
    # subtracts less. The actual constant doesn't matter for relative ranking
    # between candidates; what matters is that freq monotonically helps.
    base = TYPING_BASE_OUTPUT_SCORE - (255 - freq) * 0.0001
    if kind == 'exact':
        promo = EXACT_MATCH_PROMOTION
    elif kind == 'case_only':
        promo = EXACT_MATCH_PROMOTION - CASE_ERROR_PENALTY
    elif kind == 'accent_only':
        # nopopup fork: this is now a +boost, not a -penalty
        promo = EXACT_MATCH_PROMOTION + MISSING_ACCENT_PROMOTION_BOOST
    elif kind == 'case_and_accent':
        promo = EXACT_MATCH_PROMOTION - CASE_ERROR_PENALTY + MISSING_ACCENT_PROMOTION_BOOST
    else:
        promo = 0.0
    return int((base + promo) * SUGGEST_INTERFACE_OUTPUT_SCALE)

# -------- dict reader (shared with dump_dict.py) --------
import struct
PTNODE_TERMINATOR = 0x1F
MAGIC = 0x9BC13AFE

class Reader:
    def __init__(self, data): self.d = data
    def u8(self, p): return self.d[p]
    def u16(self, p): return (self.d[p] << 8) | self.d[p+1]
    def u24(self, p): return (self.d[p] << 16) | (self.d[p+1] << 8) | self.d[p+2]
    def u32(self, p): return struct.unpack(">I", self.d[p:p+4])[0]

def read_header(r):
    assert r.u32(0) == MAGIC
    version = r.u16(4)
    header_size = r.u32(8)
    return version, header_size

def read_char(r, p):
    b = r.u8(p)
    if b < 0x20:
        if b == PTNODE_TERMINATOR: return None, 1
        cp = (b << 16) | (r.u8(p+1) << 8) | r.u8(p+2)
        return cp, 3
    return b, 1

def read_count(r, p):
    b = r.u8(p)
    if b & 0x80: return ((b & 0x7F) << 8) | r.u8(p+1), 2
    return b, 1

def parse_node(r, pos):
    flags = r.u8(pos); pos += 1
    chars = []
    if flags & 0x20:
        while True:
            cp, c = read_char(r, pos); pos += c
            if cp is None: break
            chars.append(cp)
    else:
        cp, c = read_char(r, pos); pos += c
        if cp is not None: chars.append(cp)
    freq = None
    if flags & 0x10:
        freq = r.u8(pos); pos += 1
    ct = flags & 0xC0
    addr_field = pos
    child_pos = None
    if ct == 0x40:
        a = r.u8(pos); pos += 1
        if a: child_pos = addr_field + a
    elif ct == 0x80:
        a = r.u16(pos); pos += 2
        if a: child_pos = addr_field + a
    elif ct == 0xC0:
        a = r.u24(pos); pos += 3
        if a == 0xFFFFFF:
            a = r.u32(pos); pos += 4
            child_pos = addr_field + a
        elif a:
            child_pos = addr_field + a
    if flags & 0x08:
        size = r.u16(pos); pos += size
    if flags & 0x04:
        while True:
            bf = r.u8(pos); pos += 1
            at = bf & 0x30
            if at == 0x10: pos += 1
            elif at == 0x20: pos += 2
            elif at == 0x30: pos += 3
            if not (bf & 0x80): break
    is_word = freq is not None and not (flags & 0x02)
    chunk = ''.join(chr(cp) for cp in chars if 0 < cp <= 0x10FFFF)
    return pos, chunk, freq, child_pos, is_word

def walk(r, pos, prefix, out, visited, depth=0):
    if pos in visited or depth > 100: return
    visited.add(pos)
    if pos <= 0 or pos >= len(r.d): return
    try: count, n = read_count(r, pos)
    except IndexError: return
    pos += n
    if count <= 0 or count > 50000: return
    for _ in range(count):
        try:
            new_pos, chunk, freq, child_pos, is_word = parse_node(r, pos)
        except IndexError:
            return
        new_prefix = prefix + chunk
        if is_word:
            out.append((new_prefix, freq))
        if child_pos is not None:
            walk(r, child_pos, new_prefix, out, visited, depth + 1)
        pos = new_pos

def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <dict.bin> <input_string>", file=sys.stderr)
        sys.exit(1)
    dict_path, query = sys.argv[1], sys.argv[2]
    with open(dict_path, 'rb') as f:
        data = f.read()
    r = Reader(data)
    version, header_size = read_header(r)
    print(f"# dict version={version} header_size={header_size}", file=sys.stderr)

    print(f"# walking trie...", file=sys.stderr)
    out = []
    walk(r, header_size, '', out, set())
    print(f"# total terminals: {len(out)}", file=sys.stderr)

    print(f"# scanning for candidates with same length as '{query}' (len={len(query)}) and matching base+lower form '{base_lower(query)}'...", file=sys.stderr)
    candidates = []
    for w, f in out:
        if len(w) != len(query):
            continue
        if base_lower(w) != base_lower(query):
            continue
        kind = classify(query, w)
        if kind == 'no_match':
            continue
        s = score(f, kind)
        candidates.append((s, w, f, kind))

    candidates.sort(key=lambda x: -x[0])
    print(f"# {len(candidates)} candidates after filter")
    print(f"\n# rank score        word              freq match_type")
    for i, (s, w, f, k) in enumerate(candidates[:20], 1):
        print(f"# {i:>3}  {s:>10}  {w:<18} {f:>4}  {k}")
    print()
    if candidates:
        winner = candidates[0]
        print(f"WINNER: '{winner[1]}' (freq={winner[2]}, match={winner[3]}, score={winner[0]})")
        if winner[1] != query and winner[3] == 'case_only':
            print(f"  → user typed '{query}' but ranker prefers different-case '{winner[1]}'")

if __name__ == "__main__":
    main()

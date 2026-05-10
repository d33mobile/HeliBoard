#!/usr/bin/env python3
"""Merge HermitDave subs + Leipzig news + Leipzig wiki frequencies onto an
existing HeliBoard `combined` file (hunspell-derived, all freq=100).

Strategy:
- collapse case: aggregate corpus counts on lowercase form
- weight sources: news+wiki = formal, subs = colloquial; mix 50/50
- log-map count -> uint8 freq in [base, 255], where base=50 for words unseen in
  corpora (so they remain suggestable, just outranked)

Output: new combined file with rebalanced f= per word.
"""
import math
import sys
from collections import defaultdict

POLISH_RE_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZąćęłńóśźżĄĆĘŁŃÓŚŹŻ'-")

BASE_FREQ_UNSEEN = 50          # fallback for words not in any corpus
MIN_FREQ_SEEN = 60             # floor for any corpus-seen word (above unseen)
MAX_FREQ = 255                 # uint8 ceiling

def read_hermit(path):
    """HermitDave format: 'word count' per line."""
    out = defaultdict(int)
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) != 2:
                continue
            word, cnt = parts[0], parts[1]
            try:
                out[word.lower()] += int(cnt)
            except ValueError:
                continue
    return out

def read_leipzig(path):
    """Leipzig: 'rank<TAB>word<TAB>count' per line."""
    out = defaultdict(int)
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            _, word, cnt = parts
            try:
                out[word.lower()] += int(cnt)
            except ValueError:
                continue
    return out

def is_word(w):
    if not w:
        return False
    for ch in w:
        if ch not in POLISH_RE_OK:
            return False
    return True

def freq_to_uint8(weighted, top_weighted):
    """Map weighted corpus count to uint8 in [MIN_FREQ_SEEN, MAX_FREQ]."""
    if weighted <= 0:
        return BASE_FREQ_UNSEEN
    log_w = math.log2(weighted + 1)
    log_top = math.log2(top_weighted + 1)
    span = MAX_FREQ - MIN_FREQ_SEEN
    mapped = MIN_FREQ_SEEN + int(round(log_w / log_top * span))
    return max(MIN_FREQ_SEEN, min(MAX_FREQ, mapped))

def main(combined_in, subs_path, news_path, wiki_path, combined_out):
    print(f"Reading subs from {subs_path}...", file=sys.stderr)
    subs = read_hermit(subs_path)
    print(f"  {len(subs)} unique words", file=sys.stderr)

    print(f"Reading news from {news_path}...", file=sys.stderr)
    news = read_leipzig(news_path)
    print(f"  {len(news)} unique words", file=sys.stderr)

    print(f"Reading wiki from {wiki_path}...", file=sys.stderr)
    wiki = read_leipzig(wiki_path)
    print(f"  {len(wiki)} unique words", file=sys.stderr)

    # Combine: weight subs:news:wiki = 1:1:1 normalised by corpus size.
    # Each corpus contributes its share of word counts; the relative ranking
    # within the corpus is preserved, but no single corpus dominates.
    total_subs = sum(subs.values()) or 1
    total_news = sum(news.values()) or 1
    total_wiki = sum(wiki.values()) or 1
    print(f"Total tokens: subs={total_subs} news={total_news} wiki={total_wiki}", file=sys.stderr)

    weighted = defaultdict(float)
    SCALE = 1_000_000
    for w, c in subs.items():
        if is_word(w):
            weighted[w] += c / total_subs * SCALE
    for w, c in news.items():
        if is_word(w):
            weighted[w] += c / total_news * SCALE
    for w, c in wiki.items():
        if is_word(w):
            weighted[w] += c / total_wiki * SCALE

    top_weighted = max(weighted.values())
    print(f"Top weighted: {top_weighted:.0f}", file=sys.stderr)

    # Pre-compute lookup
    print(f"Reading combined from {combined_in}...", file=sys.stderr)
    n_total = 0
    n_seen = 0
    n_unseen = 0
    with open(combined_in, encoding="utf-8") as fin, \
         open(combined_out, "w", encoding="utf-8") as fout:
        # Header line passes through unchanged
        header = fin.readline()
        # Bump description so we know which dict it is
        if "description=" in header:
            new_desc = "description=Polish-corpus-weighted-v1"
            header = ",".join(
                new_desc if p.startswith("description=") else p
                for p in header.rstrip("\n").split(",")
            ) + "\n"
        fout.write(header)

        for line in fin:
            n_total += 1
            # Format: " word=X,f=N"
            stripped = line.strip()
            if not stripped.startswith("word="):
                fout.write(line)
                continue
            try:
                word_part, _ = stripped.split(",", 1)
                word = word_part[len("word="):]
            except ValueError:
                fout.write(line)
                continue
            lw = word.lower()
            w_count = weighted.get(lw, 0)
            if w_count > 0:
                n_seen += 1
                freq = freq_to_uint8(w_count, top_weighted)
            else:
                n_unseen += 1
                freq = BASE_FREQ_UNSEEN
            fout.write(f" word={word},f={freq}\n")

    print(f"Wrote {n_total} words: {n_seen} seen, {n_unseen} unseen", file=sys.stderr)
    print(f"  pct seen: {n_seen / n_total * 100:.1f}%", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print(f"usage: {sys.argv[0]} <combined_in> <subs.txt> <news_words.txt> <wiki_words.txt> <combined_out>", file=sys.stderr)
        sys.exit(1)
    main(*sys.argv[1:])

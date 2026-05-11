#!/usr/bin/env python3
"""Regression tests for the bugs surfaced during phone testing of the
nopopup fork. Each test asserts the behaviour the user expected; if you
revert the corresponding patch in the dict-build pipeline (merge_freq.py)
or in the bundled dict itself, the relevant test fails. Run from the
repo root:

    python3 ai/corpus/test_corpus.py

Exit code 0 = all pass, 1 = one or more failed.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BUNDLED_DICT = REPO / "app/src/main/assets/dicts/main_pl.dict"
SIM = HERE / "sim_rank.py"
MERGE = HERE / "merge_freq.py"

FAILS = []

def fail(test, msg):
    FAILS.append((test, msg))
    print(f"  FAIL  {test}: {msg}", file=sys.stderr)

def passed(test):
    print(f"  ok    {test}")

def parse_sim_output(stdout):
    """sim_rank.py prints 'WINNER: <word>' on its own line. Return that word."""
    for line in stdout.splitlines():
        if line.startswith("WINNER:"):
            # format: WINNER: 'kawałków' (freq=117, match=exact, score=...)
            after = line.split(":", 1)[1].strip()
            if after.startswith("'"):
                return after.split("'")[1]
    return None

def run_sim(query):
    r = subprocess.run(
        ["python3", str(SIM), str(BUNDLED_DICT), query],
        capture_output=True, text=True, check=True,
    )
    return parse_sim_output(r.stdout)


# ---------------------------------------------------------------------------
# Bug: typing 'kawałków' (gen-pl of kawałek) silently capitalised to 'Kawałków'
# (a Małopolska village name). Both forms are in the bundled wordlist; without
# the case-collision penalty in merge_freq.py they tie at f=117 and the
# engine picks the capitalised form via the case-error path.

def test_kawalkow_stays_lowercase():
    winner = run_sim("kawałków")
    if winner != "kawałków":
        fail("kawałków stays lowercase",
             f"expected 'kawałków', got '{winner}' — bundled dict likely lost the case-collision demotion")
        return
    passed("kawałków stays lowercase (case-collision fix)")


# ---------------------------------------------------------------------------
# Bug: typing 'Warszawa' should win over 'warszawa' (hunspell unmunch emits
# both but only the capitalised form is real). Mirror of the previous test in
# the opposite direction — protects the demotion logic from being one-sided.

def test_warszawa_stays_capitalised():
    winner = run_sim("Warszawa")
    if winner != "Warszawa":
        fail("Warszawa stays capitalised",
             f"expected 'Warszawa', got '{winner}'")
        return
    passed("Warszawa stays capitalised (case-collision fix, reverse direction)")


# ---------------------------------------------------------------------------
# Bug: typing 'fleksje' (base letter) should rank 'fleksję' (with the ę)
# first, because Polish users routinely skip diacritics on hard-to-reach
# keys. Verifies the diacritic-promotion boost added to typing_scoring.h.

def test_fleksje_prefers_diacritic():
    winner = run_sim("fleksje")
    if winner != "fleksję":
        fail("fleksje → fleksję",
             f"expected 'fleksję' to outrank 'fleksje', got winner='{winner}' — diacritic-promotion boost may have regressed")
        return
    passed("fleksje → fleksję (diacritic-promotion boost)")


# ---------------------------------------------------------------------------
# Bug: 'ostrzegał' missing from suggestion strip when typing 'ostrzega' or
# 'ostrzegał'. With corpus-weighted frequencies, the past-tense form should
# at least match itself when typed exactly (regression check on bundled dict
# integrity AND on freq-aware ranking).

def test_ostrzegal_exact_match():
    winner = run_sim("ostrzegał")
    if winner != "ostrzegał":
        fail("ostrzegał exact match",
             f"expected 'ostrzegał', got '{winner}' — dict likely missing the word")
        return
    passed("ostrzegał exact match (dict integrity)")


# ---------------------------------------------------------------------------
# Bug: krzaki (mojibake / surrogate pairs) in suggestions came from
# dicttool_aosp's silent truncation of >16 MB children-addresses in the v202
# format. v203 sentinel-extension is supposed to round-trip every word
# losslessly. Dump the bundled binary and assert zero "bad" words.

def test_bundled_dict_has_no_mojibake():
    # Re-use dump_dict.py from /tmp/pldict if available, otherwise inline
    # a minimal check via the BAD-word counter built into the dumper.
    dumper = Path("/tmp/pldict/dump_dict.py")
    if not dumper.exists():
        fail("bundled dict no-mojibake",
             f"dumper not found at {dumper}, skipping")
        return
    r = subprocess.run(
        ["python3", str(dumper), str(BUNDLED_DICT)],
        capture_output=True, text=True, check=True,
    )
    # dump_dict.py prints '# bad-encoding words: N' on stderr
    bad = None
    for line in r.stderr.splitlines():
        if "bad-encoding words:" in line:
            bad = int(line.rsplit(":", 1)[1].strip())
            break
    if bad is None:
        fail("bundled dict no-mojibake",
             f"dumper didn't report bad-encoding count; output: {r.stderr[:200]}")
        return
    if bad != 0:
        fail("bundled dict no-mojibake",
             f"{bad} mojibake words in bundled dict — v203 round-trip broken")
        return
    passed(f"bundled dict has no mojibake ({bad} bad words)")


# ---------------------------------------------------------------------------
# merge_freq.py: synthetic test of the case-collision demotion logic.
# Build a tiny wordlist + tiny corpora where the dominance ratios are known,
# then assert the merger produces the expected freqs.

def test_merge_freq_case_collision_logic():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # wordlist (combined) with both case variants
        combined_in = d / "in.combined"
        combined_in.write_text(
            "dictionary=test,locale=pl,description=test,date=0,version=1\n"
            " word=kawałków,f=100\n"
            " word=Kawałków,f=100\n"
            " word=Warszawa,f=100\n"
            " word=warszawa,f=100\n"
            " word=polski,f=100\n"
            " word=Polski,f=100\n"
        )
        # subs corpus: heavy lowercase 'kawałków', no 'Kawałków', similar
        # for the other pairs
        subs = d / "subs.txt"
        subs.write_text(
            "kawałków 5000\n"      # 99.8% lowercase → Kawałków demoted
            "Kawałków 10\n"
            "warszawa 5\n"          # 99% capitalised → warszawa demoted
            "Warszawa 5000\n"
            "polski 2000\n"         # ~50/50 → both kept
            "Polski 2000\n"
        )
        # leipzig-format placeholders (empty content is fine, only subs matters)
        news = d / "news.txt"
        news.write_text("")
        wiki = d / "wiki.txt"
        wiki.write_text("")
        combined_out = d / "out.combined"
        subprocess.run(
            ["python3", str(MERGE), str(combined_in), str(subs), str(news), str(wiki), str(combined_out)],
            check=True, capture_output=True,
        )
        out = combined_out.read_text()
        # parse
        freqs = {}
        for line in out.splitlines():
            s = line.strip()
            if not s.startswith("word="):
                continue
            word_part, freq_part = s.split(",f=")
            freqs[word_part[len("word="):]] = int(freq_part)

        def chk(word, expected_op, expected_other, msg):
            f = freqs.get(word)
            other = freqs.get(expected_other) if expected_other else None
            ok = expected_op(f, other) if other is not None else expected_op(f)
            if not ok:
                fail("merge_freq case-collision",
                     f"{msg}: {word}={f}, {expected_other}={other}")
                return False
            return True

        # kawałków should beat Kawałków
        if not chk("kawałków", lambda f, o: f > o, "Kawałków",
                   "lowercase dominant should win"):
            return
        # Warszawa should beat warszawa
        if not chk("Warszawa", lambda f, o: f > o, "warszawa",
                   "capitalised dominant should win"):
            return
        # polski and Polski should both have non-demoted freq (i.e. > 50)
        if freqs.get("polski", 0) <= 50 or freqs.get("Polski", 0) <= 50:
            fail("merge_freq case-collision",
                 f"comparable pair should both stay high: polski={freqs.get('polski')}, Polski={freqs.get('Polski')}")
            return
    passed("merge_freq case-collision (synthetic 3-way: dominant-lc, dominant-cap, balanced)")


# ---------------------------------------------------------------------------

def main():
    if not BUNDLED_DICT.exists():
        print(f"FATAL: bundled dict not found at {BUNDLED_DICT}", file=sys.stderr)
        sys.exit(2)
    print(f"Running regression tests against {BUNDLED_DICT.name}...\n")

    test_kawalkow_stays_lowercase()
    test_warszawa_stays_capitalised()
    test_fleksje_prefers_diacritic()
    test_ostrzegal_exact_match()
    test_bundled_dict_has_no_mojibake()
    test_merge_freq_case_collision_logic()

    print()
    if FAILS:
        print(f"FAIL: {len(FAILS)} test(s) failed", file=sys.stderr)
        sys.exit(1)
    else:
        print("PASS: all tests green")

if __name__ == "__main__":
    main()

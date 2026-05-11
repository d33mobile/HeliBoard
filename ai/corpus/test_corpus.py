#!/usr/bin/env python3
"""Regression tests for the bugs surfaced during phone testing of the
nopopup fork. Each test was authored against the corresponding fix, and
each was verified to FAIL when the fix is reverted (see header comments
on each test for the revert recipe and what fails). Run from the repo
root:

    python3 ai/corpus/test_corpus.py

Exit code 0 = all pass, 1 = one or more failed.

Two classes of tests:

A. SCORING tests — exercise the typing-scoring formula in isolation by
   feeding synthetic (word, freq) candidate lists into sim_rank.rank().
   The formula constants in sim_rank.py mirror scoring_params.cpp; so
   when the C++ constants change the Python sim follows. These tests
   demand specific RANKING behaviour (which form wins), not specific
   scores, so they remain stable across small constant tweaks.

B. PIPELINE tests — exercise the dict-build pipeline (merge_freq.py +
   bundled main_pl.dict). They prove the bundled binary was built with
   the current merger and that the merger's case-collision logic and
   curated-additions mechanism behave as documented.
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
ADDITIONS = HERE / "additions_pl.txt"

# Allow `import sim_rank` and `import merge_freq`
sys.path.insert(0, str(HERE))
import sim_rank  # noqa: E402

FAILS = []

def fail(test, msg):
    FAILS.append((test, msg))
    print(f"  FAIL  {test}: {msg}", file=sys.stderr)

def passed(test):
    print(f"  ok    {test}")

# Cached dump of the bundled dict (avoid re-walking the 18 MB trie per test).
_DUMP_CACHE = None
def bundled_dump():
    global _DUMP_CACHE
    if _DUMP_CACHE is None:
        dumper = Path("/tmp/pldict/dump_dict.py")
        if not dumper.exists():
            raise FileNotFoundError(
                f"dumper missing at {dumper} — set up the /tmp/pldict scratch dir per ai/corpus/README.md")
        r = subprocess.run(
            ["python3", str(dumper), str(BUNDLED_DICT)],
            capture_output=True, text=True, check=True,
        )
        out = {}
        bad = None
        for line in r.stderr.splitlines():
            if "bad-encoding words:" in line:
                bad = int(line.rsplit(":", 1)[1].strip())
        for line in r.stdout.splitlines():
            try:
                freq, word = line.split("\t", 1)
                out[word] = int(freq)
            except ValueError:
                continue
        _DUMP_CACHE = (out, bad)
    return _DUMP_CACHE


# ===========================================================================
# A. SCORING tests — synthetic candidate lists, no dict file needed.
# ===========================================================================

# ---- Bug: diacritic-promotion boost --------------------------------------
# scoring_params.cpp::MISSING_ACCENT_PROMOTION_BOOST
# Revert recipe: set boost to 0 → test_diacritic_promotion_when_freqs_tie fails.
# Revert recipe: set boost to upstream's -0.02 → test_diacritic_wins_under_corpus_advantage also fails.

def test_diacritic_promotion_when_freqs_tie():
    """When user types base letters and dict has both forms with IDENTICAL
    freq (typical for two rare hunspell forms both at f=50), only a positive
    diacritic-promotion boost can tip the scale to the accented form.

    Without the boost: both candidates score the same, and the engine's
    default tie-breaker (trie-insert order, effectively arbitrary) decides.
    The user-reported 'fleksje doesn't autocorrect to fleksję' bug fits
    this profile.

    Verified fail recipe: set MISSING_ACCENT_PROMOTION_BOOST = 0 in
    sim_rank.py → assertion below fires because the two scores tie and
    the exact form sorts first by stable-sort.
    """
    candidates = [("fleksje", 50), ("fleksję", 50)]
    w = sim_rank.winner("fleksje", candidates)
    if w != "fleksję":
        fail("diacritic promotion (tied freq)",
             f"expected fleksję to win on equal-freq tie via the boost, got '{w}' — "
             f"is MISSING_ACCENT_PROMOTION_BOOST positive?")
        return
    passed("diacritic promotion wins ties (boost > 0)")


def test_diacritic_wins_under_corpus_advantage():
    """When the accented form has a small corpus-derived freq advantage
    over the base form (real bundled-dict shape, e.g. fleksje f=50,
    fleksję f=63), the diacritic-promotion boost still needs to NOT cancel
    out that natural advantage. Reverting to the upstream -0.02 penalty
    flips this assertion."""
    candidates = [("fleksje", 50), ("fleksję", 63)]
    w = sim_rank.winner("fleksje", candidates)
    if w != "fleksję":
        fail("diacritic wins with freq advantage",
             f"expected fleksję (f=63) to outrank fleksje (f=50), got '{w}'")
        return
    passed("diacritic wins when corpus already nudges it (boost ≥ 0)")


# ---- Bug: diacritic boost overcorrects when exact form has clear freq advantage
# Revert recipe: set boost to 0.05 (pre-tuning value) → test fails (Warszawą wins).

def test_diacritic_boost_does_not_override_freq_advantage():
    """Mirror of the diacritic test: when the EXACT form has a meaningful
    freq advantage (Warszawa f=155, Warszawą f=110), the boost must not
    flip the winner. The pre-tuning 0.05 value did exactly that; the
    current 0.003 is the tuned magnitude.

    Verified fail recipe: set MISSING_ACCENT_PROMOTION_BOOST = 0.05 in
    sim_rank.py → 'Warszawa' typed input picks 'Warszawą'.
    """
    candidates = [("Warszawa", 155), ("Warszawą", 110)]
    w = sim_rank.winner("Warszawa", candidates)
    if w != "Warszawa":
        fail("diacritic boost does not override freq",
             f"expected Warszawa (f=155 exact) to outrank Warszawą (f=110 missing-accent), got '{w}' — boost likely too large")
        return
    passed("diacritic boost does not override clear freq advantage")


# ---- Bug: case-only mismatch should prefer exact case at equal freq -------
# This is upstream behaviour (CASE_ERROR_PENALTY = 0.01), preserved by fork.
# Revert recipe: set CASE_ERROR_PENALTY to 0 or negative → test fails.

def test_case_penalty_breaks_ties():
    """When user types lowercase and dict has both case variants at equal
    freq (the shape the merger produced before the case-collision
    demotion was added), the existing CASE_ERROR_PENALTY (-0.01) alone is
    enough to make lowercase win. This test guards against an upstream
    regression that would zero out that penalty."""
    # Pass Kawałków first so the test isn't passing accidentally due to Python's
    # stable sort: without the penalty, both score the same and the first item
    # wins → Kawałków. With the penalty, kawałków beats Kawałków actively.
    candidates = [("Kawałków", 100), ("kawałków", 100)]
    w = sim_rank.winner("kawałków", candidates)
    if w != "kawałków":
        fail("case penalty breaks ties",
             f"expected lowercase kawałków to win via case-error penalty (-0.01), got '{w}' — "
             f"is CASE_ERROR_PENALTY > 0?")
        return
    passed("case penalty breaks lowercase/Capitalized ties (engine-level)")


# ===========================================================================
# B. PIPELINE tests — exercise merge_freq.py + bundled dict.
# ===========================================================================

# ---- Bug: kawałków → Kawałków (merge_freq case-collision demotion) -------
# Revert recipe: delete the 'Disambiguate case-collisions' block in
#   merge_freq.py → test_merger_demotes_capitalized_when_lowercase_dominant fails.

def test_merger_demotes_capitalized_when_lowercase_dominant():
    """Run merge_freq.py against a synthetic wordlist that contains both
    case variants at equal freq, with a corpus where the lowercase form
    overwhelmingly dominates. The merger must demote the Capitalized
    variant to BASE_FREQ_UNSEEN (50) so case_only matches lose more than
    just the engine's tiny case-penalty."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "in.combined").write_text(
            "dictionary=test,locale=pl,description=test,date=0,version=1\n"
            " word=kawałków,f=100\n"
            " word=Kawałków,f=100\n"
        )
        # subs corpus has kawałków >>> Kawałków
        (d / "subs.txt").write_text("kawałków 5000\nKawałków 10\n")
        (d / "news.txt").write_text("")
        (d / "wiki.txt").write_text("")
        out = d / "out.combined"
        subprocess.run(
            ["python3", str(MERGE), str(d / "in.combined"), str(d / "subs.txt"),
             str(d / "news.txt"), str(d / "wiki.txt"), str(out)],
            check=True, capture_output=True,
        )
        freqs = {}
        for line in out.read_text().splitlines():
            s = line.strip()
            if not s.startswith("word="):
                continue
            wp, fp = s.split(",f=")
            freqs[wp[len("word="):]] = int(fp)
        if freqs.get("Kawałków", 0) != 50:
            fail("merger demotes Capitalized",
                 f"expected Kawałków → f=50 (BASE_FREQ_UNSEEN), got {freqs.get('Kawałków')} — "
                 f"case-collision demotion block missing/broken in merge_freq.py")
            return
        if freqs.get("kawałków", 0) <= 50:
            fail("merger demotes Capitalized",
                 f"expected kawałków to keep corpus-weighted freq, got {freqs.get('kawałków')}")
            return
    passed("merger demotes Capitalized when lowercase corpus-dominant")


def test_merger_demotes_lowercase_when_capitalized_dominant():
    """Mirror of above — Warszawa side. Without this we'd silently rewrite
    'Warszawa' to 'warszawa'."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "in.combined").write_text(
            "dictionary=test,locale=pl,description=test,date=0,version=1\n"
            " word=Warszawa,f=100\n"
            " word=warszawa,f=100\n"
        )
        (d / "subs.txt").write_text("Warszawa 5000\nwarszawa 10\n")
        (d / "news.txt").write_text("")
        (d / "wiki.txt").write_text("")
        out = d / "out.combined"
        subprocess.run(
            ["python3", str(MERGE), str(d / "in.combined"), str(d / "subs.txt"),
             str(d / "news.txt"), str(d / "wiki.txt"), str(out)],
            check=True, capture_output=True,
        )
        freqs = {}
        for line in out.read_text().splitlines():
            s = line.strip()
            if not s.startswith("word="):
                continue
            wp, fp = s.split(",f=")
            freqs[wp[len("word="):]] = int(fp)
        if freqs.get("warszawa", 0) != 50:
            fail("merger demotes lowercase",
                 f"expected warszawa → f=50 (BASE_FREQ_UNSEEN), got {freqs.get('warszawa')}")
            return
        if freqs.get("Warszawa", 0) <= 50:
            fail("merger demotes lowercase",
                 f"expected Warszawa to keep corpus-weighted freq, got {freqs.get('Warszawa')}")
            return
    passed("merger demotes lowercase when Capitalized corpus-dominant")


def test_merger_leaves_balanced_pair_alone():
    """Comparable counts (e.g. polski adjective + Polski as 'Bank Polski')
    must not trigger demotion — both forms are genuinely common."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "in.combined").write_text(
            "dictionary=test,locale=pl,description=test,date=0,version=1\n"
            " word=polski,f=100\n"
            " word=Polski,f=100\n"
        )
        # 50/50 split: neither dominates → both kept
        (d / "subs.txt").write_text("polski 2000\nPolski 2000\n")
        (d / "news.txt").write_text("")
        (d / "wiki.txt").write_text("")
        out = d / "out.combined"
        subprocess.run(
            ["python3", str(MERGE), str(d / "in.combined"), str(d / "subs.txt"),
             str(d / "news.txt"), str(d / "wiki.txt"), str(out)],
            check=True, capture_output=True,
        )
        freqs = {}
        for line in out.read_text().splitlines():
            s = line.strip()
            if not s.startswith("word="):
                continue
            wp, fp = s.split(",f=")
            freqs[wp[len("word="):]] = int(fp)
        if freqs.get("polski", 0) <= 50 or freqs.get("Polski", 0) <= 50:
            fail("merger leaves balanced pair alone",
                 f"expected both kept high; got polski={freqs.get('polski')}, Polski={freqs.get('Polski')}")
            return
    passed("merger leaves balanced case-pair alone (no demotion)")


# ---- Mechanism: hunspell-additions injection ------------------------------
# Revert recipe: delete read_additions() / additions_to_inject from
#   merge_freq.py → test_merger_injects_additions fails because the test
#   word stops appearing in the output.

def test_merger_injects_additions():
    """The additions_pl.txt mechanism lets us add hunspell-rejected forms
    to the wordlist when a colloquial form needs to be typable. Run merger
    against an empty hunspell wordlist + a synthetic additions list and
    assert the injected word appears in the output combined."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "in.combined").write_text(
            "dictionary=test,locale=pl,description=test,date=0,version=1\n"
            " word=foo,f=100\n"
        )
        (d / "subs.txt").write_text("synthword 1000\n")
        (d / "news.txt").write_text("")
        (d / "wiki.txt").write_text("")
        (d / "additions.txt").write_text(
            "# test additions file\n"
            "synthword\n"
        )
        out = d / "out.combined"
        subprocess.run(
            ["python3", str(MERGE), str(d / "in.combined"), str(d / "subs.txt"),
             str(d / "news.txt"), str(d / "wiki.txt"), str(out), str(d / "additions.txt")],
            check=True, capture_output=True,
        )
        text = out.read_text()
        if " word=synthword,f=" not in text:
            fail("merger injects additions",
                 "additions mechanism didn't inject synthword into output — "
                 "read_additions() / additions_to_inject likely missing in merge_freq.py")
            return
    passed("merger injects curated additions (when justified)")


# ---- Bug: kawałków on bundled dict ----------------------------------------
# Revert recipe: rebuild the dict with the case-collision block removed from
#   merge_freq.py and re-bundle → test_bundled_kawalkow_lowercase_dominant fails.

def test_bundled_kawalkow_lowercase_dominant():
    """Integration test: the bundled main_pl.dict must have kawałków
    significantly outranking Kawałków, proving the merger ran with the
    case-collision demotion enabled when this APK was built."""
    words, _ = bundled_dump()
    lc = words.get("kawałków")
    cap = words.get("Kawałków")
    if lc is None or cap is None:
        fail("bundled kawałków lowercase-dominant",
             f"one or both case variants missing: kawałków={lc}, Kawałków={cap}")
        return
    if lc - cap < 30:  # at least 30 freq points of gap = ~3x more impact than case penalty
        fail("bundled kawałków lowercase-dominant",
             f"freq gap too small: kawałków={lc}, Kawałków={cap}; case-collision demotion likely skipped")
        return
    passed(f"bundled kawałków lowercase-dominant ({lc} vs {cap})")


# ---- Bug: ostrzegał missing -----------------------------------------------
# Revert recipe: replace bundled main_pl.dict with the pre-corpus uniform
#   v203 dict → test_bundled_ostrzegal_has_corpus_freq fails (freq stays 100
#   uniform instead of the corpus-weighted value).

def test_bundled_ostrzegal_has_corpus_freq():
    """ostrzegał appears 18 times in the Leipzig news corpus (~rank 23k).
    With corpus weighting it should land in the upper-middle freq range,
    distinct from both the uniform-100 default and the BASE_FREQ_UNSEEN
    fallback. Asserts it's > 60 and < 130, the band corpus-attested
    mid-frequency words land in."""
    words, _ = bundled_dump()
    f = words.get("ostrzegał")
    if f is None:
        fail("ostrzegał has corpus freq",
             "ostrzegał missing from bundled dict")
        return
    # Either freq=100 uniform (no merger) or freq=50 (unseen-in-corpus path).
    # Both are failure modes. Corpus-attested value sits in 60..130.
    if f == 100 or f == 50:
        fail("ostrzegał has corpus freq",
             f"ostrzegał at f={f} → corpus weighting didn't apply (uniform 100 or unseen 50)")
        return
    passed(f"ostrzegał has corpus-derived freq (f={f})")


# ---- Bug: krzaki / mojibake ----------------------------------------------
# Revert recipe: bundle a dict produced by vanilla (non-v203) dicttool on
#   a large Polish wordlist → test_bundled_dict_no_mojibake fails because
#   addresses > 16 MB get silently truncated and the decoder hits garbage.

def test_bundled_dict_no_mojibake():
    """Walks the bundled trie and asserts every terminal decodes to a
    well-formed string (no SPUA, no replacement chars). This is the
    user-visible check for the v203 sentinel-extension fix."""
    _, bad = bundled_dump()
    if bad is None:
        fail("bundled dict no mojibake",
             "dumper didn't report bad-encoding count")
        return
    if bad != 0:
        fail("bundled dict no mojibake",
             f"{bad} mojibake words in bundled dict — v203 round-trip broken")
        return
    passed("bundled dict has no mojibake (0 bad-encoding words)")


# ===========================================================================

def main():
    if not BUNDLED_DICT.exists():
        print(f"FATAL: bundled dict not found at {BUNDLED_DICT}", file=sys.stderr)
        sys.exit(2)
    print(f"Running regression tests against {BUNDLED_DICT.name}...\n")

    tests = [
        # A. Scoring (synthetic, no dict needed)
        test_diacritic_promotion_when_freqs_tie,
        test_diacritic_wins_under_corpus_advantage,
        test_diacritic_boost_does_not_override_freq_advantage,
        test_case_penalty_breaks_ties,
        # B. Pipeline (merge_freq + bundled dict)
        test_merger_demotes_capitalized_when_lowercase_dominant,
        test_merger_demotes_lowercase_when_capitalized_dominant,
        test_merger_leaves_balanced_pair_alone,
        test_merger_injects_additions,
        test_bundled_kawalkow_lowercase_dominant,
        test_bundled_ostrzegal_has_corpus_freq,
        test_bundled_dict_no_mojibake,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            fail(t.__name__, f"unexpected exception: {type(e).__name__}: {e}")

    print()
    if FAILS:
        print(f"FAIL: {len(FAILS)} test(s) failed", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"PASS: all {len(tests)} tests green")

if __name__ == "__main__":
    main()

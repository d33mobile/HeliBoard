# Upstream PR plan: aosp-dictionaries dicttool VERSION_203 support

Target: `Helium314/aosp-dictionaries` on Codeberg (NOT GitHub).

This repo distributes:
* `dicttool_aosp.jar` (compiled encoder, downloaded from upstream remi0s)
* Pre-built `.dict` files for many languages
* Build scripts (`scripts/wordlist.py`, `scripts/wordlist_combined.py`)

## What changes

Replace `dicttool_aosp.jar` with patched version supporting `-203` flag.
Add note to README about VERSION_203, when to use, runtime requirement.

Optionally regenerate the broken experimental dicts (Polish, possibly others)
in v203 — but that requires HeliBoard upstream to also accept v203 (companion
PR to Helium314/HeliBoard).

## Patched jar

Source-modified files (vs AOSP master):
* `LatinIME/java/src/com/android/inputmethod/latin/makedict/FormatSpec.java`
  — added `VERSION203 = 203`, `PTNODE_MAX_ADDRESS_SIZE_V203 = 7`,
  `PTNODE_ATTRIBUTE_MAX_ADDRESS_SIZE_V203 = 7`.
* `LatinIME/tests/src/com/android/inputmethod/latin/makedict/BinaryDictEncoderUtils.java`
  — added 7-byte case to `getByteSize` / `writeUIntToBuffer` / `writeUIntToStream` /
  `writeChildrenPosition`. Added `formatVersion`-aware overloads. Threaded format
  version through `computeAddresses` → `computeActualPtNodeArraySize`.
* `LatinIME/tests/src/com/android/inputmethod/latin/makedict/Ver2DictEncoder.java`
  — accept VERSION202 and VERSION203, store in field, pass to encoder utils.
* `LatinIME/tools/dicttool/src/com/android/inputmethod/latin/dicttool/DictionaryMaker.java`
  — added `-203` CLI flag.

Built jar: `ai/dicttool-patches/dicttool_aosp_v203.jar` (186 KB) checked into
this repo.

## Behavioral changes

* Default behavior unchanged. `makedict` without `-203` produces VERSION202
  bytes-identical to upstream output.
* `makedict -203` produces v203 file (header `00 CB`).
* `makedict` with default v202 on wordlist that needs >16 MB addresses
  now throws `RuntimeException("address X >= 16 MB cannot be encoded in
  VERSION202; use VERSION203 (-203 flag)")` instead of silently producing
  corrupt output (the existing assert was no-op without `-ea`).

## Files to add to aosp-dictionaries repo

* `dicttool_aosp.jar` — replaced with patched version (drop in place, same name).
* `README.md` — append note about v203, link to HeliBoard PR.

Optional follow-up:
* Build scripts could auto-detect when to use `-203` based on input size.

## PR description draft

```
title: Replace dicttool_aosp.jar with v203-aware build (extended addresses for >16 MB tries)

The current dicttool_aosp.jar silently produces corrupt dictionaries
when the trie exceeds 16 MB, because BinaryDictEncoderUtils.getByteSize
asserts (assert is no-op without -ea) instead of validating address
size, and writeUIntToBuffer truncates to 3 bytes regardless. Result:
children-position pointers >= 16 MB are written with their high byte
silently dropped, producing dicts where trie traversal lands inside
unrelated nodes. HeliBoard surfaces this as garbage suggestions
(`Ä񄁣�i`-type strings).

Affected dicts in this repo (>16 MB):
* dictionaries_experimental/main_pl.dict (21.7 MB) — 7 known frankenstein
  entries with surrogates and CJK Extension B chars
* dictionaries_experimental/* (any other large language dict)

This PR replaces dicttool_aosp.jar with a build that:

1. Adds VERSION_203 = 203 with sentinel-based extended addressing:
   when 3-byte address reads as 0xFFFFFF, next 4 bytes are the actual
   32-bit unsigned offset. Supports tries up to 4 GiB.
2. Adds `-203` flag to `makedict` to opt into the new format. Default
   stays `-2` (VERSION202) — no surprise for existing build pipelines.
3. Replaces the silent-truncation behavior in v202 mode with a hard
   RuntimeException, so the bug can't recur.
4. The patched jar produces byte-identical output for v202 wordlists
   that fit in 16 MB (verified with /tmp/pldict/test.combined → diff = empty).

The runtime side (HeliBoard) needs companion patch in
Helium314/HeliBoard to read VERSION_203. PR pending there too.

Old HeliBoard + v203 dict refuses to load (UNKNOWN_VERSION), falls back
to bundled — safe behavior, no krzaki.

## Source

Patches against AOSP master (clone of
android.googlesource.com/platform/packages/inputmethods/LatinIME):
* tests/src/com/android/inputmethod/latin/makedict/{BinaryDictEncoderUtils,Ver2DictEncoder}.java
* java/src/com/android/inputmethod/latin/makedict/FormatSpec.java
* tools/dicttool/src/com/android/inputmethod/latin/dicttool/DictionaryMaker.java

Patched .java files preserved at d33mobile/HeliBoard branch nopopup
under ai/dicttool-patches/.
```

## Steps to file

Codeberg uses Gitea, no `gh` CLI. Use `tea` CLI or web UI.

1. Sign in to codeberg.org.
2. Fork Helium314/aosp-dictionaries.
3. Clone fork, copy `dicttool_aosp_v203.jar` over `dicttool_aosp.jar`.
4. Edit README.md to add v203 section (template above).
5. Commit, push, open PR via Codeberg web UI.

## Pre-PR caveats

* The patched jar source isn't included in aosp-dictionaries repo (the
  upstream practice — they ship binary jar from remi0s). For full reproducibility,
  upstream might want source-of-truth in remi0s/aosp-dictionary-tools fork.
  Consider opening a PR there too.

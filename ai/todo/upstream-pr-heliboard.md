# Upstream PR plan: HeliBoard runtime VERSION_203 support

Target: `Helium314/HeliBoard` (canonical) — also redirects from `HeliBorg/HeliBoard`.

## Branch

Off mainline `master`. Patch sits cleanly on top of master because all changes are additive (no semantic change to v202 path).

## Files modified

| File | Change | LOC |
|---|---|---|
| `app/src/main/jni/src/dictionary/utils/format_utils.h` | Add `VERSION_203 = 203` to enum | +6 |
| `app/src/main/jni/src/dictionary/utils/format_utils.cpp` | Add case in `getFormatVersion()` | +2 |
| `app/src/main/jni/src/dictionary/structure/pt_common/patricia_trie_reading_utils.cpp` | Sentinel detection in `readChildrenPositionAndAdvancePosition()` THREEBYTES branch | +9 |
| `app/src/main/jni/src/dictionary/structure/pt_common/bigram/bigram_list_read_write_utils.cpp` | Sentinel detection in `getBigramAddressAndAdvancePosition()` THREEBYTES branch | +9 |
| `app/src/main/java/helium314/keyboard/latin/makedict/FormatSpec.java` | Add `VERSION203 = 203` constant | +5 |

Total: ~31 LOC additions, no deletions, no behavioral change for VERSION202 dicts.

## PR description draft

```
title: Add VERSION_203 dict format support (extended addresses for tries > 16 MB)

Adds runtime support for reading dictionaries built with format VERSION_203.
VERSION_203 is identical to VERSION_202 except for an extension to the
children-address and bigram-address encoding: when the 3-byte address field
reads as 0xFFFFFF (the previous max value, never legitimately produced by
the v202 encoder which asserts address <= 16777215), the next 4 bytes are
the actual 32-bit unsigned address. This raises the maximum trie size from
16 MiB to 4 GiB.

## Why

The v202 format silently truncates addresses > 16 MB because:
  static int getByteSize(int address) {
      assert address <= 16777215;          // no-op without -ea
      ...
      return 3;                            // truncates writeUIntToBuffer
  }

This produces dicts with broken trie pointers, observable as garbage
suggestions ("krzaki") in HeliBoard. Affected upstream dicts include
the experimental Polish (5M form, 21.7 MB) which has 7 corrupted entries
containing UTF-16 surrogates — the runtime renders them as krzaki because
trie traversal lands in the middle of unrelated nodes.

A companion PR to Helium314/aosp-dictionaries adds the v203 encoding
support to dicttool_aosp.jar (-203 flag) and a runtime-check to fail loud
instead of silent truncation in v202 mode.

## Backward compatibility

* Old HeliBoard + v202 dict: works as before.
* Old HeliBoard + v203 dict: format_utils returns UNKNOWN_VERSION, dict
  refuses to load (safe — no krzaki, just falls back to bundled).
* New HeliBoard + v202 dict: works as before. Sentinel check is dead code
  for v202 because v202 encoder never produced 0xFFFFFF (assertion).
* New HeliBoard + v203 dict: full read with extended addresses.

## Tests

Manual integration: built APK with patched runtime, sideloaded a 20.7 MB
v203 Polish dict (3.77M form built from Hunspell pl_PL via patched
dicttool), verified spell-check and suggestions work without krzaki.

## Files

- app/src/main/jni/src/dictionary/utils/format_utils.{h,cpp}
- app/src/main/jni/src/dictionary/structure/pt_common/patricia_trie_reading_utils.cpp
- app/src/main/jni/src/dictionary/structure/pt_common/bigram/bigram_list_read_write_utils.cpp
- app/src/main/java/helium314/keyboard/latin/makedict/FormatSpec.java
```

## Pre-PR cleanup needed (currently open in fork)

* Add native unit test in `app/src/main/jni/tests/dictionary/structure/` that exercises a small synthetic v203 dict with a sentinel-extended address, verify decoded position == intended.
* Add Java unit test mirroring same.
* Add integration test that round-trips: compile small v203 wordlist via dicttool → load via runtime → assert content match.

## Steps to file

1. `gh repo fork Helium314/HeliBoard --remote=upstream`
2. Cherry-pick our 4 commits from `nopopup` branch (`05af5e0` runtime patch + later) onto branch `v203-format`.
3. Rebase off `master`.
4. Strip nopopup-specific changes (label rename, applicationId, spell-checker hack, abi filters, build.gradle.kts sign config) — keep only v203 format support.
5. `gh pr create -R Helium314/HeliBoard -B master -H d33mobile:v203-format`.

Estimated PR scope after cleanup: ~31 LOC across 5 files.

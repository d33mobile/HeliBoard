# dicttool VERSION_203 — progress tracker

Update each iteration. Commit + push każde uderzenie. Plan w `dicttool-expansion.md`.

## Working dir
`/home/user/ai/heliboard` (branch `nopopup` na fork `d33mobile/HeliBoard`).
Build artifacts: `/tmp/pldict/`.
Decompiled encoder: `/tmp/dec/`.

## Faza 0 — fork i lokalna walidacja
- [x] Recon: encoder + decoder code mapped (zob. plan §5,6)
- [x] Repro bugu z `-ea` na `main_pl_v2.combined`
- [x] Pobrać AOSP dicttool source (`/tmp/aosp-dicttool/` z `android.googlesource.com/platform/packages/inputmethods/LatinIME`)
- [x] Postawić build pipeline dla dicttool jar — ręczny javac, 85 src files, jar 186 KB (oryg 238 KB ale różnica to junit deps bundled)
- [x] Powtórzyć repro własnym buildem — byte-identyczny output dla test.combined → test.dict

## Faza 1 — encoder patch
- [x] `BinaryDictEncoderUtils.getByteSize`: dodać warunek extended (>0xFFFFFE → 7) + new overload z formatVersion
- [x] `BinaryDictEncoderUtils.writeUIntToBuffer/Stream/DictBuffer`: case 7 (3 sentinel + 4 BE)
- [x] `BinaryDictEncoderUtils.writeChildrenPosition`: case 7 + new overload z formatVersion
- [x] `BinaryDictEncoderUtils.makePtNodeFlags`: case 7 (flags = THREEBYTES, sentinel ukryty)
- [x] `BinaryDictEncoderUtils.makeBigramFlags`: case 7 = THREEBYTES
- [x] `BinaryDictEncoderUtils.getPtNodeMaximumSize` + `calculatePtNodeArrayMaximumSize`: użyć PTNODE_MAX_ADDRESS_SIZE_V203 dla v203 (overload added)
- [ ] `BinaryDictEncoderUtils.computeAddresses`: bumping `MAX_PASSES` — nie potrzeba, 24 wystarcza dla 3.7M wordlist
- [x] `FormatSpec.VERSION203 = 203` + PTNODE_MAX_ADDRESS_SIZE_V203 + ATTRIBUTE_MAX_ADDRESS_SIZE_V203
- [x] `DictionaryMaker.java` (CLI): flag `-203` mapuje na `FormatSpec.VERSION203`
- [x] `Ver2DictEncoder.java`: accept VERSION202 i VERSION203, store mFormatVersion field, pass do all writeChildrenPosition/makePtNodeFlags/makeBigramFlags call sites
- [x] Threading formatVersion przez `computeAddresses` → `computeActualPtNodeArraySize` → `getByteSize` (overloady)
- [ ] Unit tests dla nowego format — pominę, manual repro wystarcza dla teraz
- [x] Build patched dicttool jar (`/tmp/aosp-dicttool/build/dicttool_aosp_v203.jar`, 186 KB)
- [x] Run repro: 3.77M wordlist → v203 dict → SUCCESS (20.7 MB, header `00 CB`)
- [x] Run regression: same wordlist → v202 (default) → HARD FAIL z RuntimeException (zamiast cichego truncate). Małe `test.combined` v202 nadal byte-identical do upstream output.
- [ ] Sanity check: zero bajtów-śmieci w trie (test funkcjonalny po decoder patchu, w fazie 2)

## Faza 2 — decoder patch
- [ ] Native: `format_utils.h` + `format_utils.cpp` add VERSION_203
- [ ] Native: `patricia_trie_reading_utils.cpp` add sentinel handling w `readChildrenPositionAndAdvancePosition`
- [ ] Native: bigram path patch w `patricia_trie_policy.cpp` (jeśli potrzeba)
- [ ] Java: `FormatSpec.java` add VERSION203
- [ ] Java: `BinaryDictionaryUtils.java` whitelist bumping
- [ ] Native unit tests
- [ ] Build APK z patchem
- [ ] Manual integration test na phone (po deploy):
  - [ ] Stary v202 dict dalej działa (regression)
  - [ ] Nowy v203 dict załadowany, brak krzaków przy `z`
  - [ ] `robiłem` nie czerwony

## Faza 3 — wykorzystanie i upstream
- [ ] Regenerować `main_pl_hunspell.dict` w v203, wgrać na F-Droid repo
- [ ] Bump versionCode HeliBoarda nopop, opublikować v3.9-nopopup7+ (z runtime patchem)
- [ ] PR do `Helium314/HeliBoard` z decoder support
- [ ] Issue/PR do `Helium314/aosp-dictionaries` z patched dicttool
- [ ] Zregenerować `main_be.dict` (3.97M form, w stable!) jeśli też cierpi

## Notatki

### Iteracje
- 2026-05-10 ~13:30 — plan napisany, progress tracker zainicjowany
- 2026-05-10 ~13:35 — clone AOSP LatinIME source (`/tmp/aosp-dicttool/`). Encoder source: `tests/src/com/android/inputmethod/latin/makedict/BinaryDictEncoderUtils.java` (37 java files w dicttool, encoder w tests/ bo separated od runtime). FormatSpec w `java/src/com/android/inputmethod/latin/makedict/`. Build: Android.bp jest soong-only, do lokalnego buildu trzeba ręczne `javac` lub Gradle, do zrobienia w nast. iteracji.
- 2026-05-10 ~13:53 — build pipeline up. Used `javac` direct, deps z gradle-cached jars (jsr305, junit-4.13.2). `/tmp/aosp-dicttool/build/dicttool_aosp_local.jar` (186 KB) działa identycznie jak oryginalny `dicttool_aosp.jar` (238 KB), output dla `test.combined` byte-identyczny (`diff /tmp/test_local.dict /tmp/pldict/test.dict` = empty). Faza 0 zakończona.
- 2026-05-10 ~14:00 — Faza 1 patch w toku. Zaedytowane `/tmp/aosp-dicttool/`: FormatSpec.java (VERSION203 = 203, PTNODE_MAX_ADDRESS_SIZE_V203 = 7, PTNODE_ATTRIBUTE_MAX_ADDRESS_SIZE_V203 = 7), BinaryDictEncoderUtils.java (getByteSize z formatVersion overload, writeUIntToBuffer/Stream case 7, writeChildrenPosition case 7, makePtNodeFlags case 7 = THREEBYTES, makeBigramFlags case 7 = THREEBYTES). Zostaje: getPtNodeMaximumSize parametryzacja, computeAddresses MAX_PASSES check, Ver2DictEncoder version, Makedict.java -203 flag, build + test.
- 2026-05-10 ~14:05 — research prior art przed inwestycją: nikt nie zrobił. AOSP nie ruszał format od 2014 (ostatnia commit lut 2025 = test infra cleanup). HeliBoard issues: #2476 to UI feature dla dict editor, nie ma issue o 16MB / krzakach. Codeberg aosp-dictionaries 27 issues wszystkie to language requests. Github code search "VERSION203 dict" = 0 trafień związanych. Forki aosp-dictionaries (10+) tylko dodają języki. Czyste pole, własna implementacja jedyną drogą.
- 2026-05-10 ~14:11 — **Faza 1 zamknięta**. Patched dicttool jar `/tmp/aosp-dicttool/build/dicttool_aosp_v203.jar` (186 KB) zbudowany. Eksperymentalna weryfikacja: pl 3.77M form → v203 → 20.7 MB plik z header `00 CB` (203). Same wordlist → v202 (default) → `RuntimeException("address X >= 16 MB cannot be encoded in VERSION202; use VERSION203 (-203 flag)")` zamiast silent corruption. Mały test.combined v202 nadal byte-identical do upstream. Threading version przez `Ver2DictEncoder.mFormatVersion` field + nowe overloady w `BinaryDictEncoderUtils`. Edycje commited do `/tmp/aosp-dicttool/` (nie do tego repo, źródła AOSP są poza repo nopop).

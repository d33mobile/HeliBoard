# dicttool VERSION_203 — progress tracker

Update each iteration. Commit + push każde uderzenie. Plan w `dicttool-expansion.md`.

## Working dir
`/home/user/ai/heliboard` (branch `nopopup` na fork `d33mobile/HeliBoard`).
Build artifacts: `/tmp/pldict/`.
Decompiled encoder: `/tmp/dec/`.

## Faza 0 — fork i lokalna walidacja
- [x] Recon: encoder + decoder code mapped (zob. plan §5,6)
- [x] Repro bugu z `-ea` na `main_pl_v2.combined`
- [ ] Pobrać AOSP dicttool source (lub użyć decompile)
- [ ] Postawić build pipeline dla dicttool jar (ant/gradle)
- [ ] Powtórzyć repro własnym buildem (sanity check że build infra działa)

## Faza 1 — encoder patch
- [ ] `BinaryDictEncoderUtils.getByteSize`: dodać warunek extended (>0xFFFFFE → 7)
- [ ] `BinaryDictEncoderUtils.writeUIntToBuffer/Stream/DictBuffer`: case 7
- [ ] `BinaryDictEncoderUtils.writeChildrenPosition`: case 7
- [ ] `BinaryDictEncoderUtils.makePtNodeFlags`: case 7 (flags = THREEBYTES, sentinel ukryty)
- [ ] `BinaryDictEncoderUtils.makeBigramFlags`: case 7
- [ ] `BinaryDictEncoderUtils.computeAddresses`: bumping `MAX_PASSES` jeśli potrzeba
- [ ] `FormatSpec.VERSION203 = 203`
- [ ] `Makedict.java`: flag `-203`
- [ ] `Ver2DictEncoder.java`: parametryzacja wersji header
- [ ] Unit tests dla nowego format
- [ ] Build patched dicttool jar
- [ ] Run repro: 3.77M wordlist → v203 dict → success
- [ ] Sanity check: zero bajtów-śmieci w trie

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

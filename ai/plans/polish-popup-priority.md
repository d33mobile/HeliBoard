# Polish layout — diacritics lose long-press priority

## Goal (z user message 2026-05-24)
> napraw mi polski layout. znaki diakrytyczne niech stracą priorytet — long press ma faworyzować cyfry i znaki interpunkcyjne. jeśli będę chciał ogonki, mogę dać swipe

Diakrytyki polskie (`ą`, `ę`, `ó`, `ś`, `ń`, `ć`, `ż`, `ź`, `ł`) NIE mają być primary popup (hint) na long-press literowych klawiszy. Powinny być cyfry / interpunkcja. Diakrytyki dalej dostępne (gdzieś dalej w popup menu).

## Approach (user feedback 2026-05-24 "ogarnij najpierw jakieś testy")

**Najpierw diagnoza przez testy — co aktualnie jest pod którym klawiszem.** Bez tego strzelałbym w ciemno.

### Faza 1 — diagnostic test (PRZED fixem)
- [ ] Dodać test w `app/src/test/.../KeyboardParserTest.kt` (lub nowy plik) który buduje polish qwerty alphabet keyboard przez `buildKeyboard()` helper
- [ ] Test drukuje dla każdego klawisza literowego: `label | hint label | popup keys (in order)` — wszystkie 3 rzędy
- [ ] Run: `./gradlew :app:testReleaseUnitTest --tests "*KeyboardParserTest*polish*"` (lub assemble + manual run)
- [ ] Zapisać output jako baseline w `ai/plans/polish-popup-baseline.txt`

### Faza 2 — analiza baseline
- [ ] Sprawdzić: czy hint na `a` w polish to faktycznie `ą` (lub jakiś diacritic)?
- [ ] Sprawdzić jakie popup keys są na każdym kluczu (kolejność)
- [ ] Zdecydować root cause:
  - (A) `pl.txt` daje diakrytyki w `language` group + symbols/number nie aktywne dla non-top-row → `addSymbolPopupKeys` faktycznie powinno dać symbol jako hint, ale może `language` jest wcześniej w order
  - (B) `POPUP_KEYS_ORDER_DEFAULT` w `PopupKeysUtils.kt` ma niewłaściwy default
  - (C) Coś w forku nopopup zmieniło logikę

### Faza 3 — fix
Możliwe podejścia (do wyboru po diagnozie):
- **A) Zmienić `Defaults.PREF_POPUP_KEYS_ORDER`** — wyłączyć `language` group lub przesunąć na ostatnią pozycję
  - Plus: zmiana globalna, czysty config
  - Minus: dotyka wszystkich języków (de/fr też tracą umlauty/accents jako hint)
- **B) Zmodyfikować `pl.txt`** — usunąć diakrytyki w ogóle (lub przenieść do osobnej grupy)
  - Plus: targeted, tylko polski
  - Minus: jak user dostanie diakrytyki? Tylko przez glide typing + autocorrect?
- **C) Stworzyć custom `polish.txt` layout** z explicit popup keys (cyfra+punkt na każdej literze) + register w method.xml
  - Plus: targeted, daje pełną kontrolę
  - Minus: więcej kodu, user musi wybrać layout
- **D) Hybrid:** zmienić `pl.txt` aby diakrytyki były w pozycji 5+ w `language` group (po wszystkim innym) — nie wystarczy bo group level decyduje

Likely pick: **A modyfikowana** — zmienić `POPUP_KEYS_ORDER_DEFAULT` tak, żeby `language` było default `false`, ALE TYLKO dla polskiego (per-locale override jeśli HeliBoard wspiera) lub jako globalna default zmiana w forku nopopup.

Albo **B+swipe**: usunąć diakrytyki z pl.txt, polegać na glide typing + suggestions z dict v203 (który ma wszystkie formy). User wiedział o glide → "swipe" w jego wiadomości to glide.

### Faza 4 — regression test
- [ ] Po fixie: test asercjuje że `a` ma hint NIE-diacritic + diacritic dalej dostępny w popup keys (jeśli zostawiamy go w popup) lub że hint = cyfra/symbol
- [ ] Test musi failować na main bez patcha (regression-first per global CLAUDE.md)

### Faza 5 — build + push
- [ ] Bump versionCode 3901017 → 3901018 (nopopup18)
- [ ] `./gradlew :app:assembleRelease` (jeśli OOM przy mergeDex — retry, znany pattern)
- [ ] Skopiować APK do `/mnt/HC_Volume_103952790/heliboard-fork/publish/heliboard-nopopup-fdroid/repo/`
- [ ] `finalize.sh` (uwaga: dotyka tylko `repo/`, nie `dicts/`)
- [ ] git push w fork repo

## Konfiguracja techniczna

**Klucz w `app/src/main/java/helium314/keyboard/latin/utils/PopupKeysUtils.kt`:**
```kotlin
const val POPUP_KEYS_ORDER_DEFAULT =
    language_priority+true + number+true + symbols+true + layout+true + language+true
```
Każdy entry: `<group>=<enabled>`, separator `;`.

**`pl.txt` format** (`app/src/main/assets/locale_key_texts/pl.txt`):
```
[popup_keys]
a ą
e ę
...
```
Bez `%` → wszystko w group `language`. Z `%` → przed `%` jest `language_priority`, po `%` `language`.

**Symbols layout** (`app/src/main/assets/layouts/symbols/symbols.txt`) → automatically maps position-to-position do `popup.symbol` na alphabet keys via `addSymbolPopupKeys` w `KeyboardParser.kt:292`.

**Number assignment** (`KeyboardParser.kt:288`) → tylko top row literowych klawiszy dostaje `numberLabel` (q→1, w→2, ..., p→0). Drugi/trzeci rząd nie ma cyfr.

## Open questions
- Co user dokładnie ma na myśli przez "swipe"? Glide typing? Sliding key input? Pomiń pytanie, zgaduj że glide.
- Czy zmiana ma być globalna dla forku nopopup (wszystkie języki) czy tylko polski?
- Likely answer: zmiana per-locale jeśli HeliBoard wspiera, lub globalna jeśli nie wspiera. Sprawdzić `PREF_POPUP_KEYS_ORDER + "_" + locale`.

## Notes / iteracje
- 2026-05-24 18:50 — plan napisany. CWD `/mnt/HC_Volume_103952790/relocated/ai/heliboard`, branch `nopopup`.
- 2026-05-24 19:20 — **diagnoza empiryczna**: `LocaleKeyboardInfos.kt:51` ładuje primary locale (`pl.txt`) zawsze z `priority=true` → **wszystkie** polskie diakrytyki idą do `priorityPopupKeys` map (group `language_priority`). Default `POPUP_KEYS_ORDER_DEFAULT` ma `language_priority` PIERWSZE → diakrytyki na początku popup keys. Hint label OK (osobny `POPUP_KEYS_LABEL_DEFAULT` z `language_priority:false`), ale popup keys list ma diakrytyk pod palcem.
- 2026-05-24 19:25 — `%` marker z dokumentacji `layouts.md` NIE jest implementowany w `readStream`/`addPopupKeys`. Dead doc.
- 2026-05-24 19:30 — fix wybrany: **D** (zmiana global default `POPUP_KEYS_ORDER_DEFAULT` w `PopupKeysUtils.kt`) — przesunięcie `language_priority` na ostatnią pozycję. Nie zmienia hint label (osobny setting). Dla niemca/francuza: popup keys order się zmienia (diakrytyki na końcu zamiast początku), ale hint dalej OK. User polski → korzysta. Niemiecki w forku nopopup też dostaje to samo — można argumentować że to fix dla wszystkich Latin scripts.
- 2026-05-24 19:35 — **fix verified** przez `polish qwerty — diacritics last in popup, not first` test:
  - `a`: `[ą, @, à, …]` → `[@, à, …, ą]`
  - `e`: `[ę, 3, |, é, …]` → `[3, |, é, …, ę]`
  - `n`: `[ń, !, ñ]` → `[!, ñ, ń]`
  - `l`: `[ł, )]` → `[), ł]`
  - `z`: `[ż, ź, *]` → `[*, ż, ź]`
- 2026-05-24 19:40 — bump versionCode 3901017 → 3901018, ready dla buildu.

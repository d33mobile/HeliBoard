# Plan: rozszerzenie formatu HeliBoard dict do >16 MB (VERSION 203)

Status: research zrobiony, plan szczegółowy, **żadna linia kodu jeszcze nie zmieniona**.

## 1. Problem

Statyczny binary dict format `VERSION_202` (używany przez `HeliBoard` + AOSP `dicttool_aosp.jar`) ma children-address w PtNode encodowany na **maks. 3 bajty** = 16 777 215 (≈16 MiB). Gdy łączny rozmiar trie przekracza 16 MiB i dicttool wygeneruje long-distance link, pisze tylko dolne 24 bity adresu — wyższe bajty milcząco gubione. Runtime HeliBoard ląduje wskaźnikiem dziecka kilka megabajtów obok celu, interpretuje śmieć bajtowy jako multi-char node, dekoder UTF-8 dorabia surrogate'y i SPUA → użytkownik dostaje sugestie typu `Ä񄁣�i`.

### Diagnoza w kodzie

Plik: `dicttool_aosp.jar → com/android/inputmethod/latin/makedict/BinaryDictEncoderUtils.class` (decompile w `/tmp/dec/BinaryDictEncoderUtils.java`).

```java
static int getByteSize(final int address) {
    assert address <= 16777215;     // (1) no-op bez -ea, brak runtime checku
    if (!BinaryDictIOUtils.hasChildrenAddress(address)) return 0;
    if (Math.abs(address) <= 255) return 1;
    if (Math.abs(address) <= 65535) return 2;
    return 3;                       // (2) zwraca 3 ale dla addr > 16MB to za mało
}

static int writeUIntToBuffer(byte[] buf, int from, int value, int size) {
    switch (size) {
        case 4: buf[i++] = (byte)(value >> 24);   // unreachable bo getByteSize nigdy nie zwraca 4
        case 3: buf[i++] = (byte)(value >> 16);   // (3) wysokie bity > 24 trafiają do śmietnika
        case 2: buf[i++] = (byte)(value >> 8);
        case 1: buf[i++] = (byte)(value);
    }
}
```

Reprodukcja eksperymentalna (ścieżka: `/tmp/pldict/`, `dicttool_aosp.jar` z `https://codeberg.org/Helium314/aosp-dictionaries`):

```
java -ea -jar dicttool_aosp.jar makedict -s wordlist.combined -d out.dict
```

| Wordlistów (linii combined) | Rozmiar .dict | Z `-ea` | Bez `-ea` |
|---|---|---|---|
| 1.5M | 7.75 MB | ✓ ok | ✓ ok |
| 2.0M | 10.37 MB | ✓ ok | ✓ ok |
| 2.4M | (krzaczy) | `AssertionError` | "ok" + krzaki w runtime |
| 3.7M | 20.7 MB | `AssertionError` | "ok" + krzaki w runtime |

Próg deterministyczny: ~10 MB pliku binarnego dla typowego polskiego korpusu z bigramami/sufiksami.

Ten sam mechanizm produkuje 7 znanych "frankenstein" wpisów w upstream'owym `https://codeberg.org/Helium314/aosp-dictionaries/raw/branch/main/dictionaries_experimental/main_pl.dict` (date=1721723726, 21.7 MB, 5M form). Dump'y w `/tmp/pldict/dump.out`.

## 2. Constraints, których nie można złamać

* **Backward compat reading**: HeliBoard z patchem MUSI dalej czytać istniejące `.dict` v202 bez krzaków (cały APK shipuje 18 takich w `app/src/main/assets/dicts/`).
* **Forward compat reading**: stary HeliBoard wczytujący nowy `.dict` v203 powinien **odmówić** (header version check) zamiast czytać śmietnik.
* **dicttool back compat**: `dicttool_aosp.jar` musi nadal generować v202 dla małych dictów (default), v203 tylko gdy wymagane lub flagą.
* **Native + Java sync**: stałe formatu są zduplikowane w Java (`FormatSpec.java`) i C++ (`format_utils.h`). MUSZĄ pozostać zsynchronizowane.

## 3. Wybór wariantu rozwiązania

Trzy rozważone:

### A) Quick fail-fast (no-format-change)
Zmienić `assert` w `getByteSize` na `throw new RuntimeException(...)` — dicttool głośno fail, użytkownik wie że dict za duży, szuka workaround (split wordlistu).

**Plus**: kilka linii kodu, brak wpływu na format, działa z istniejącymi HeliBoardami.
**Minus**: nie naprawia problemu — polski korpus 5M form dalej nie da się skompilować w jednym dict.

### B) Sentinel-based extension w v202 (no-version-bump)
W v202 wartość 3-byte address `0xFFFFFF` reservowana jako sentinel "extended" — czytać następne 4 bajty jako pełny 32-bit address. Stare dicty nigdy nie generowały 0xFFFFFF (assert by się rozwalał), więc decoder z patchem bezpiecznie ignoruje sentinel w starych plikach.

**Plus**: brak nowej wersji formatu, decoder z patchem czyta i stare i nowe dicty.
**Minus**: ukryta zmiana semantyki. Stary HeliBoard czytający nowy dict z sentinelem dostaje śmieci (interpretuje 0xFFFFFF jako legitymny address ~16 MB → krzak). Magic version w header'ze nie zmienia się, więc stare HeliBoard "zaakceptuje" plik.

### C) **VERSION_203 z explicit 4-byte address mode** ← REKOMENDOWANY

Nowa wersja formatu w header (2-byte field after magic). Stary HeliBoard widzi nieznaną wersję i odmawia (już to robi w `format_utils.cpp::getFormatVersion` → `UNKNOWN_VERSION`). Nowy HeliBoard czyta oba.

Encoding: ten sam sentinel `0xFFFFFF` w 3-byte address, ale formalnie zaszyty w specyfikację v203, dokumentowany. Stare v202 dicty wyglądają identycznie (i są czytane przez to samo path w decoderze, bo różnica jest tylko w kodzie który rozumie sentinel).

Wybór C bo:
* Jawna semantyka, łatwiej zaPRować upstream.
* Bezpieczne dla starych HeliBoardów — magic version chroni przed czytaniem inkompatybilnego pliku.
* Decoder change w runtime jest mały (jeden if w `readChildrenPositionAndAdvancePosition`).
* Encoder change w dicttool też mały (sentinel + 4-byte tail).

## 4. Format spec — VERSION_203

Identyczny z VERSION_202 z dwiema zmianami:

### 4.1 Header
* `version` field (offset 4, 2 bytes BE) = `0x00CB` (= 203)
* `description` (text key w body header) bez zmian — opisuje dict.
* Opcjonalny **nowy klucz** w body header: `largeAddressing=1` — flaga informacyjna, że dict używa sentinel-extension. Decoder może od niej zależnie sprawdzać sentinel albo pominąć (mikro-optymalizacja).

### 4.2 Children address encoding
Children address w PtNode pozostaje pole o variable size 0/1/2/3 bajtów wskazane przez 2 wysokie bity flag (bez zmian). DODATKOWO:

```
gdy CHILDREN_ADDRESS_TYPE == THREEBYTES (0xC0):
    raw3 = readUint24(buf, pos); pos += 3
    if (raw3 == 0xFFFFFF):
        # sentinel: extended 4-byte address follows
        offset = readUint32(buf, pos); pos += 4
    else:
        offset = raw3
    childPos = base + offset
```

Czyli max 7 bajtów na children address (3 sentinel + 4 extended). Adresowalna przestrzeń = 4 GiB (32-bit unsigned).

### 4.3 Bigram address encoding
Bigram offset w `bigram address list` ma analogiczny problem. Aktualnie 1/2/3 bajty wskazane przez `MASK_BIGRAM_ATTR_ADDRESS_TYPE = 0x30` w bigram flags byte.

Dla v203 ten sam pattern: gdy 3-byte bigram offset = `0xFFFFFF`, czytaj kolejne 4 bajty jako extended.

Plus addressSign (`FLAG_BIGRAM_ATTR_OFFSET_NEGATIVE = 0x40`) stosuje się do extended offsetu tak samo jak do regularnego — daje range -4 GiB..+4 GiB.

### 4.4 Co NIE wymaga zmiany w v203
* Char encoding (1 lub 3 bajty) — bez zmian.
* PtNode count (1 lub 2 bajty) — max 32k nodes per array, wystarczy.
* Shortcut block size (2 bajty) — max 64KB shortcut content per node, wystarczy.
* Frequency (1 bajt) — bez zmian.
* Magic number — bez zmian (`0x9BC13AFE`).
* Header text format (key-value via `\x1f`) — bez zmian.

## 5. Zmiany w encoderze (dicttool)

Encoder żyje w `dicttool_aosp.jar`, source w upstream AOSP `packages/inputmethods/LatinIME/tools/dicttool/`. Ja mam jar i decompile (procyon) w `/tmp/dec/`. Modyfikujemy z dwóch stron:

### 5.1 Pliki do zmiany w dicttool (Java)

| Plik | Co zmienić |
|---|---|
| `BinaryDictEncoderUtils.java` | `getByteSize`: dodać warunek `if (address > 0xFFFFFE) return 7`. Usunąć stary assert lub zostawić jako `assert address <= 0xFFFFFFFFL`. |
| `BinaryDictEncoderUtils.java` | `writeUIntToBuffer/Stream/DictBuffer`: dodać case `case 7` — najpierw 3 bajty `0xFF`, potem 4 bajty BE z value. |
| `BinaryDictEncoderUtils.java` | `writeChildrenPosition`: dodać case `case 7`. |
| `BinaryDictEncoderUtils.java` | `makePtNodeFlags(... childrenAddressSize ...)`: case `7` → flagi takie jak dla `3` (`0xC0` THREEBYTES) — sentinel jest ukryty wewnątrz 3-byte field. |
| `BinaryDictEncoderUtils.java` | `makeBigramFlags`: dodać case `7` analogicznie, `0x30` THREEBYTES + extended. |
| `BinaryDictEncoderUtils.java` | `computeAddresses`: limit `MAX_PASSES = 24` może wymagać podniesienia jeśli iterative shrink dla większych dictów się nie zbieżności. Zwiększyć do 48 i monitorować. |
| `FormatSpec.java` | Dodać `VERSION203 = 203`. Zmienić `MAXIMUM_SUPPORTED_STATIC_VERSION = VERSION203`. |
| `Makedict.java` (CLI dla `makedict` w dicttool) | Dodać flagę `-203` (jak istniejące `-2`, `-3`, `-4`) wybierającą format wyjściowy. Default zostaje `-2` (= v202). |
| `Ver2DictEncoder.java` | Sprawdzić czy nie hardcoduje wersji header — jeśli tak, parametryzować wg `FormatOptions.mVersion`. |
| `BinaryDictIOUtils.java` | `hasChildrenAddress` chyba bez zmian (sprawdza tylko `!= 0`). Zweryfikować podczas pisania kodu. |

### 5.2 Iterative compression edge case

`computeAddresses` ma do 24 passes. Każdy pass próbuje zmniejszyć adresy (1B/2B/3B) i potem shifts wszystkie pozycje. Z extended (3+4=7 bytes) dochodzi nowy wymiar — adres może rosnąć z 3B na 7B gdy odkryjemy że trzeba sentinel. To może pogorszyć konwergencję.

**Sanity check**: napisać assertion w `computeActualPtNodeArraySize`: jeśli `getByteSize` dla danego node zwiększyła się między passes, log'ować i kontynuować. Jeśli oscyluje — fail loud po 48 passes.

### 5.3 Test approach dla encodera

W `dicttool_aosp.jar` source są tests (`Ver2DictEncoderTests`, `BinaryDictDecoderEncoderTests`). Nowe casy:

* Test 1: zbuduj wordlist 3M form, kompiluj v203, sprawdź `getByteSize` zwraca 7 dla największych adresów.
* Test 2: zbuduj wordlist 3M form, kompiluj v203, sprawdź czy bajt na pozycji 16777215+ ma sensowny PtNode flag (nie binary śmieć).
* Test 3: kompiluj ten sam wordlist v202 vs v203, dla v202 expect `RuntimeException` (po dodaniu hard fail), dla v203 expect success.
* Test 4: round-trip — wordlist → v203 dict → dump → wordlist. Compare original vs dumped, expect set-equality.

## 6. Zmiany w decoderze (HeliBoard)

### 6.1 Native (C++)

| Plik | Co zmienić |
|---|---|
| `app/src/main/jni/src/dictionary/utils/format_utils.h` | Dodać `VERSION_203 = 203` do enum `FORMAT_VERSION`. |
| `app/src/main/jni/src/dictionary/utils/format_utils.cpp` | W `getFormatVersion(int)` dodać case `VERSION_203 → VERSION_203`. |
| `app/src/main/jni/src/dictionary/structure/pt_common/patricia_trie_reading_utils.cpp` | `readChildrenPositionAndAdvancePosition`: dla `THREEBYTES` przeczytać u24, sprawdzić sentinel `0xFFFFFF`, jeśli tak — czytać dodatkowe 4 bajty. Pamiętać że `*pos` musi być przesunięte o 7. |
| `app/src/main/jni/src/dictionary/structure/v2/patricia_trie_policy.cpp` | (jeśli decoder dla v202 jest reused dla v203) — sprawdzić że ścieżki bigram są też patched, lub utworzyć osobny `Ver203PatriciaTriePolicy`. |
| `app/src/main/jni/src/dictionary/structure/v2/ver2_pt_node_array_reader.cpp` | Forward link semantics niezmienione. |
| `app/src/main/jni/src/dictionary/structure/pt_common/patricia_trie_reading_utils.h` | Header dla nowych funkcji (jeśli wprowadzamy `readExtendedAddress`). |
| `app/src/main/jni/src/dictionary/utils/byte_array_utils.h` | `readUint32AndAdvancePosition` już istnieje (linia 80). NIC nie trzeba dodawać. |

Drobny risk: `Ver2PatriciaTriePolicy` używa lookup tables które mogą cache'ować pozycje children. Cache należy przejrzeć — jeśli przechowuje `childPos` jako int, OK (int = 32-bit, mieści 4GB). Jeśli przechowuje jako `int_least24_t` lub podobne wąskie pole — zwiększyć.

### 6.2 Java

| Plik | Co zmienić |
|---|---|
| `app/src/main/java/helium314/keyboard/latin/makedict/FormatSpec.java` | Dodać `VERSION203 = 203`. Zmienić `MAXIMUM_SUPPORTED_STATIC_VERSION = VERSION203`. |
| `app/src/main/java/helium314/keyboard/latin/makedict/DictionaryHeader.kt` | Bez zmian — czyta tylko text key=value pairs z header body. |
| `app/src/main/java/com/android/inputmethod/latin/BinaryDictionary.java` | Wrapper na native. Zweryfikować że nie hardcoduje wersji w `loadDictionary`. |
| `app/src/main/java/helium314/keyboard/latin/utils/BinaryDictionaryUtils.java` | Sprawdzić — możliwe że `getHeader` waliduje wersję; rozszerzyć whitelist'ę. |

### 6.3 Tests

`app/src/main/jni/tests/dictionary/utils/format_utils_test.cpp` — istniejące testy dla format detection. Dodać:
* Test detect VERSION_203 z header bytes `00 CB`.
* Test odmowy dla unknown version (np. 999) — istniejący behavior, walidacja regression.

`app/src/main/jni/tests/dictionary/structure/pt_common/` — jeśli istnieją unit testy dla `readChildrenPositionAndAdvancePosition`, dodać:
* Czytanie 3-byte non-sentinel value → return base+offset.
* Czytanie 3-byte 0xFFFFFF + 4-byte → return base + extended_offset.
* Position advancement = 3 dla regular, = 7 dla sentinel.

## 7. Backward compatibility — szczegółowo

| Scenariusz | v202 dict | v203 dict |
|---|---|---|
| Stary HeliBoard (bez patcha) | ✓ czyta jak dotąd | ✗ `UNKNOWN_VERSION` → odmowa, dict nie ładuje się (silent na poziomie UI, fallback na bundled) |
| Nowy HeliBoard (z patchem) | ✓ czyta jak dotąd (sentinel check tanio kosztuje, nie aktywuje się gdy dict legitymny) | ✓ czyta z extended |
| Stary dicttool (bez patcha) | ✓ generuje | ✗ nie potrafi |
| Nowy dicttool (z patchem) | ✓ generuje gdy `-2` (default) | ✓ generuje gdy `-203` lub auto (gdy address > 16MB) |

**Auto-upgrade logika w dicttool**: jeśli `computeAddresses` napotka address > 16MB i format = v202 → `RuntimeException` z sugestią `--format=203`. Lub: domyślnie auto-bump do v203 jeśli potrzeba (mniej user-facing change).

## 8. Test plan dokładny

### 8.1 Encoder (dicttool)

Test rig: `/tmp/pldict/main_pl_v2.combined` (3.77M form, ~97 MB tekst, znany trigger bugu).

```
# 1. Build with patched dicttool, format v202 — expect HARD FAIL
java -jar dicttool_patched.jar makedict -2 -s main_pl_v2.combined -d /tmp/should-fail.dict
# Expected: RuntimeException "address X > 16MB, use -203"

# 2. Build same wordlist v203 — expect SUCCESS
java -jar dicttool_patched.jar makedict -203 -s main_pl_v2.combined -d /tmp/v203.dict
# Expected: file ~21 MB, header version=203

# 3. Decode v203 with patched Python decoder (zaktualizować /tmp/pldict/dump_dict.py)
python3 dump_dict.py /tmp/v203.dict | wc -l
# Expected: ~3.77M unikalnych słów, zero non-BMP/SPUA codepointów
```

### 8.2 Decoder (HeliBoard runtime)

Test integration: zbudować HeliBoard fork z patchem, deploy na telefon, wgrać v203 dict, otworzyć notatnik:

* Test 1: wpisać `z` → sugestie regularne polskie (`za`, `ze`, `zna`, `zostać`...). Zero krzaków.
* Test 2: wpisać `robiłem` → bez czerwonego podkreślenia (jest w dict).
* Test 3: wpisać `xyzqwerty` → czerwone (nie ma w dict). Popup z `Add to dictionary`.
* Test 4: wgrać stary v202 dict (np. bundlowany `main_pl.dict`) na ten sam HeliBoard → dalej działa (regression check backward compat).

### 8.3 Round-trip

```
# Original wordlist (3.77M form)
md5sum /tmp/pldict/main_pl_v2.combined  # baseline

# Compile to v203
java -jar dicttool_patched.jar makedict -203 -s main_pl_v2.combined -d v203.dict

# Decode back to wordlist via patched dump_dict.py
python3 dump_dict.py v203.dict | sort -u > roundtrip.txt
sort -u <(grep '^ word=' main_pl_v2.combined | sed 's/^ word=//;s/,f=.*//') > original.txt

# Diff
diff -u original.txt roundtrip.txt | head -20
# Expected: empty diff
```

## 9. Roadmap PR

### Faza 0 — fork i lokalna walidacja (1 dzień)
* Sklonować dicttool source: szukać w `https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/master/tools/dicttool/` lub mirror github (`https://github.com/aosp-mirror/platform_packages_inputmethods_LatinIME`).
* Zbudować jar lokalnie: `ant` lub `gradle` (sprawdzić w jego repo).
* Powtórzyć repro z `/tmp/pldict/main_pl_v2.combined`, potwierdzić że własny build daje ten sam bug.

### Faza 1 — encoder patch
* Apply changes z §5.1.
* Run encoder unit tests, dodać nowe.
* Build patched jar, replace `/tmp/pldict/dicttool_aosp.jar`.
* Powtórzyć build polskiego, expect success bez krzaków.

### Faza 2 — decoder patch
* Apply changes z §6.1, §6.2 w forku `d33mobile/HeliBoard` branch `nopopup-v203`.
* Recompile native lib via existing nopopup build pipeline (`./gradlew :app:assembleRelease`, ndkBuild handles ABI).
* Sideload APK, install v203 dict, manual testy z §8.2.

### Faza 3 — upstream PRs
* PR do `Helium314/HeliBoard` z decoder support (patch §6).
* PR do `Helium314/aosp-dictionaries` (separate repo) z patched dicttool jar + skrypt regenerujący polski/inne duże dicty (białoruski 3.97M form już ma 4M+ entries — możliwe że też cierpi).
* Issue na AOSP gerrit (jeśli ktoś w ogóle tym żyje) — głównie żeby zalogować `assert` problem.

### Faza 4 — regenerate problem dicty
Lista do regeneracji w v203 (z `https://codeberg.org/Helium314/aosp-dictionaries` README, kandydaci ze >2M words):
* `main_be.dict` (Belarusian, 3,979,928 words) — w stable!
* `main_pl.dict` w `dictionaries_experimental` (znamy 7 frankensteinów)
* sprawdzić wszystkie inne >2M w README.

## 10. Otwarte pytania i ryzyka

* **MAX_PASSES=24 w iterative compression**: czy z extended addresses może oscylować? Jeśli tak → dodać monotonic check (size only grows lub only shrinks per pass), albo greedy assign.
* **Bigram offsets z `FLAG_BIGRAM_ATTR_OFFSET_NEGATIVE`**: extended bigram address musi obsługiwać sign bit. Aktualnie `addressSign` stosuje się do absolute value czytanego adresu — semantyka po extended pozostaje, sprawdzić explicit w testach.
* **Reading speed**: extended address dodaje conditional read na hot path. Dla małych dictów (większość) wykonuje się tylko sprawdzenie `if (raw3 == 0xFFFFFF)`, co kosztuje 1 branch. Acceptable.
* **Format compat z dynamic v403/v402**: te wersje używają `Ver4PtNodeArrayReader` z innym layoutem (forward links). Patch dotyczy tylko **statycznego** v202/v203 path. Dynamic v403 ma inny problem (różne kompresja adresów) — out of scope dla tego PR.
* **Code point table optimization (`MINIMUM_SUPPORTED_VERSION_OF_CODE_POINT_TABLE = VERSION201`)**: czy ten optimization współgra z extended addresses? Tak — codepoint table to osobne pole (1-byte char encoding lookup), niezależne od children pointers.

## 11. Stan ad hoc

Wszystkie pliki skanu/repro w `/tmp/pldict/`:
* `main_pl_v2.combined` — wordlist 3.77M form
* `main_pl_v2.dict` — current broken build
* `dicttool_aosp.jar` — original from Codeberg
* `dump_dict.py` — Python decoder (buggy w children traversal, ale wystarcza dla weryfikacji header + count + zero-krzaków check przez byte-scan)
* `/tmp/dec/BinaryDictEncoderUtils.java` — decompiled encoder
* `/tmp/dump.out` — dump experimental dict (5M entries + 7 frankensteins)
* `/tmp/clean.out` — dump my v2 (decoder buggy, ignore counts)

HeliBoard fork z patchem nopopup żyje w `https://github.com/d33mobile/HeliBoard` branch `nopopup`.
F-Droid repo z gotowymi dictami: `https://d33mobile.github.io/heliboard-nopopup-fdroid/dicts/`.

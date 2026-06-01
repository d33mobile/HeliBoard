# Emoji search false-positive on ':c da s'

## Bug (user 2026-06-01)
> zobacz jakie dostajesz sugestie kiedy spróbujesz napisać ":c da s". ja wtedy caly czas dostaje sugestie emoji mimo ze mam te sugestie wyłączone.

User types `:c da s` and still sees emoji suggestions even with "te sugestie wyłączone" — emoji suggestions turned off. Either:
- (a) inline emoji search activates even with PREF_INLINE_EMOJI_SEARCH=false, or
- (b) bail-out for `:c rozu`-style emoticon+space pattern doesn't survive a SECOND space (`:c da s` has two spaces), or
- (c) regular suggestion strip shows emoji (PREF_SUGGEST_EMOJIS path) and that pref isn't being honored, or
- (d) state from step `:c` (enters inline mode) doesn't get reset when subsequent space triggers bail-out — `updateInlineEmojiSearch` isn't called on that space.

Static analysis of `getInlineEmojiSearchString` in `InputLogic.java:2725-2766` says it SHOULD bail on `:c da s` — head before first space is `c`, single letter → `looksLikeAsciiEmoticonSuffix` returns true → method returns null. Existing unit test `inlineEmojiSearchString` already covers `:c rozu`-style cases. But user observes real-app bug → mismatch between static helper and runtime input flow. Most likely (d).

## Approach — per CLAUDE.md "regresja test najpierw"

1. **Repro:** add integration test in `InputLogicTest.kt` that drives `chainInput(":c da s")` step-by-step and asserts at end:
   - `latinIME.mInputLogic.mSuggestedWords` has no emoji results, OR
   - `isInlineEmojiSearchAction()` returns false (no inline search mode active), OR
   - emoji-state diagnostic indicates inline emoji search not active.

   Compare with same flow under `PREF_INLINE_EMOJI_SEARCH=false` to see if the toggle is honored at all.

2. **Sub-question:** which pref does user mean by "te sugestie wyłączone"? Test both — `PREF_INLINE_EMOJI_SEARCH=false` and `PREF_SUGGEST_EMOJIS=false`. If the bug only repros under one path, that narrows root cause.

3. **If repros:** identify divergence between static `getInlineEmojiSearchString` (returns null for `:c da s`) and runtime state (still in inline emoji mode). Likely culprit: `updateInlineEmojiSearch` not called after space, OR `setInlineEmojiSearchAction(false)` requires keyboard reload that doesn't happen.

4. **Fix:** likely add `updateInlineEmojiSearch` call right after any space input, OR honor the pref in `searchForEmojiInline`, OR short-circuit `mEmojiDictionaryFacilitator` based on pref.

5. **Re-run regression test:** must pass after fix.

6. **Self-review via foreground subagent:** spawn an agent to audit the change. If subagent flags issues, write follow-up plan in same file under "Iteracje" and continue loop.

7. **Build + push** (nopopup22 bump) to F-Droid when subagent audit is clean.

## Steps per loop tick (each iteration is a foreground subagent invocation)

The loop body should:
1. `cd /mnt/HC_Volume_103952790/relocated/ai/heliboard` and `git pull --rebase origin nopopup` (no-op if up to date).
2. Read this file (`ai/plans/emoji-search-multiword-bailout.md`) — find first `[ ]` checkbox item under "Tracker" and act on it.
3. Mark item `[x]` when done; append a one-line note under "Iteracje" with timestamp + result.
4. If all items done → spawn audit subagent — if audit says OK, build APK signed + run finalize.sh + commit log; if audit says NOT OK, append new items to Tracker.
5. Commit + push every iteration.

The harness `/loop` macro fires every 1 min in foreground subagent. Each tick is one self-contained iteration; no shared state outside this file + git.

## Tracker

- [x] Add integration test `inlineEmojiSearchSpaceBail` in `app/src/test/java/helium314/keyboard/latin/InputLogicTest.kt` that calls `chainInput(":c da s")` and checks emoji-search state. Test should ASSERT no-inline-emoji-search at end. Run via `./gradlew :app:testReleaseUnitTest --tests "*inlineEmojiSearchSpaceBail*"`.
- [x] Run the test on `main..nopopup` head. Record output (pass / fail / specific behavior) under "Iteracje". If passes → bug is elsewhere; add second test for `PREF_INLINE_EMOJI_SEARCH=false` honoring.
- [x] If test reproduces bug: trace why (read `updateInlineEmojiSearch` call sites; check whether space input triggers it).
- [ ] Patch: minimal change in `InputLogic.java` so that `:c da s` flow exits inline emoji search after the space. Keep upstream behavior for legitimate multi-word emoji search like `:fire truck`.
- [ ] Verify regression test passes after patch.
- [ ] Run full `./gradlew :app:testReleaseUnitTest --tests "*InputLogicTest*"` — no regressions in other tests.
- [ ] Spawn foreground audit subagent (general-purpose). Prompt: "Read commit HEAD (`git show HEAD`). Read this plan file. Audit fix: is it minimal? does the regression test demonstrably fail without the patch (revert + run)? are there missed scenarios (multi-emoticon `:c :D rozu`, leading space `\:c rozu`, full-width space)? Report PASS / FAIL with concrete reasoning."
- [ ] If audit FAIL: append findings to "Tracker" as new `[ ]` items, continue loop.
- [ ] If audit PASS: bump versionCode 3901021 → 3901022, versionName `3.9-nopopup22`, commit, build APK with `HELIBOARD_KEYSTORE=...`, verify signing, run `/mnt/HC_Volume_103952790/heliboard-fork/finalize.sh`, verify on remote by SHA. Then mark this whole plan DONE in "Iteracje".

## Iteracje

- 2026-06-01 ~05:10 — plan napisany. Recon: helper `getInlineEmojiSearchString` w `InputLogic.java:2725` ma już bail-out na `:c rozu` (commit 2247607); unit test `inlineEmojiSearchString` covers go. Mismatch między static (zwraca null dla `:c da s`) a runtime (user widzi emoji) → suspect (d) z above: runtime state nie odświeża się po space.
- 2026-06-01 ~05:15 — added e2e regression test `inlineEmojiSearchSpaceBail` in `InputLogicTest.kt`. Drives `chainInput(":c da s")` then calls `InputLogic.getInlineEmojiSearchString(connection.getTextBeforeCursor(50, 0))` and asserts null. PASSES on current HEAD, which means at the connection-text level the static helper does the right thing — so the runtime bug must be in how that helper's result is *applied* (the `setInlineEmojiSearchAction` / keyboard-reload path), not in what it computes. Next tick will run the test on a baseline (revert the `:c rozu` bail-out) to confirm it can demonstrably fail, and add a `PREF_INLINE_EMOJI_SEARCH=false` variant per Tracker item 2.
- 2026-06-01 ~09:10 — formally re-ran `*inlineEmojiSearchSpaceBail*` on HEAD: PASS (gradle `BUILD SUCCESSFUL`, no failed assertions). Confirms the static helper does the right thing for `:c da s` end-to-end via the connection text. Per Tracker instructions ("If passes → bug is elsewhere; add second test for `PREF_INLINE_EMOJI_SEARCH=false` honoring") added `inlineEmojiSearchPrefHonored` which toggles `PREF_INLINE_EMOJI_SEARCH` and asserts `Settings.getValues().mInlineEmojiSearch` flips in lock-step. Test PASSES too — so the pref *is* honored at the SettingsValues level. Conclusion so far: neither hypothesis (b) "static helper misses two-space pattern" nor (c) "pref not read" reproduces. Suspicion narrows to (d) — runtime state from an *earlier* `:c` (when the input WAS valid as inline emoji) doesn't get torn down when the space arrives, because `updateInlineEmojiSearch` may not be called on every space input. Next tick will instrument or trace: look at every `updateInlineEmojiSearch()` callsite and see whether space → that call happens.
- 2026-06-01 ~09:20 — static trace of `updateInlineEmojiSearch()` callsites in `InputLogic.java`. Only TWO callsites exist: `handleBackspaceEvent` line 1286, and `restartSuggestionsOnWordTouchedByCursor` line 1794. **Crucially: `handleSeparatorEvent` does NOT call it.** When the user types `:c`, `enterInlineEmojiSearchIfNeeded` flips `setInlineEmojiSearchAction(true)` which reloads the keyboard with `INLINE_EMOJI_SEARCH_DONE` action. When the next char is a space, `handleSeparatorEvent` runs: it calls `enterInlineEmojiSearchIfNeeded(' ')` at line 1219 but that's a no-op (guarded by `isInlineEmojiSearchAction()` returning true; the helper only *enters* the mode, never exits). The space is committed; `setRequiresUpdateSuggestions()` fires; `getSuggestedWords()` at line 2521 sees `isInlineEmojiSearchAction() == true` and routes to `searchForEmojiInline`. Inside `searchForEmojiInline`, `getInlineEmojiSearchString()` correctly returns null for `":c "` and emits an empty `SuggestedWords` — BUT the keyboard layout is still `INLINE_EMOJI_SEARCH_DONE` and every subsequent suggestion query keeps going through `searchForEmojiInline`. Also, `performUpdateSuggestionStripSync` line 1741-1744 falls back to `retrieveOlderSuggestions(typedWordInfo, mSuggestedWords)` when `suggestedWords.size() <= 1 && typedWordString.length() > 1`, which can resurrect stale emoji from the `:c` step on the second/third char of the next word. Both effects vanish if we just call `updateInlineEmojiSearch()` after committing the space. Next tick: patch `handleSeparatorEvent` to call `updateInlineEmojiSearch()` after the separator is committed, so that the keyboard layout and the routing match what the static helper says.

## Self-audit checklist (used by subagent)

- Does the regression test actually FAIL on `main..nopopup` HEAD before the patch?
- Is the test e2e (`chainInput`), not just calling the static helper?
- Does the patch survive related cases (`:c x`, `:c hi all`, `:fire truck`, `:c😀 rozu`)?
- Does the patch break any existing passing test in `InputLogicTest`?
- Does the patch respect `PREF_INLINE_EMOJI_SEARCH=false` (separately from the bail-out logic)?
- Commit message explains WHY (root cause), not just WHAT.

/*
 * Copyright (C) 2011 The Android Open Source Project
 * modified
 * SPDX-License-Identifier: Apache-2.0 AND GPL-3.0-only
 */
package helium314.keyboard.latin.common

import android.content.Context
import android.text.Spannable
import android.text.SpannableString
import android.text.Spanned
import android.text.style.SuggestionSpan
import helium314.keyboard.latin.SuggestedWords
import java.util.*

fun getTextWithAutoCorrectionIndicatorUnderline(context: Context?, text: String, locale: Locale?): CharSequence {
    if (text.isEmpty())
        return text
    val spannable: Spannable = SpannableString(text)
    val suggestionSpan = SuggestionSpan(context, locale, arrayOf(), SuggestionSpan.FLAG_AUTO_CORRECTION, null)
    spannable.setSpan(suggestionSpan, 0, text.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE or Spanned.SPAN_COMPOSING)
    return spannable
}

fun getTextWithSuggestionSpan(context: Context, pickedWord: String, suggestedWords: SuggestedWords, locale: Locale): CharSequence {
    // nopopup fork: don't attach the IME's autocomplete candidates as a
    // SuggestionSpan on committed text. Combined with the empty-array
    // SuggestionsInfo from AndroidWordLevelSpellCheckerSession, this leaves
    // the system long-press popup with no suggestion list, so it shows only
    // "Add to dictionary" / "Delete".
    return pickedWord
}

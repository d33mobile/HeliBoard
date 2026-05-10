# Polish corpus → frequency-weighted dictionary

The bundled `main_pl.dict` is built from Hunspell `pl_PL` unmunched, which
produces 3.77M morphological forms but **no frequency information** (every
word ends up at the same uniform `f=100`). With everything tied, the
suggestion engine has to break ties by spatial/edit-distance only, which
means rare forms outrank common ones as often as the other way around.

`merge_freq.py` rebalances this by overlaying real-world counts from three
free Polish corpora.

## Sources

| Corpus | Size | Register | Notes |
|--------|------|----------|-------|
| HermitDave/FrequencyWords (`pl_full.txt`, 2018) | 1.49M words | colloquial | Pre-counted from OpenSubtitles. |
| Leipzig `pol_news_2024_300K-words.txt` | 250k words | journalism | News scraped 2024. |
| Leipzig `pol_wikipedia_2021_300K-words.txt` | 365k words | encyclopedic | Polish Wikipedia 2021 dump. |

```
curl -L https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/pl/pl_full.txt -o pl_subs.txt
curl -L https://downloads.wortschatz-leipzig.de/corpora/pol_news_2024_300K.tar.gz | tar xz
curl -L https://downloads.wortschatz-leipzig.de/corpora/pol_wikipedia_2021_300K.tar.gz | tar xz
```

## Mapping rule

For each word in the existing combined wordlist:

* if seen in *any* corpus → log-mapped to `[60, 255]` based on its share of
  total tokens across all three sources (each corpus normalised to its own
  total before summing, so subs doesn't drown news+wiki by sheer volume);
* if not seen → assigned base `f=50` (still searchable, just outranked by
  any corpus-attested word).

Lowercase folding before lookup so `Ostrzegał` and `ostrzegał` get the same
boost from a lowercase corpus count.

## Use

```
python3 merge_freq.py \
  /path/to/main_pl_hunspell.combined \
  pl_subs.txt \
  pol_news_2024_300K/pol_news_2024_300K-words.txt \
  pol_wikipedia_2021_300K/pol_wikipedia_2021_300K-words.txt \
  main_pl_corpus.combined

java -ea -jar dicttool_aosp_v203.jar makedict -203 \
  -s main_pl_corpus.combined \
  -d main_pl.dict
```

The `-203` flag and `-ea` are critical (see `ai/todo/dicttool-expansion.md`):
without `-ea`, dicttool silently truncates >16MB addresses; the `-203` flag
opts into the fork's extended-address format that handles real-world Polish
dict sizes.

## Quality check

After generation, top-ranked words for a given prefix should look natural:

```
$ grep "^ word=ostrzeg" main_pl_corpus.combined | sort -t= -k3 -nr | head -5
 word=ostrzega,f=123        # most common form
 word=ostrzegają,f=110      # plural
 word=ostrzegałem,f=100     # 1sg.past
 word=ostrzegał,f=99        # 3sg.past
 word=ostrzegała,f=86       # 3sg.past.fem
```

vs. the old uniform `f=100` everywhere where the order was effectively
random.

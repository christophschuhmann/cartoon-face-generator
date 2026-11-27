"""Unambiguous short German cardinal numbers for speech and ASR matching.

No dates, decimals, ranges, signed numbers, identifiers, or leading zeroes
are rewritten. Single '1' remains unchanged because it may be an article.
"""
import re
from functools import lru_cache

_SMALL=('null','eins','zwei','drei','vier','fünf','sechs','sieben','acht','neun','zehn','elf','zwölf','dreizehn','vierzehn','fünfzehn','sechzehn','siebzehn','achtzehn','neunzehn')
_TENS=('', '', 'zwanzig','dreißig','vierzig','fünfzig','sechzig','siebzig','achtzig','neunzig')


def german_cardinal(number):
    if not 0 <= number <= 9999:
        raise ValueError('Number out of range')
    if number < 20:return _SMALL[number]
    if number < 100:
        tens,ones=divmod(number,10)
        return (('ein' if ones==1 else _SMALL[ones])+'und' if ones else '')+_TENS[tens]
    if number < 1000:
        hundreds,rest=divmod(number,100)
        return ('ein' if hundreds==1 else _SMALL[hundreds])+'hundert'+(german_cardinal(rest) if rest else '')
    thousands,rest=divmod(number,1000)
    return ('ein' if thousands==1 else _SMALL[thousands])+'tausend'+(german_cardinal(rest) if rest else '')


@lru_cache(maxsize=1)
def _reverse():
    return {german_cardinal(i):str(i) for i in range(2,10000)}


def canonical_german_number(word):
    return _reverse().get(word,word)


def normalize_spoken_german(text):
    # Conventional prose abbreviation, not arbitrary initial sequences.
    text=re.sub(r'(?<!\w)z\s*\.\s*b\s*\.(?!\w)', 'zum Beispiel',text,flags=re.I)
    def replace(match):
        raw=match.group(0)
        if len(raw)>1 and raw[0]=='0' or raw=='1':return raw
        return german_cardinal(int(raw))
    return re.sub(r'(?<![\w.,:/+\-−–—])\d{1,4}(?![\w.,:/+\-−–—])',replace,text)

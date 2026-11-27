from bolt_text import Sentence
from robby_speech_numbers import german_cardinal, normalize_spoken_german


def test_cardinals_and_abbreviations_are_spelled_in_german_tts_only():
    text='Im Jahr 2026 kostet das z. B. 15 Euro und 50 Cent.'
    result=Sentence(text,language='de').spec()
    assert result['text']==text
    assert 'zweitausendsechsundzwanzig' in result['manual_prompt']
    assert 'zum Beispiel fünfzehn Euro und fünfzig Cent' in result['manual_prompt']
    assert german_cardinal(21)=='einundzwanzig'
    assert german_cardinal(101)=='einhunderteins'
    assert Sentence('2026 is here.',language='en').spec()['manual_prompt'].endswith('2026 is here.')


def test_do_not_rewrite_dates_signed_values_decimals_ids_or_one():
    original='Am 12.05.2026 waren es -15, −16, +20, 3,5, 2024–2026, A123 und 007 sowie 1 Euro.'
    assert normalize_spoken_german(original)==original

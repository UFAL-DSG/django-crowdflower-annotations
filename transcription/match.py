import re

# Constants.
_more_spaces = re.compile(r'\s{2,}')
_special_words = ["breath", "hum", "laugh", "noise", "sil", "unint"]
_special_rx = '(?:' + '|'.join(_special_words) + ')'
_dashusc_rx = re.compile(r'[_-]')
_nondashusc_punct_rx = re.compile(r'(?![\s_-])\W', flags=re.UNICODE)
_w_vimrx = re.compile(r'\b\w*\W*', flags=re.UNICODE)


def remove_punctuation(text):
    """Removes punctuation characters from `text' except for parentheses around
    special symbols."""
    text = re.sub(_dashusc_rx, '', text)
    text = re.sub(r'\(({s})\)'.format(s=_special_rx),
                  r'_\1-',
                  text)
    text = re.sub(_nondashusc_punct_rx, '', text)
    return re.sub(r'_({s})-'.format(s=_special_rx),
                  r'(\1)',
                  text)


def lowercase(text):
    """Lowercases text except for words with multiple capital ltrs in them.

    Assumes the text has been tokenised.

    May return the same object, or a newly constructed string, depending on
    whether any substitutions were needed.

    """
    words = _w_vimrx.findall(text)
    made_changes = False
    for wordIdx, word in enumerate(words):
        lower = word.lower()
        # If the lowercased version does not differ from the original word
        # except maybe for the first letter,
        if sum(map(lambda char1, char2: char1 != char2,
                   word[1:],
                   lower[1:])) == 0:
            # Substitute the word with its lowercased version.
            words[wordIdx] = lower
            made_changes = True
    if made_changes:
        return u''.join(words)
    else:
        return text


def normalise_trs_text(text):
    """Normalises the text of a transcription:

        - throws away capitalisation except for words with multiple capital
          letters in them
        - throws away punctuation marks except for parentheses in special
          symbols
        - removes non-speech symbols
        - performs some predefined word substitutions.

    """
    # Remove punctuation.
    text = remove_punctuation(text)
    # Shrink spaces.
    text = _more_spaces.sub(u' ', text.strip())
    text = lowercase(text)
    # TODO Do the other modifications yet.
    return text


def trss_match(trs1, trs2):
    """Checks whether two given transcriptions can be considered equal.

    Keyword arguments:
        trs1: first Transcription to compare
        trs2: second Transcription to compare

    """
    # FIXME: Ignore non-speech events.
    return normalise_trs_text(trs1.text) == normalise_trs_text(trs2.text)

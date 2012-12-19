#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# vim: set fdm=marker :
# This code is PEP8-compliant. See http://www.python.org/dev/peps/pep-0008.

"""
Provides functions for transcription normalisation.

Parts are inspired by SDS.corpustools.cued-audio2ufal-audio.normalization.

"""

import re


# Constants.
_more_spaces = re.compile(r'\s{2,}')
_special_words = ["breath", "hum", "laugh", "noise", "sil", "unint"]
_special_rx = '(?:' + '|'.join(_special_words) + ')'
_dashusc_rx = re.compile(r'[_-]')
_nondashusc_punct_rx = re.compile(r'(?![\s_-])\W', flags=re.UNICODE)
_w_vimrx = re.compile(r'\b\w*\W*', flags=re.UNICODE)


_subst = [(u'good-bye', u'goodbye'),
          (u'good bye', u'goodbye'),
          (u'price range', u'pricerange'),
          (u'west side', u'westside'),
          (u'kings hedges', u'kinkgshedges'),
          (u'river side', u'riverside'),
          (u'cherry hinton', u'cherryhinton'),
          (u'fen ditton', u'fenditton'),
          (u'phonenumber', u'phone number'),
          (u'okey', u'ok'),
          (u'okay', u'ok'),
          (u'yep', u'yup'),
          (u'does\'t', u'doesn\'t'),
          (u'whats', u'what\'s'),
          (u'fo', u'for'),
          (u'tel', u'tell'),
          (u'bout', u'about'),
          (u'yo', u'you'),
          (u're', ''),
          (u'sh', ''),
          (u'centre', u'center'),
          (u'yesyes', u'yes yes'),
          (u'yesi', u'yes'),
          (u'youwhat', u'you what'),
          (u'youtell', u'youtell'),
          (u'xpensive', u'expensive'),
          (u'withwhat', u'with what'),
          (u'withinternet', u'with internet'),
          (u'wi-fi', u'wifi'),
          (u'whatwhat', u'what what'),
          (u'whatprice', u'what price'),
          (u'whatarea', u'what area'),
          (u'whatthat', u'what that'),
          (u'whataddress', u'what address'),
          (u'wantinternational', u'want international'),
          (u'wanta', u'want a'),
          (u'trumpingtonarea', u'trumpington area'),
          (u'thevenue', u'the venue'),
          (u'theromsey', u'the romsey'),
          (u'thepricerange', u'the pricerange'),
          (u'theprice', u'the price'),
          (u'thephone', u'the phone'),
          (u'theinterview', u'the interview'),
          (u'thefusion', u'the fusion'),
          (u'theexpensive', u'the expensive'),
          (u'thebest', u'the best'),
          (u'theaddress', u'the address'),
          (u'thatchildren', u'that children'),
          (u'thabk', u'thank'),
          (u'sil', '(sil)'),
          (u'restauant', u'restaurant'),
          (u'restauran', u'restaurant'),
          (u'restaurante', u'restaurant'),
          (u'restauranti n', u'restaurant in'),
          (u'restaurantin', u'restaurant in'),
          (u'resturtant', u'restaurant'),
          (u'reataurant', u'restaurant'),
          (u'reallyum', u'really um'),
          (u'ranchthe', u'ranch the'),
          (u'pubmoderate', u'pub moderate'),
          (u'phonen', u'phone'),
          (u'okdo', u'ok do'),
          (u'okdoes', u'ok does'),
          (u'okgoodbay', u'okgoodbay'),
          (u'okmay', u'ok may'),
          (u'okthank', u'ok thank'),
          (u'okhwat', u'ok what'),
          (u'okwhat\'s', u'ok what\'s'),
          (u'placewith', u'place with'),
          ('11', u'eleven'),
          ('24', u'twenty four'),
          (u'acontemporary', u'a contemporary'),
          (u'addelbrooke\'s', u'addenbrooke\'s'),
          (u'adderss', u'address'),
          (u'addess', u'address'),
          (u'addressof', u'address of'),
          (u'addressphone', u'address phone'),
          (u'addresss', u'address'),
          (u'adsresssir', u'address sir'),
          (u'adenbrook\'s', u'addenbrook\'s'),
          (u'adrdess', u'address'),
          (u'adress', u'address'),
          (u'andand', u'and and'),
          (u'andarea', u'and area'),
          (u'andchinese', u'and chinese'),
          (u'andenglish', u'and english'),
          (u'andwell', u'and well'),
          (u'andthat', u'and that'),
          (u'andwhat', u'and what'),
          (u'andwhere', u'and where'),
          (u'anexpensive', u'an expensive'),
          (u'arestaurant', u'a restaurant'),
          (u'athai', u'a thai'),
          (u'aturkish', u'a turkish'),
          (u'baronin', u'baron in'),
          (u'casle', u'castle'),
          (u'caste', u'castle'),
          (u'castle hill', u'castlehill'),
          (u'cheappricerange', u'cheap pricerange'),
          (u'cheaprestaurant', u'cheap restaurant'),
          (u'chidren', u'children'),
          (u'chinese', u'chines'),
          (u'chlidren', u'children'),
          (u'cinese', u'chinese'),
          (u'coffee', u'coffe'),
          (u'connectio', u'connection'),
          (u'coul', u'could'),
          (u'dbay', u'bay'),
          (u'doens\'t', u'doesn\'t'),
          (u'doesrve', u'deserve'),
          (u'dothat', u'do that'),
          (u'expansive', u'expensive'),
          (u'expensivee', u'expensive'),
          (u'fantasticthank', u'fantastic thank'),
          (u'fenditon', u'fenditton'),
          (u'findamerican', u'find american'),
          (u'goo', u'good'),
          (u'goodthank', u'good thank'),
          (u'goodwhat', u'good what'),
          (u'goodybe', u'goodbye'),
          (u'greatthank', u'great thank'),
          (u'greatwhat', u'grat thank'),
          (u'hastv', u'has tv'),
          (u'heges', u'hedges'),
          (u'hii', u'hill'),
          (u'hil', u'hill'),
          (u'i\'\'m', u'i\'m'),
          (u'iam', u'i am'),
          (u'ian', u'i am'),
          (u'iu"m', u'i\'m'),
          (u'ii', u'i'),
          (u'ii\'m', u'i\'m'),
          (u'indianindian', u'indian indian'),
          (u'inditton', u'in ditton'),
          (u'inexprnsive', u'inexpensive'),
          (u'inpricerange', u'in pricerange'),
          (u'kingthe', u'kingthe'),
          (u'lookin', u'looking'),
          (u'lookinf', u'looking'),
          (u'mediterraranean', u'mediterranean'),
          (u'middele', u'middle'),
          (u'muchhave', u'much have'),
          (u'needa', u'need a'),
          (u'needaddenbrook\'s', u'need addenbrook\'s'),
          (u'needexpensive', u'need expensive'),
          (u'nocontemporary', u'no contemporary'),
          (u'nodoes', u'no does'),
          (u'numberand', u'numberand'),
          ('3', u'three'),
          ('4', u'four'),
          ('5', u'five'),
          ('73', u'seventy three'),
          (u'accomidation', u'accommodation'),
          (u'accomodation', u'accommodation'),
          (u'addelbrooke\'s', u'addenbrooke\'s'),
          (u'addenbrookes', u'addenbrooke\'s'),
          (u'addensbrooke', u'addenbrooke\'s'),
          (u'addnebrooke', u'addenbrooke\'s'),
          (u'adenbrooke\'s', u'addenbrooke\'s'),
          (u'addenbrooks', u'addenbrooke\'s'),
          (u'adresses', u'addresses'),
          (u'adresss', u'address'),
          (u'aidenbrook', u'addenbrooke\'s'),
          (u'anykind', u'any kind'),
          (u'arbory', u'arbury'),
          (u'caffe', u'cafe'),
          (u'catherine\'s\'s', u'catherine\'s'),
          (u'ccan', u'can'),
          (u'centrap', u'central'),
          (u'cheery', u'chery'),
          (u'coff', u'coffee'),
          (u'coffe', u'coffee'),
          (u'conncetion', u'connection'),
          (u'contintenal', u'continental'),
          (u'dosen\'t', u'doesn\'t'),
          (u'dont\'t', u'don\'t'),
          (u'enginering', u'engineering'),
          (u'expencive', u'expensive'),
          (u'fanditton', u'fenditton'),
          (u'fenderton', u'fenditton'),
          (u'finda', u'find a'),
          (u'fordable', u'afordable'),
          (u'galleria', u'gallery'),
          (u'gerten', u'girton'),
          (u'gerton', u'girton'),
          (u'good0bye', u'goodbye'),
          (u'goodye', u'goodbye'),
          (u'hinson', u'hinston'),
          (u'hitton', u'hinston'),
          (u'moder', u'modern'),
          (u'motal', u'motel'),
          (u'nummber', u'number'),
          (u'openning', u'opening'),
          (u'ot', u'or'),
          (u'phonbe', u'phone'),
          (u'prce', u'price'),
          (u'prize', u'price'),
          (u'reasturtant', u'restaurant'),
          (u'restuarant', u'restaurant'),
          (u'riveside', u'riverside'),
          (u'sendeton', u'fenditton'),
          (u'sendington', u'fendington'),
          (u'senditton', u'fenditton'),
          (u'shushi', u'sushi'),
          (u'silence', '(sil)'),
          (u'silent', '(sil)'),
          (u'sindeentan', u'fenditton'),
          (u'sindeetan', u'fenditton'),
          (u'sindinton', u'fenditton'),
          (u'somethingin', u'something in'),
          (u'televison', u'television'),
          (u'televsion', u'television'),
          (u'thanh', u'thank'),
          (u'theire', u'their'),
          (u'veneue', u'venue'),
          (u'vodca', u'vodka'),
          (u'waht', u'what'),
          (u'adenbrooks', u'addenbrook\'s'),
          (u'archecticture', u'architecture'),
          (u'avanue', u'avenue'),
          (u'enterainment', u'entertainment'),
          (u'gueshouse', u'guesthouse'),
          (u'isnt', u'isn\'t'),
          (u'phonme', u'phone'),
          (u'ofcourse', u'of course'),
          (u'plce', u'price'),
          (u'pone', u'phone'),
          (u'resaurant', u'restaurant'),
          (u'restautant', u'restaurant'),
          (u'shampain', u'champain'),
          (u'staion', u'station'),
          (u'staions', u'stations'),
          (u'telivision', u'television'),
          (u'telivison', u'television'),
          (u'thnk', u'thank'),
          (u'univercity', u'university'),
          (u'wannt', u'want'),
          (u'zizi', u'zizzi'),
          (u'amarican', u'american'),
          (u'aweful', u'awful'),
          (u'cheep', u'cheap'),
          (u'chines', u'chinese'),
          (u'doesnt', u'doesn\'t'),
          (u'excelent', u'excellent'),
          (u'fendington', u'fenditton'),
          (u'prive', u'price'),
          (u'postcode', u'post code'),
          (u'zipcode', u'zip code'),
          (u'raodside', u'roadside'),
          (u'repet', u'repeat'),
          (u'psot', u'post'),
          (u'teh', u'the'),
          (u'thak', u'thank'),
          (u'vanue', u'venue'),
          (u'begent', u'regent'),
          (u'chine', u'chinese'),
          (u'chines', u'chinese'),
          (u'afordable', u'affordable'),
          (u'addres', u'address'),
          (u'addenbrooke', u'addenbrooke\'s'),
          (u'anytihng', u'anything'),
          (u'numberand', u'number and'),
          (u'pirce', u'price'),
          (u'pricep', u'price'),
          (u'tnank', u'thank'),
          (u'somthing', u'something'),
          (u'whnat', u'what'),
          ]
for idx, tup in enumerate(_subst):
    pat, sub = tup
    _subst[idx] = (re.compile(ur'\b{pat}\b'.format(pat=pat)), sub)


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


def remove_punctuation(text, remove_nonspeech=False):
    """Removes punctuation characters from `text' except for parentheses around
    special symbols."""
    text = re.sub(_dashusc_rx, '', text)
    text = re.sub(r'\(({s})\)'.format(s=_special_rx),
                  r'_\1-',
                  text)
    text = re.sub(_nondashusc_punct_rx, '', text)
    spec_sub = '' if remove_nonspeech else r'(\1)'
    return re.sub(r'_({s})-'.format(s=_special_rx), spec_sub, text)


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
    text = remove_punctuation(text, remove_nonspeech=True)
    # Shrink spaces.
    text = _more_spaces.sub(u' ', text.strip())
    text = lowercase(text)
    # Do dictionary substitutions.
    for pat, sub in _subst:
        text = pat.sub(sub, text)
    return text


def edit_dist(str1, str2):
    """Computes the edit distance between strings."""
    len1, len2 = len(str1), len(str2)
    # Special case: zero length of one of the strings.
    if len1 == 0 or len2 == 0:
        return len1 + len2

    # Initialise the table for dynamic programming.
    dist = range(len2 + 1)

    # Fill in the table based on the recurrent formula.
    for i1 in xrange(1, len1 + 1):
        corner = i1 - 1  # previous dist[i2] (here i2 == 0)
        dist[0] = i1
        for i2 in xrange(1, len2 + 1):
            new_corner = dist[i2]
            diff = int(str1[i1 - 1] != str2[i2 - 1])
            dist[i2] = min(dist[i2] + 1,       # adding to str1
                           dist[i2 - 1] + 1,   # deleting from str1
                           corner + diff)      # substitution
            corner = new_corner
    # Return.
    return dist[len2]


def trss_match(trs1, trs2, max_char_er=0.):
    """Checks whether two given transcriptions can be considered equal.

    Keyword arguments:
        trs1: first Transcription to compare
        trs2: second Transcription to compare
        max_char_er: maximal character error rate (how many characters
            relatively are allowed to differ, after normalisation)

    """
    norm1 = normalise_trs_text(trs1.text)
    norm2 = normalise_trs_text(trs2.text)
    if max_char_er <= 0.:
        return norm1 == norm2
    else:
        # a shortcut
        if norm1 == norm2:
            return True
        # the proper evaluation
        len1 = len(norm1)
        len2 = len(norm2)
        char_er = edit_dist(norm1, norm2) / float(max(len1, len2))
        return char_er <= max_char_er

#!/usr/bin/python
# -*- coding: UTF-8 -*-
import os
import os.path

import settings
from transcription.models import Transcription, UserTurn


def is_gold(dg):
    """Returns True iff any turn of `dg' has a gold transcription."""
    return Transcription.objects.filter(dialogue_annotation__dialogue=dg,
                                        is_gold=True).exists()


def update_price(dg):
    """Computes the price of a dialogue transcription (in USD)."""
    uturns = UserTurn.objects.filter(dialogue=dg)
    # Compute the length of the audio.
    wavsize = 0
    for turn in uturns:
        wavsize += os.path.getsize(os.path.join(
            settings.CONVERSATION_DIR,
            turn.wav_fname))
    sec = wavsize / float(16000 * 2)
    minutes = sec / 60.

    price = (settings.PRICE_CONST + settings.PRICE_PER_MIN * minutes
             + settings.PRICE_PER_TURN * len(uturns))
    dg.transcription_price = price

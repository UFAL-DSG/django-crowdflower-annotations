#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

from datetime import datetime
import os.path


def get_log_path(dirname):
    assert os.path.isdir(dirname)
    timestamp = datetime.strftime(datetime.now(), '%y-%m-%d-%H%M%S')
    log_num = 0
    while True:
        log_fname = '{ts}.{num!s}.log'.format(ts=timestamp, num=log_num)
        log_path = os.path.join(dirname, log_fname)
        if not os.path.exists(log_path):
            break
        log_num += 1
    return log_path

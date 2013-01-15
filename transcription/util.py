#!/usr/bin/python
# -*- coding: UTF-8 -*-

from datetime import datetime
import os.path


def get_log_path(dirname):
    timestamp = datetime.strftime(datetime.now(), '%y-%m-%d-%H%M%S')
    while True:
        log_num = 0
        log_fname = '{ts}.{num!s}.log'.format(ts=timestamp, num=log_num)
        log_path = os.path.join(dirname, log_fname)
        if not os.path.exists(log_path):
            break
        else:
            log_num += 1
    return log_path

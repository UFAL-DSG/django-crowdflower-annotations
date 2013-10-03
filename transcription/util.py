#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

from datetime import datetime
from functools import wraps
import os.path

from django.core.mail import mail_admins
from django.shortcuts import render
from django.db import DatabaseError

import settings


def get_log_path(dirname):
    """
    Creates a path to a new log file that is in the right directory and does
    not clash with existing paths.
    """
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


def catch_locked_database(meth):
    """
    This decorator takes care of catching DatabaseError for a locked database.

    In case the decorated view method raises a DatabaseError with "database is
    locked" as the exception value:

        1. A meaningful page is displayed, informing the annotator what
           happened.

        2. An email is sent to admins.

    """

    @wraps(meth)
    def wrapper(*args, **kwargs):
        try:
            request = args[0]
        except Exception as ex:
            raise Exception('A view method was called with no arguments!')

        try:
            ret = meth(*args, **kwargs)
        except DatabaseError as ex:
            if str(ex) == 'database is locked':
                # Send an email to admins.
                app_port = (':{port}'.format(port=settings.APP_PORT)
                            if settings.APP_PORT else '')
                app_url = settings.DOMAIN_URL + app_port + settings.APP_PATH
                subj = "[{app}] Problem with database access".format(
                    app=app_url)
                msg = """\
                    Hi, Django admin,

                    an annotator in your transcription application at {app}
                    encountered a "database locked" database error. This means
                    that either someone was accessing the database through
                    a back door while the annotations are running or the
                    annotations are coming faster than your database backend
                    can handle.

                    If you are using SQLite and you have already gotten
                    a number of emails like this, you should consider switching
                    to a different backend or reducing the number of
                    annotations you are running.

                    Sincerely,
                        your Transcription app""".format(app=app_url)
                mail_admins(subj, msg, fail_silently=True)

                # Inform the annotator what happened.
                context = dict()
                return render(request, "trs/dbaccess-error.html", context)

            # For unexpected exceptions,
            else:
                # Reraise the exception.
                raise ex

        # If nothing special happened, return what the original method
        # returned.
        return ret

    return wrapper

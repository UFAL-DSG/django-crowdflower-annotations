#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

from datetime import datetime
from functools import wraps
import os.path

from django.core.mail import mail_admins
from django.shortcuts import render
from django.db import DatabaseError
from django.core.urlresolvers import reverse, NoReverseMatch
from django.utils.html import escape
from django.utils.safestring import mark_safe

import settings


def get_object_url(obj):
    """
    Tries to construct a URL pointing to the admin page for this object.

    Raises NoReversMatch if unsuccessful.

    """
    clsname = obj._meta.object_name.lower()
    url_str = ('admin:transcription_{cls}_change'.format(cls=clsname))
    # Construct the URL from the base URL string plus the object ID.
    return reverse(url_str, args=(obj.pk, ))


def get_object_and_url(model, attrs):
    try:
        db_obj = model.objects.get(**attrs)
    except model.DoesNotExist:
        return (None,
                mark_safe(u'<span class="warning">Object not found</span>'))
    except model.MultipleObjectsReturned:
        return None, mark_safe(u'<span class="warning">Ambiguous</span>')
    # clsname = db_obj._meta.object_name.lower()
    clsname = model.__name__.lower()
    url_str = ('admin:transcription_{cls}_change'.format(cls=clsname))
    try:
        # Construct the URL from the base URL string plus the object ID.
        url = reverse(url_str, args=(db_obj.pk, ))
    except NoReverseMatch:
        # In case this type of objects is not managed by the admin system
        # (the most probable reason), render just the object as a Unicode
        # string, with the player appended if appropriate.
        return None, escape(unicode(db_obj))
    # If an admin page for the object is available, return the URL of that
    # page.
    return (db_obj, url)


def get_object_link(model, attrs):
    db_obj, url = get_object_and_url(model, attrs)
    # If an admin page for the object is available, render a link to
    # that page.
    return (db_obj,
            mark_safe(u'<a href="{url}">Show the object</a>'.format(url=url)))


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


def group_by(objects, attrs):
    """Groups `objects' by the values of their attributes `attrs'.

    Returns a dictionary mapping from a tuple of attribute values to a list of
    objects with those attribute values.

    """
    groups = dict()
    for obj in objects:
        key = tuple(getattr(obj, attr) for attr in attrs)
        groups.setdefault(key, []).append(obj)
    return groups


# TODO Define a proper DA matching function.
def das_match(da1, da2, *args, **kwargs):
    return True


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

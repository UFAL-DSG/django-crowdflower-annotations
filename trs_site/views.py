#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

from django.contrib.auth import views as auth_views

import settings


_file_email_backend = 'django.core.mail.backends.filebased.EmailBackend'
if settings.EMAIL_BACKEND == _file_email_backend:
    _reset_extra_text = """
        <h1>Note</h1>
        <p>
        This application uses a bogus email sending. That means that you won't
        receive any email in your mailbox, it gets stored at the server.
        Please, ask the admins for help.
        </p>
    """

    def password_reset_done(
            request, template_name='registration/password_reset_done.html',
            current_app=None, extra_context=None):
        tpt_response = auth_views.password_reset_done(
            request, template_name, current_app, extra_context)
        text = tpt_response.rendered_content
        last_p_idx = text.rfind('</p>')
        # If the template contains no <p> tags,
        if last_p_idx == -1:
            # Give up, return the stock template.
            return tpt_response

        # If the last <p> tag was found, append our note after it.
        tpt_response.content = text[:last_p_idx] + '</p>\n' + _reset_extra_text
        return tpt_response

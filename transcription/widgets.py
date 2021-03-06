from __future__ import unicode_literals

from django import forms
from django.forms.widgets import HiddenInput, TextInput, Widget
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string

from settings import APP_PATH, CONVERSATION_DIR, MEDIA_URL
from transcription.util import get_object_link


class ROInput(TextInput):
    """A read-only input."""

    def render(self, name, value, attrs=None):
        attrs[u'readonly'] = u'true'
        with_equals = super(TextInput, self).render(name, value, attrs)
        return mark_safe(with_equals.replace(u'readonly="true"', u'readonly'))


class PlayWidget(Widget):
    """A widget that features a Play button if provided with a path towards
    a wav file.

    """
    num_wavs = 0
    """number of fields with wavs rendered using PlayWidget so far"""

    def __init__(self, attrs=None):
        super(PlayWidget, self).__init__(attrs)
        self.hidinput = HiddenInput()

    def render(self, name, value, attrs=None):
        # Merge attributes from self.attr and attrs argument.
        final_attrs = self.build_attrs(attrs)

        # Render the link plus the wav player if applicable.
        content_html = self.render_content(name, value, attrs)

        if 'add_link' in final_attrs and 'db_field' in final_attrs:
            db_field = final_attrs['db_field']
            model = db_field.model
            link_html = get_object_link(model, {db_field.attname: value})[1]
        else:
            link_html = mark_safe(u'')

        # Render the form element that retains information about the
        # corresponding model field and its value.
        hidden_html = self.hidinput.render(name, value, attrs)
        return (hidden_html + content_html + link_html)

    def render_content(self, name, value, attrs=None):
        if (not hasattr(value, 'startswith')
                or not value.startswith(CONVERSATION_DIR)):
            return mark_safe('N/A')
        wav_rest = value[len(CONVERSATION_DIR):]
        context = {'wav_fname': wav_rest,
                   'script_id': unicode(PlayWidget.num_wavs),
                   'MEDIA_URL': MEDIA_URL,
                   'APP_PATH' : APP_PATH}
        PlayWidget.num_wavs += 1
        player_html = render_to_string("trs/wav_player.html",
                                       dictionary=context)
        return player_html


class LinkWidget(PlayWidget):
    """This widget is to be used for foreign key db fields."""

    def render_content(self, name, value, attrs=None):
        """value -- the primary key value for the object in question"""
        if attrs is None:
            return mark_safe(u'None')

        # Merge attributes from self.attr and attrs argument.
        final_attrs = self.build_attrs(attrs)

        if not value or len(final_attrs['queryset']) == 0:
            return mark_safe(u'None')
        else:
            target_obj, link_html = get_object_link(
                final_attrs['queryset'].model, {'pk': value})
            # Check whether we can add a play button to this object.
            if hasattr(target_obj, 'wav_fname'):
                player_html = super(LinkWidget, self).render_content(
                    name, target_obj.wav_fname, final_attrs)
            else:
                player_html = mark_safe(u'')
            return mark_safe(link_html + player_html)


class DatetimeWidget(forms.DateTimeInput):
    def render(self, name, value, attrs=None):
        # Check whether we can add a play button to this object.
        html = super(DatetimeWidget, self).render(name, value, attrs)
        id_ = attrs.pop('id', 'id_{name}'.format(name=name))
        cal_html = ('<img src="{dtp_dir}/images2/cal.gif" onclick='
                    '"javascript:NewCssCal(\'{id_}\',\'yyyyMMdd\','
                    '\'dropdown\',true,\'24\',true)" '
                    'style="cursor:pointer; margin-left: 6px;" />').format(
                        dtp_dir=MEDIA_URL + '/js/datetimepicker', id_=id_)
        return mark_safe(html + cal_html)

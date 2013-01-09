from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse, NoReverseMatch
from django.forms.widgets import HiddenInput, Widget
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string

from settings import MEDIA_URL


class LinkWidget(Widget):
    num_wavs = 0
    """number of fields with wavs rendered using LinkWidget so far"""

    def __init__(self, attrs=None):
        super(LinkWidget, self).__init__(attrs)
        self.hidinput = HiddenInput()

    def render(self, name, value, attrs=None):
        # Render the link plus the wav player if applicable.
        # NOTE: Not tested with multiple wav fields per object yet.
        content_html = self.render_content(name, value, attrs)
        # Render the form element that retains information about the
        # corresponding model field and its value.
        hidden_html = self.hidinput.render(name, value, attrs)
        return (hidden_html + content_html)

    def render_content(self, name, value, attrs=None):
        # Merge attributes from self.attr and attrs argument.
        final_attrs = self.build_attrs(attrs)

        if not value or len(final_attrs['queryset']) == 0:
            return mark_safe(u'None')
        else:
            try:
                target_obj = final_attrs['queryset'].get(pk=value)
            except ObjectDoesNotExist:
                out_html = (u'<span class="warning">The object linked '
                            u'to is missing from the database!</span>')
                return mark_safe(out_html)
            # Check whether we can add a play button to this object.
            if hasattr(target_obj, 'wav_fname'):
                path_len = len(target_obj._meta\
                               .get_field_by_name('wav_fname')[0].path)
                wav_rest = target_obj.wav_fname[path_len:]
                context = {'wav_fname': wav_rest,
                           'script_id': unicode(LinkWidget.num_wavs),
                           'MEDIA_URL': MEDIA_URL}
                LinkWidget.num_wavs += 1
                player_html = render_to_string("trs/wav_player.html",
                                               dictionary=context)
            else:
                player_html = mark_safe(u'')
            clsname = target_obj._meta.object_name.lower()
            url_str = 'admin:transcription_{cls}_change'\
                      .format(cls=clsname)
            out_html = escape(unicode(target_obj))
            try:
                # Construct the URL from the base URL string plus the object
                # ID.
                url = reverse(url_str, args=(value, ))
            except NoReverseMatch:
                # In case this type of objects is not managed by the admin
                # system (the most probable reason), render just the object as
                # a Unicode string, with the player appended if appropriate.
                return (out_html + player_html)
            # If an admin page for the object is available, render a link to
            # that page.
            out_html += u' <a href="{url}">Show the object</a>{wav}'\
                        .format(url=url, wav=player_html)
            return mark_safe(out_html)

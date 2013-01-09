from django.forms.models import ModelChoiceField

from transcription.widgets import LinkWidget


class LinkField(ModelChoiceField):

    def __init__(self, queryset, *args, **kwargs):
        # Ignore the 'widget' argument.
        accepted_kwargs = ('required', 'label', 'initial', 'help_text',
                           'error_messages', 'show_hidden_initial',
                           'validators', 'localize')
        super_kwargs = dict()
        for kwarg in kwargs:
            if kwarg in accepted_kwargs:
                super_kwargs[kwarg] = kwargs[kwarg]
        # Set the widget to LinkWidget.
        super_kwargs['widget'] = LinkWidget

        self._queryset = queryset
        super(LinkField, self).__init__(queryset, *args, **super_kwargs)

    def widget_attrs(self, widget):
        attrs = super(LinkField, self).widget_attrs(widget)
        # Put the query set among the attributes.
        attrs['queryset'] = self._queryset
        return attrs

#!/usr/bin/python
# -*- coding: UTF-8 -*-

from django import forms
from transcription.widgets import DatetimeWidget, LinkWidget, PlayWidget
from django.forms.models import ModelChoiceField


field_kwargs = ('required', 'label', 'initial', 'help_text', 'error_messages',
                'show_hidden_initial', 'validators', 'localize', 'widget')


def filter_field_kwargs(kwargs):
    """Filters kwargs to only such that are accepted by the Field
    initialiser."""
    new_kwargs = dict()
    for kwarg in kwargs:
        if kwarg in field_kwargs:
            new_kwargs[kwarg] = kwargs[kwarg]
    return new_kwargs


class LinkField(ModelChoiceField):
    """Implements a field for the admin interface to represent a related
    object. It provides for the LinkWidget the information needed in order to
    render the related object.

    """

    def __init__(self, queryset, *args, **kwargs):
        super_kwargs = filter_field_kwargs(kwargs)
        super_kwargs['widget'] = LinkWidget
        self._queryset = queryset
        super(LinkField, self).__init__(queryset, *args, **super_kwargs)

    def widget_attrs(self, widget):
        attrs = super(LinkField, self).widget_attrs(widget)
        # Put the query set among the attributes.
        attrs['queryset'] = self._queryset
        return attrs


class PlayField(forms.fields.Field):

    def __init__(self, *args, **kwargs):
        super_kwargs = filter_field_kwargs(kwargs)
        super_kwargs['widget'] = PlayWidget
        self._db_field = kwargs.pop('db_field', None)
        super(PlayField, self).__init__(*args, **super_kwargs)

    def widget_attrs(self, widget):
        attrs = super(PlayField, self).widget_attrs(widget)
        # Put the query set among the attributes.
        attrs['db_field'] = self._db_field
        attrs['add_link'] = True
        return attrs


class DatetimeField(forms.fields.DateTimeField):

    def __init__(self, *args, **kwargs):
        super_kwargs = filter_field_kwargs(kwargs)
        super_kwargs['widget'] = DatetimeWidget
        super(DatetimeField, self).__init__(*args, **super_kwargs)


class ListField(forms.Field):
    def to_python(self, value):
        """Normalises data to a list of strings."""
        # Return None if no input was given.
        if not value:
            return list()
        return sorted(set(map(unicode.strip, value.split(','))))

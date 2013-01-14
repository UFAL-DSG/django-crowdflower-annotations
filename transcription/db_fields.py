from django import forms
from django.db.models import fields
from django.utils.translation import ugettext_lazy as _

from transcription import form_fields


class WavField(fields.FilePathField):
    description = _("Wav field")

    def formfield(self, **kwargs):
        defaults = {
            'form_class': form_fields.PlayField,
            'db_field': self
        }
        defaults.update(kwargs)
        return super(WavField, self).formfield(**defaults)


class SizedTextField(fields.TextField):
    """Implements the model field that gets rendered as a textarea of size
    specified at initialisation time. Note this does not affect the appearance
    in the admin interface, as that one uses AdminTextarea instead of Textarea.

    """

    def __init__(self, verbose_name=None, name=None, primary_key=False,
                 max_length=None, unique=False, blank=False, null=False,
                 db_index=False, rel=None, default=fields.NOT_PROVIDED,
                 editable=True, serialize=True, unique_for_date=None,
                 unique_for_month=None, unique_for_year=None, choices=None,
                 help_text='', db_column=None, db_tablespace=None,
                 auto_created=False, validators=[], error_messages=None,
                 cols=None, rows=None):
        super(SizedTextField, self).__init__(
            verbose_name=verbose_name, name=name, primary_key=primary_key,
            max_length=max_length, unique=unique, blank=blank, null=null,
            db_index=db_index, rel=rel, default=default, editable=editable,
            serialize=serialize, unique_for_date=unique_for_date,
            unique_for_month=unique_for_month, unique_for_year=unique_for_year,
            choices=choices, help_text=help_text, db_column=db_column,
            db_tablespace=db_tablespace, auto_created=auto_created,
            validators=validators, error_messages=error_messages)
        self.dimensions = dict()
        if cols is not None:
            self.dimensions['cols'] = cols
        if rows is not None:
            self.dimensions['rows'] = rows

    def formfield(self, **kwargs):
        if len(self.dimensions):
            defaults = {'widget': forms.Textarea(attrs=self.dimensions)}
            defaults.update(kwargs)
        else:
            defaults = kwargs
        return super(SizedTextField, self).formfield(**defaults)

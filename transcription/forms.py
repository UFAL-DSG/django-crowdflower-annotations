#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

import os
import re

from django import forms
from django.utils.datastructures import SortedDict

from crowdflower import default_job_cml_path, price_class_handler
from form_fields import DatetimeField, ListField
import settings


class TranscriptionForm(forms.Form):
    if 'quality' in settings.EXTRA_QUESTIONS:
        quality = forms.CharField()
    if 'accent' in settings.EXTRA_QUESTIONS:
        accent = forms.CharField()
        accent_name = forms.CharField(required=False)
    if 'offensive' in settings.EXTRA_QUESTIONS:
        offensive = forms.BooleanField(required=False)
    notes = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        turn_dicts = kwargs.pop('turn_dicts', None)
        if turn_dicts is None:
            turn_dicts = tuple()
        cid = kwargs.pop('cid', None)
        if args:
            data = args[0]
        else:
            data = kwargs.get('data', None)
        super(TranscriptionForm, self).__init__(*args, **kwargs)

        self.fields['cid'] = forms.CharField(widget=forms.HiddenInput(),
                                             initial=cid)

        # FIXME These variable-number data are not regenerated currently.
        # Recover transcriptions.
        if 'asr' in settings.TASKS:
            for tpt_turn_num, turn_dict in enumerate(turn_dicts, start=1):
                if not turn_dict['has_rec']:
                    continue
                self.fields['trs_{0}'.format(tpt_turn_num)] = forms.CharField(
                    widget=forms.Textarea(
                        attrs={'style': 'width: 90%', 'rows': '3'}),
                    label=tpt_turn_num)

        # Recover semantic annotations.
        if 'slu' in settings.TASKS:
            if data is not None:
                checklist = filter(lambda item: item[0].startswith('check'),
                                   data.iteritems())
                for tpt_turn_num, turn_dict in enumerate(turn_dicts, start=1):
                    if not turn_dict['has_rec']:
                        continue
                    sem_prefix = 'sludai_{0}_'.format(tpt_turn_num)
                    dat_prefix = 'newdat_{0}_'.format(tpt_turn_num)
                    sem_trss = filter(
                        lambda item: item[0].startswith(sem_prefix),
                        data.iteritems())
                    for trs_name, text in sem_trss:
                        # FIXME This is weird, using the checkbox widget for
                        # a text input field. Why is this so?
                        self.fields[trs_name] = forms.CharField(
                            widget=forms.CheckboxInput())
                    newdat_trss = filter(
                        lambda item: item[0].startswith(dat_prefix),
                        data.iteritems())
                    for trs_name, text in newdat_trss:
                        if text != '':
                            coords = trs_name[len('newdat_'):]
                            check_name = 'check_{coo}'.format(coo=coords)
                            if check_name in checklist:
                                self.fields['newdat_{0}'.format(coords)] = (
                                    forms.CharField(widget=forms.Select()))
                                self.fields['slot_{0}'.format(coords)] = (
                                    forms.CharField(widget=forms.Select()))
                                self.fields['value_{0}'.format(coords)] = (
                                    forms.CharField(widget=forms.Select()))

    def __unicode__(self):
        import pprint
        return pprint.pformat(self.fields, depth=3)

    def __repr__(self):
        return self.__unicode__()

    def __str__(self):
        return self.__unicode__()


class DateRangeForm(forms.Form):
    dt_from = DatetimeField(label='from after (excl.)', required=False)
    dt_to = DatetimeField(label='until (incl.)', required=False)


if settings.USE_CF:
    class WorkLogsForm(forms.Form):
        logs_list_path = forms.FilePathField(
            path=settings.LISTS_DIR,
            label="Path to the worklogs list file",
            help_text=('Select the file that lists paths towards worklog '
                       'files that should be reused.'))


    class CustomFieldsForm(forms.Form):
        def __init__(self, fields, data=None):
            super(CustomFieldsForm, self).__init__(data)
            self.fields.update(fields)


    class CreateJobForm(forms.Form):
        """A form for creating Crowdflower jobs."""

        class CountriesField(ListField):
            """Form field for entering country codes."""
            def validate(self, value):
                "Check if value consists only of two-letter codes."
                # Use the parent's handling of required fields, etc.
                super(CreateJobForm.CountriesField, self).validate(value)
                wrong_codes = set()
                for code in value:
                    if len(code) != 2 or not code.isupper():
                        wrong_codes.add(code)
                if wrong_codes:
                    codes_list = ', '.join('"{code}"'.format(code=code)
                                           for code in sorted(wrong_codes))
                    msg = ('Following are definitely not valid country codes: '
                           '{codes}.').format(codes=codes_list)
                    raise forms.ValidationError(msg)

        class PricesField(forms.Field):
            """Form field for entering a list of integers."""
            def to_python(self, value):
                "Normalize data to a list of integers."
                # Return None if no input was given.
                if not value:
                    return list()

                # Otherwise, check all input values whether they can be coerced
                # to ints.
                string_list = set(map(unicode.strip, value.split(',')))
                wrong_ints = set()
                good_ints = set()
                for int_str in string_list:
                    try:
                        good_ints.add(int(int_str))
                    except ValueError:
                        wrong_ints.add(int_str)
                if wrong_ints:
                    ints_list = ', '.join('"{int_}"'.format(int_=int_)
                                          for int_ in wrong_ints)
                    msg = ('Following are not valid integers: {ints}.'
                           .format(ints=ints_list))
                    raise forms.ValidationError(msg)
                else:
                    return list(sorted(good_ints))

        # Constants.
        default_countries = ",".join(("AU", "CA", "GB", "IE", "IM", "NZ",
                                      "US"))
        default_title = 'Dialogue transcription – {price}c'
        default_instructions = re.sub(' +', ' ', """\
            Please, write down what is said in the provided recordings. The
            recordings capture a dialogue between a human and a computer. The
            computer utterances are known, so only the human's utterances need
            to be transcribed.""").strip().replace('\n ', '\n')
        inputWidth = len(default_title)
        fixedWidthTextInput = forms.TextInput(attrs={'size': inputWidth})

        # Fields.
        cents_per_unit = PricesField(
            initial='5, 10, 15, 20, 25, 30, 35, 40',
            widget=fixedWidthTextInput,
            help_text=('Specify desired price per dialogue in cents. This can '
                       'be a comma-separated list of integers. A job will be '
                       'created for each price specified here.'))
        store_job_id = forms.BooleanField(
            initial=True,
            label='Store job ID',
            help_text=('Should job IDs be written to a job ID list file? '
                       '(Leave this checked if you want to upload dialogues '
                       'for this job.)'),
            required=False)
        job_cml_path = forms.FilePathField(
            path=os.path.dirname(default_job_cml_path),
            match='\.cml$',
            initial=default_job_cml_path,
            label="Path to the job CML file",
            help_text=('Select the file that defines the body of the '
                       'Crowdflower unit.\n'
                       'If you see no choices here, you might need to run '
                       'the scripts/setup_script.py script yet.'))
        judgments_per_unit = forms.IntegerField(
            initial=1,
            widget=fixedWidthTextInput,
            help_text='How many times do you want each dialogue transcribed?')
        units_per_assignment = forms.IntegerField(
            initial=2,
            widget=fixedWidthTextInput,
            help_text='How many dialogues in a HIT?')
        pages_per_assignment = forms.IntegerField(
            initial=1,
            widget=fixedWidthTextInput,
            help_text='How many visual pages to split each HIT into?')
        gold_per_assignment = forms.IntegerField(
            initial=1,
            widget=fixedWidthTextInput,
            help_text='How many gold dialogues per HIT?')
        title = forms.CharField(
            initial=default_title, widget=fixedWidthTextInput,
            help_text=('Title for the job. "{price}" will be substituted '
                       'with the HIT price in cents.'))
        instructions = forms.CharField(
            initial=default_instructions,
            widget=forms.Textarea(attrs={'rows': 3, 'cols': 64}),
            help_text='Specify instructions for the Crowdflower job in HTML.')
        bronze = forms.BooleanField(
            initial=True,
            help_text=('Require bronze classification from workers to work on '
                       'this job?'),
            required=False)
        included_countries = CountriesField(
            initial=default_countries, widget=fixedWidthTextInput,
            help_text=('Specify countries which workers have to reside in '
                       'in order to qualify for working on this job. '
                       'Use two-letter country codes.'))


    class DeleteJobForm(forms.Form):
        """A form for deleting Crowdflower jobs."""

        def __init__(self, data=None):
            """Creates the form.

            Arguments:
                data -- request.POST if the form is bound

            """

            super(DeleteJobForm, self).__init__(data)

            # If creating a bound form,
            if data is not None:
                # Create hidden fields.
                fields = dict()
                # Collect job IDs of the old jobs.
                if data['old_job_ids']:
                    old_job_ids = data['old_job_ids'].split(',')
                else:
                    old_job_ids = list()
                self.has_old_job_ids = bool(old_job_ids)
                fields['old_job_ids'] = ListField(widget=forms.HiddenInput(),
                                                  required=False)
                # Collect job IDs of the active jobs.
                if data['active_job_ids']:
                    active_job_ids = data['active_job_ids'].split(',')
                else:
                    active_job_ids = list()
                self.has_active_job_ids = bool(active_job_ids)
                fields['active_job_ids'] = ListField(
                    widget=forms.HiddenInput(), required=False)
                # Store the hidden fields and their data.
                self._hidden_fields = fields
                self._hidden_data = {key: data[key] for key in fields}
                self.fields.update(fields)

                # Re-create old job fields.
                field_items, self._old_data = self._populate_bound_fields(
                    data, old_job_ids)
                fields = SortedDict(field_items)
                self._old_job_fields = fields
                self.fields.update(fields)
                # Re-create active job fields.
                field_items, self._active_data = self._populate_bound_fields(
                    data, active_job_ids)
                fields = SortedDict(field_items)
                self._active_job_fields = fields
                self.fields.update(fields)

            # If creating a new form,
            else:
                fields = dict()
                # Collect job IDs of the old jobs.
                old_price_classes = price_class_handler.old_price_classes
                old_job_ids = [job_id for price, job_id in old_price_classes]
                old_job_ids_str = ','.join(sorted(old_job_ids))
                # Remember what all old job IDs we have.
                self.has_old_job_ids = bool(old_job_ids)
                fields['old_job_ids'] = ListField(
                    widget=forms.HiddenInput(),
                    initial=old_job_ids_str,
                    required=False)

                # Collect job IDs of the active jobs.
                price_classes = price_class_handler.price_classes.viewitems()
                active_job_ids = [job_id for price, job_id in price_classes]
                active_job_ids_str = ','.join(sorted(active_job_ids))
                # Remember what all active job IDs we have.
                self.has_active_job_ids = bool(active_job_ids)
                fields['active_job_ids'] = ListField(
                    widget=forms.HiddenInput(),
                    initial=active_job_ids_str,
                    required=False)

                # Store the hidden fields.
                self._hidden_fields = fields
                self._hidden_data = {'old_job_ids': old_job_ids_str,
                                     'active_job_ids': active_job_ids_str}
                self.fields.update(fields)

                # Create old job fields.
                field_items = self._populate_unbound_fields(old_price_classes)
                fields = SortedDict(field_items)
                self._old_data = None
                self._old_job_fields = fields
                self.fields.update(fields)
                # Create active job fields.
                field_items = self._populate_unbound_fields(price_classes)
                fields = SortedDict(field_items)
                self._active_data = None
                self._active_job_fields = fields
                self.fields.update(fields)

        def _populate_bound_fields(self, data, job_ids):
            field_items = list()
            my_data = dict()
            for job_id in job_ids:
                # Find the field's label.
                label_field_name = '{job_id}-label'.format(job_id=job_id)
                label = data[label_field_name]
                # Create the field itself and its label field.
                field = forms.BooleanField(label=label, required=False)
                field_items.append((job_id, field))
                field = forms.CharField(widget=forms.HiddenInput())
                field_items.append((label_field_name, field))
                # Copy the data items used.
                my_data[label_field_name] = data[label_field_name]
                my_data[job_id] = job_id in data
            return field_items, my_data

        def _populate_unbound_fields(self, price_classes):
            field_items = list()
            for price, job_id in sorted(price_classes):
                # Create the field itself.
                label = '{job_id} ({cents}c)'.format(
                    cents=int(100 * price), job_id=job_id)
                field = forms.BooleanField(initial=True, label=label,
                                           required=False)
                field_items.append((job_id, field))
                # Remember the label for the field.
                label_field = forms.CharField(widget=forms.HiddenInput(),
                                              initial=label)
                label_field_name = '{job_id}-label'.format(job_id=job_id)
                field_items.append((label_field_name, label_field))
            return field_items

        def gen_html_parts(self):
            # Generate the hidden HTML.
            hidden_form = CustomFieldsForm(self._hidden_fields,
                                           self._hidden_data)
            self.hidden_html = hidden_form.as_table()

            # Generate HTML for the old jobs part.
            old_jobs_form = CustomFieldsForm(self._old_job_fields,
                                             self._old_data)
            old_jobs_form.is_valid()
            self.old_jobs_html = old_jobs_form.as_table()

            # Generate HTML for the active jobs part.
            active_jobs_form = CustomFieldsForm(self._active_job_fields,
                                                self._active_data)
            active_jobs_form.is_valid()
            self.active_jobs_html = active_jobs_form.as_table()

            # Return an empty string, so that this method can be called from
            # within a template.
            return ''

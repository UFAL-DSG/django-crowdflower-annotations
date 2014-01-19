from django.conf.urls import patterns, url

import settings

pattern_args = ['',
                url('^transcribe$',
                    'transcription.views.transcribe',
                    name='transcribe'),

                url('^open_annotations$',
                    'transcription.views.open_annions',
                    name='open_annions'),

                url('^static/(?P<path>.*)$',
                    'django.views.static.serve'),

                url('^data/recs/(?P<path>.*)$',
                    'django.views.static.serve',
                    {'document_root': settings.CONVERSATION_DIR}),

                url('^finished$',
                    'transcription.views.finished',
                    name="finished"),

                url('^import$',
                    'transcription.views.import_dialogues',
                    name="import_dialogues"),

                url('^delete$',
                    'transcription.views.delete_list',
                    name="delete_dialogues"),

                url('^stats$',
                    'transcription.views.dialogue_stats',
                    name="dialogue_stats"),
                ]

if settings.DEBUG:
    pattern_args.append(url(r'^test-view$',
                            'transcription.views.temp_test',
                            name="test_view"))

# Only when using Crowdflower:
if settings.USE_CF:
    cf_pattern_args = [url('^create-jobs$',
                           'transcription.views.create_job_view',
                           name="create_jobs"),
                       url('^delete-jobs$',
                           'transcription.views.delete_job_view',
                           name="delete_jobs"),
                       url('^collect-reports$',
                           'transcription.views.collect_reports',
                           name="collect_reports"),
                       url('^fill-in-worker-ids$',
                           'transcription.views.fill_in_worker_ids',
                           name="fill_in_worker_ids"),
                       ]
    pattern_args.extend(cf_pattern_args)
    if settings.USE_WEBHOOKS:
        cf_pattern_args = [url('^log-work$',
                               'transcription.views.log_work',
                               name="log_work"),
                           url('^fire-hooks$',
                               'transcription.views.fire_hooks',
                               name="fire_hooks"),
                           url('^reuse-worklogs$',
                               'transcription.views.reuse_worklogs',
                               name="reuse_worklogs"),
                           ]
        pattern_args.extend(cf_pattern_args)

# Displaying the home page is the default.
pattern_args.append(url(r'^',
                        'transcription.views.home',
                        name='home'))

urlpatterns = patterns(*pattern_args)

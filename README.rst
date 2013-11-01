=============
Prerequisites
=============
- Python 2 (version 2.7.3 proven to work)

  ::

    # apt-get install python2.7

- Django (version 1.4.1 proven to work)

  ::

    # pip install Django==1.4.1

  *or* a newer version, such as

  ::

    # pip install Django==1.5.4

- a web server (example relevant configuration is shown for Apache 2) 
  able to handle WSGI

  ::

    # apt-get install libapache2-mod-wsgi


=========================================================
How to set up the transcription environment on the server
=========================================================
1. Update the ``localsettings.py`` config file (create this by copying 
   ``localsettings.py.example``) to suit your environment. Meaning and 
   format of all configuration variables should be clear from the comments 
   in ``localsettings.py.example``.

2. Run ``scripts/setup_script.py``.

3. Set up your webserver to find your new transcription web application.  
   For Apache, this can be done by inserting a snippet like the following to

   ::

     /etc/apache2/sites-available/default

   and

   ::

     /etc/apache2/sites-enabled/000-default

   (which is by default a symlink to the former file)
   below the root ``<VirtualHost>`` element:
 
   ::

     WSGIDaemonProcess app_transcript
     WSGIScriptAlias /apps/transcription /webapps/transcription/trs_site/wsgi.py
     <Location /apps/transcription>
       WSGIProcessGroup app_transcript
     </Location>
 
   This particular configuration would make the Apache webserver associate 
   the ``<hostname>/apps/transcription`` URL with the application directory 
   ``/webapps/transcription``, affecting where the ``wsgi.py`` script and 
   other Python modules used by the app are looked for.

4. Create the database (following is pseudocode, do *not* copy & paste it to 
   your terminal):

   ::

     cd /webapps/transcription && ./manage.py syncdb

   .. _`creating superuser`:

   You may be asked to enter a login, a password, and an email for 
   a superuser account. It is a good idea to do so, unless you want to 
   `Load users from a dump`_.

   Make sure the access permissions are set correctly for directories used 
   by Django.  This can mean you need to issue the following commands, 
   depending on your configured paths:
  
   ::

     # PROJECT_PATH=/webapps/transcription
     # cd $PROJECT_PATH &&\
       chown www-data db/{,trss.db} data/{,conversations,import,lists} log/{curl,work}_logs
  
5. [Optional] Save the name and domain of your new site to the database.  
   The name of the site appears in password-reset emails, and defaults to 
   ``example.com``.
  
   You can change the domain and name of the site using the following 
   commands:
  
   ::

     # cd $PROJECT_PATH && ./manage.py dbshell
     SQL> UPDATE django_site SET name = '<your chosen site name>';
     SQL> UPDATE django_site SET domain = '<your site domain>';
  
6. Collect static files using the following command:
  
   ::

     $ cd $PROJECT_PATH && ./manage.py collectstatic -l

   You may be asked to confirm you want to override existing files. In 
   a clean installation, with the default setting of ``STATIC_ROOT``, this 
   warning is a false alarm. If there were static files collected, they 
   would be overwritten, but there are none.
  
7. Reload the web server, open the site URL, and log in with the superuser 
   account `you created`__.
   
   __ `creating superuser`_


===========================================
How to set up transcription via Crowdflower
===========================================

1. Get yourself an account with Crowdflower (http://crowdflower.com).
  
2. Make sure ``USE_CF`` is set to ``True`` in ``localsettings.py``.  Update 
   all other related configuration, including ``CF_KEY`` (should be 
   provided by Crowdflower for your account).
  
   If you changed ``USE_CF`` or any configuration variables pointing to 
   directories or URLs, you probably have to repeat the previous part.
  
3. Create Crowdflower jobs using the `Create new Crowdflower jobs` item on 
   the main menu. Main menu is what you see when you log in to the site 
   using your web browser.
  
   When you submit the form for creating Crowdflower jobs, the 
   Transcription app will communicate with Crowdflower. You will have to 
   wait for a response for a minute or so.
  
   When successful, you will have new jobs created in your Crowdflower 
   account, and in the Transcription app's database. Dialogue prices will 
   now be associated with corresponding Crowdflower job IDs, and your 
   dialogues will be uploaded to their appropriate job based on the price.
  
   Dialogue prices are computed using the configuration variables 
   ``PRICE_CONST``, ``PRICE_PER_MIN``, and ``PRICE_PER_TURN``. If you 
   change your mind about these constants any time later, you can 
   reconfigure Django and have it recompute dialogue prices by using the 
   `Update Price` action in the `Dialogues` admin view.

4. Prepare gold items. See the howto: `Add more gold`_.

5. Upload dialogues you want to have annotated to Crowdflower. This is done 
   through an action at the `Dialogues` admin page called `Upload to 
   CrowdFlower (only those dialogues that have not been uploaded yet)`.  
   This action uploads the dialogues (their CID and codes) to the 
   Crowdflower job corresponding to their price bin and marks them as gold 
   items if there are any gold transcriptions for them.
   
6. Order your units through the Crowdflower web interface. You want to set 
   the price for each job according to what the title specifies. By 
   default, the title says `price level K` where `K` is one tenth of the 
   calculated job price.

   *Update*: Crowdflower now defaults to ordering your jobs on no channels, 
   which is definitely not what you want. Therefore, when ordering the job,
   don't forget to select the channels where you want your job to be worked 
   on. Also, the workers' skills are now not set up the highest possible by 
   the app (because of a Crowdflower API update), hence you might want to 
   do so manually at the Crowdflower job website.


=======================
How to import dialogues
=======================

1. Make the dialogue log directories available at the server's filesystem.
   If the dialogue logs are on a remote filesystem, you can use the
   ``fetch_dgdir.sh`` script (from the ``scripts`` directory) to achieve 
   this.  The script also creates a list of imported dialogues for you, so 
   you can then skip the next step.
   
   For using the ``fetch_dgdir.sh`` script, you need to:

   1. create a directory with dialogue logs as its immediate children at
      the remote filesystem;
   2. (optional) pack the directory;
   3. run the script at the target server; run the script without
      arguments for usage message.
  
2. Create a text file listing paths towards the log directories, one per 
   line (preferably in ``localsettings.LISTS_DIR``, although whether you 
   put it in this directory or elsewhere, probably has no impact).
  
3. Open the web interface of your application and navigate to dialogue 
   import (through an option in the menu at the first page after login, or 
   through the `Dialogues->Add` option of the Admin app). Specify the path 
   towards the file listing your dialogues, any other options as required, 
   and press the button. Depending on the number of dialogues imported, you 
   might have to wait a considerable amount of time until the page with an 
   import report loads.
  
   If you are using Crowdflower, you can choose to upload all imported 
   dialogues to Crowdflower right away (using the corresponding checkbox in 
   the `Import Dialogues` form) or you can do so any time later using the 
   Upload to Crowdflower action from the `Dialogues` admin page.  There, 
   you will be provided with various filters to help you specify exactly 
   the set of dialogues you wish to have annotated.
  
   Note that the CSV file you are asked to provide name for may be very 
   helpful when the transcriptions are done and you want to delete the 
   dialogue logs from the filesystem. Therefore, you should enter a name for 
   it by which you will be able to recognize what data subset it belongs to.  
   This CSV file is stored in the directory configured as 
   ``CONVERSATION_DIR``.


=================================
How to get data out of the system
=================================

There are two ways to export the data from the database Django uses 
internally:

.. _(A):

A) Make a database dump.

.. _(B):

B) Export the dialogue logs.


---------------------------
Dumping the Django database
---------------------------
`(A)`_ is done by simply running the script ``scripts/dumpdata.sh``. This 
exports the data from the Transcription app and data about the Django 
users, to the ``data/dumps`` directory in the JSON format.

This is a good option to backup your data (they can be loaded again using 
``./manage.py loaddata dump.json``) but not the right option if you want to 
further process the transcriptions. In the latter case, follow the option 
`(B)`_.


-----------------------
Exporting dialogue logs
-----------------------
`(B)`_ is done from the Admin site (`Admin` option in the main menu). See 
`How to export`_ below for details.

Before you export
~~~~~~~~~~~~~~~~~
There are two mechanisms to track workers:

A) Crowdflower webhooks

B) cookies.

Crowdflower webhooks should track workers more smartly but they do not work 
as smoothly as plain cookies. Anyway, it is good to try to take the best of 
both. The app implements two special actions for this purpose:

1. reconstructing missing worker IDs from stored cookie data

2. firing Crowdflower webhooks for gold items (which are not ever fired by 
   default).

Thus, when you are finished with a batch of transcriptions, you should run 
these two actions. The former is accessible from the Main menu as 
`Reconstruct worker IDs`, and takes some time to complete – please be 
patient waiting for the page to reload. The same applies for the latter 
action. The link's name is `Fire hooks for gold items`. This action should 
not be triggered before the formerly mentioned one, as the assignment of 
worker IDs to annotations is based on a heuristic and may be faulty.

How to export
~~~~~~~~~~~~~
Go to the Admin site (`Admin` option in the main menu) for Dialogues (click 
the link `Dialogues` at the main admin page).  Select dialogues you wish to 
export using the checkboxes left of dialogue names, possibly with the help 
of filters or the search field.  (Note also the `Select all N dialogues` 
link right of the search field if you check the checkbox in the header 
row.) From the `Action` rolldown menu, select the `Export annotations` 
option and click `Go`.  The dialogue logs with annotations will be exported 
to ``data/export``.  Check the message at the top of the page that loads 
after the export is done for the exact path to the annotated logs 
directory.

After you export
~~~~~~~~~~~~~~~~
After you have exported the data, you probably want to copy them back to 
the dialogue directories, possibly on a remote server. You can use the 
``scripts/copyback_transcriptions.sh`` script for copying the XML logs back 
to their directories after you put them back to the target server. You will 
see the script's usage instructions by running it without arguments.

Note that by exporting the data, you do *not* remove them either from the 
app's database nor from the filesystem. There is a dedicated view for doing 
exactly this, accessible from the main menu through the `Delete dialogues` 
option. After selecting the option, you will be asked for selecting the 
file list from which the dialogues you wish to remove came from. When you 
submit the form, the dialogues will be removed from the 
``settings.CONVERSATION_DIR`` directory and from the app's database, 
*including all recordings and annotations*. Therefore, double-check that 
you have all your data copied to a safe place before you submit this form.  
Check also the following paragraphs.

**BEFORE YOU REMOVE THE DATA** from the database, you might want to measure 
work done for all the annotators, unless a different awarding scheme is in 
force. Use the `Transcriptions` admin page and the `Measure work done` 
action to get a report about the amount of work done by each annotator.

You may also want to export all dialogues with transcriptions currently 
marked as gold. Do that by setting the `By gold status` filter in
`Admin -> Dialogues` to `true`, selecting all the dialogues after filtering 
and choosing the `Export logs (annotations and audio)` action. The logs 
will be exported to ``settings.EXPORT_DIR`` (``data/export`` by default).


=============
Random howtos
=============

How to...

----------------------
Load users from a dump
----------------------
If you are starting an application with a new database where you had 
a running application earlier with users you want to have in the new 
application too, you can simply copy them from the original installation to 
the new one.

First, you need to have a dump of users of the original app. This can be 
easily obtained by running ``scripts/dumpdata.sh``. This scripts writes 
dumps of the database to ``data/dumps/TIMESTAMP_trss-dump.json`` and 
``data/dumps/TIMESTAMP_trss_users-dump.json``. The latter is needed to 
copy users, the earlier contains all information about dialogues, 
transcriptions etc.

The dump is loaded to the new application easily by running its 
``manage.py`` script like so:

  ::

  $ ./manage.py loaddata path-to-the-data-dump

-----------------------------------
Monitor a job, adjust gold settings
-----------------------------------
If you open the admin page for `Dialogue annotations`, you will see the 
newest annotations submitted. After clicking an annotation name, you can 
see all related transcriptions and replay the audio.

If you are worried whether your gold items are not too hard, select 
annotations from your workers (100 newest annotations will do) and choose 
the `Show what transcriptions break gold` action. This displays a listing 
of transcriptions that were compared to a gold one. Gold transcriptions are 
in bold. You can go to a `User turn` corresponding to each transcription 
shown on the listing and adjust the gold if needed. Alternatively, you can 
adjust the ``localsettings.MAX_CHAR_ER`` setting. If you do so, you should 
restart your web server for the change to take effect.

If you changed gold statuses of transcriptions or changed the 
``localsettings.MAX_CHAR_ER`` value, you should now re-evaluate what 
transcriptions break gold. This is done from the `Dialogue annotations` 
admin page through the `Update gold breaking statuses` action.

-------------
Add more gold
-------------
The easiest way to add more gold is waiting for workers to transcribe 
a smaller number of dialogues and then just *select* transcriptions that 
are good enough and suitable as gold transcriptions. Start from the 
`Dialogue annotations` admin page, and set the `By breaks gold: has no 
gold` filter. Then, open annotations at random by clicking them, choose 
transcriptions that look suitable to be used as gold (they should be long 
and clear enough; avoid transcriptions that contain non-speech events by 
and large), mark `Is gold` for them and save. Because some workers who want 
to trick the app transcribe only the first turn and then copy it as 
transcriptions to other turns, be sure to *not* mark just the first 
transcription as gold for all dialogues.

You can later check how many gold dialogues you have by selecting the 
appropriate filter at the `Dialogues` admin page. You can tell Crowdflower 
about your new gold items by using the `Update dialogue gold status on CF` 
action from the `Dialogues` admin page.

When bootstrapping transcriptions for a new domain or language, you start 
with no gold. You may then gather the first few annotations with no gold or 
you may transcribe a few dialogues yourself to create gold. Anyway, if you 
start from the lowest price bins with the transcriptions, you can use you 
gold transcriptions as gold for higher price bins. Do this by selecting the 
lower price bin (one you have gold transcriptions for), and `By gold 
status: true` filters in the `Dialogues` admin view, selecting the 
dialogues shown, and choosing the `Upload to Crowdflower (to a higher price 
class)` action.

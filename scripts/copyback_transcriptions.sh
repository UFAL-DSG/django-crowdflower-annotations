#!/bin/bash
# This script copies back logs with transcriptions to the directory 
# containing the original logs. The new logs are renamed and placed beside 
# the original logs, overwriting is avoided.
#
# 2013-10-16
# Matěj Korvas

# Parameters.
: ${NEW_XML_NAME:=asr_transcribed.xml}
: ${OLD_XML_NAME:='*.xml'}

# Useful constants.
QUIT="return 2>/dev/null || exit"
usage="Usage: $0 <exported_dir> <target_dir>

Copies XML files containing transcribed audio from <exported_dir> to 
<target_dir>.  They will be detected as files named 'session.xml' and 
renamed to '$NEW_XML_NAME' in the process.  File overwriting is 
avoided.

If another name for the new logs is desired (the default being 
\"asr_transcribed.xml\"), export it in the environment variable 
NEW_XML_NAME, like this (in bash):

	NEW_XML_NAME=new_session_name.xml ./copyback_transcriptions.sh a b

or like this

	export NEW_XML_NAME=new_session_name.xml
	./copyback_transcriptions.sh a b

Similarly, OLD_XML_NAME can be set to a glob to match filenames of the log 
files from <exported_dir>. The default for OLD_XML_NAME is '*.xml'.

This script relies on the \`rename' implementation that uses Perl regexes."

# Check the command-line arguments.
if [[ $# != 2 ]]; then
	echo "$usage"
	eval $QUIT
fi

# Directory constants.
SCRIPT_DIR="$(dirname "$(readlink -e "$0")")"
TGT_DIR="`readlink -e $2`"

# Do the work.
find "$1" -name "$OLD_XML_NAME" -exec \
	rename 's/\/[^\/]+$/\/'"$NEW_XML_NAME/" '{}' \+
cd "$1" &&\
	find . -name "$NEW_XML_NAME" -exec cp -pvn --parents '{}' "$TGT_DIR" \;

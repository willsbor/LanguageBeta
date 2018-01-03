import gspread
import os
import io
import subprocess
import shutil
import re
import sys
import getopt
import json
import ConfigParser
import ssl
from datetime import date
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from distutils.version import LooseVersion, StrictVersion

COL_SHIFT = 7
KEYS_COLUMN = 0
DEFAULT_VALUES_COLUMN = KEYS_COLUMN + COL_SHIFT
GROUP_LOCATION_COLUMN = 2
GROUP_NAME_COLUMN = 3
LANGUAGE_CODE_ROW = 0
RENAME_COLUMN = 1
START_VERSION_COLUMN = 4
END_VERSION_COLUMN = 5

CURRENT_MARKET_VERSION = ""

# p = subprocess.Popen(['pwd'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
# DEFAULT_PATH, err = p.communicate()
# DEFAULT_PATH = DEFAULT_PATH.replace("\n","")
# DEFAULT_PATH = DEFAULT_PATH + '/result/'
# print DEFAULT_PATH

SKIP_KEYS = ['CFBundleShortVersionString']
SEARCH_FILE_SKIP_DIR_NAMES = ['.git', '.DS_Store', 'Pods']
WORKING_SPREAD_NAME = 'gspread'
PROJECT_GIT_REPO = 'repo url ssh or https'
PROJECT_GIT_BRANCH = 'master'

# Copy your credentials from the console
CLIENT_ID = '...'
CLIENT_SECRET = '...'
DEFAULT_GROUP_LOCATION = '...'
DEFAULT_GROUP = '...'

# Check https:https://developers.google.com/google-apps/spreadsheets/authorize
OAUTH_SCOPE = 'https://spreadsheets.google.com/feeds https://docs.google.com/feeds'
# Redirect URI for installed apps
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'


def toWPString(content):
    return content

def get_immediate_subdirectories(a_dir):
    return [name for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name))]

def find_string_file(a_dir, a_extension_name='.strings'):
    result = []
    for name in os.listdir(a_dir):
        full_path = os.path.join(a_dir, name)
        #print name
        #print full_path
        if os.path.isdir(full_path):
            if not name in SEARCH_FILE_SKIP_DIR_NAMES:
                result.extend(find_string_file(full_path,a_extension_name))
        elif name.endswith(a_extension_name):
            #print 'find ' + name
            result.append(full_path)
    return result

def copy_project_files(a_project_temp_dir, a_prject_dir, a_extension_names = ['.strings']):
    if os.path.exists(a_project_temp_dir):
        shutil.rmtree(a_project_temp_dir)

    os.makedirs(a_project_temp_dir)

    all_strings_files = []
    for ext_name in a_extension_names:
        all_strings_files.extend(find_string_file(a_prject_dir + "/", ext_name))

    # copy
    for path in all_strings_files:
        dst = path.replace(a_prject_dir, a_project_temp_dir + "/")
        directory = os.path.dirname(dst)
        if not os.path.exists(directory):
            os.makedirs(directory)
        shutil.copyfile(path, dst)

def get_project_string_key_index_comment(a_project_temp_dir):
    all_strings_files = find_string_file( a_project_temp_dir + "/")
    refKeyIndex = {}
    refKeyKey = {}
    refKeyValue = {}
    refKeyComment = {}
    for path in all_strings_files:
        # print 'reading ' + path
        names = path.replace(a_project_temp_dir + "/", '').split('/')
        group_name = names[-1].replace('.strings', '')
        lang = names[-2].replace('.lproj', '')
        group_location = "/".join(names[:-2])
        
        if group_location not in refKeyIndex:
            refKeyIndex[group_location] = {}
        if group_location not in refKeyKey:
            refKeyKey[group_location] = {}
        if group_location not in refKeyValue:
            refKeyValue[group_location] = {}
        if group_location not in refKeyComment:
            refKeyComment[group_location] = {}

        if group_name not in refKeyIndex[group_location]:
            refKeyIndex[group_location][group_name] = {}
        if group_name not in refKeyKey[group_location]:
            refKeyKey[group_location][group_name] = {}
        if group_name not in refKeyValue[group_location]:
            refKeyValue[group_location][group_name] = {}
        if group_name not in refKeyComment[group_location]:
            refKeyComment[group_location][group_name] = {}

        if lang not in refKeyIndex[group_location]:
            refKeyIndex[group_location][group_name][lang] = {}
        if lang not in refKeyKey[group_location]:
            refKeyKey[group_location][group_name][lang] = []
        if lang not in refKeyValue[group_location]:
            refKeyValue[group_location][group_name][lang] = []
        if lang not in refKeyComment[group_location]:
            refKeyComment[group_location][group_name][lang] = []

        index = 0
        with open(path) as f:
            content = f.readlines()
            comment = ''
            for line in content:
                if line.startswith('"'):
                    key, value = line.split("\" = \"", 2)
                    key = key[1:]
                    value = value[:-3]
                    refKeyIndex[group_location][group_name][lang][key] = index
                    refKeyKey[group_location][group_name][lang].append(key)
                    refKeyValue[group_location][group_name][lang].append(value)
                    refKeyComment[group_location][group_name][lang].append(comment)
                    comment = ''
                    index += 1
                else:
                    comment += line

    return refKeyIndex, refKeyKey, refKeyValue, refKeyComment

def getGroupLocationWithDefault(string):
    if string == '':
        return DEFAULT_GROUP_LOCATION
    else:
        return string

def getGroupWithDefault(string):
    if string == '':
        return DEFAULT_GROUP
    else:
        return string

def decode_value(string):
    string = re.sub(r"^'", "^", string)
    return string.replace('\\\'', '\'').replace("\n", "\n")

def more_decode_value_for_strings(string):
    return string.replace("\n", "\\n").replace("\"", "\\\"")

def encode_value_for_strings(string):
    string = string.replace('\'', '\\\'').replace("\\n", "\n").replace("\\\"", "\"")
    return re.sub(r"^", "'", string)

def jsons_to_one_file(a_input_dir, a_output_filename):
    all_json_files = find_string_file( a_input_dir + "/", '.json')

    lang_group_key_value = {}
    for path in all_json_files:
        #print 'reading ' + path
        names = path.replace(a_input_dir + "/", '').split('/')
        group_name = names[-1].replace('.json', '')
        lang = names[-2].replace('.lproj', '')
        group_location = "/".join(names[:-2])

        data = {}
        with open(path) as f:
            data = json.load(f)

        if lang not in lang_group_key_value:
            lang_group_key_value[lang] = {}
        lang_group_key_value[lang][group_name] = data

    with open(a_output_filename, 'w') as outfile:
        json.dump(lang_group_key_value, outfile)

def openGC():
  # Create a credential storage object.  You pick the filename.
    storage = Storage('a_credentials_file_2')

  # Attempt to load existing credentials.  Null is returned if it fails.
    credentials = storage.get()

    if not credentials:
        print "request new access token"
        # Run through the OAuth flow and retrieve credentials
        flow = OAuth2WebServerFlow(CLIENT_ID, CLIENT_SECRET, OAUTH_SCOPE,
                                   redirect_uri=REDIRECT_URI)
        authorize_url = flow.step1_get_authorize_url()
        print 'Go to the following link in your browser: ' + authorize_url
        code = raw_input('Enter verification code: ').strip()
        credentials = flow.step2_exchange(code)
        storage.put(credentials)

    if sys.version_info >= (2, 7, 9):
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context

    gc = gspread.authorize(credentials)
    return gc

def get_keys_map_to_new_name_keys(a_sheet_name):
    gc = openGC()
    wk = gc.open(WORKING_SPREAD_NAME)
    try:
        wks = wk.worksheet(a_sheet_name)
    except:
        print "error for wks"
        return
    rowCount = wks.row_count
    colCount = wks.col_count
    list_of_lists = wks.get_all_values()

    oldkey_to_newkey = {}
    old_key_set = []
    new_key_set = []
    for r in range(2, rowCount):
        try:
            key = list_of_lists[r][KEYS_COLUMN]
            rename = list_of_lists[r][RENAME_COLUMN]
            group_location = getGroupLocationWithDefault(list_of_lists[r][GROUP_LOCATION_COLUMN])
            group_name = getGroupWithDefault(list_of_lists[r][GROUP_NAME_COLUMN])
        except:
            break

        if key is '' or key is None:
            continue
        if key[0] == '#':
            continue
        if key in SKIP_KEYS:
            print "skip key = " + real_key
            continue

        if rename is None or rename == "":
            continue

        if group_location is '' or group_location is None:
            group_location = 'empty'

        if group_name is '' or group_name is None:
            group_name = 'Localizable'

        group_name_key = group_location + ";|;" + group_name + ";|;" + key
        group_name_rename = group_location + ";|;" + group_name + ";|;" + rename
        if group_name_key not in old_key_set:
            if group_name_rename not in new_key_set:
                if group_name_rename in old_key_set:
                    print "there shouldn't be the same rename [" + group_name_rename + "] of keys [" + group_name_key + "] in old key set"
                    return
                if group_name_key in new_key_set:
                    print "there shouldn't be the same rename [" + group_name_key + "] in old key set"
                    return

                old_key_set.append(group_name_key)
                new_key_set.append(group_name_rename)
                oldkey_to_newkey[group_name_key] = group_name_rename
            else:
                print "there shouldn't be the same rename [" + group_name_rename + "] of keys [" + group_name_key + "]"
                return
        else:
            print "there shouldn't be the same keys [" + group_name_key + "]"
            return

    return oldkey_to_newkey
        
def exportStrings(a_sheet_name, a_output_dir, a_project_temp_dir, a_output_type='strings'):
    gc = openGC()
    wk = gc.open(WORKING_SPREAD_NAME)
    try:
        wks = wk.worksheet(a_sheet_name)
    except:
        print "error for wks"
        return
    rowCount = wks.row_count
    colCount = wks.col_count
    list_of_lists = wks.get_all_values()
    refKeyIndex, refKeyKey, refKeyValue, refKeyComment = get_project_string_key_index_comment(a_project_temp_dir)

    if os.path.exists(a_output_dir):
        shutil.rmtree(a_output_dir)

    for c in range(COL_SHIFT, colCount):
        try:
            lang = list_of_lists[LANGUAGE_CODE_ROW][c]
        except:
            break
        if lang is not None:

            if lang == 'key':
                continue

            refKeyToBeRemoved = []

            for r in range(2, rowCount):
                try:
                    key = list_of_lists[r][KEYS_COLUMN]
                    group_location = getGroupLocationWithDefault(list_of_lists[r][GROUP_LOCATION_COLUMN])
                    group_name = getGroupWithDefault(list_of_lists[r][GROUP_NAME_COLUMN])
                    start_version = list_of_lists[r][START_VERSION_COLUMN]
                    end_version = list_of_lists[r][END_VERSION_COLUMN]
                except:
                    break

                if key is '' or key is None:
                    continue
                if key[0] == '#':
                    continue
                if key in SKIP_KEYS:
                    print "skip key = " + real_key
                    continue
                if lang not in refKeyIndex[group_location][group_name]:
                    continue

                if start_version != '' and end_version != '' and LooseVersion(start_version) > LooseVersion(end_version):
                    raise ValueError("[%s][%s] last version (%s) is smaller than start_version (%s)" % (r, key, end_version, start_version))

                to_be_removed = False
                if start_version != '' and CURRENT_MARKET_VERSION != '' and LooseVersion(start_version) > LooseVersion(CURRENT_MARKET_VERSION):
                    to_be_removed = True
                if end_version != '' and CURRENT_MARKET_VERSION != '' and LooseVersion(end_version) < LooseVersion(CURRENT_MARKET_VERSION):
                    to_be_removed = True

                if group_location is '' or group_location is None:
                    group_location = 'empty'

                if group_name is '' or group_name is None:
                    group_name = 'Localizable'

                value = toWPString(list_of_lists[r][c])
                #if value is None or value == '':
                #    value = toWPString(list_of_lists[r][DEFAULT_VALUES_COLUMN])

                print "[processing] " + key + " (to_be_removed = " + str(to_be_removed) + ")"
                

                if key in refKeyIndex[group_location][group_name][lang]:
                    key_index = refKeyIndex[group_location][group_name][lang][key]
                    refKeyValue[group_location][group_name][lang][key_index] = decode_value(value.encode('utf-8'))
                    if to_be_removed:
                        refKeyToBeRemoved.append(key_index)
                elif value != '' and value != None:
                    print "append a new key = " + key + " at " + lang + ", " + group_name + ", " + group_location + "with [" + value + "]"
                    refKeyIndex[group_location][group_name][lang][key] = len(refKeyKey[group_location][group_name][lang])
                    refKeyKey[group_location][group_name][lang].append(key)
                    refKeyValue[group_location][group_name][lang].append(decode_value(value.encode('utf-8')))
                    refKeyComment[group_location][group_name][lang].append('\n/* No comment provided by engineer. */\n')
                    if to_be_removed:
                        refKeyToBeRemoved.append(key_index)

            print "[Start to File]"
            for group_location in iter(refKeyKey):
                #print "==> " + group_location
                for group_name in iter(refKeyKey[group_location]):
                    if lang not in refKeyIndex[group_location][group_name]:
                        continue

                    if a_output_type == 'json':
                        filename = a_output_dir + "/" + group_location + "/{0}.lproj/".format(lang) + group_name + ".json"

                        directory = os.path.dirname(filename)
                        if not os.path.exists(directory):
                            os.makedirs(directory)

                        content = {}
                        total = len(refKeyKey[group_location][group_name][lang])
                        for x in range(0, total):
                            if x in refKeyToBeRemoved:
                                continue
                            sub = {}
                            sub['comment'] = refKeyComment[group_location][group_name][lang][x]
                            sub['value'] = refKeyValue[group_location][group_name][lang][x]
                            content[refKeyKey[group_location][group_name][lang][x]] = sub
                        print filename
                        with open(filename, 'w') as outfile:
                            json.dump(content, outfile)
                    else:                        
                        filename = a_output_dir + "/" + group_location + "/{0}.lproj/".format(lang) + group_name + ".strings"
                        directory = os.path.dirname(filename)
                        if not os.path.exists(directory):
                            os.makedirs(directory)

                        print filename
                        # f = io.open(filename, 'w', encoding='utf-8')
                        f = io.open(filename, 'wb')
                        total = len(refKeyKey[group_location][group_name][lang])
                        for x in range(0, total):
                            if x in refKeyToBeRemoved:
                                continue
                            content = refKeyComment[group_location][group_name][lang][x] + '\"' + refKeyKey[group_location][group_name][lang][x] + '\" = \"' + more_decode_value_for_strings(refKeyValue[group_location][group_name][lang][x]) + '\";\n'
                            f.write(content)
                        if total > 0:
                            f.write('\n')
                        f.close()


def copy_back_to_project_files(a_from_dir, a_to_project_dir, a_extension_names = ['.strings']):

    if os.path.exists(a_from_dir):
        print "start back to project from " + a_from_dir + '/ to ' + a_to_project_dir
        # all_strings_files = find_string_file(a_from_dir + '/')
        all_strings_files = []
        for ext_name in a_extension_names:
            all_strings_files.extend(find_string_file(a_from_dir + "/", ext_name))

        # copy
        for path in all_strings_files:
            dst = path.replace(a_from_dir + "/", a_to_project_dir)
            if os.path.exists(dst):
                shutil.copyfile(path, dst)
            else:
                print "file is not existed [" + path + " => " + dst + "]"
                # directory = os.path.dirname(dst)
                # if not os.path.exists(directory):
                #     os.makedirs(directory)
                

def read_all_reference_data(a_project_temp_dir):
    all_strings_files = find_string_file(a_project_temp_dir + "/")
    refKeyValue = {}
    refValueKeys = {}
    refPathValue = {}
    for path in all_strings_files:
        # print 'reading ' + path
        names = path.replace(a_project_temp_dir + "/", '').split('/')
        group_name = names[-1].replace('.strings', '')
        lang = names[-2].replace('.lproj', '')
        group_location = "/".join(names[:-2])
        # print group_name + ';' + group_location + ';' + lang
        with open(path) as f:
            content = f.readlines()
            for line in content:
                if line.startswith('"'):
                    key, value = line.split("\" = \"", 2)
                    key = key[1:]
                    value = value[:-3]
                    #print "[" + key + ";" + value + "]"
                    if lang not in refValueKeys:
                        refValueKeys[lang] = {}
                    if lang not in refKeyValue:
                        refKeyValue[lang] = {}

                    value = re.sub(r"\s", "", value)
                    if value not in refValueKeys[lang]:
                        refValueKeys[lang][value] = []
                    group_name_key = group_location + ";|;" + group_name + ";|;" + key
                    refValueKeys[lang][value].append(group_name_key)
                    refKeyValue[lang][group_name_key] = value
                    refPathValue[group_name_key] = [group_location, group_name]
    return refKeyValue, refValueKeys, refPathValue

def read_all_reference_data_type2(a_project_temp_dir):
    all_strings_files = find_string_file(a_project_temp_dir + "/")
    refKeyValue = {}
    for path in all_strings_files:
        # print 'reading ' + path
        names = path.replace( a_project_temp_dir + "/", '').split('/')
        group_name = names[-1].replace('.strings', '')
        lang = names[-2].replace('.lproj', '')
        group_location = "/".join(names[:-2])
        # print group_name + ';' + group_location + ';' + lang
        with open(path) as f:
            content = f.readlines()
            for line in content:
                if line.startswith('"'):
                    key, value = line.split("\" = \"", 2)
                    key = key[1:]
                    value = value[:-3]
                    group_name_key = group_location + ";|;" + group_name + ";|;" + key
                    #print "[" + group_name_key + ";" + value + "]"
                    if group_name_key not in refKeyValue:
                        refKeyValue[group_name_key] = {}
                        refKeyValue[group_name_key]["key"] = key
                        refKeyValue[group_name_key]["group location"] = group_location
                        refKeyValue[group_name_key]["group"] = group_name

                    refKeyValue[group_name_key][lang] = value
    return refKeyValue

def read_all_reference_data_type3(a_project_temp_dir):
    all_strings_files = find_string_file(a_project_temp_dir + "/")
    refKeyValue = {}
    for path in all_strings_files:
        # print 'reading ' + path
        names = path.replace( a_project_temp_dir + "/", '').split('/')
        group_name = names[-1].replace('.strings', '')
        lang = names[-2].replace('.lproj', '')
        group_location = "/".join(names[:-2])
        # print group_name + ';' + group_location + ';' + lang
        if lang not in refKeyValue:
            refKeyValue[lang] = {}
        with open(path) as f:
            content = f.readlines()
            for line in content:
                if line.startswith('"'):
                    key, value = line.split("\" = \"", 2)
                    key = key[1:]
                    value = value[:-3]
                    group_name_key = group_location + ";|;" + group_name + ";|;" + key
                    # print "[" + group_name_key + ";" + value + "]"
                    if group_name_key not in refKeyValue[lang]:
                        refKeyValue[lang][group_name_key] = {}
                        refKeyValue[lang][group_name_key]["key"] = key
                        refKeyValue[lang][group_name_key]["group location"] = group_location
                        refKeyValue[lang][group_name_key]["group"] = group_name
                        refKeyValue[lang][group_name_key]["value"] = []

                    refKeyValue[lang][group_name_key]["value"].append(value)
                    
    return refKeyValue

def keys_string_to_map(a_keystring):
    group_location = 'melmanSharediOS/Localization'
    group_name = 'Localizable'
    lang = 'en'
    keys = a_keystring.strip().split(',')

    refKeyValue = {}
    if lang not in refKeyValue:
            refKeyValue[lang] = {}
    for key in keys:
        key = key.strip()
        group_name_key = group_location + ";|;" + group_name + ";|;" + key
        if group_name_key not in refKeyValue[lang]:
            refKeyValue[lang][group_name_key] = {}
            refKeyValue[lang][group_name_key]["key"] = key
            refKeyValue[lang][group_name_key]["group location"] = group_location
            refKeyValue[lang][group_name_key]["group"] = group_name
            refKeyValue[lang][group_name_key]["value"] = []

        refKeyValue[lang][group_name_key]["value"].append(key)

    return refKeyValue

def search_key_and_replace(key_name_map, project_path, ext_filetypes):
    files = []
    for ext_name in ext_filetypes:
        files.extend(find_string_file(project_path + "/", ext_name))

    files_context = {}
    # open file and got matched line
    for group_name_key in iter(key_name_map):
        group_name_rename = key_name_map[group_name_key]

        real_key = group_name_key.split(";|;")[-1]
        real_rename = group_name_rename.split(";|;")[-1]

        if real_rename == real_key:
            continue

        real_key = real_key.replace("[", "\[")
        real_key = real_key.replace("]", "\]")
        real_key = real_key.replace("@", "\@")
        real_key = real_key.replace("%", "\%")
        real_key = real_key.replace(")", "\)")
        real_key = real_key.replace("(", "\(")
        real_key = real_key.replace("$", "\$")

        regex = re.compile(r"([@]?\")" + real_key + "\"")
        #print "real_key = " + real_key
        is_hit = False
        for path in files:
            #print "path = " + path
            if path not in files_context:
                files_context[path] = open(path).read()

            new_string = regex.sub(r'\1' + real_rename + "\"", files_context[path])

            if new_string != files_context[path]:
                files_context[path] = new_string
                is_hit = True
            #result = regex.findall(files_context[path])
            #if len(result) > 0:
            #    print "result = " + str(result)

        if not is_hit:
            print "!!! Can't find Key: " + group_name_key

    for path in iter(files_context):
        #print "path = " + path
        with open(path, 'w') as f:
            f.write(files_context[path])

def update_list_from_key_to_new_key(a_sheet_name, a_key_map):
    gc = openGC()
    wk = gc.open(WORKING_SPREAD_NAME)
    try:
        wks = wk.worksheet(a_sheet_name)
    except:
        print "error for wks"
        return

    rowCount = wks.row_count
    colCount = wks.col_count
    list_of_lists = wks.get_all_values()

    row_size = len(list_of_lists)
    for x in range(1, row_size):
        try:
            list_key = list_of_lists[x][KEYS_COLUMN]
            list_group_location = getGroupLocationWithDefault(list_of_lists[x][GROUP_LOCATION_COLUMN])
            list_group_name = getGroupWithDefault(list_of_lists[x][GROUP_NAME_COLUMN])
        except:
            break

        if len(list_key) == 0 or list_key[0] == '#':
            continue

        group_name_key = list_group_location + ";|;" + list_group_name + ";|;" + list_key
        if group_name_key in a_key_map:
            group_name_rename = a_key_map[group_name_key]
            real_rename = group_name_rename.split(";|;")[-1]
            wks.update_cell(x + 1, KEYS_COLUMN + 1, real_rename)
            wks.update_cell(x + 1, RENAME_COLUMN + 1, "")
     
def get_key_index(list_of_lists):
    list_group_name_key_index = {}
    row_size = len(list_of_lists)
    for x in range(1, row_size):
        try:
            key = list_of_lists[x][KEYS_COLUMN]
            group_location = getGroupLocationWithDefault(list_of_lists[x][GROUP_LOCATION_COLUMN])
            group_name = getGroupWithDefault(list_of_lists[x][GROUP_NAME_COLUMN])
        except:
            break
        if key is '' or key is None:
            continue
        group_name_key = group_location + ";|;" + group_name + ";|;" + key
        list_group_name_key_index[group_name_key] = x
        #print "[[[" + group_name_key + "]]] = " + str(x)
    return list_group_name_key_index

def update_values_to_new_worksheet(a_sheet_name, a_project_temp_dir, a_force_update_value=False):
    refKeyValue = read_all_reference_data_type3(a_project_temp_dir)
    _update_values_to_new_worksheet(a_sheet_name, refKeyValue, a_force_update_value)

def _update_values_to_new_worksheet(a_sheet_name, refKeyValue, a_force_update_value=False):
    gc = openGC()
    wk = gc.open(WORKING_SPREAD_NAME)
    try:
        wks = wk.worksheet(a_sheet_name)
    except:
        print "error for wks"
        return

    rowCount = wks.row_count
    colCount = wks.col_count
    list_of_lists = wks.get_all_values()
    list_group_name_key_index = get_key_index(list_of_lists)
    # refKeyValue = read_all_reference_data_type3(a_project_temp_dir)
    
    list_size = len(list_of_lists)
    list_done_count = 0
    free_index = list_size + 5
    print_add_key_title = False
    print "free_index = " + str(free_index)

    for c in range(COL_SHIFT, colCount):
        try:
            full_language_code = list_of_lists[LANGUAGE_CODE_ROW][c]
        except:
            break

        if full_language_code not in refKeyValue:
            continue

        for group_name_key in iter(refKeyValue[full_language_code]):
            list_done_count += 1
            # print "group_name_key = " + group_name_key + "(" + str(list_done_count) + "/" + str(list_size) + ")"

            real_key = group_name_key.split(";|;")[-1]
            # CFBundleShortVersionString
            if real_key in SKIP_KEYS:
                print "skip key = " + real_key
                continue

            if group_name_key in list_group_name_key_index:
                # update
                realrow = list_group_name_key_index[group_name_key]
                try:
                    list_key = list_of_lists[realrow][KEYS_COLUMN]
                    list_group_location = getGroupLocationWithDefault(list_of_lists[realrow][GROUP_LOCATION_COLUMN])
                    list_group_name = getGroupWithDefault(list_of_lists[realrow][GROUP_NAME_COLUMN])
                    list_lang_value = list_of_lists[realrow][c]
                except:
                    break
                if list_group_location != refKeyValue[full_language_code][group_name_key]["group location"].decode('utf-8'):
                    print "update group location for " + str(realrow + 1)
                    wks.update_cell(realrow + 1, GROUP_LOCATION_COLUMN + 1, refKeyValue[full_language_code][group_name_key]["group location"])
                if list_group_name != refKeyValue[full_language_code][group_name_key]["group"].decode('utf-8'):
                    print "update group for " + str(realrow + 1)
                    wks.update_cell(realrow + 1, GROUP_NAME_COLUMN + 1, refKeyValue[full_language_code][group_name_key]["group"])

                lang_value = refKeyValue[full_language_code][group_name_key]["value"][0]
                list_lang_value = more_decode_value_for_strings(decode_value(list_lang_value.encode('utf-8'))).decode('utf-8')
                if lang_value.decode('utf-8') != list_lang_value:
                    if (a_force_update_value and list_lang_value != lang_value) or list_lang_value == '' or list_lang_value is None:
                        print "update [" + full_language_code + "] for " + str(realrow + 1) + " with new value = " + lang_value
                        wks.update_cell(realrow + 1, c + 1, encode_value_for_strings(lang_value).decode('utf-8'))

                values_len = len(refKeyValue[full_language_code][group_name_key]["value"])
                if values_len > 1:
                    for x in range(1,values_len):
                        value = encode_value_for_strings(refKeyValue[full_language_code][group_name_key]["value"][x]).decode('utf-8')
                        free_index, print_add_key_title = local_update_cell_with_new_key(wks, c, free_index, print_add_key_title, group_name_key, full_language_code, "### duplicate " + str(x) + " ###" + real_key, refKeyValue, value)

            else:
                value = encode_value_for_strings(refKeyValue[full_language_code][group_name_key]["value"][0]).decode('utf-8')
                free_index, print_add_key_title = local_update_cell_with_new_key(wks, c, free_index, print_add_key_title, group_name_key, full_language_code, real_key, refKeyValue, value)
                
                values_len = len(refKeyValue[full_language_code][group_name_key]["value"])
                if values_len > 1:
                    for x in range(1,values_len):
                        value = encode_value_for_strings(refKeyValue[full_language_code][group_name_key]["value"][x]).decode('utf-8')
                        free_index, print_add_key_title = local_update_cell_with_new_key(wks, c, free_index, print_add_key_title, group_name_key, full_language_code, "### duplicate " + str(x) + " ###" + real_key, refKeyValue, value)

def local_update_cell_with_new_key(wks, c, free_index, print_add_key_title, group_name_key, full_language_code, real_key, refKeyValue, value):
    if not print_add_key_title:
        print_add_key_title = True
        today = date.today()
        wks.update_cell(free_index, KEYS_COLUMN + 1, "#### add new key on " + today.isoformat() + " ####")
    free_index += 1
    print "this is new key [" + group_name_key + "] at " + str(free_index) + " for " + full_language_code
    wks.update_cell(free_index, KEYS_COLUMN + 1, real_key)
    wks.update_cell(free_index, GROUP_LOCATION_COLUMN + 1, refKeyValue[full_language_code][group_name_key]["group location"])
    wks.update_cell(free_index, GROUP_NAME_COLUMN + 1, refKeyValue[full_language_code][group_name_key]["group"])
    wks.update_cell(free_index, c + 1, value)

    return free_index, print_add_key_title

def update_list_key_mark_no_used(a_sheet_name, a_project_temp_dir):
    gc = openGC()
    wk = gc.open(WORKING_SPREAD_NAME)
    try:
        wks = wk.worksheet(a_sheet_name)
    except:
        print "error for wks"
        return

    rowCount = wks.row_count
    colCount = wks.col_count
    list_of_lists = wks.get_all_values()
    refKeyValue = read_all_reference_data_type2(a_project_temp_dir)
    row_size = len(list_of_lists)
    for x in range(1, row_size):
        try:
            list_key = list_of_lists[x][KEYS_COLUMN]
            list_group_location = getGroupLocationWithDefault(list_of_lists[x][GROUP_LOCATION_COLUMN])
            list_group_name = getGroupWithDefault(list_of_lists[x][GROUP_NAME_COLUMN])
        except:
            break

        if len(list_key) == 0 or list_key[0] == '#':
            continue

        group_name_key = list_group_location + ";|;" + list_group_name + ";|;" + list_key
        if group_name_key not in refKeyValue:
            print "marked " + group_name_key + " at row = " + str(x + 1)
            wks.update_cell(x + 1, KEYS_COLUMN + 1, "##" + list_key)

def main(argv):
    config = ConfigParser.ConfigParser()
    config.read('config.ini')
    global CLIENT_ID
    global CLIENT_SECRET
    global WORKING_SPREAD_NAME
    global PROJECT_GIT_REPO
    global PROJECT_GIT_BRANCH
    global DEFAULT_GROUP_LOCATION
    global DEFAULT_GROUP
    global CURRENT_MARKET_VERSION
    WORKING_SPREAD_NAME = config.get('parse_language', 'WORKING_SPREAD_NAME')
    CLIENT_ID = config.get('parse_language', 'CLIENT_ID')
    CLIENT_SECRET = config.get('parse_language', 'CLIENT_SECRET')
    DEFAULT_GROUP_LOCATION = config.get('parse_language', 'DEFAULT_GROUP_LOCATION')
    DEFAULT_GROUP = config.get('parse_language', 'DEFAULT_GROUP')
    DEFAULT_EXPORT_SHEET = config.get('parse_language', 'DEFAULT_EXPORT_SHEET')
    
    try:
        PROJECT_GIT_REPO = config.get('parse_language', 'PROJECT_GIT_REPO')
        PROJECT_GIT_BRANCH = config.get('parse_language', 'PROJECT_GIT_BRANCH')
    except ConfigParser.NoOptionError:
        pass
    else :
        pass


    print CLIENT_ID
    print CLIENT_SECRET
    print WORKING_SPREAD_NAME
    print PROJECT_GIT_REPO
    print PROJECT_GIT_BRANCH

    project_path = ''

    project_temp_dir = 'project_string'
    export_sheet = DEFAULT_EXPORT_SHEET
    result_dir = 'result'
    command = ''
    output_format = 'strings'
    input_dir = ''
    forceUpdateToSheet = False
    forceUpdateWorkspaceStrings = False
    commit_message=''
    keys = ''
    try:
        #opts, args = getopt.getopt(argv,"hi:o:",["ifile=","ofile="])
        opts, args = getopt.getopt(argv,
            "ho:p:eumf:j:ak:v:",
            ["output=","project=","exportSheet","updateSheet","markUnusedKey","forceUpdateProjectStrings=","json","mergeJsonfiles=","forceUpdateToSheet","force-update-workspcae-strings","add-keys-to","keys=","rename","market-version="])
    except getopt.GetoptError:
        print 'error: parse.py wrong command'
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
           print 'parse.py ????'
           sys.exit()
        elif opt in ("-e", "--exportSheet"):
            command = 'e'
        elif opt in ("-u", "--updateSheet"):
            command = 'u'
        elif opt in ("-m", "--markUnusedKey"):
            command = 'm'
        elif opt in ("-f", "--forceUpdateProjectStrings"):
            command = 'f'
            commit_message = arg
        elif opt in ("-j", "--mergeJsonfiles"):
            command = 'j'
            input_dir = arg
        elif opt in ("-v", "--market-version"):
            CURRENT_MARKET_VERSION = arg
        elif opt in ("--json"):
            print 'setting to json'
            output_format = 'json'
        elif opt in ("-o", "--output"):
            result_dir = arg
        elif opt in ("-p", "--project"):
            project_path = arg
        elif opt in ("--forceUpdateToSheet"):
            forceUpdateToSheet = True
        elif opt in ("--force-update-workspcae-strings"):
            forceUpdateWorkspaceStrings = True
        elif opt in ("-a", "--add-keys-to"):
            command = 'a'
        elif opt in ("-k", "--keys"):
            keys = arg
        elif opt in ("--rename"):
            command = 'r'
    
    if command not in ['', 'j', 'a'] and project_path == '' and (PROJECT_GIT_REPO != '' and PROJECT_GIT_BRANCH != ''):
        print 'using ' + project_path + ', and updating by Git ...'
        errcode = os.system("git clone " + PROJECT_GIT_REPO + " --branch " + PROJECT_GIT_BRANCH + " --single-branch workspace")
        if errcode != 0:
            os.system("cd workspace && git reset --hard HEAD");
            os.system("cd workspace && git pull origin " + PROJECT_GIT_BRANCH);
        project_path = 'workspace/'
    else :
        print 'using \"' + project_path + '\" without updating by Git'

    if command not in ['', 'f', 'j'] and export_sheet == '':
        print 'need [export_sheet]'
        sys.exit(2)

    if command == 'e':
        print 'prject dir = ' + project_path
        print "project temp dir = " + project_temp_dir
        print "export sheet = " + export_sheet
        copy_project_files(project_temp_dir, project_path)
        exportStrings(export_sheet, result_dir, project_temp_dir, output_format)
        if forceUpdateWorkspaceStrings:
            copy_back_to_project_files(result_dir, project_path)
        if output_format == 'json':
            jsons_to_one_file(result_dir, 'test_strings.json')
    elif command == 'u':
        print 'prject dir = ' + project_path
        print "update sheet = " + export_sheet
        print "result dir = " + result_dir
        print "forceUpdateToSheet = " + str(forceUpdateToSheet)
        copy_project_files(project_temp_dir, project_path)
        update_values_to_new_worksheet(export_sheet, project_temp_dir, forceUpdateToSheet)
    elif command == 'm':
        print 'prject dir = ' + project_path
        print "update sheet = " + export_sheet
        copy_project_files(project_temp_dir, project_path)
        update_list_key_mark_no_used(export_sheet, project_temp_dir)
    elif command == 'f':
        print "result dir = " + result_dir
        print 'prject dir = ' + project_path

        today = date.today()

        os.system("cd workspace && git branch localization-" + today.isoformat());
        os.system("cd workspace && git checkout localization-" + today.isoformat());
        copy_back_to_project_files(result_dir, project_path)
        os.system("cd workspace && git commit -a -m \"" + commit_message + "\"");
        os.system("cd workspace && git push origin localization-" + today.isoformat());
        os.system("cd workspace && git reset --hard HEAD");
        os.system("cd workspace && git checkout " + PROJECT_GIT_BRANCH);

    elif command == 'j':
        print "input dir = " + input_dir
        print "output filename = " + result_dir
        jsons_to_one_file(input_dir, result_dir)
    elif command == 'a':
        print "update sheet = " + export_sheet
        new_key_map = keys_string_to_map(keys)
        _update_values_to_new_worksheet(export_sheet, new_key_map)
    elif command == 'r':
        print "rename the keys, and replace all the keys in the project"
        print 'prject dir = ' + project_path
        print "project temp dir = " + project_temp_dir
        print "export sheet = " + export_sheet
        copy_project_files(project_temp_dir, project_path, [".m", ".swift"])
        key_name_map = get_keys_map_to_new_name_keys(export_sheet)
        if key_name_map is not None:
            #print "key_name_map = " + str(key_name_map)
            search_key_and_replace(key_name_map, project_temp_dir, [".m", ".swift"])

            copy_back_to_project_files(project_temp_dir, project_path, [".m", ".swift"])
            update_list_from_key_to_new_key(export_sheet, key_name_map)


   
if __name__ == "__main__":
   main(sys.argv[1:])

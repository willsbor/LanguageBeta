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
from datetime import date

COL_SHIFT = 4
KEYS_COLUMN = 0
DEFAULT_VALUES_COLUMN = KEYS_COLUMN + COL_SHIFT
GROUP_LOCATION_COLUMN = 1
GROUP_NAME_COLUMN = 2
LANGUAGE_CODE_ROW = 0


# p = subprocess.Popen(['pwd'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
# DEFAULT_PATH, err = p.communicate()
# DEFAULT_PATH = DEFAULT_PATH.replace("\n","")
# DEFAULT_PATH = DEFAULT_PATH + '/result/'
# print DEFAULT_PATH

SKIP_KEYS = ['CFBundleShortVersionString']
SEARCH_FILE_SKIP_DIR_NAMES = ['.git', '.DS_Store', 'Pods']
LOGIN_ACCOUNT = 'account'
LOGIN_PASSWORD = 'xxxxxxx'
WORKING_SPREAD_NAME = 'gspread'
PROJECT_GIT_REPO = 'repo url ssh or https'
PROJECT_GIT_BRANCH = 'master'


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

def copy_project_files(a_project_temp_dir, a_prject_dir):
    if os.path.exists(a_project_temp_dir):
        shutil.rmtree(a_project_temp_dir)

    all_strings_files = find_string_file(a_prject_dir)
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


def exportStrings(a_sheet_name, a_output_dir, a_project_temp_dir, a_output_type='strings'):
    gc = gspread.login(LOGIN_ACCOUNT, LOGIN_PASSWORD)
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

            for r in range(2, rowCount):
                try:
                    key = list_of_lists[r][KEYS_COLUMN]
                    group_location = list_of_lists[r][GROUP_LOCATION_COLUMN]
                    group_name = list_of_lists[r][GROUP_NAME_COLUMN]
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

                if group_location is '' or group_location is None:
                    group_location = 'empty'

                if group_name is '' or group_name is None:
                    group_name = 'Localizable'

                

                value = toWPString(list_of_lists[r][c])
                #if value is None or value == '':
                #    value = toWPString(list_of_lists[r][DEFAULT_VALUES_COLUMN])

                if key in refKeyIndex[group_location][group_name][lang]:
                    key_index = refKeyIndex[group_location][group_name][lang][key]
                    refKeyValue[group_location][group_name][lang][key_index] = decode_value(value.encode('utf-8'))
                elif value != '' and value != None:
                    print "append a new key = " + key + " at " + lang + ", " + group_name + ", " + group_location + "with [" + value + "]"
                    refKeyIndex[group_location][group_name][lang][key] = len(refKeyKey[group_location][group_name][lang])
                    refKeyKey[group_location][group_name][lang].append(key)
                    refKeyValue[group_location][group_name][lang].append(decode_value(value.encode('utf-8')))
                    refKeyComment[group_location][group_name][lang].append('\n/* No comment provided by engineer. */\n')

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
                            content = refKeyComment[group_location][group_name][lang][x] + '\"' + refKeyKey[group_location][group_name][lang][x] + '\" = \"' + more_decode_value_for_strings(refKeyValue[group_location][group_name][lang][x]) + '\";\n'
                            f.write(content)
                        if total > 0:
                            f.write('\n')
                        f.close()



def copy_back_to_project_files(a_from_dir, a_to_project_dir):
    if os.path.exists(a_from_dir):
        print "start back to project from " + a_from_dir + '/ to ' + a_to_project_dir
        all_strings_files = find_string_file(a_from_dir + '/')
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

def create_new_worksheet(a_sheet_name):
    gc = gspread.login(LOGIN_ACCOUNT, LOGIN_PASSWORD)
    wk = gc.open(WORKING_SPREAD_NAME)
    try:
        wks = wk.worksheet(a_sheet_name)
    except:
        wks = wk.add_worksheet(a_sheet_name, 1000, 32)

    index = 1
    for value in ["key", "group location", "group", "description", "en", "zh-Hant", "ja", "ko", "pt", "Th"]:
        print "[" + str(index) + ";" + value + "]"
        wks.update_cell(1, index, value)
        index += 1
     
def get_key_index(list_of_lists):
    list_group_name_key_index = {}
    row_size = len(list_of_lists)
    for x in range(1, row_size):
        try:
            key = list_of_lists[x][KEYS_COLUMN]
            group_location = list_of_lists[x][GROUP_LOCATION_COLUMN]
            group_name = list_of_lists[x][GROUP_NAME_COLUMN]
        except:
            break
        if key is '' or key is None:
            continue
        group_name_key = group_location + ";|;" + group_name + ";|;" + key
        list_group_name_key_index[group_name_key] = x
        #print "[[[" + group_name_key + "]]] = " + str(x)
    return list_group_name_key_index

def update_values_to_new_worksheet(a_sheet_name, a_project_temp_dir):
    gc = gspread.login(LOGIN_ACCOUNT, LOGIN_PASSWORD)
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
    refKeyValue = read_all_reference_data_type2(a_project_temp_dir)
    
    list_size = len(list_of_lists)
    list_done_count = 0
    free_index = list_size + 5
    print "free_index = " + str(free_index)
    for group_name_key in iter(refKeyValue):
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
                list_group_location = list_of_lists[realrow][GROUP_LOCATION_COLUMN]
                list_group_name = list_of_lists[realrow][GROUP_NAME_COLUMN]
            except:
                break
            if list_group_location != refKeyValue[group_name_key]["group location"].decode('utf-8'):
                print "update group location for " + str(realrow + 1)
                wks.update_cell(realrow + 1, GROUP_LOCATION_COLUMN + 1, refKeyValue[group_name_key]["group location"])
            if list_group_name != refKeyValue[group_name_key]["group"].decode('utf-8'):
                print "update group for " + str(realrow + 1)
                wks.update_cell(realrow + 1, GROUP_NAME_COLUMN + 1, refKeyValue[group_name_key]["group"])
            
            for c in range(COL_SHIFT, colCount):
                try:
                    full_language_code = list_of_lists[LANGUAGE_CODE_ROW][c]
                    list_lang_value = list_of_lists[realrow][c]
                except:
                    break
                if full_language_code in refKeyValue[group_name_key]:
                    lang_value = refKeyValue[group_name_key][full_language_code]
                    list_lang_value = more_decode_value_for_strings(decode_value(list_lang_value.encode('utf-8'))).decode('utf-8')
                    if lang_value.decode('utf-8') != list_lang_value:
                        print "update [" + full_language_code + "] for " + str(realrow + 1) + " with new value = " + lang_value
                        wks.update_cell(realrow + 1, c + 1, encode_value_for_strings(lang_value).decode('utf-8'))
        else:
            free_index += 1
            print "this is new key [" + group_name_key + "] at " + str(free_index)
            wks.update_cell(free_index, KEYS_COLUMN + 1, real_key)
            wks.update_cell(free_index, GROUP_LOCATION_COLUMN + 1, refKeyValue[group_name_key]["group location"])
            wks.update_cell(free_index, GROUP_NAME_COLUMN + 1, refKeyValue[group_name_key]["group"])
            for c in range(COL_SHIFT, colCount):
                try:
                    full_language_code = list_of_lists[LANGUAGE_CODE_ROW][c]
                except:
                    break
                if full_language_code in refKeyValue[group_name_key]:
                    wks.update_cell(free_index, c + 1, encode_value_for_strings(refKeyValue[group_name_key][full_language_code]).decode('utf-8'))


def update_list_key_mark_no_used(a_sheet_name, a_project_temp_dir):
    gc = gspread.login(LOGIN_ACCOUNT, LOGIN_PASSWORD)
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
            list_group_location = list_of_lists[x][GROUP_LOCATION_COLUMN]
            list_group_name = list_of_lists[x][GROUP_NAME_COLUMN]
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
    global LOGIN_ACCOUNT
    global LOGIN_PASSWORD
    global WORKING_SPREAD_NAME
    global PROJECT_GIT_REPO
    global PROJECT_GIT_BRANCH
    LOGIN_ACCOUNT = config.get('parse_language', 'LOGIN_ACCOUNT')
    LOGIN_PASSWORD = config.get('parse_language', 'LOGIN_PASSWORD')
    WORKING_SPREAD_NAME = config.get('parse_language', 'WORKING_SPREAD_NAME')
    PROJECT_GIT_REPO = config.get('parse_language', 'PROJECT_GIT_REPO')
    PROJECT_GIT_BRANCH = config.get('parse_language', 'PROJECT_GIT_BRANCH')

    print LOGIN_ACCOUNT
    print LOGIN_PASSWORD
    print WORKING_SPREAD_NAME
    print PROJECT_GIT_REPO
    print PROJECT_GIT_BRANCH

    project_path = ''

    project_temp_dir = 'project_string'
    export_sheet = ''
    result_dir = 'result'
    command = ''
    output_format = 'strings'
    input_dir = ''
    try:
        #opts, args = getopt.getopt(argv,"hi:o:",["ifile=","ofile="])
        opts, args = getopt.getopt(argv,"ho:p:e:c:u:m:fj:",["output=","project=","exportSheet=","createSheet=","updateSheet=","markUnusedKey=","forceUpdateProjectStrings","json","mergeJsonfiles="])
    except getopt.GetoptError:
        print 'error: parse.py wrong command'
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
           print 'parse.py ????'
           sys.exit()
        elif opt in ("-e", "--exportSheet"):
            command = 'e'
            export_sheet = arg
        elif opt in ("-c", "--createSheet"):
            command = 'c'
            export_sheet = arg
        elif opt in ("-u", "--updateSheet"):
            command = 'u'
            export_sheet = arg
        elif opt in ("-m", "--markUnusedKey"):
            command = 'm'
            export_sheet = arg
        elif opt in ("-f", "--forceUpdateProjectStrings"):
            command = 'f'
        elif opt in ("-j", "--mergeJsonfiles"):
            command = 'j'
            input_dir = arg
        elif opt in ("--json"):
            print 'setting to json'
            output_format = 'json'
        elif opt in ("-o", "--output"):
            result_dir = arg
        elif opt in ("-p", "--project"):
            project_path = arg
    
    if command not in ['', 'j'] and project_path == '':
        errcode = os.system("git clone " + PROJECT_GIT_REPO + " --branch " + PROJECT_GIT_BRANCH + " --single-branch workspace")
        if errcode != 0:
            os.system("cd workspace && git reset --hard HEAD");
            os.system("cd workspace && git pull origin " + PROJECT_GIT_BRANCH);
        project_path = 'workspace/'

    if command not in ['', 'f', 'j'] and export_sheet == '':
        print 'need [export_sheet]'
        sys.exit(2)

    if command == 'e':
        print 'prject dir = ' + project_path
        print "project temp dir = " + project_temp_dir
        print "export sheet = " + export_sheet
        copy_project_files(project_temp_dir, project_path)
        exportStrings(export_sheet, result_dir, project_temp_dir, output_format)
        if output_format == 'json':
            jsons_to_one_file(result_dir, 'test_strings.json')
    elif command == 'c':
        print "create sheet = " + export_sheet
        create_new_worksheet(export_sheet)
    elif command == 'u':
        print 'prject dir = ' + project_path
        print "update sheet = " + export_sheet
        print "result dir = " + result_dir
        copy_project_files(project_temp_dir, project_path)
        update_values_to_new_worksheet(export_sheet, project_temp_dir)
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
        os.system("cd workspace && git push origin localization-" + today.isoformat());
        os.system("cd workspace && git reset --hard HEAD");
        os.system("cd workspace && git checkout " + PROJECT_GIT_BRANCH);

    elif command == 'j':
        print "input dir = " + input_dir
        print "output filename = " + result_dir
        jsons_to_one_file(input_dir, result_dir)

   
if __name__ == "__main__":
   main(sys.argv[1:])

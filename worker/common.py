import subprocess
import os
import time
import json
import shutil
from datetime import datetime
try:
    import local_functions as functions
except:
    import aws_functions as functions

EMAIL_TIMEOUT = 30 # time after which an email will be sent, in seconds
tmp_directory = '/tmp/'

def log(start, message):
    now = time.time()
    elapsed = round(now - start, 2)
    print(elapsed, message)
    return now


def getInputFiles(body):

    if not body.get("inputFiles"):
        return None

    with open('packages/' + body.get('method') + '.json') as json_file:
        package = json.load(json_file)

    inputFiles = {}

    user = functions.get_user_table_id(body["userId"])
    filepath = os.path.join(tmp_directory, user, body["requestId"])

    if not os.path.exists(filepath):
        os.makedirs(filepath)

    for key, filename in body.get("inputFiles").items():
        if key not in package.get("inputFiles"):
            continue

        inputFiles[key] = os.path.join(filepath, filename)

        # get file
        with open(inputFiles[key], 'wb') as fd:
            functions.download_file(body["userId"], filename, fd)

    return inputFiles, filepath


def prepareCommand(request, inputFiles):
    try:
        with open('packages/' + request.get('method') + '.json') as json_file:
            package = json.load(json_file)
    except:
        sys.exit("Package does not exist")
        return

    if not package:
        sys.exit("Package does not exist")
        return

    command = [w.replace('packages/', os.getcwd() + '/packages/')
               for w in package.get("cmd")]

    for key, value in inputFiles.items():
        if key in package.get("inputFiles"):
            command += [key, value]

    params = package.get("params")

    if request.get("params"):
        for param, value in request.get("params").items():
            if param not in params:
                print("Not in")
                continue
            if isinstance(params[param], bool):
                if value:
                    command.append(param)
            elif value != "":
                command.append(param)
                command.append(str(value))

    outputFiles = package.get("outputFiles")

    return command, outputFiles


def runCommand(command, filepath):
    # run cmd and clean it
    output = subprocess.run(
        command,
        timeout=functions.TIMEOUT,
        check=True,
        capture_output=True,
        cwd=filepath).stdout.decode().replace('\r', '').replace('\n', '')

    return output


def uploadResults(body, outputFilenames, output, filepath):

    item = {
        'done': True,
        'errors': False,
        'method': body.get('method')
    }

    if output:
        item["output"] = functions.parse_output(output)

    if outputFilenames:
        item["pending"] = True
    else:
        item["pending"] = False

    item["inputFiles"] = body.get("inputFiles")
    
    updated = functions.writeOutput(item, body["userId"], body.get("requestId"))

    if not updated:
        return False

    filesToUpload = {}

    for fileName, content in outputFilenames.items():
        datasetId = body["requestId"] + "_" + fileName
        newDatasetId = os.path.join(filepath, datasetId)
        datasetName = body["requestName"] + "_" + fileName

        # Get attributes that depend on input file
        original = content.pop("original", {})
        for fileKey, info in original.items():
            id = body.get("inputFiles").get(fileKey)
            table = info.get("table", None)
            data = functions.get_metadata(table, body["userId"], id)
            for attribute in info.get("attributes"):
                content[attribute] = data.get(attribute)

        table = content.pop("table", None)
        result = functions.post_metadata(
            table,
            body["userId"],
            body["requestId"],
            datasetId,
            datasetName,
            content
        )

        filesToUpload[fileName] = result

        os.rename(os.path.join(filepath, fileName), newDatasetId)
        with open(newDatasetId, 'rb') as data:
            functions.upload_file(data, body["userId"], result["datasetId"])

    functions.update_result(filesToUpload, body["userId"], body["requestId"])


    if body.get("notification"):
        email(body.get("address"), body.get("link") + body.get("requestId"), True, body.get("time"))

    return True


def cleanup(filepath):
    shutil.rmtree(filepath)


def email(address, link, result, requestTime):

    requestTime = datetime.fromisoformat(requestTime)
    now = datetime.utcnow()

    if (now - requestTime).total_seconds() < EMAIL_TIMEOUT or not address:
        return

    sender = "MAESTRO <{}>".format(os.environ.get("DEFAULT_EMAIL"))

    if result:
        subject = "Your result is ready!"
        body = "Check it at " + link + "."
    else:
        subject = "Your request failed"
        body = "Check the logs at " + link + "."

    functions.send_email(address, body, subject, sender)


def writeError(body, error):
    item = {
        'done': True,
        'errors': True,
        'output': error
    }

    response = functions.writeOutput(item, body["userId"], body.get("requestId"))

    if response and body.get("notification"):
        email(body.get("address"), body.get("link") + body.get("requestId"), False, body.get("time"))


def exec(event):
    start = log(time.time(), event)

    try:
        inputFiles, filepath = getInputFiles(event)
        command, outputFilenames = prepareCommand(event, inputFiles)
    except Exception as e:
        log(start, e)
        writeError(event, ["There was an error in your request input"])
        return

    start = log(start, "Command prepared")

    try:
        output = runCommand(command, filepath)
    except subprocess.CalledProcessError as e:
        error = e.stderr.decode().replace('\r', '').splitlines()
        log(start, "runCommand error")
        writeError(event, error)
        return
    except subprocess.TimeoutExpired:
        log(start, "runCommand timedout")
        error = "Your request took too long to process"
        writeError(event, error)
        return

    start = log(start, "Program ran")

    try:
        uploaded = uploadResults(event, outputFilenames, output, filepath)
        if not uploaded:
            log(start, "Result was already there")
            return
        start = log(start, "Files uploaded")

        cleanup(filepath)
        log(start, "Files cleaned")
    except Exception as e:
        log(start, "ERROR" + str(e))
        return

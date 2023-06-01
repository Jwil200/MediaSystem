# Project 2 Imports
import pymongo
import argparse
import csv
import os
import datetime

# Project 3 Imports
import subprocess
import json
import xlsxwriter
import sys
from datetime import timedelta

parser = argparse.ArgumentParser()

parser.add_argument("--files", nargs='+', required=False)
parser.add_argument("--xytech", type=str, required=False)
parser.add_argument("--verbose", action="store_true")
parser.add_argument("--output", type=str, choices=["DB", "CSV"], required=False)
parser.add_argument("--process", type=str, required=False)
parser.add_argument("--ignore_storage", action="store_true")
args_ = parser.parse_args()

def vprint(contents):
    if args_.verbose:
        print(contents)

def subrun(command):
    command.append("-v")
    if args_.verbose:
        command.append("error")
    else:
        command.append("verbose") # Silence
    return subprocess.run(command, capture_output=True, text=True).stdout

def dbOut(args):
    # Do this at the start just to make sure the client can connect.
    client = None
    if args.output == "DB":
        client = pymongo.MongoClient("mongodb://localhost:27017/")

    if (args.xytech is None or args.output is None):
        print("Invalid args.")
        return

    # Get all the files
    files_dict = {}
    for file in args.files:
        file_info = file[:len(file)-4].split("_")
        files_dict[file] = {
            "type": file_info[0],
            "name": file_info[1],
            "date": file_info[2],
            "frames": []
        }

    vprint(args)
    vprint(files_dict)

    # Returns a tuple with a dictionary and an array
    # The dictionary has the Xytech producer, operator, etc.
    # The array has the set of folders to look through
    def read_xytech(contents):
        dict = {
            'producer': 'None',
            'operator': 'None',
            'job': 'None',
            'notes': 'None'
        }
        arr = []
        notesFound = False
        locationsFound = False
        for line in contents:
            if (locationsFound):
                if (line.strip(" ") == "\n"):
                    locationsFound = False
                    continue
                arr.append(line[:-1])
            elif (notesFound):
                dict["notes"] = line[:-1]
                notesFound = False
            elif (line.startswith("Producer")):
                dict["producer"] = line[10:][:-1] # Remove Producer and remove line end
            elif (line.startswith("Operator")):
                dict["operator"] = line[10:][:-1]
            elif (line.startswith("Job")):
                dict["job"] = line[5:][:-1]
            elif (line.startswith("Notes")):
                notesFound = True
            elif (line.startswith("Location")):
                locationsFound = True
        return dict, arr

    # Converts baselight information into a dictionary
    # This dictionary contains the filepath as the key
    # The value of each is an array of frames
    # We cutout the first folder since that one seems
    # to usually be the movie folder
    def baselight_to_dict(contents):
        dict = {}
        for line in contents:
            line = line[line.index("/", 1):][:-1]
            splice = line.split(" ")
            path_name = splice[0]
            if path_name not in dict:
                dict[splice[0]] = []
            dict[path_name].append(splice[1:])
        return dict

    # Gets the proper prefix for each folder name
    # from the Xytech folder list
    def get_prefix_length(xytech, baselight):
        xytech = xytech.split("/")[1:]
        baselight = baselight.split("/")[1:][0]
        prefix = "/"
        for dir in xytech:
            if dir == baselight:
                break
            prefix += dir + "/"
        return len(prefix[:-1])

    # Gets the last valid frame in the list of frames
    # Returns that value
    def last_valid_frame(frames):
        frames = frames[::-1]
        for frame in frames:
            if frame.isnumeric():
                return int(frame)
        return 0

    # Creates groups of frames based on asscending order
    # Individual frames are solo in the groups.
    def group_frames(frames):
        arr = []
        start_frame = 0
        curr_frame = -1
        last_frame = last_valid_frame(frames)
        for frame in frames:
            if frame.isnumeric():
                frame = int(frame)
                # Base State
                if curr_frame == -1:
                    curr_frame = frame
                    start_frame = curr_frame
                    # Very very bad solution, but it works.
                    # Covers last edge case of single frame in list.
                    if curr_frame == last_frame:
                        arr.append(str(start_frame))
                    continue
                # Actual 
                curr_frame += 1
                if curr_frame != frame:
                    curr_frame -= 1
                    if (curr_frame == start_frame):
                        arr.append(str(start_frame))
                    else:
                        final_frame = curr_frame
                        arr.append(str(start_frame) + "-" + str(final_frame))
                    if (frame == last_frame):
                        arr.append(str(frame))
                        start_frame = frame
                        curr_frame = frame
                elif frame == last_frame:
                    arr.append(str(start_frame) + "-" + str(frame))
                else:
                    # Skip if not numeric
                    continue
        return arr


    # Converts a Flames file into a Baselight file.
    # This will make it easier to work with as we can then just
    # send the Flames file down the Baselight pipeline.
    def flamesToBaselight (file):
        with open("flame.txt", "w") as tfile:
            for line in file:
                tfile.write("/prefix/{}".format(line[line.index(" ")+1:]))
        with open("flame.txt") as tfile:
            return baselight_to_dict(tfile.readlines())


    # Get dictionary of lines from baselight for working later
    def read_file(file_name, type):
        dict = {}
        try:
            with open(file_name) as file:
                if type == "Baselight":
                    dict = baselight_to_dict(file.readlines())
                elif type == "Flame":
                    dict = flamesToBaselight(file.readlines())
                else:
                    if args.verbose:
                        print("Error: Unknown file type {}.".format(type))
        except EnvironmentError:
            print("Error reading file: " + args.files)
            exit(0)
        return dict

    # Setting up some variables for later
    line1 = [] # Information for line1
    line4 = {} # Information for line4+
    locations = [] # Locations of folders
    baselight_dict = {} # Baselight dictionary for later
    prefix = None
    prefix_length = 0

    # Get dictionary of stuff from Xytech file for first line values
    try:
        with open(args.xytech) as file:
            dict, locations = read_xytech(file.readlines())
            line1 = dict.values()
    except EnvironmentError:
        print("Error reading file: " + args.files)
        exit(0)

    # Sorting function to sort by frame value.
    def frame_val(e):
        frame = e[1]
        if "-" in frame:
            return int(frame[0:frame.index("-")])
        return int(frame)

    # Run through each file in the dictionary.
    # This will be each of the baselight and flame inputs.
    for file in files_dict:
        line4 = {} # Information for line4+
        type = files_dict[file]['type']
        dict = read_file(file, type)
        for location in locations:
            prefix_length = get_prefix_length(location, list(dict.keys())[0])
            if location[prefix_length:] not in dict:
                continue
            frames_list = dict[location[prefix_length:]]
            for frames in frames_list:
                if location not in line4:
                    line4[location] = []
                line4[location] += group_frames(frames)
        location_frame = []
        for location in locations:
            if location not in line4:
                continue
            for frameset in line4[location]:
                location_frame.append([location, frameset])
        location_frame.sort(key=frame_val)
        files_dict[file]['frames'] = location_frame

    vprint(files_dict)

    if args.output == "DB":
        # Write to MongoDB
        db = client["production"]

        # Data Prep
        line1 = list(line1)

        # Collections
        submissions = db["submissions"]
        data = db["data"]

        # Submission Entry
        current_user = os.getlogin()
        submitted_date = str(datetime.datetime.now().date()).replace("-","") # Timestamp
        for file in files_dict:
            submissions.insert_one({
                "user": current_user,
                "machine": files_dict[file]['type'],
                "user_on_file": files_dict[file]['name'],
                "date_on_file": files_dict[file]['date'],
                "submission_date": submitted_date
            })

        # Data Entry
        for file in files_dict:
            for frameset in files_dict[file]['frames']:
                data.insert_one({
                    "name": files_dict[file]['name'],
                    "date": files_dict[file]['date'],
                    "location": frameset[0],
                    "frames": frameset[1]
                })
    else:
    # Writing to CSV
        with open("output.csv", 'w', newline='') as file:
            writer = csv.writer(file)

            writer.writerow(line1)

            for i in range(2):
                writer.writerow("")

            # Write the ordered list of locations and framesets.
            for file in files_dict:
                for frameset in files_dict[file]['frames']:
                    writer.writerow(frameset)
    print("Done")

def process (args):
    # Check unchecked args.
    if (args.output is None):
        print("Missing output argument.")
        return
    elif (args.output == "DB"):
        print("Database output not implemented.")
        return

    # This function is actually pretty slow, so we use storage in order to speed it up.
    def get_frames(input_video):
        if os.path.isfile("./storage.json") and  not args.ignore_storage:
            with open("./storage.json", "r") as file:
                try:
                    js = json.load(file)
                    if js["name"] == input_video:
                        return int(js["frames"])
                except:
                    vprint("Storage file found but not formatted correctly.")
        result = int(subrun(["ffprobe", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "default=nokey=1:noprint_wrappers=1", input_video]))
        js = {
            "name": input_video,
            "frames": result
        }
        with open("./storage.json", "w") as file:
            json.dump(js, file)
        return result
    
    # Establish connection to DB
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["production"]

    # Get the frames from the current process.
    frames = get_frames(args.process)

    # Search through the DB for frames within the current process.
    data = db["data"].find({})
    itemset = []
    for item in data:
        frame_range = item["frames"].split("-")
        max_frame = int(max(frame_range))
        if len(frame_range) == 1:
            continue
        if max_frame < frames:
            # Append the middle frame so we can use it later.
            item["middle_frame"] = int((int(frame_range[0]) + int(frame_range[1])) / 2)
            itemset.append(item)
    
    # Basic path information.
    output_path = "output.xlsx"
    image_path = "./thumbnails" # Folder where thumbnails will be stored.
    if not os.path.exists(image_path):
        os.makedirs(image_path)

    # Run ffprobe to get the width and height. We'll use this to scale images when writing to xslx.
    output = json.loads(subrun(["ffprobe", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-print_format", "json", args.process]))

    width = output['streams'][0]['width']
    height = output['streams'][0]['height']

    # Run ffprobe to get the FPS of the video so we can create timecodes.
    fps = output = int(json.loads(subrun(["ffprobe", "-print_format", "json", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", args.process]))["streams"][0]["r_frame_rate"].split("/")[0])

    print("File: {} | Width: {} | Height: {} | FPS: {}".format(args.process, width, height, fps))

    def getImage(frame_number, suffix):
        thumbnail_path_name = "{}/image{}.jpg".format(image_path, suffix)
        subrun(["ffmpeg", "-i", args.process, "-vf", "select=gte(n\,{})".format(frame_number), "-vframes", "1", thumbnail_path_name, "-y"]) # -y, overwrite image
        return thumbnail_path_name

    print("Writing...")

    workbook = xlsxwriter.Workbook(output_path)
    worksheet = workbook.add_worksheet()

    worksheet.set_column_pixels("D:D", 96) # Set width of image column.

    x_scale, y_scale = 96 / width, 74 / height

    i = 0
    for item in itemset:
        if not args.verbose:
            percentage = int((i / len(itemset)) * 100)
            progress = int(20 * (percentage / 100)) - 1
            if progress < 0:
                progress = 0
            remaining = int(20 * ((100 - percentage) / 100))
            sys.stdout.write("\rJob ({}/{}) [{}]".format(
                i,
                len(itemset),
                "{}>{}".format(progress * "=", remaining * ".")
            ))
        image = getImage(item["middle_frame"], i)
        worksheet.set_row_pixels(i, 74)
        worksheet.write("A{}".format(i + 1), item["location"]) # Location
        worksheet.write("B{}".format(i + 1), item["frames"]) # Frame Range
        frame_range = item["frames"].split("-")
        worksheet.write("C{}".format(i + 1), "{}-{}".format(str(timedelta(seconds=int(frame_range[0])/output)), str(timedelta(seconds=int(frame_range[1])/output)))) # Timecode
        worksheet.insert_image("D{}".format(i + 1), image, {"x_scale": x_scale, "y_scale": y_scale}) # Image
        i += 1
        sys.stdout.flush()
    
    worksheet.autofit() # Helps make it a bit more readable.
    workbook.close()
    print("\nProcessing Complete.")

# Run the correct program.
if (args_.process is None):
    dbOut(args_)
elif (not args_.process is None):
    process(args_)
else:
    print("Invalid args.")
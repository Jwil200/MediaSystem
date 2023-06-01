# Multimedia System App
This app was made throughout my COMP 467 class. It allows reading of Baselight, Flame, and Xytech information to generate entries into a database, output a CSV report, and create detailed thumbnail reports.

#### Tools Used
- MongoDB Compass
Used to run and test the local compass file.

Baselight, Flame, and Xytech were not used in the project, instead output files were simulated. This promoted some challenges, such as having to work with potentially invalid or unclean data, which in the end made the program more robust.

## Usage
The python file can be run with the following commands:

### --files
Specify individual intake files for Baselight or Flame. Must have a valid file name to intake properly. File names should be in the format ```source_name_date.txt``` where the source is Baselight or Flame.
```
--files Baselight_GLopez_20230325.txt Flame_DFlowers_20230323.txt
```

### --xytech
Specify the input Xytech file.
```
--files Xytech_20230323.txt
```

### --verbose
Including this flag will show console output and progress.

### --output
Used to specify if the program should output to CSV or DB (MongoDB).
```
--output CSV
```

### --process
Instead out outputting will instead process inputs into a thumbnail report. Conflicts with ```--output```.

### --ignore_storage
Allows ignoring of the storage.json file.

## Demo
TBD

<!--[![Watch the video]()]()-->
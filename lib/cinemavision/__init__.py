import os
import sys
import inspect

# Include this smoothstreams folder in sys.path so included libs will import properly
cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
print cmd_folder
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

import content
import sequence
import util

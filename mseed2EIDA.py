"""
mseed2EIDA.py

Created by Alex Rutson, SEIS-UK
Document creation date: 2025/11/12

This script is designed to transfer miniseed datasets from a source to an EIDA Data Centre.

This python3 script is modified from the miniseed2DMC from Earthscope built in the
C Language, and replicates many of its functions and naming conventions.

Please note, this script is not a complete recreation of the miniseed2dmc 
script and some aspects of the original file are missing.

"""
#%% Modules
#### Modules ####


from datetime import datetime
import time

#from tqdm import tqdm # If tqdm is unavailable, comment this and check line 350

import os
import sys
import argparse
from glob import glob

import pandas as pd
import re

from obspy.io.mseed import util
from obspy import UTCDateTime, read

import socket


#%% Parameters
#### Parameters ####

PACKAGE = "miniseed2EIDA"
VERSION = "1.1"


    # TEMPORARY

statefilevar = "statefile"


    # TEMPORARY

workdir = "."

"""

Filelink parameter file used for setting miniseed file variables


"""

class FileParam:
    """
    Creates a class object to define the parameters of the miniseed files.
    Variables:
    name: File name
    size: File size
    offset: Current position in file
    bytecount: number of bytes sent to server
    recordcount: number of records sent to server
    """
    def __init__(self, filename):
        self.name = filename
        self.offset = 0
        self.size = os.path.getsize(filename)        
        self.bytecount = 0
        self.recordcount =0
        

class Tracker:
    """
    This class is used to track the total number of records and bytes
    sent to the remote server during the current instance.
    """
    
    def __init__(self):
        
        self.totalbytes = 0
        self.totalrecords = 0

# Start the record tracker        
tracker = Tracker()


#%% Functions
"""

Functions used in this script


"""


def addfile(filelist):
    """
    Takes a list of miniseed files and creates a list of FileParam class objects.
    
    The FileParam class object is based on the original miniseed2dmc script
    and includes information on the size of the file, the current location
    of the pointer (offset), the number of bytes sent (bytecount), 
    and the records sent (recordcount) to the server.
    
    """

    filelink = list(map(FileParam,filelist))
        # FileParam: Class object defined at the top of the script

    return filelink
   
def addtrace(Traces,filelink):
    """
    Read the metadata of the mseed (filelink) and check against a miniseed 
    trace list (Traces)

    If the metadata is already in the trace list, update the startime and endtime (if required)
    and update samplecount to update with the data sent.

    """
    st = read(filelink.name, headonly=True) # reads only the metadata

    # if current trace (st) exists in TraceList (Traces)
    # Note: This only checks the network, station and channel code
    
    if Traces[['network','station','code']].isin({'network':[st[0].stats.network],
        'station':[st[0].stats.station],'code':[st[0].stats.channel]}
        ).all(axis="columns").any():
        for index, row in Traces.iterrows():
            if (row['network'] == st[0].stats.network) and (row['station'] == st[0].stats.station) and (row['code'] == st[0].stats.channel):
                
                # Update starttime if the Tracelist starttime is greater than current Stream
                if (row['starttime'] > st[0].stats.starttime):
                    Traces.loc[index,'starttime'] = st[0].stats.starttime
                
                # Update endtime if the Tracelist endtime is lesser than current Stream
                if (row['endtime'] < st[0].stats.endtime):
                    Traces.loc[index,'endtime'] = st[0].stats.endtime  
                
                # Update samplecount of how many samples have been sent to the
                # server
                Traces.loc[index,'samplecount'] += st[0].stats.npts  
    
    # if current trace (st) does not exist in TraceList (Traces)
    else:
        new_trace ={
                  'network':st[0].stats.network,
                  'station':st[0].stats.station,      
                  'location':st[0].stats.location,
                  'code':st[0].stats.channel,
                  'starttime':st[0].stats.starttime,
                  'endtime':st[0].stats.endtime,
                  'samplerate':st[0].stats.sampling_rate,
                  'samplecount':st[0].stats.npts
                  }

        Traces.loc[len(Traces)] = new_trace


def get_input_files():
    """
    Retrieve input files from the command line arguments
    
    NOTE:
    Assumes that if -l flag is used, no additional files will be loaded
    """

    lprintf("Retrieving input files")
    if args.send != None:
        with open(args.send) as f:
            filelist = f.read().splitlines()
    elif args.file_or_directory != None:
        filelist = args.file_or_directory
    return filelist


def lprintf(string_format,*arg):
    """
    This is the print log originally used by miniseed2dmc

    string_format = unformated string
    *arg = arguments to go into the unformatted string, must be equal to number 
            of {} in unformatted string

    Example 1:
    input    lprintf("{} {} {} {} {}",1,2,3,4,5)
    output  Wed Nov 12 15:33:31 2025 miniseed2EIDA: 1 2 3 4 5
    
    
    Example 2:

    input    lprintf("{} bytes sent in {} seconds",123,45)
    output    Wed Nov 12 15:36:52 2025 miniseed2EIDA: 123 bytes sent in 45 seconds
    

    formated_string = "{} bytes sent in {} seconds" 

    lprintf(formated_string,123,45)

    """
    
    current_time = datetime.now()

    time_str = current_time.ctime() # e.g. Wed Nov 12 15:21:21 2025
    
    message = string_format.format(*arg) # format the string based on the arg pointer
    
    print("{}".format(time_str),"-",PACKAGE +":", message)


def ms_selection(mseed,selection):
    """
    This function checks the details from the miniseed (mseed) against 
    the selection criteria.
    
    If all the values match the selection return True, otherwise return False

    mseed: miniseed file to be sent
    selection: selection dataframe in the format:
        ('net', 'sta', 'loc', 'chan', 'qual', 'start', 'end')
        
    
    NOTE: 
        The LINUX wildcard "*" in python regex is "()"
    """
    if not isinstance(selection, pd.DataFrame): #!= None:
        # If no selection is defined at the command line, the program will
        # assume that all files need to be sent to the server
        return True
    
    recinf = util.get_record_information(mseed)

    recdict = {"net":recinf["network"],
            'sta':recinf["station"], 
            'loc':recinf["location"], 
            'chan':recinf["channel"], 
            'qual':str(recinf["data_quality_flags"]), 
            'start':recinf["starttime"].format_seedlink(), 
            'end':recinf["endtime"].format_seedlink()
            }

    #

    match = 0
    for index, row in selection.iterrows():
        # For each selection criteria

        for key in recdict:
            # for each key in the miniseed record dictionary

            if re.match(row[key],recdict[key]): # match(pattern,string)
                # If the selection wildcard matches the record string

                match +=1

            # If a specific date range is required
            elif key =="starttime":

                if UTCDateTime(recdict[key]) >= UTCDateTime(row[key]): 
                # if mseed start is higher than/equal to the select start
                    match +=1
            elif key =="endtime":
                if UTCDateTime(recdict[key]) <= UTCDateTime(row[key]):
                # if mseed end is lower than/equal to the select end
                    match +=1


        if match == 7: # 7 means each key has been matched
            #

            Match = True
            break # Match found
        else:
            match = 0
            Match = False
            continue
    
    del(recinf)
    return Match # bool operator to confirm whether to send miniseed

def processparam():
    """
    Function to Process the parameter flags from the command line
    
    By default, the command line needs the host:port and miniseed files
    """
    # Parse the command line arguments
    parser = argparse.ArgumentParser(prog="mseed2EIDA.py", description='Transfer data from a local user to and EIDA node')

    parser.add_argument('hostport', help='EIDA node host and port number in format host:port')

    parser.add_argument('file_or_directory',nargs="*",default=None)
    parser.add_argument('-p', '--pretend', action='store_true', help="Pretend mode: don't connect to the server.")

    parser.add_argument("-s", "--select", help="Choose select file", default=None)

    parser.add_argument("-l","--send", help="Choose list file of mseeds to send", default=None)

    parser.add_argument("-v","--verbose", action='store_true' ,help="verbose")


    args = parser.parse_args()

    return args
    

def recoverstate(statefile, filelist):
    """
    Attempt to recover the statefile of the script if one exists.
    Output is an updated filelist with the correct offset, bytecount and recordcount of sent files
    """
    if not os.path.isfile(statefile):
        # if no statefile is found
        #
        return False

    lprintf('Recovering state')
    
    count = 1 # Linenumber of a file rather than a python array/list
    
    with open(statefile, 'r') as state:
        num_of_lines = len(state.readlines())
        state.seek(0)
        
        # Check all the files in the statefile are accounted for.
        
        for line in state:     # If tqdm isn't available, uncomment this line
        #for line in tqdm(state, total=num_of_lines): # If tqdm isn't available, comment this line

            # for each line in the state file
            fields = line.split()
            # split the line into individual fields 
            filename, offset, size, bytecount, recordcount = fields # assigns field values to variables
            if len(fields) <0:
                # Empty line, most likely the last line
                continue
            if len(fields) < 5:
                # error with the formatiing
                lprintf("Could not parse line %d of state file",count)
                
            
            found = False
            for filelink in filelist:
                if int(filelink.offset) > 0:
                    # Quick check
                    # if file has already been updated from previous 
                    # checks, no need to check details again
                    continue
                
                # Check current File Parameter object values against statefile
                if filelink.name == filename:
                    filelink.offset = int(offset)
                    filelink.bytecount = int(bytecount)
                    filelink.recordcount = int(recordcount)
                    if filelink.size != int(size):
                        lprintf("%s: size has changed since last execution (%lld => %lld)",filename, size, filelink.size)
                
                found = True

            if found !=True:
            
                lprintf("{}: found in state file but not an input file", filename)
                lprintf("Wrong state file?\n\n")
                raise Exception("Please review statefile and input data")

            count +=1 # next line in the statefile
            #
        
        # If the number of input files doesn't match the statefile
            # count -1 as count is used as the linenumber in the previous section
        if (count-1) != len(filelist):
            lprintf("More input files detected than registered in the statefile")
            lprintf("Wrong state or send file?\n\n")
            raise Exception("Please review statefile and input data")
            
            
    return True



def savestate(statefile):

    # open temp statefile
    tmp_file = statefile + ".tmp"
    with open(tmp_file,"w") as fp:
        # write filelist to temporary statefile using 
        # printfilelist function as a template
        
        
        for filename in filelist:
            fp.write("{}\t {}\t {}\t {} \t{}\n".format(
                        filename.name,
                        filename.offset,
                        filename.size,
                        filename.bytecount,
                        filename.recordcount
                        ))

        #

    time.sleep(0.01) # This is to stop a read write error appearing

    # rename temporary state file to statefile
    os.rename(tmp_file,statefile)


def send_mseed(filename, ByteCount=4096): # Keep Bytecount as 4096 unless agreed request with the datacentre
    
    #### Open file and check record information

    recinf = util.get_record_information(filename.name)

    reclen = recinf["record_length"] 

    number_of_records =  recinf["number_of_records"]

    
    #### Check to see if files meet Criteria
    
    if ms_selection(filename.name,selection) == True:
        # After checking the selection file to match the miniseed
        

        sendname = filename.name

        if not args.pretend: # if not a pretend run
            
            
            fl = STREAMID(sendname)
            fl = bytes(fl,'utf-8') # convert the STREAMID/filename to bytes
            
            client.send(fl) # send the filename to the server
            
            # Message is sent back to check the filename/STREAMID is correct
            message = client.recv(1024) # Filename received
            
            message = message.decode()
            if message != "Filename Received":
                raise Exception("Unexpected response from server")
            
            
            lprintf("{} Sending File",filename.name)
            
            with open(sendname,'rb') as f: 
                # rb: read bytes
                
                # with statement helps with memory management and will close when
                # finished.
                
                # Read the first record
                l = f.read(ByteCount)
                
                
                while (l): # while there is data to send in the 
                           # current file
                    try:
                        # Send the miniseed record to the server
                        client.send(l)
                        
                        # update file parameter values
                        filename.bytecount += reclen
                        filename.recordcount += 1
                        filename.offset = f.tell()           
                        
                        # Used at the end of the script to show how
                        # much data has been sent.
                        tracker.totalbytes += reclen
                        tracker.totalrecords += 1
                        
                        # read the next record, 
                        # if there's nothing to read, l will be empty
                        # ending the while loop
                        
                        l = f.read(ByteCount)
                        
                        
                    except:
                        
                        print("error sending {}".format(filename.name))
                        
                        return -1
                
                # Update the statefile with the record data
                savestate(statefile)

                time.sleep(1) # needed during testing.
                
                # Close the miniseed file
                f.close()
                
                # Tells the server not to expect more records for this
                # miniseed.
                client.send(b"FILE-SENT")
                
                
                # Print output to terminal
                lprintf("{}: sent {} bytes in {} records",
                    filename.name,
                    filename.bytecount,
                    filename.recordcount
                    )
                
                del(f)
                
            
        else: # PRETEND MODE
            
            lprintf("{}: (Pretend) sent {} bytes in {} records",
                filename.name,
                filename.size,
                number_of_records
                )

        #### Add files to Trace list for the .sync file
        addtrace(Traces,filename)
        

    
    else: # The miniseed is not in the selection criteria
        # Print selection check to terminal
        lprintf("{}: not in selection criteria",
            filename.name
            )

        
        
    # At this point, the miniseed file should be closed
    
    # Final update of the statefile
    savestate(statefile)
        


def server_connection(hostport):
    
    host, port = hostport.split(":")

    try:
        # Create a client-server connection 
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # socket.AF_INET: IPv4 address family 
        # socket.SOCK_STREAM: byte stream used for the tcp connection
        
        # Connect to the server
        s.connect((host, int(port)))
        
        lprintf("Connected to {}",hostport)
        
        return s 
    
    except socket.error as msg:
        print(msg)
    
    except: 
        print("Error connecting to server")
        sys.exit(1)
        


        
def STREAMID(filename):
    """
    The stream ID that is sent to the server that will enable a more human
    readable filename structure on the server side, while also aiding in managing
    the files sent.
    
    """
    
    st =read(filename, headonly=True) # open the metadata of the miniseed only
    
    starttime = [ "S",
                       st[0].stats.starttime.year,
                       st[0].stats.starttime.julday,
                       st[0].stats.starttime.hour,
                       st[0].stats.starttime.minute,
                       st[0].stats.starttime.second]
    
    starttime = "".join(list(map(str,starttime)))
    
    endtime =[
                       "E",
                       st[0].stats.endtime.year,
                       st[0].stats.endtime.julday,
                       st[0].stats.endtime.hour,
                       st[0].stats.endtime.minute,
                       st[0].stats.endtime.second,
                       ]
    endtime = "".join(list(map(str,endtime)))
    
    stream_list = [st[0].stats.network,
                   st[0].stats.station,
                   st[0].stats.channel,
                   starttime,
                   endtime
                   ]
    
    stream = list(map(str,stream_list))
    
    stream = "-".join(stream)

    return stream
    
    
    


def writesync(mseedtracelist, start, end):
    # Creates a sync file from the tracelist
    
    # Output:
    # NET|STAT||CHAN|YEAR,JULDAY,00:00:00.000000|YEAR,JULDAY,23:59:59.980000||SAMPLERATE|SAMPLECOUNT|||||||YEAR,DAY


    mseedtracelist = mseedtracelist.sort_values(['network','station','code']) 

    nt = datetime.now()
    yearday = F"{nt.year},{nt.timetuple().tm_yday}"

    filename = f"{workdir}/{start.year}-{start.month}-{start.day}T{start.hour}:{start.minute}:{start.second}--{end.year}-{end.month}-{end.day}T{end.hour}:{end.minute}:{end.second}.sync"
    

    with open(filename, "w") as fl:
        # Open the sync file
        header = f"EDC|{yearday}\n" #EIDA DATA CENTRE
        fl.write(header)
        
        # Write each tracelist to the sync file
        for index,row in mseedtracelist.iterrows():
            string = f"{row.network}|{row.station}|{row.location}|{row.code}|{row.starttime.format_seed()}|{row.endtime.format_seed()}||{int(row.samplerate)}|{row.samplecount}|||||||{yearday}\n"

            fl.write(string)



#%% Argument Parser
"""


Argument Parser 


"""


args = processparam() # Process the parameters from the command line (see functions)

print('The server location is: {}'.format(args.hostport))
if args.pretend:
    lprintf('Pretend Mode')


if args.send:
    send =0
    
elif (args.file_or_directory):
    send=0
    
else:
    print("error recovering mseeds")

cwd = os.getcwd() # current working directory
statefile = os.path.join(cwd,statefilevar)

if args.select:
    #
    selection = pd.read_csv(args.select,sep="\s+", 
        names= ('net', 'sta', 'loc', 'chan', 'qual', 'start', 'end'), 
        comment="#")
    
    # Replaces wildcard arguments from Linux notation to python regex
    selection = selection.fillna("*") # Fillna * for linux notation
    selection = selection.replace("*","()") # * wildcard to python regex wildacard
    selection['chan'] = selection['chan'].str.replace("?",".") # single character ? wildcard replaced with single character . (dot) python regex wildacard

else:
    selection=None



filelist = args.file_or_directory

filelist = get_input_files()


#%% Parameter Processing
"""

Processing Parameters

"""


# Process Parameters

# Variable setup



start = datetime.now() # Allows for the runtime to be calculated


# The Traces DataFrame is used to track the network and stations sent to the 
# the server.

Traces = pd.DataFrame({'network':[],'station':[],'location':[],'code':[],
            'starttime':[],'endtime':[],'samplerate':[],
            'samplecount':[]})



# List of all miniseeds to be processed

ms_list =[] # miniseed list
for filename in filelist:
    if os.path.isfile(filename):
        print(os.path.splitext(filename))
        if os.path.splitext(filename)[-1] in [".m",".mseed"]:
            ms_list.append(filename)
    else:
        # go through each directory and subdirectory
        ms_list += [y for x in os.walk(filename) for y in glob(os.path.join(x[0], '*.m'))]
        ms_list += [y for x in os.walk(filename) for y in glob(os.path.join(x[0], '*.mseed'))]

del(filename)

# List is sorted to ensure the mseeds are sent in order and to prevent any being missed

ms_list.sort(reverse=True)
ms_list.reverse()


filelist = addfile(ms_list) # Creates FileParam class objects with attached variables

# Checks whether a statefile exists

if recoverstate(statefile, filelist) == True:
    lprintf("Connection state recovered")


totalbytes = 0        # Counts the amount of data transferred
totalrecords =0        # Counts the number of records sent


#%% Check all sent short cut
"""

Check if all files to be sent have been sent

"""

if len(filelist) == 0:
    print("no files in input")
    sys.exit()


# check if files have already been sent
for filename in filelist: # filelist is a list of FileParam class objects 
    if filename.bytecount != filename.size:
        allsent=False
        break
    elif filename.bytecount == filename.size:
        allsent=True

if allsent:
    lprintf("All data transmitted (based on saved state).")
    sys.exit()

#%% Server Connection
"""

Connecting to server

"""


if not args.pretend:
    client = server_connection(args.hostport)

else:
    lprintf ("Pretend Mode: Connected to %s", args.hostport)



#%% Check Files
"""
Sort through the filelist of file class objects to 
check whether the file has been sent first.

Following this, the file is checked against a selection criteria

After each iteration, the statefile is saved to update whether files have been read

"""


try:

    for filename in filelist: #for filename in ms_list:
        
        ####  Skip file if already sent
        
        if filename.offset == filename.size and not args.pretend:
            lprintf("{} already sent",filename.name)
            continue
        
        
        send_mseed(filename)
    
    if not args.pretend: 
        client.shutdown(socket.SHUT_WR)
    
    print("Finished Sending")
    
        
    
except KeyboardInterrupt:
    if not args.pretend:
        client.close()
        print("Client manually closed connection to the server")

except:
    print("General error sending file")

finally:



    
    #%% Write sync file
    
    end = datetime.now() # Allows for the runtime to be calculated
    
    writesync(Traces,start,end)
    
    
    #%% Final Comments
    
    
    formated_string = "Sent {} bytes in {} records, sent in {} minutes" 
    
    time_taken =end-start
    
    
    
    lprintf(formated_string,tracker.totalbytes,tracker.totalrecords,round(time_taken.seconds/60,2))

    
    if not args.pretend:
        client.close() # If an error occurs in sending the file, the connection
                        # is closed



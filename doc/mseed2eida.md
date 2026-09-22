# mseed2EIDA

1. [Command Line] (#command-line)
1. [Select File] (#select-file)
1. [Send File] (#send-file)

## <a id='command-line'>Command Line Argument</a>
Executing the code
<pre >
miniseed2eida.py host:port [Optional] -s select-file.txt -l send-file.txt
</pre>

## <a id='select-file'>Select File</a>
To “query” the datasets to ensure only the specified data is sent, the “select” file is created by the user to specify the data records that will need to be transferred.

<pre >
#net sta  loc  chan  qual  start             end
IU   ANMO *    BH?
II   *    *    *     Q
IU   COLA 00   LH[ENZ] R
IU   COLA 00   LHZ   *     2008,100,10,00,00 2008,100,10,30,00
</pre>


## <a id='send-file'>Send File</a>

Directories where the miniseed files are found.

<b>Note</b>: Please make sure the absolute path name is included. The program will search through all subdirectories in the defined directories

<pre >
/PROJECT/2000/miniseed/
/PROJECT/2001/miniseed/Station.mseed

</pre>



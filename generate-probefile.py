#!/usr/bin/env python

# Copyright (c) 2016 Ericsson AB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import sys
import re
import argparse
import time

# Print is expensive and can be disabled
do_print=1

time1 = time.time()

if (len(sys.argv) != 5):
    print "Usage: gen-probefile <inputfile.c> <outputfile.c.probed> <probedata.dmce> <constructs.exclude>"
    exit()

# Read constructs exclude file
cxl = open(sys.argv[4])
cxl_buf = cxl.readlines()
cxl.close()

# Pre compiled reg-ex
re_cxl_list = []
for construct in cxl_buf:
    re_cxl_list.append(re.compile(".*" + construct.rstrip() + ".*"))
    if do_print == 1: print ".*{}.*".format(construct.rstrip())

if do_print == 1: print "constructs exclude list: {}".format(len(re_cxl_list))

parsed_c_file = sys.argv[1]

# c++ file?
m_cc = re.match( r'.*\.cc$', parsed_c_file, re.I)
m_cpp = re.match( r'.*\.cpp$', parsed_c_file, re.I)
if (m_cc or m_cpp):
    c_plusplus=1
else:
    c_plusplus=0

parsed_c_file_exp = parsed_c_file
probe_prolog = "(DMCE_PROBE(TBD),"
probe_epilog = ")"

expdb_exptext = []
expdb_linestart = []
expdb_colstart = []
expdb_lineend = []
expdb_colend = []
expdb_elineend = []
expdb_ecolend = []
expdb_in_c_file= []
expdb_tab = []
expdb_exppatternmode = []
expdb_index = 0

cur_lend = 0
cur_cend = 0
cur_tab = 0

lskip = 0
cskip = 0
skip_tab = 0
skip_statement = 0
skip_backtrail = 0
skip_lvalue = 0

lineindex = 0

inside_expression = 0
in_parsed_c_file = 0

probed_lines = []

trailing = 0

lstart = "0"
lend = "0"
cstart = "0"
cend = "0"

last_lstart = "0"
last_cstart = "0"

probes = 0

# Read from stdin
rawlinebuf = sys.stdin.readlines()
linebuf=[]

if do_print == 1: print "Generating DMCE probes"

# Construct list of file lines

rawlinestotal = len(rawlinebuf)

# Pre-filter out general stuff
for line in rawlinebuf:
    if '<<built-in>' in line:
        # Make built-in functions look like lib functions
        finalline = re.sub("<built\-in>", "built_in.h", line)
        linebuf.append(finalline)
    else:
        linebuf.append(line)

linestotal=rawlinestotal

srcline = 0
srccol = 0

# Used for c expression recognition
exppatternlist = ['.*-CallExpr\sHexnumber\s<.*\,.*>.*',
                  '.*-CXXMemberCallExpr\sHexnumber\s<.*\,.*>.*',
                  '.*-ConditionalOperator\sHexnumber\s<.*\,.*>.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\*\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\/\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\-\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\+\'.*',
                  '.*UnaryOperator Hexnumber <.*\,.*>.*\'\+\+\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\&\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\|\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'=\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'<\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'>\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'==\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'!=\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\&\&\'.*',
                  '.*BinaryOperator Hexnumber <.*\,.*>.*\'\|\|\'.*',
                  '.*ReturnStmt Hexnumber <.*\,.*>.*']

re_exppatternlist = []

for exp in exppatternlist:
    re_exppatternlist.append(re.compile(exp))

# Modes:
#  1    Contained space, use as is
#  2    Free, need to look for next
#  x    Free, look for next at colpos + x
exppatternmode = [1,1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,6]

# Escape some characters
parsed_c_file_exp = re.sub("\/", "\/", parsed_c_file_exp)
parsed_c_file_exp = re.sub("\.", "\.", parsed_c_file_exp)
parsed_c_file_exp = re.sub("\-", "\-", parsed_c_file_exp)
parsed_c_file_exp = re.sub("\+", "\+", parsed_c_file_exp)

cf = open(parsed_c_file)
pbuf = cf.readlines()

cf_len = len(pbuf)

if do_print == 1: print "!!!" + parsed_c_file + "!!!"


# Used for parsing the textual AST

re_compile_skip_pos         = re.compile(r'.*<.*\.h:(\d*):(\d*)\,\s.*\.c:(\d*):(\d*)>.*')
re_c_file_start             = re.compile(".*<" + parsed_c_file_exp + ".*")
re_leaving_c_file           = re.compile(", .*\.c:\d+:\d+>")
re_self                     = re.compile(", " + parsed_c_file_exp + ":\d+:\d+>")
re_h_files                  = re.compile(r'.*\.h:\d*:\d*.*')
re_h_file_statement         = re.compile(r'.*\.h:\d*:\d*,\sline:\d*:\d*>.*')
re_parsed_file_statement    = re.compile(r'.*<line:\d*:\d*,\sline:\d*:\d*>.*')
re_self_anywhere            = re.compile(".*" + parsed_c_file_exp + ".*")
re_update_pos_A             = re.compile(r'.*<line:(\d*):(\d*)\,\sline:(\d*):(\d*)>.*')
re_update_pos_B             = re.compile(r'.*<line:(\d*):(\d*)\,\scol:(\d*)>.*')
re_update_pos_C             = re.compile(r'.*<col:(\d*)>.*')
re_update_pos_D             = re.compile(r'.*<col:(\d*)\,\sline:(\d*):(\d*)>.*')
re_update_pos_E             = re.compile(r'.*<col:(\d*)\,\scol:(\d*)>.*')
re_update_pos_F             = re.compile(r'.*<line:(\d*):(\d*)>.*')
re_parsed_c_file            = re.compile(".*\,\s" + parsed_c_file_exp + ".*")
re_lvalue                   = re.compile(".*lvalue.*")

# Used in probe insertion pass
re_regret_insertion         = re.compile(".*case.*DMCE.*:.*")

re_sections_to_skip = []
re_sections_to_skip.append(re.compile(r'.*-VarDecl Hexnumber.*'))
re_sections_to_skip.append(re.compile(r'.*RecordDecl Hexnumber.*'))
re_sections_to_skip.append(re.compile(r'.*EnumDecl Hexnumber.*'))

# Populate c expression database
while (lineindex<linestotal):
    if '<<<NULL>>>' in linebuf[lineindex] or '<<invalid sloc>>' in linebuf[lineindex]:
        lineindex+=1
        continue

    # Addition according to diff file?
    if linebuf[lineindex].startswith("+"):
        is_addition=1
    else:
        is_addition=0

    # Check what tab we are on
    tab = linebuf[lineindex].find("-")
    #Compensate for + if added line in diff
    if (is_addition):
        tab-=1

    # Check if we popped up tab to skip_tab_*
    if (skip_statement and (tab <= skip_statement_tab)):
        skip_statement=0
    if (skip_backtrail and (tab <= skip_backtrail_tab)):
        skip_backtrail=0
    if (skip_lvalue and (tab <= skip_lvalue_tab)):
        skip_lvalue=0

    # If statement is within a .h file, skip all indented statements and expressions
    # CompoundStmt Hexnumber </tmp/epatabe/dmce/inc/internal.h:146:5, line:151:5>
    found_h_file_statement = re_h_file_statement.match(linebuf[lineindex])
    if (found_h_file_statement):
        skip_statement = 1
        skip_statement_tab = tab

    # Do not probe lvalues for c, but do for c++
    found_lvalue = re_lvalue.match(linebuf[lineindex])
    if (found_lvalue and not c_plusplus):
        skip_lvalue = 1
        skip_lvalue_tab = tab

    # <common/rhai-client_helper.c:101:3
    # Replace file statements and set appropriate state
    # print linebuf[lineindex].rstrip()

    # If we start in a .h file and end in a c-file, skip!
    get_skip_pos = re_compile_skip_pos.match(linebuf[lineindex])
    if (get_skip_pos):
        lskip_temp = int(get_skip_pos.group(3))
        cskip_temp = int(get_skip_pos.group(4))
        if do_print == 1: print "Expression starts in .h file and ends in this file, skip until: (" + str(lskip_temp) + "," + str(cskip_temp) + ")"
        if (lskip_temp > lskip):
            lskip=lskip_temp
            cskip=cskip_temp
        if ((lskip_temp == lskip) and (cskip_temp > cskip)):
            cskip=cskip_temp


    # Check if we for this line is within the parsed c file
    found_parsed_c_file_start = re_c_file_start.match(linebuf[lineindex])
    if (found_parsed_c_file_start):
        # Assume that we are within the parsed c file
        in_parsed_c_file = 1

        # Assure that we are not leaving the parsed c file
        #
        # ParmVarDecl Hexnumber <myfile.c:1:15, ../another-file.c:6:33>
        if (re_leaving_c_file.search(linebuf[lineindex])):
            if (re_self.search(linebuf[lineindex])):
                # Do nothing
                pass
            else:
                if do_print == 1: print "Entering another c-file, reset 'in_parsed_c_file'"
                in_parsed_c_file = 0

        # Replace filename with 'line' for further parsing
        linebuf[lineindex] = re.sub(parsed_c_file_exp, "line", linebuf[lineindex])

    # h-files
    #
    # <line:101:3, /usr/include/x86_64-linux-gnu/bits/errno.h:54:39>
    # </usr/include/x86_64-linux-gnu/bits/poll.h:41:20, line:48:18>
    # </usr/include/x86_64-linux-gnu/bits/poll.h:27:18>
    if (re_h_files.match(linebuf[lineindex])):
        trailing=0
        in_parsed_c_file = 0
        # Remove .h filename for further parsing
        linebuf[lineindex] = re.sub("\,\s/.*\.h:\d*:\d*>", ">", linebuf[lineindex])
        linebuf[lineindex] = re.sub(".*</.*\.h:\d*:\d*\,\s.*", "<external file,", linebuf[lineindex])
        linebuf[lineindex] = re.sub(".*</.*\.h:\d*:\d*>.*", "<external file>", linebuf[lineindex])

    # Other c-files (not self)
    #
    # <gcc.c-torture/compile/pr54713-1.c:21:31, col:42>
    elif not found_parsed_c_file_start and '.c:' in linebuf[lineindex]:
        if (re_self_anywhere.match(linebuf[lineindex])):
            # Self, do nothing
            pass
        else:
            trailing=0
            in_parsed_c_file = 0
            # Remove .c filename for further parsing
            linebuf[lineindex] = re.sub(".*<.*\.c:\d*:\d*\,\s", "<external file, ", linebuf[lineindex])
            if do_print == 1: print "in another c file, linebuf after re.sub: {}".format(linebuf[lineindex])

    # The different ways of updating position:
    #
    # A <line:62:3, line:161:3>
    # B <line:26:3, col:17>
    # C <col:17>
    # D <col:54, line:166:1>
    # E <col:5, col:58>
    # F <line:26:3>

    backtrailing = 0
    exp_extra = 0
    col_position_updated=0
    line_position_updated=0

    # Sort in order of common apperance
    # MATCH C
    # MATCH E
    # MATCH B
    # MATCH F
    # MATCH A
    # MATCH D

    # C
    exp_pos_update = re_update_pos_C.match(linebuf[lineindex])
    if exp_pos_update:
        col_position_updated=1
        cstart = exp_pos_update.group(1)
        cend = cstart
        #if do_print == 1: print "MATCH C: Start: ("+ lstart + ", " + cstart + ") End: (" + lend + ", " + cend + ") ->" + linebuf[lineindex].rstrip()

    # E
    if not col_position_updated:
        exp_pos_update = re_update_pos_E.match(linebuf[lineindex])
        if exp_pos_update:
            col_position_updated=1
            exp_extra = 1
            cstart = exp_pos_update.group(1)
            cend = exp_pos_update.group(2)
            #if do_print == 1: print "MATCH E: Start: (" + lstart + ", " + cstart + ") End: (" + lend + ", " + cend + ") ->" + linebuf[lineindex].rstrip()

    # B
    exp_pos_update = re_update_pos_B.match(linebuf[lineindex])
    if exp_pos_update:
        line_position_updated=1
        exp_extra = 1
        lstart = exp_pos_update.group(1)
        lend = lstart
        cstart = exp_pos_update.group(2)
        cend = exp_pos_update.group(3)
        if (in_parsed_c_file):
            trailing=1

        #if do_print == 1: print "MATCH B: Start: ("+ lstart + ", " + cstart + ") End: (" + lend + ", " + cend + ") ->" + linebuf[lineindex].rstrip()

    # F
    if not line_position_updated:
        exp_pos_update = re_update_pos_F.match(linebuf[lineindex])
        if exp_pos_update:
            line_position_updated=1
            lstart = exp_pos_update.group(1)
            cstart = exp_pos_update.group(2)
            lend=lstart
            cend=cstart
            if (in_parsed_c_file):
                trailing=1

            #if do_print == 1: print "MATCH F: Start: (" + lstart + ", " + cstart + ") End: (" + lend + ", " + cend + ") ->" + linebuf[lineindex].rstrip()

    # A
    if not line_position_updated:
        exp_pos_update = re_update_pos_A.match(linebuf[lineindex])
        if exp_pos_update:
            line_position_updated=1
            exp_extra = 1
            lstart = exp_pos_update.group(1)
            lend = exp_pos_update.group(3)
            cstart = exp_pos_update.group(2)
            cend = exp_pos_update.group(4)
            if (in_parsed_c_file):
                trailing=1

            #if do_print == 1: print "MATCH A: Start: ("+ lstart + ", " + cstart + ") End: (" + lend + ", " + cend + ") ->" + linebuf[lineindex].rstrip()

    # D
    if not col_position_updated:
        exp_pos_update = re_update_pos_D.match(linebuf[lineindex])
        if exp_pos_update:
            col_position_updated=1
            exp_extra = 1
            lend = exp_pos_update.group(2)
            cstart = exp_pos_update.group(1)
            cend = exp_pos_update.group(3)
            #if do_print == 1: print "MATCH D: Start: (" + lstart + ", " + cstart + ") End: (" + lend + ", " + cend + ") ->" + linebuf[lineindex].rstrip()

    # Check if backtrailing within current expression
    if (int(lstart) > int(lend)):
        backtrailing = 1
        if do_print == 1: print "Local backtrailing in " + parsed_c_file + " AT start:" + lstart + "   end:" + lend
        if do_print == 1: print "EXPR: " + linebuf[lineindex]

    # Check if global backtrailing. Note! Within the parsed c file!
    if ( in_parsed_c_file and (( int(last_lstart) > int(lstart))  or ( ( int(last_lstart) == int(lstart) ) and (int(last_cstart) > int(cstart)))) ):
        backtrailing = 1
        if do_print == 1: print "Global backtrailing in " + parsed_c_file + " AT line start:" + lstart + "   col start:" + cstart + " current location:(" + last_lstart + "," + last_cstart + ")"
        if do_print == 1: print "EXPR: " + linebuf[lineindex]
        
        # Check if this backtrailing is a compound or similar, in that case skip the whole thing
        # CompoundStmt Hexnumber <line:104:44, line:107:15>
        found_parsed_file_statement = re_parsed_file_statement.match(linebuf[lineindex])
        if (found_parsed_file_statement):
            skip_backtrail = 1
            skip_backtrail_tab = tab

    # Check for sections to skip
    # VarDecl Hexnumber <line:88:1, line:100:1>
    # RecordDecl Hexnumber <line:5:1, line:8:1>

    found_section_to_skip=0
    for section in re_sections_to_skip:
        m = section.match(linebuf[lineindex])
        if (m):
            found_section_to_skip=1

    if (found_section_to_skip and in_parsed_c_file):
        lskip_temp = int(lend)
        cskip_temp = int(cend)
        if (lskip_temp > lskip):
            lskip=lskip_temp
            cskip=cskip_temp
        if ((lskip_temp == lskip) and (cskip_temp > cskip)):
            cskip=cskip_temp

    # Set skip flag
    if (int(lstart) > lskip):
        skip = 0
    else:
        skip = 1

    if ( int(lstart) == lskip):
        if (int(cstart) > cskip):
            skip=0
        else:
            skip=1
    if do_print == 1: print "SKIP: " + str(skip) + "    lskip: " + str(lskip) + "   lend:"  + lend

# ...and this is above. Check if found (almost) the end of an expression and update in that case
    if inside_expression:

        # If we reached the last subexpression in the expression or next expression or statement
        if ( (int(lstart) > cur_lend) or ( (int(lstart) == cur_lend) and (int(cstart) > cur_cend) ) ):
            expdb_lineend.append(int(lstart))
            expdb_colend.append(int(cstart) -1 )
            expdb_tab.append(tab)
            expdb_index +=1
            if do_print == 1: print "FOUND END/NEXT (" + linebuf[lineindex].rstrip() + ") FOR (" + linebuf[inside_expression].rstrip() + ")"
            if do_print == 1: print "Start: ("+ str(cur_lstart) + ", " + str(cur_cstart) + ") End: (" + lstart  + ", " + str(int(cstart) -1) + ") ->" + linebuf[lineindex].rstrip()
            inside_expression = 0

# Check if expression is interesting
    if (trailing and (linebuf[lineindex] != "")):
        if do_print == 1: print parsed_c_file + " trailing:" + str(trailing) + " is_addition:" + str(is_addition) + " backtrailing:" + str(backtrailing) + " inside_expression:" + str(inside_expression) + " skip:" + str(skip)
        if do_print == 1: print parsed_c_file + " >" + linebuf[lineindex].rstrip()

    if ((exp_extra) and (trailing) and (is_addition) and (not backtrailing) and (not inside_expression) and (not skip) and (not skip_statement) and (not skip_backtrail) and (not skip_lvalue)):
        i = 0
        while (i < len(re_exppatternlist)):
            re_exp = re_exppatternlist[i]
            if (re_exp.match(linebuf[lineindex])):
               if do_print == 1: print "FOUND EXP: start: (" + lstart.rstrip() + "," + cstart.rstrip() + ")" + linebuf[lineindex].rstrip()

               # Sanity check
               if (int(lstart) > int(cf_len)):
                 raise ValueError('{} sanity check failed! lstart: {} cf_len {}'.format(parsed_c_file, lstart, cf_len))

               # Self contained expression
               if (exppatternmode[i] == 1):
 #                  if do_print == 1: print "Self contained"
                   expdb_linestart.append(int(lstart))
                   expdb_colstart.append(int(cstart))
                   expdb_lineend.append(int(lend))
                   expdb_colend.append(int(cend))
                   expdb_elineend.append(int(lend))
                   expdb_ecolend.append(int(cend))
                   expdb_exptext.append(linebuf[lineindex])
                   expdb_in_c_file.append(in_parsed_c_file)
                   expdb_tab.append(tab)
                   expdb_exppatternmode.append(1)
                   expdb_index +=1

               # Need to look for last sub expression
               if (exppatternmode[i] == 2):
                   cur_lstart = int(lstart)
                   cur_cstart = int(cstart)
                   cur_lend = int(lend)
                   cur_cend = int(cend)
                   cur_tab = tab
                   expdb_linestart.append(int(lstart))
                   expdb_colstart.append(int(cstart))
                   expdb_elineend.append(int(lend))
                   expdb_ecolend.append(int(cend))
                   expdb_exptext.append(linebuf[lineindex])
                   expdb_in_c_file.append(in_parsed_c_file)
                   expdb_exppatternmode.append(2)
#                   if do_print == 1: print "START: (" + lstart + "," + cstart + ")"
                   inside_expression = lineindex

               # Need to look for last sub expression. Also need to add length of keyword
               if (exppatternmode[i] > 2):
                   cur_lstart = int(lstart)
                   cur_cstart = int(cstart) + exppatternmode[i]
                   cur_lend = int(lend)
                   cur_cend = int(cend)
                   cur_tab = tab
                   expdb_linestart.append(int(lstart))
                   expdb_colstart.append(int(cstart) + exppatternmode[i])
                   expdb_elineend.append(int(lend))
                   expdb_ecolend.append(int(cend))
                   expdb_exptext.append(linebuf[lineindex])
                   expdb_in_c_file.append(in_parsed_c_file)
                   expdb_exppatternmode.append(2)
#                   if do_print == 1: print "START: (" + lstart + "," + cstart + ")"
                   inside_expression = lineindex

            i+=1

    # Check if we for next line is within the parsed c file
    found_parsed_c_file = re_parsed_c_file.match(linebuf[lineindex])
    if (found_parsed_c_file):
        in_parsed_c_file = 1

    # If lstart or curstart moved forward in parsed c file, update
    if ( line_position_updated and in_parsed_c_file and (int(lstart) > int(last_lstart))): 
        last_lstart=lstart
        last_cstart=cstart
        if do_print == 1: print "Line moving forward! last_lstart:" + last_lstart + " last_cstart:" + last_cstart

    if ( col_position_updated and in_parsed_c_file and (int(lstart) == int(last_lstart)) and ( int(cstart) > int(last_cstart) ) ):
        last_cstart=cstart
        if do_print == 1: print "Column moving forward! last_lstart:" + last_lstart + " last_cstart:" + last_cstart

    # Update lend and cend to reflect the position BEFORE THE NEXT expression, and not beginning iof the last in this one. See above...
    lstart = lend
    cstart = cend

    # Finally, update input file line index
    lineindex+=1

# If we were inside an expression when the file ended, take care of the last one
if inside_expression:
    expdb_lineend.append(int(lstart))
    expdb_colend.append(int(cstart) - 1)
    expdb_tab.append(tab)
    expdb_index +=1

# Open probe data file to start append entries
pdf = open(sys.argv[3], "w")

# Insert probes
if do_print == 1: print "Probing starting at {}".format(parsed_c_file)

i=0
while (i < expdb_index):
    bail_out=0
    ls = expdb_linestart[i] - 1
    cs = expdb_colstart[i] - 1
    le = expdb_lineend[i] - 1
    ce = expdb_colend[i] #- 1
    ele = expdb_elineend[i] - 1

    if (expdb_exppatternmode[i] == 2 ):
        ece = expdb_ecolend[i]
    else:
        ece = expdb_ecolend[i] - 1

    tab = expdb_tab[i]

    # Sanity check input

    # Ends before start?
    if ((ls == ele) and (ece <= cs)):
        bail_out=1

    if do_print == 1: print str(expdb_in_c_file[i]) + "  EXP:" + expdb_exptext[i].rstrip() + "STARTPOS: (" + str(ls) + "," + str(cs) + ")" + "ENDPOS: (" + str(le) + "," + str(ce) + ")" + "ECE: " + str(ece) + "Tab: " + str(tab)

    #single line
    #    if (ls==le):
    if (0):
       if (ls not in probed_lines):
            line = pbuf[ls]

            iline = line[:cs] + "(DMCE_PROBE(TBD)," + line[cs:ce+1] + ")" + line[ce+1:]
            if do_print == 1: print "Old single line: " + line.rstrip()
            if do_print == 1: print "New single line: " + iline.rstrip()
            pbuf.pop(ls)
            pbuf.insert(ls,iline)
            probed_lines.append(ls)
            if do_print == 1: print "1 Added line :" + str(ls)
            pdf.write(parsed_c_file + ":" + str(ls) + "\n")
    else:
        # Multiple lines
        # Insert on first line and last line
        # mark all lines in between as probed
        # Also, adjust le and ce if a ; or a ) is found before

        if (ls not in probed_lines):
            lp=ls
            while (lp < ele):
                probed_lines.append(lp)
                if do_print == 1: print "2 Added line :" + str(lp)
                lp +=1

            cp=ece

            found=0
            if do_print == 1: print "Searching from (" + str(lp+1) + "," + str(cp) + ")"
            stack_curly=0
            stack_parentesis=0
            stack_bracket=0
            while ((lp < len(pbuf)) and not found and not bail_out):
                line = pbuf[lp].rstrip()

                #Bail out candidates to MAYBE be fixed later
                if ("#define" in line):
                    bail_out=1

                # Filter out escaped backslash
                line = re.sub(r'\\\\', "xx", line)

                # Filter out escaped quotation mark and escaped apostrophe
                line = re.sub(r'\\"', "xx", line)
                line = re.sub(r"\\'", "xx", line)

                # Replace everything within '...' with xxx
                line_no_strings = list(line)
                p = re.compile("'.*?'")
                for m in p.finditer(line):
                    j=0
                    while (j < len(m.group())):
                        line_no_strings[m.start() + j] = 'x'
                        j = j + 1

                line = "".join(line_no_strings)

                # Replace everything within "..." with xxx
                line_no_strings = list(line)
                p = re.compile("\".*?\"")
                for m in p.finditer(line):
                    j=0
                    while (j < len(m.group())):
                        line_no_strings[m.start() + j] = 'x'
                        j = j + 1

                line = "".join(line_no_strings)

                # Replace everything within /*...*/ with xxx
                line_no_strings = list(line)
                p = re.compile("\/\*.*?\*\/")
                for m in p.finditer(line):
                    j=0
                    while (j < len(m.group())):
                        line_no_strings[m.start() + j] = 'x'
                        j = j + 1

                line = "".join(line_no_strings)

                tail = line[cp:]
                if do_print == 1: print "LINE: " + line
                if do_print == 1: print "TAIL: " + tail

                # Find first ) } ] or comma that is not inside brackets of any kind
                pos_index = 0
                while (pos_index < len(tail)):
                    # Curly brackets
                    if (tail[pos_index] == "}"):
                        stack_curly-=1
                    if (tail[pos_index] == "{"):
                        stack_curly+=1
                    if (stack_curly == -1):
                        break


                    # Brackets
                    if (tail[pos_index] == "]"):
                        stack_bracket-=1
                    if (tail[pos_index] == "["):
                        stack_bracket+=1
                    if (stack_bracket == -1):
                        break


                    # Parentesis
                    if (tail[pos_index] == ")"):
                        stack_parentesis-=1
                    if (tail[pos_index] == "("):
                        stack_parentesis+=1
                    if (stack_parentesis == -1):
                        break

                    # Comma, colon, questionmark (only valid if not inside brackets)
                    if (stack_parentesis == stack_bracket == stack_curly == 0 ):
                        if (tail[pos_index] == ","):
                            break
                        # Question mark
                        if (tail[pos_index] == "?"):
                            break
                        # Colon
                        if (tail[pos_index] == ":"):
                            break

                    # Semicolon (always valid)
                    if (tail[pos_index] == ";"):
                        break
                     
                    pos_index+=1

                if do_print == 1: print "index: " + str(pos_index)

                if (pos_index < len(tail) and not bail_out):
                    found=1
                    cp += pos_index

                    # NOTE! Lines commented out prevents us to go further lines down than the actual expression was.
                    # Not sure if we need them, leave commented out for now.
 
#                    if (lp < le):
                    le = lp
                    ce = cp
#                    elif (lp == le):
##                        if (cp < ce):
#                        ce = cp

                    if do_print == 1: print "FOUND EARLY: (" + str(le+1) + "," + str(ce) + ") in:" + pbuf[lp].rstrip()


                cp=0 # All following lines need to be searched from beginnning of line
                probed_lines.append(lp)
                if do_print == 1: print "3 Added line :" + str(lp+1)
                lp+=1

            # pre insertion
            if (not bail_out):
                line = pbuf[ls]

                match_exclude = 0
                for re_exp in re_cxl_list:
                    j=0
                    while (ls + j) <= le:
                        if do_print == 1: print "searching for '{}' in '{}'".format(re_exp.pattern, pbuf[ls + j])
                        if (re_exp.match(pbuf[ls + j])):
                            match_exclude = 1
                            if do_print == 1: print "match_exclude=1"
                            break
                        j = j + 1

                    if match_exclude:
                        break

                if (not match_exclude):
                    # Pick line to insert prolog
                    iline_start = line[:cs] + probe_prolog + line[cs:]
                    if do_print == 1: print "Old starting line: " + line.rstrip()
                    if do_print == 1: print "New starting line: " + iline_start.rstrip()

                    # if start and end on same line, compensate column for inserted data
                    if (ls == le):
                        ce+= len(probe_prolog)

                    # Last time to regret ourselves! Check for obvious errors on line containing prolog. If more is needed create a list instead like for sections to skip!
                    regret = re_regret_insertion.match(iline_start)

                    if (not regret):
                        # Insert prolog
                        pbuf.pop(ls)
                        pbuf.insert(ls,iline_start)

                        # Pick line to insert epilog
                        if do_print == 1: print "Multi line INSERTION end: (" + str(le+1) +"," + str(ce) + ")" + ": " + line.rstrip()
                        line = pbuf[le]
                        iline_end = line[:ce] + probe_epilog + line[ce:]

                        # Print summary
                        if do_print == 1: print "Old ending line: " + line.rstrip()
                        if do_print == 1: print "New ending line: " + iline_end.rstrip()

                        # Insert epilog
                        pbuf.pop(le)
                        pbuf.insert(le,iline_end)

                        probes+=1

                        # Update probe file
                        pdf.write(parsed_c_file + ":" + str(ls) + "\n")
    i += 1

# write back c file
pf = open(sys.argv[2],"w")
for line in pbuf:
   pf.write(line)

pdf.close()
print '{:5.1f} ms {:5} probes'.format((time.time()-time1)*1000.0, probes)

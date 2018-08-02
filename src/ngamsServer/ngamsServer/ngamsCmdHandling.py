#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2012
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#
#******************************************************************************
#
# "@(#) $Id: ngamsCmdHandling.py,v 1.5 2008/08/19 20:51:50 jknudstr Exp $"
#
# Who       When        What
# --------  ----------  -------------------------------------------------------
# jknudstr  07/01/2002  Created
#
"""
Contains various functions for handling commands.
"""

import imp
import importlib
import logging
import sys

from ngamsLib.ngamsCore import \
    NGAMS_RETRIEVE_CMD, NGAMS_ARCHIVE_CMD, NGAMS_CACHEDEL_CMD, \
    NGAMS_CHECKFILE_CMD, NGAMS_CLONE_CMD, NGAMS_CONFIG_CMD, NGAMS_DISCARD_CMD, \
    NGAMS_EXIT_CMD, NGAMS_HELP_CMD, NGAMS_INIT_CMD, NGAMS_LABEL_CMD, \
    NGAMS_OFFLINE_CMD, NGAMS_ONLINE_CMD, NGAMS_REARCHIVE_CMD, NGAMS_REGISTER_CMD, \
    NGAMS_REMDISK_CMD, NGAMS_REMFILE_CMD, NGAMS_STATUS_CMD, NGAMS_SUBSCRIBE_CMD, \
    NGAMS_UNSUBSCRIBE_CMD


logger = logging.getLogger(__name__)

_builtin_cmds = {
    NGAMS_ARCHIVE_CMD, NGAMS_CACHEDEL_CMD, NGAMS_CHECKFILE_CMD, NGAMS_CLONE_CMD,
    NGAMS_CONFIG_CMD, NGAMS_DISCARD_CMD, NGAMS_EXIT_CMD, NGAMS_HELP_CMD,
    NGAMS_INIT_CMD, NGAMS_LABEL_CMD, NGAMS_OFFLINE_CMD, NGAMS_ONLINE_CMD,
    NGAMS_REARCHIVE_CMD, NGAMS_REGISTER_CMD, NGAMS_REMDISK_CMD, NGAMS_REMFILE_CMD,
    NGAMS_RETRIEVE_CMD, NGAMS_STATUS_CMD, NGAMS_SUBSCRIBE_CMD, NGAMS_UNSUBSCRIBE_CMD,
    'CAPPEND', 'CARCHIVE', 'CCREATE', 'CDESTROY', 'CLIST', 'CREMOVE', 'CRETRIEVE',
    'QARCHIVE', 'QUERY', 'BBCPARC'
}

# The reload function has moved around a bit
if sys.version_info[0] < 3:
    from __builtin__ import reload
elif sys.version_info[0:2] < (3, 4):
    reload = imp.reload
else:
    reload = importlib.reload

class NoSuchCommand(Exception):
    """Error thrown when a command's implementation cannot be found"""
    pass

def cmdHandler(srvObj,
               reqPropsObj,
               httpRef):
    """
    Handle a command.

    srvObj:        Reference to NG/AMS server class object (ngamsServer).

    reqPropsObj:   Request Property object to keep track of
                   actions done during the request handling
                   (ngamsReqProps).

    httpRef:       Reference to the HTTP request handler
                   object (ngamsHttpRequestHandler).

    Returns:       Void.
    """
    msg = _get_module(srvObj, reqPropsObj).handleCmd(srvObj, reqPropsObj, httpRef)
    if msg is not None:
        if httpRef.reply_sent:
            logger.warning("Module returned message to send back to client, but reply has been sent, ignoring")
            return
        httpRef.send_status(msg)

def _get_module(server, request):

    # Interpret the command + parameters.
    cmd = request.getCmd()
    logger.info("Received command: %s", cmd)

    # Special handling for certain commands
    # TODO: these should certainly disappear at some point
    if cmd == 'robots.txt':
        cmd = 'robots'
    if cmd == 'favicon.ico':
        cmd = 'favicon'
    if cmd == "ngamsInternal.dtd":
        request.setCmd(NGAMS_RETRIEVE_CMD).addHttpPar("internal", cmd)
        cmd = 'RETRIEVE'

    # Is it a built-in or a plug-in?
    if cmd in _builtin_cmds:
        modname = __package__ + '.commands.' + cmd.lower()
    elif cmd in server.cfg.cmd_plugins:
        modname = server.cfg.cmd_plugins[cmd]
    else:
        modname = 'ngamsPlugIns.ngamsCmd_%s' % cmd

    # Reload the module if requested.
    reload_mod = 'reload' in request and int(request['reload']) == 1

    # Need to acquire the importing lock if we want to check the sys.modules
    # dictionary to short-cut the call to importlib.import_module. This is
    # because the modules are put into sys.modules by the import machinery
    # *before* they are fully loaded (probably to detect circular dependencies)
    # For details on a similar issue found in the pickle module see
    # https://bugs.python.org/issue12680
    #
    # In python 3.3+ this shoudn't be necessary anymore, as the locking scheme
    # has been changed to per-module locks. This function has been marked as
    # deprecated, and therefore we probably don't need it anymore
    imp.acquire_lock()
    try:
        mod = sys.modules.get(modname, None)
        if mod is None:
            logger.debug("Importing dynamic command module: %s", modname)
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                logger.error("No module %s found", modname)
                raise NoSuchCommand()
            except:
                logger.exception("Error while importing %s", modname)
                raise
        elif reload_mod:
            logger.debug("Re-loading dynamic command module: %s", modname)
            mod = reload(mod)
        return mod
    finally:
        imp.release_lock()

# EOF
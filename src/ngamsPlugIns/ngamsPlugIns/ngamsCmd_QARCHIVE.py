#
#    ALMA - Atacama Large Millimiter Array
#    (c) European Southern Observatory, 2002
#    Copyright by ESO (in the framework of the ALMA collaboration),
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
# "@(#) $Id: ngamsCmd_QARCHIVE.py,v 1.6 2009/12/07 16:36:40 awicenec Exp $"
#
# Who       When        What
# --------  ----------  -------------------------------------------------------
# jknudstr  03/02/2009  Created
#
"""
NGAS Command Plug-In, implementing a Quick Archive Command.

This works in a similar way as the 'standard' ARCHIVE Command, but has been
simplified in a few ways:

  - No replication to a Replication Volume is carried out.
  - Target disks are selected randomly, disregarding the Streams/Storage Set
    mappings in the configuration. This means that 'volume load balancing' is
    provided.
  - Archive Proxy Mode is not supported.
  - No probing for storage availability is supported.
  - In general, less SQL queries are performed and the algorithm is more
    light-weight.
  - crc is computed from the incoming stream
  - ngas_files data is 'cloned' from the source file
"""

import logging
import os
import random
import sys
import time
import urlparse

from ngamsLib.ngamsCore import TRACE, genLog, checkCreatePath, \
    NGAMS_HTTP_HDR_CHECKSUM, NGAMS_ONLINE_STATE, \
    NGAMS_IDLE_SUBSTATE, NGAMS_BUSY_SUBSTATE, NGAMS_STAGING_DIR, genUniqueId, \
    mvFile, getFileCreationTime, NGAMS_FILE_STATUS_OK, \
    getDiskSpaceAvail, NGAMS_HTTP_SUCCESS, NGAMS_SUCCESS, loadPlugInEntryPoint
from ngamsLib import ngamsDiskInfo, ngamsHighLevelLib, ngamsFileInfo
from ngamsServer import ngamsCacheControlThread, \
    ngamsArchiveUtils


GET_AVAIL_VOLS_QUERY = "SELECT %s FROM ngas_disks nd WHERE completed=0 AND " +\
                       "host_id='%s'"


logger = logging.getLogger(__name__)

def getTargetVolume(srvObj):
    """
    Get a random target volume with availability.

    srvObj:         Reference to NG/AMS server class object (ngamsServer).

    Returns:        Target volume object or None (ngamsDiskInfo | None).
    """
    res = srvObj.getDb().getAvailableVolumes(srvObj.getHostId())
    if not res:
        return None

    # Shuffle the results.
    res = list(res)
    random.shuffle(res)
    return ngamsDiskInfo.ngamsDiskInfo().unpackSqlResult(res[0])


def saveFromHttpToFile(ngamsCfgObj,
                       reqPropsObj,
                       trgFilename,
                       mutexDiskAccess = 1,
                       diskInfoObj = None):
    """
    Save the data available on an HTTP channel into the given file.

    ngamsCfgObj:     NG/AMS Configuration object (ngamsConfig).

    reqPropsObj:     NG/AMS Request Properties object (ngamsReqProps).

    trgFilename:     Target name for file where data will be
                     written (string).

    mutexDiskAccess: Require mutual exclusion for disk access (integer).

    diskInfoObj:     Disk info object. Only needed if mutual exclusion
                     is required for disk access (ngamsDiskInfo).

    Returns:         Tuple. Element 0: Time in took to write
                     file (s) (tuple).
    """
    T = TRACE()

    logger.debug("Saving data in file: %s", trgFilename)

    try:
        # Make mutual exclusion on disk access (if requested).
        if mutexDiskAccess:
            ngamsHighLevelLib.acquireDiskResource(ngamsCfgObj, diskInfoObj.getSlotId())

        block_size = ngamsCfgObj.getBlockSize()
        size = reqPropsObj.getSize()
        fin = reqPropsObj.getReadFd()
        checkCreatePath(os.path.dirname(trgFilename))

        # The CRC variant is configured in the server, but can be overriden
        # in a per-request basis
        if reqPropsObj.hasHttpPar('crc_variant'):
            variant = reqPropsObj.getHttpPar('crc_variant')
        else:
            variant = ngamsCfgObj.getCRCVariant()

        result = ngamsArchiveUtils.archive_contents(trgFilename, fin, size, block_size, variant)

        reqPropsObj.setBytesReceived(size)
        ingestRate = size / result.totaltime

        # Compare checksum if required
        checksum = reqPropsObj.getHttpHdr(NGAMS_HTTP_HDR_CHECKSUM)
        if checksum and result.crc is not None:
            if checksum != str(result.crc):
                msg = 'Checksum error for file %s, local crc = %s, but remote crc = %s' % (reqPropsObj.getFileUri(), str(result.crc), checksum)
                raise Exception(msg)
            else:
                logger.debug("%s CRC checked, OK!", reqPropsObj.getFileUri())

        logger.debug('Block size: %d; File size: %d; Transfer time: %.4f s; CRC time: %.4f s; write time %.4f s',
                     block_size, size, result.totaltime, result.crctime, result.wtime)
        logger.info('Saved data in file: %s. Bytes received: %d. Time: %.4f s. Rate: %.2f Bytes/s',
                    trgFilename, size, result.totaltime, ingestRate)

        return [result.totaltime, result.crc, result.crcname, ingestRate]
    finally:
        if mutexDiskAccess:
            ngamsHighLevelLib.releaseDiskResource(ngamsCfgObj, diskInfoObj.getSlotId())


def handleCmd(srvObj,
              reqPropsObj,
              httpRef):
    """
    Handle the Quick Archive (QARCHIVE) Command.

    srvObj:         Reference to NG/AMS server class object (ngamsServer).

    reqPropsObj:    Request Property object to keep track of actions done
                    during the request handling (ngamsReqProps).

    httpRef:        Reference to the HTTP request handler
                    object (ngamsHttpRequestHandler).

    Returns:        (fileId, filePath) tuple.
    """
    T = TRACE()

    logger.debug("Check if the URI is correctly set.")
    if not reqPropsObj.getFileUri():
        errMsg = genLog("NGAMS_ER_MISSING_URI")
        raise Exception(errMsg)

    logger.debug("Is this NG/AMS permitted to handle Archive Requests?")
    if not srvObj.getCfg().getAllowArchiveReq():
        errMsg = genLog("NGAMS_ER_ILL_REQ", ["Archive"])
        raise Exception, errMsg

    srvObj.checkSetState("Archive Request", [NGAMS_ONLINE_STATE],
                         [NGAMS_IDLE_SUBSTATE, NGAMS_BUSY_SUBSTATE],
                         NGAMS_ONLINE_STATE, NGAMS_BUSY_SUBSTATE,
                         updateDb=False)

    logger.debug("Get mime-type (try to guess if not provided as an HTTP parameter).")
    mimeType = reqPropsObj.getMimeType()
    if not mimeType:
        mimeType = ngamsHighLevelLib.determineMimeType(srvObj.getCfg(),
                                                        reqPropsObj.getFileUri())
        reqPropsObj.setMimeType(mimeType)

    uri = reqPropsObj.getFileUri()
    logger.debug("Checking File URI scheme for %s", uri)
    file_version_uri = None

    if reqPropsObj.is_GET():

        # work around https://bugs.python.org/issue9374 in python < 2.7.4
        # where the query part is not parsed for all schemes (so we have to
        # parse it out from the path ourselves)
        uri_res = urlparse.urlparse(uri)
        if sys.version < (2,7,4):
            scheme, netloc, path, params, query, fragment = uri_res
            if not query:
                idx = uri_res.path.find('?')
                if idx != -1:
                    query = uri_res.path[idx+1:]
                    path = uri_res.path[:idx]
            uri_res = urlparse.ParseResult(scheme, netloc, path, params, query, fragment)

        base_name = uri_res.path
        if uri_res.scheme:
            if uri_res.query:
                params = urlparse.parse_qs(uri_res.query)
                try:
                    file_id = params['file_id'][0]
                    base_name = os.path.basename(file_id)
                except KeyError:
                    pass
                try:
                    file_version_uri = params['file_version'][0]
                    try:
                        file_version_uri = int(file_version_uri)
                    except ValueError:
                        raise Exception('file_version is not an integer')
                except KeyError:
                    pass

            uri_open = uri
            if 'file' in uri_res.scheme:
                uri_open = uri_res.path

            handle = ngamsHighLevelLib.openCheckUri(uri_open)
            reqPropsObj.setSize(handle.info()['Content-Length'])
            reqPropsObj.setReadFd(handle)
    else:
        base_name = os.path.basename(uri)

    if reqPropsObj.getSize() <= 0:
        errMsg = genLog("NGAMS_ER_ARCHIVE_PULL_REQ",
                        [reqPropsObj.getSafeFileUri(), 'Content-Length is 0'])
        raise Exception(errMsg)

    logger.debug("Determine the target volume, ignoring the stream concept.")
    targDiskInfo = getTargetVolume(srvObj)
    if targDiskInfo is None:
        errMsg = "No disk volumes are available for ingesting any files."
        raise Exception(errMsg)

    reqPropsObj.setTargDiskInfo(targDiskInfo)

    stgFilename = os.path.join('/', targDiskInfo.getMountPoint(),
                               NGAMS_STAGING_DIR,
                               '{0}{1}{2}'.format(genUniqueId(), '___', base_name))

    if stgFilename.count('.') == 0:  #make sure there is at least one extension
        stgFilename = ngamsHighLevelLib.checkAddExt(srvObj.getCfg(), reqPropsObj.getMimeType(), stgFilename)

    logger.debug("Staging filename is: %s", stgFilename)
    reqPropsObj.setStagingFilename(stgFilename)

    # Retrieve file contents (from URL, archive pull, or by storing the body
    # of the HTTP request, archive push).
    stagingInfo = saveFromHttpToFile(srvObj.getCfg(), reqPropsObj,
                                     stgFilename, 1, targDiskInfo)
    ioTime = stagingInfo[0]
    logger.debug("IO_TIME: %10.3f s", ioTime)
    reqPropsObj.incIoTime(ioTime)

    # Invoke DAPI.
    plugIn = srvObj.getMimeTypeDic()[mimeType]
    try:
        plugInMethod = loadPlugInEntryPoint(plugIn)
    except Exception, e:
        errMsg = "Error loading DAPI: %s. Error: %s" % (plugIn, str(e))
        raise Exception, errMsg

    logger.info("Invoking DAPI: %s to handle data for file with URI: %s" % (plugIn, base_name))

    timeBeforeDapi = time.time()
    resDapi = plugInMethod(srvObj, reqPropsObj)

    if logger.level <= logging.DEBUG:
        logger.debug("Invoked DAPI: %s. Time: %.3fs.", plugIn, (time.time() - timeBeforeDapi))
        logger.debug("Result DAPI: %s", str(resDapi.toString()))

    # Move file to final destination.
    logger.debug("Moving file to final destination")
    ioTime = mvFile(reqPropsObj.getStagingFilename(),
                    resDapi.getCompleteFilename())
    reqPropsObj.incIoTime(ioTime)

    # Get crc info
    logger.debug("Get checksum info")
    crc = stagingInfo[1]
    crc_name = stagingInfo[2]
    logger.debug("Checksum variant used: %s to handle file: %s. Result: %s",
            crc_name, resDapi.getCompleteFilename(), str(crc))

    file_version = resDapi.getFileVersion()

    # If there was a previous version of this file, and it had a container associated with it
    # associte the new version with the container too
    containerId = None
    if file_version > 1:
        fileInfo = ngamsFileInfo.ngamsFileInfo().read(srvObj.getHostId(),
                                                      srvObj.getDb(), resDapi.getFileId(), fileVersion=(file_version-1))
        containerId = fileInfo.getContainerId()
        prevSize = fileInfo.getUncompressedFileSize()

    # Check/generate remaining file info + update in DB.
    logger.debug("Creating db entry")
    ingestionRate = stagingInfo[3]
    creDate = getFileCreationTime(resDapi.getCompleteFilename())
    fileInfo = ngamsFileInfo.ngamsFileInfo().\
               setDiskId(resDapi.getDiskId()).\
               setFilename(resDapi.getRelFilename()).\
               setFileId(resDapi.getFileId()).\
               setFileVersion(file_version).\
               setFormat(resDapi.getFormat()).\
               setFileSize(resDapi.getFileSize()).\
               setUncompressedFileSize(resDapi.getUncomprSize()).\
               setCompression(resDapi.getCompression()).\
               setIngestionDate(time.time()).\
               setChecksum(crc).setChecksumPlugIn(crc_name).\
               setFileStatus(NGAMS_FILE_STATUS_OK).\
               setCreationDate(creDate).\
               setIoTime(reqPropsObj.getIoTime()).\
               setIngestionRate(ingestionRate)
    fileInfo.write(srvObj.getHostId(), srvObj.getDb())

    # Update the container size with the new size
    if containerId:
        newSize = fileInfo.getUncompressedFileSize()
        srvObj.getDb().addFileToContainer(containerId, resDapi.getFileId(), True)
        srvObj.getDb().addToContainerSize(containerId, (newSize - prevSize))

    # Inform the caching service about the new file.
    logger.debug("Inform the caching service about the new file.")
    if (srvObj.getCachingActive()):
        diskId      = resDapi.getDiskId()
        fileId      = resDapi.getFileId()
        fileVersion = file_version
        filename    = resDapi.getRelFilename()
        ngamsCacheControlThread.addEntryNewFilesDbm(srvObj, diskId, fileId,
                                                   fileVersion, filename)

    # Update disk info in NGAS Disks.
    logger.debug("Update disk info in NGAS Disks.")
    srvObj.getDb().updateDiskInfo(resDapi.getFileSize(), resDapi.getDiskId())

    # Check if the disk is completed.
    # We use an approximate extimate for the remaning disk space to avoid
    # to read the DB.
    logger.debug("Check available space in disk")
    availSpace = getDiskSpaceAvail(targDiskInfo.getMountPoint(), smart=False)
    if (availSpace < srvObj.getCfg().getFreeSpaceDiskChangeMb()):
        targDiskInfo.setCompleted(1).setCompletionDate(time.time())
        targDiskInfo.write(srvObj.getDb())

    # Request after-math ...
    srvObj.setSubState(NGAMS_IDLE_SUBSTATE)
    msg = "Successfully handled Archive Pull Request for data file with URI: %s" %\
            reqPropsObj.getSafeFileUri()
    logger.info(msg)

    srvObj.ingestReply(reqPropsObj, httpRef, NGAMS_HTTP_SUCCESS,
                       NGAMS_SUCCESS, msg, targDiskInfo)

    # Trigger Subscription Thread. This is a special version for MWA, in which we simply swapped MIRRARCHIVE and QARCHIVE
    # chen.wu@icrar.org
    logger.debug("triggering SubscriptionThread for file %s", resDapi.getFileId())
    srvObj.addSubscriptionInfo([(resDapi.getFileId(),
                                 resDapi.getFileVersion())], [])
    srvObj.triggerSubscriptionThread()

    return (resDapi.getFileId(), '%s/%s' % (targDiskInfo.getMountPoint(), resDapi.getRelFilename()), ingestionRate)

# EOF

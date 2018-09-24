Changelog
=========

.. rubric:: Development version

* Initial python 3 support.
  The code not only correctly imports under python 3,
  but also all unit tests pass correctly.
  The code is both 2.7/3.5+ compatible,
  so users don't need to immediately switch to python 3.
  Given that our test coverage currently sits at about 65%,
  it is likely that there are code paths that need further work.
* :doc:`Command plug-ins <plugins/commands>` can be implemented
  as user-provided plug-ins.
  This was almost the case until now, as they still had the restriction
  of having to reside on the ``ngamsPlugIns`` package,
  which is not the case anymore.
  Moreover, a single python module can implement the logic
  of more than one command.
* Added new CRC variant called ``crc32z``.
  It behaves exactly like ``crc32``, except that its values,
  *as stored in the database*, should be consistent
  across python 2.7 and 3.
  The ``crc32`` variant does not have this property,
  although we can still (and do) normalize them
  when checking files' checksums.
* Changed the server to use a thread pool to serve requests
  instead of creating a brand new thread every time a request comes in.
* Improving how the :ref:`RETRIEVE <commands.retrieve>` command works
  when returning compressed files.
* Adding support to the ``CRETRIEVE`` command
  to retrieve all files as a tarball.
  It internally uses ``sendfile(2)`` when possible.
* Users can configure NGAS to issue a specific SQL statement
  at connection-establishment time, similarly to how other connection pools do.
* Fixed a few details regarding expected v/s real datatypes
  used in some SQL queries.
  These affected only the Sybase ASE official driver,
  which is now working correctly.
* Unit tests moved to the top-level ``test`` directory,
  and renamed to ``test_*.py``.
  This makes it more straight-forward to use unit test runners
  which usually rely on this layout for test discovery.
* A new sample configuration file replaces the old, large set
  of configuration files that used to be shipped with NGAS.
* Starting a server in cache mode is now be done
  via a configuration file preference rather than a command-line argument.
* The subscription code and the cache handling thread
  update the file status flags atomically.
  Before they had a race condition which resulted in files
  not being deleted on the cache server.
* Improving and simplifying the ``QUERY`` command.
* Removed many unnecessary internal usage
  of ``.bsddb`` files.
* Added a MacOS build
  to our `Travis CI <https://travis-ci.org/ICRAR/ngas>`_ set up.
* Misc bug fixes and code improvements.

.. rubric:: 10.0

* The ``ARCHIVE``, ``QARCHIVE``, ``REARCHIVE`` and ``BBCPARC`` commands now use the same underlying code.
  All the small differences between the commands has been kept, so they should behave exactly as before.
  This was a required step we needed to take before implementing other improvements/bugfixes.
* The archiving commands listed above are now more efficient in how they calculate the checksum of the incoming data.
  If the data archiving plug-in promises not to change the data, then the checksum is calculated on the incoming stream
  instead of calculating it on the file, reducing disk access and response times.
  This behavior was previously not seen
  neither on the ``ARCHIVE`` command,
  which always dumped all contents to disk
  and then did a checksum on the on-disk contents,
  nor in the ``QARCHIVE`` command,
  which **unconditionally** calculated the checksum
  on the incoming stream,
  irrespective of whether the data archiving plug-in
  changed the data afterward or not.
* Partial content retrieval for the ``RETRIEVE`` command has been implemented.
  This feature was present in the ALMA branch of the NGAS code,
  and now has been incorporated into ours.
* We merged the latest ALMA mirroring code into our code base.
  This and the point above should ensure that NGAS is ALMA-compatible.
* Unified and centralized all the CRC checksuming code,
  and how different variants are chosen.
* We have improved response times for scenarios
  when many parallel ``RETRIEVE`` commands are issued.
  Worst-case scenario times in 100 parallel request scenarios were brought down
  from tens of seconds to about 2 seconds (i.e., an order of magnitude).
* Moved the :ref:`data-check <bg.datacheck_thread>` background thread checksum
  to a separate pool of processes
  to avoid hanging up the main process.
  The checksuming also pauses/resumes depending on whether the server
  is serving any requests or not to avoid exhausting access to the disk.
* Added the ability to write plug-ins that will react to each file archiving
  (e.g., to trigger some processing, etc).
* Added support for the latest `bbcp <https://www.slac.stanford.edu/~abh/bbcp/>`_ release,
  which includes, among other things, our contributions
  to add support for the ``crc32c`` checksum variant,
  plus other fixes to existing code.
* Fixed a few small problems with different installation scenarios.

.. rubric:: 9.1

* NGAS is now hosted in our public `GitHub repository <https://github.com/ICRAR/ngas>`_.
* `Travis CI <https://travis-ci.org/ICRAR/ngas>`_ has been set up
  to ensure that tests runs correctly against SQLite3, MySQL and PostgreSQL.
* User-provided plug-ins do not need to be installed alongside NGAS anymore.
  This allows users to place their plug-ins
  in their own personally-owned directories,
  which in turn allows to install NGAS in isolation,
  and probably with more strict permissions.
* Project-specific plug-ins under the ``ngamsPlugIns`` package
  have been moved to sub-packages (e.g., ``ngamsPlugIns.mwa``),
  and will eventually be phased out as projects take ownership
  of their own plug-ins.
* :ref:`Janitor Thread <bg.janitor_thread>` changes:

  * Plug-ins: Instead of having a fixed, single module with all the business logic of the Janitor Thread,
    its individual components have been broken down into separate modules
    which are loaded and run using a standard interface.
    This makes the whole Janitor Thread logic simpler.
    It also allows us to implement users-written plug-ins
    that can be run as part of the janitor thread.
  * The execution of the Janitor Thread doesn't actually happen in a thread anymore,
    but in a separate process.
    This takes some burden out from the main NGAS process.
    In most places we keep calling it a thread though;
    this will continue changing continuously as we find these occurrences.

* The NGAS server script, the daemon script and the SystemV init script
  have been made more flexible,
  removing the need of having more than one version for each of them.
* Some cleanup has been done on the NGAS client-side HTTP code
  to remove duplicates and offer a better interface both internally and externally.
* Self-archiving of logfiles is now optional.
* A few occurrences of code incorrectly handling database results
  have been fixed,
  making the code behave better across different databases.
* Misc bug fixes and code cleanups.

.. rubric:: 9.0

* Switched from our ``pcc``-based, own home-brewed logging package
  to the standard python logging module.
* Unified time conversion routines, eliminating heaps of old code
* Removed the entire ``pcc`` set of modules.
* General bug fixes and improvements.

.. rubric:: 8.0

* Re-structured NGAS python packages.
  Importing NGAS python packages is now simpler and doesn't alter the python path in any way.
  The different packages can be installed
  either as zipped eggs, exploded eggs, or in development mode.
  This makes NGAS behave like other standard python packages,
  and therefore easier to install in any platform/environment
  where setuptools or pip is available.
* ``RETRIEVE`` command uses ``sendfile(2)`` to serve files to clients.
  This is more efficient both in terms of kernel-user interaction
  (less memory copying), and python performance (less python instructions
  have to be decoded/interpreted, needing less GIL locking, leading to better
  performance and less multithread contention).
* Initial support for logical containers.
  Logical containers are groups of files, similar to how directories group files in a filesystem.
* NGAS server replying with more standard HTTP headers
  (e.g., ``Content-Type`` instead of ``content-type``).
  Most HTTP client-side libraries are lenient to these differences though.
* Streamlined ``crc32c`` support throughout ``QARCHIVE`` and subscription flows.
  We use the `crc32c <https://github.com/ICRAR/crc32c>`_ module for this,
  which was previously found as part of NGAS's source code,
  but that has been separated into its own package for better reusability.
* Stabilization of unit test suite.
  Now the unit test suite shipped with NGAS runs reliably on most computers.
  This made it possible to have a continuous integration environment
  (based on a private Jenkins installation)
  to monitor the health of the software after each change on the code.
* Improved SQL interaction, making sure we use prepared statements all over the place,
  and standard PEP-249 python modules for database connectivity.
* Improved server- and client-side connection handling,
  specially error-handling paths.
* General bug fixes and improvements.
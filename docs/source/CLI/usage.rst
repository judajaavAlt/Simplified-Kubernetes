=====
Usage
=====

``easyk8s`` creates microservice templates, shares them through a registry
(the easyK8s API) and instantiates, builds and deploys them. Run it with
``python run.py`` or build the ``easyk8s`` executable with ``build.bat``.

Typical flow
------------

DevOps::

    easyk8s template create                 # reads ./template.yaml
    easyk8s login registry:8000             # once per registry
    easyk8s template push registry:8000/team/web:v1

Developer::

    easyk8s work set registry:8000/team     # default prefix
    easyk8s login registry:8000
    easyk8s template pull web:v1
    easyk8s template setup web:v1 -s -o shop    # sample values.env, build.env, deploy.env
    easyk8s template setup web:v1 -o shop -v shop/values.env
    cd shop
    easyk8s instance -b -d --dry-run         # required the first time
    easyk8s instance -b -d

Commands
--------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Command
     - What it does
   * - ``template create [-c FILE] [-e IGNORE]``
     - Validates ``template.yaml``, packs each layer in a reproducible
       tarball and stores the manifest. The ID is the SHA-256 of the manifest.
   * - ``template list``
     - ``REPOSITORY TAG ID CREATED SIZE``. A template that lost its tag shows
       ``<none>``.
   * - ``template inspect NAME``
     - Description, README, variables and commands of a template.
   * - ``template setup NAME [-v FILE] [-o DIR] [-s] [-f]``
     - Unpacks the template, replaces the variables and writes
       ``config.template``. ``-s`` only writes sample ``.env`` files.
   * - ``template tag SOURCE TARGET``
     - Adds another reference to a template, like ``docker tag``.
   * - ``template rm NAME [--remote]``
     - Removes a reference; the last one also deletes the manifest and the
       layers no other template uses. An ID removes every reference.
       ``--remote`` also deletes the manifest in the registry.
   * - ``template push NAME`` / ``template pull REFERENCE``
     - Transfer in 1 MB pieces verified with SHA-256 (3 retries per piece).
   * - ``template reindex``
     - Rebuilds the local index from the stored manifests.
   * - ``work set PREFIX`` / ``work show`` / ``work clear``
     - Default prefix to complete short references.
   * - ``login REGISTRY [-u USER] [-p PASSWORD] [--insecure]``
     - Saves a token per registry. If the registry asks for a new password,
       it is asked there. ``--insecure`` uses HTTP instead of HTTPS.
   * - ``logout REGISTRY``
     - Revokes and forgets the token.
   * - ``instance [-b] [-d] [-c FILE] [--build-file F] [--deploy-file F] [--dry-run] [--base-path DIR] [--admin]``
     - Resolves and runs the build and/or deploy commands of
       ``config.template``.

``NAME`` is a reference, a complete ID or the first 4 or more characters of
an ID. ``--verbose`` (before the command) shows the full trace of an error.

References
----------

A complete reference is ``host:port/organization/repo[:tag]``; the default
tag is ``latest``. With a default prefix (``work set``) a short reference is
completed from the left:

.. list-table::
   :header-rows: 1

   * - Prefix
     - You write
     - Result
   * - ``host:port``
     - ``org/repo:v1``
     - ``host:port/org/repo:v1``
   * - ``host:port/org``
     - ``repo``
     - ``host:port/org/repo:latest``
   * - ``host:port/org/repo``
     - ``:v1``
     - ``host:port/org/repo:v1``

Without a prefix only complete references are accepted.

template.yaml
-------------

.. code-block:: yaml

    tag: registry:8000/team/web:v1     # or a short reference
    description: Web service             # optional
    readme: docs/README.md               # optional, embedded in the manifest
    template:
      layers:                            # at least one
        - origin: src                    # folder: its content goes inside objective/
          objective: app
        - origin: build.bat              # file: goes to objective/build.bat
          objective: .
    instantiation:
      arguments:                         # optional
        - name: service
          type: str                      # str, int, bool or float
          default: shop                  # required, of the declared type
          description: Service name
    build:
      arguments: []
      commands:
        - docker build -t [%service%] .
    deploy:
      commands:
        - kubectl apply -f k8s

Every problem is reported at once: missing sections, missing origins, invalid
names, types or defaults, repeated names and invalid commands.

Every ``.yaml`` or ``.yml`` file of the layers must also be well formed: no
syntax errors, no key without a value (``spec:`` with nothing after it) and no
empty list item. Write ``null`` or ``~`` when a value is empty on purpose. The
check runs in ``template create`` with the defaults of the variables and again
in ``template setup`` with the chosen values. Files with ``{{ }}`` (Go or Helm
templates) are skipped, because they only become YAML once rendered. The
meaning of Kubernetes values (replicas, ports, labels) is not checked. Files are
excluded with ``.templateignore`` (or else ``.gitignore``) next to
``template.yaml``, using the ``.gitignore`` syntax.

Variables
---------

* Placeholders are ``[%name%]``; spaces inside are optional: ``[% name %]``.
  This syntax does not clash with Helm or Go templates (``{{ }}``).
* They are replaced in file contents, in file and folder names and in
  commands. Placeholders of undeclared names are left untouched.
* ``\[%name%]`` produces the literal text ``[%name%]``.
* Booleans are only ``true`` or ``false``, in lowercase.

``.env`` files (``values.env``, ``build.env``, ``deploy.env``) use
``NAME = VALUE``; quotes around the value are optional and ``#`` starts a
comment. In build and deploy, values come (from lowest to highest priority)
from the stage defaults, the values chosen in ``template setup`` and the
stage ``.env`` file.

Existing files
--------------

When ``template setup`` would overwrite files, the list is shown once and you
choose ``[a] overwrite all``, ``[o] one by one`` or ``[c] cancel``. Nothing is
written before the answer. ``--force`` overwrites without asking.

Build and deploy commands
-------------------------

Each command is one line. Programs such as ``docker``, ``kubectl`` or
``helm`` are run directly, without a shell, so the same template works on
Windows and Linux. Pipes and redirections (``|``, ``>``, ``<``, ``&&``,
``;``) are not allowed; for file handling use the standard commands, which
the CLI runs itself on any system:

.. list-table::
   :header-rows: 1

   * - Standard command
     - Effect
   * - ``makeDirectory PATH``
     - Creates a folder and its parents.
   * - ``removePath PATH``
     - Deletes a file or folder (marked as destructive).
   * - ``copyPath SOURCE TARGET``
     - Copies a file or folder.
   * - ``movePath SOURCE TARGET``
     - Moves or renames.
   * - ``writeFile PATH TEXT...``
     - Writes the text to a file.
   * - ``changeDirectory PATH``
     - Changes the folder of the following commands.
   * - ``setEnv NAME VALUE``
     - Sets an environment variable for the following commands.
   * - ``print TEXT...``
     - Prints the text.

A shell can still be called explicitly (``powershell -Command ...`` or
``bash -c ...``), but then the template is no longer portable.

Dry run
-------

The first time a template (manifest ID) is used on a machine, each stage
must be run with ``--dry-run``. It shows every resolved command, the
equivalent PowerShell or shell command of each standard command, and marks
destructive commands (``removePath``, ``kubectl delete``, ``docker rm``,
``helm uninstall``...). After that, the stage can run. ``--admin`` runs
programs with ``sudo`` on Linux and requires a terminal opened as
administrator on Windows.

Exit codes
----------

.. list-table::
   :header-rows: 1

   * - Code
     - Meaning
   * - 0
     - Success.
   * - 1
     - Usage or validation error, missing template or file, cancelled.
   * - 2
     - Registry or network error (including not being logged in).
   * - 3
     - A build or deploy command failed.

Data folder
-----------

``%LOCALAPPDATA%\judajaav\easyK8s`` on Windows and
``~/.local/share/easyk8s`` on Linux (``$XDG_DATA_HOME`` is respected).
``EASYK8S_DATA`` overrides it. It contains ``config.json`` (default prefix),
``credentials.json`` (tokens per registry), ``index.db`` (local index and
dry runs), ``manifests/`` and ``layers/``.

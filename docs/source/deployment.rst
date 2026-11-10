================
Deployment guide
================

This guide is for the **system administrators** who install easyK8s for a
team. End users do not need it: they only need the address of the registry
(``host:port``), an account, and the CLI (see :doc:`CLI/usage`).

easyK8s has two parts:

* the **registry server** (``api``), installed once per organization, which
  stores and shares the templates;
* the **CLI** (``easyk8s``), installed on the machine of every DevOps engineer
  and developer.

Server requirements
-------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Requirement
     - Value
   * - Operating system
     - Windows or Linux.
   * - Python
     - 3.11 or newer.
   * - Python dependencies
     - About 20 MB (FastAPI, Uvicorn, PyYAML and their dependencies). The
       source code takes less than 1 MB.
   * - Disk for data
     - The size of the stored templates plus a margin for uploads in
       progress. Identical layers are stored only once. A single file
       (layer or manifest) is limited to 1 GB by default, and the pieces of
       an unfinished upload are kept until the session expires (24 hours
       without activity by default).
   * - Network
     - One TCP port for the API (8000 by default). Users must reach it
       through HTTPS, so a reverse proxy with a TLS certificate is needed
       in front of the server.
   * - Memory and CPU
     - Modest: one Python process. Transfers are made in pieces of 1 MB.

Installing the server
---------------------

1. **Get the code** and enter the folder::

      git clone https://github.com/judajaavAlt/Simplified-Kubernetes.git
      cd Simplified-Kubernetes

2. **Create a virtual environment and install the dependencies**::

      python -m venv .venv
      .venv\Scripts\activate          (Windows)
      source .venv/bin/activate       (Linux)
      pip install -r requirements.txt

   ``requirements.txt`` also contains the development tools (pytest and
   Sphinx). A server that is only going to run needs
   ``pip install fastapi uvicorn pyyaml``.

3. **Configure the server** with environment variables. All of them are
   optional:

   .. list-table::
      :header-rows: 1
      :widths: 40 60

      * - Variable
        - Meaning
      * - ``EASYK8S_API_DATA``
        - Data folder. Default: ``%LOCALAPPDATA%\judajaav\easyK8s-api`` on
          Windows and ``~/.easyk8s-api`` on Linux.
      * - ``EASYK8S_API_PEPPER``
        - Secret added to every password hash. If it is not set, a random
          one is created once in ``pepper.key`` inside the data folder.
      * - ``EASYK8S_API_MAX_BLOB_SIZE``
        - Largest accepted file, in bytes (1 GB by default).
      * - ``EASYK8S_API_SESSION_TTL_HOURS``
        - Hours without activity before an upload or download expires
          (24 by default).
      * - ``EASYK8S_API_HASH_ITERATIONS``
        - PBKDF2 iterations for passwords (600 000 by default).

4. **Create the first administrator** on the server machine. The password is
   asked when it is not given::

      python -m api create-admin --nickname root

5. **Start the server**::

      python -m api serve --host 127.0.0.1 --port 8000

   It can also be started directly with Uvicorn:
   ``uvicorn api.main:create --factory --host 127.0.0.1 --port 8000``.
   The interactive description of the endpoints is available at ``/docs``.

6. **Publish it through HTTPS.** The server does not provide TLS by itself.
   Place a reverse proxy in front of it; for example, with Caddy, which
   obtains the certificate automatically, the whole configuration is::

      registry.example.com {
          reverse_proxy 127.0.0.1:8000
      }

   Users then write references such as
   ``registry.example.com:443/team/web:v1``. For tests on a local network,
   the CLI can connect over plain HTTP with ``easyk8s login host:port
   --insecure``.

7. **Create the user accounts.** There is no CLI command for this yet; the
   administrator calls the API. First obtain a token, then create each user
   with a temporary password and a role (``devops`` publishes and deletes
   templates, ``developer`` only downloads them, ``admin`` manages the
   server)::

      curl -X POST https://registry.example.com/v1/auth/token \
           -H "Content-Type: application/json" \
           -d '{"nickname": "root", "password": "<password>"}'

      curl -X POST https://registry.example.com/v1/users \
           -H "Authorization: Bearer <token>" \
           -H "Content-Type: application/json" \
           -d '{"nickname": "ana", "password": "<temporary>", "role": "devops"}'

   Each user must replace the temporary password the first time they run
   ``easyk8s login``; the CLI asks for the new one.

8. **Check the installation** from a user machine::

      easyk8s login registry.example.com:443

Running the server as a service
-------------------------------

On Linux, a ``systemd`` unit keeps the server running and starts it with the
machine (adjust the paths and the user)::

   [Unit]
   Description=easyK8s registry
   After=network.target

   [Service]
   User=easyk8s
   WorkingDirectory=/opt/Simplified-Kubernetes
   Environment=EASYK8S_API_DATA=/var/lib/easyk8s
   ExecStart=/opt/Simplified-Kubernetes/.venv/bin/python -m api serve --host 127.0.0.1 --port 8000
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target

On Windows, the same command can be registered as a service with a tool such
as NSSM or started by the Task Scheduler.

Operation and maintenance
-------------------------

* **Data folder.** It contains ``registry.db`` (users, repositories, tags,
  sessions and audit log), ``storage/blobs`` (stored templates, one folder per
  file), ``storage/uploads`` (pieces of unfinished uploads) and ``pepper.key``.
* **Backups.** Stop the server and copy the whole data folder. Keep
  ``pepper.key`` (or the ``EASYK8S_API_PEPPER`` value) secret and safe:
  without it no password can be verified.
* **Disk space.** Unfinished uploads are removed when they expire; this
  happens when the server starts and when an administrator calls
  ``POST /v1/admin/cleanup``. Deleting a template
  (``easyk8s template rm <reference> --remote``) also deletes the layers no
  other template uses.
* **Audit.** ``GET /v1/audit`` (administrators only) lists who did what and
  when.

Installing the CLI on user machines
-----------------------------------

* **Requirements:** Windows or Linux and Python 3.11 or newer. The CLI
  dependencies (Click, PyYAML and HTTPX) take about 7 MB.
* **Installation:** clone the repository, create a virtual environment and
  run ``pip install click pyyaml httpx``; the CLI is then started with
  ``python run.py`` (or ``python -m cli``). ``build.bat`` packages it as a
  single ``easyk8s`` executable with PyInstaller (this packaging is still to
  be validated).
* **Local data:** templates, the local index and the sessions are stored in
  ``%LOCALAPPDATA%\judajaav\easyK8s`` on Windows and
  ``~/.local/share/easyk8s`` on Linux (``EASYK8S_DATA`` changes it). This
  folder grows with every template created or pulled; see :doc:`CLI/usage`.

Known limitations
-----------------

* The server does not provide HTTPS by itself; a reverse proxy is required.
* Tokens do not expire until the user logs out or changes the password.
* Users are created through the API; there is no CLI command for it yet.
* One server serves one organization.

.. Simplified k8s documentation master file, created by
   sphinx-quickstart on Sun Mar 22 18:02:39 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Simplified k8s documentation
============================

easyK8s lets DevOps teams publish microservice templates and lets developers
instantiate, build and deploy them on Kubernetes without writing the
infrastructure themselves.

* The **CLI** creates templates, stores them locally, instantiates them and
  runs their build and deploy commands.
* The **API** is the registry each organization deploys: it receives and hands
  out templates in 1 MB pieces verified with SHA-256, with users, roles and an
  audit log.

Both follow the same layered architecture: ``data`` → ``persistence`` →
``domain`` → ``application`` → ``presentation`` → ``userInterface``, with
``infraestructure`` as a transversal layer injected from a single composition
root. Docstrings follow the Google style.

.. toctree::
   :maxdepth: 3

   deployment
   CLI/cli
   API/api

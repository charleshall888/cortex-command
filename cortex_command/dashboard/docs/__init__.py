"""The Docs view: read, map and (rarely) edit a repo's governing documents.

Modules:

``model``    the dataclasses every other module speaks — nodes, edges, the
             corpus, and the map geometry the templates draw verbatim.
``corpus``   builds a :class:`model.Corpus` from a repo root: the closed
             governing set, mechanical edge extraction, backlinks.
``render``   markdown → sanitized HTML with citations linkified and a TOC.
``layout``   server-side geometry for the ladder map and the neighbourhood
             strip. Integers only, no markup.
``edit``     the hash-locked, allowlisted, atomic write behind the Edit form.

Everything is computed per request. No module here writes to dashboard
state, and only ``edit`` writes to disk at all.
"""

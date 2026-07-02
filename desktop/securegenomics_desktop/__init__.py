"""SecureGenomics Desktop — a native UI over the `secgen` CLI engine.

The desktop app does not re-implement any genomics, crypto, or networking logic.
It drives the very same manager classes the CLI commands use
(``securegenomics.auth``, ``securegenomics.project``, ``securegenomics.data`` …),
so every custody guarantee the CLI makes holds here unchanged: the FHE secret
key is generated and used locally and never crosses the network.
"""

__version__ = "0.1.0"

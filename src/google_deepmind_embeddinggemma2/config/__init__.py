"""Configuration layer: YAML in, typed entities out.

The only thing you normally need from here is the manager, importable either way::

    from google_deepmind_embeddinggemma2.config import ConfigurationManager
    from google_deepmind_embeddinggemma2.config.configuration import ConfigurationManager
"""

from google_deepmind_embeddinggemma2.config.configuration import ConfigurationManager

__all__ = ["ConfigurationManager"]

"""Integration provider framework.

Importing this package registers every available provider (the Python analogue
of ``registerIntegration(new PlayitProvider())``). Add new providers here.
"""

from app.integrations.playit.provider import PlayitProvider
from app.integrations.registry import register_provider

register_provider(PlayitProvider())

# Future providers register the same way, e.g.:
# from app.integrations.cloudflare.provider import CloudflareTunnelProvider
# register_provider(CloudflareTunnelProvider())

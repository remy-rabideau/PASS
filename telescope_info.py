import os
from across.sdk.v1.configuration import Configuration
from across.sdk.v1.api_client_wrapper import ApiClientWrapper
from across.sdk.v1.api.telescope_api import TelescopeApi
from across.sdk.v1.api.observatory_api import ObservatoryApi

# Credentials come from env vars ACROSS_SERVER_ID and ACROSS_SERVER_SECRET
# (or pass username/password directly to Configuration)
config = Configuration(host="https://api.across.sciencecloud.nasa.gov/v1")
client = ApiClientWrapper.get_client(configuration=config)

# api = TelescopeApi(client)
# telescopes = api.get_telescopes()
# for t in telescopes:
#     print(t.id, t.name)

observatory_api = ObservatoryApi(client)
observatories = observatory_api.get_observatories()
for o in observatories:
    print(o.id, o.name)
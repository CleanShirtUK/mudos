def register(context):
    from lulu.lutris_install import LutrisInstallExecutor
    from lulu.catalogue import CatalogueStore
    from lulu.paths import PATHS
    context.register("acquisition", {"provider": "lutris",
                                      "executor": LutrisInstallExecutor(catalogue=CatalogueStore(PATHS.catalogue_db)),
                                      "limit": 1})

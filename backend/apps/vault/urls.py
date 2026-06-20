from django.urls import path

from .views import VaultDeleteView, VaultImportAllView, VaultImportView, VaultInitView, VaultKeysView, VaultSetView, VaultSourcesView
from .views_copy import VaultCopyView
from .views_pull import VaultPullFromHubView

urlpatterns = [
    path(
        "projects/<slug:project_slug>/vault/init/",
        VaultInitView.as_view(),
        name="vault-init",
    ),
    path(
        "projects/<slug:project_slug>/vault/keys/",
        VaultKeysView.as_view(),
        name="vault-keys",
    ),
    path(
        "projects/<slug:project_slug>/vault/keys/set/",
        VaultSetView.as_view(),
        name="vault-set",
    ),
    path(
        "projects/<slug:project_slug>/vault/keys/delete/",
        VaultDeleteView.as_view(),
        name="vault-delete",
    ),
    path(
        "projects/<slug:project_slug>/vault/keys/copy/",
        VaultCopyView.as_view(),
        name="vault-copy",
    ),
    path(
        "projects/<slug:project_slug>/vault/pull-from-hub/",
        VaultPullFromHubView.as_view(),
        name="vault-pull-from-hub",
    ),
    path(
        "projects/<slug:project_slug>/vault/import-all/",
        VaultImportAllView.as_view(),
        name="vault-import-all",
    ),
    path(
        "projects/<slug:project_slug>/vault/sources/",
        VaultSourcesView.as_view(),
        name="vault-sources",
    ),
    path(
        "projects/<slug:project_slug>/vault/import/",
        VaultImportView.as_view(),
        name="vault-import",
    ),
]

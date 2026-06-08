from django.urls import path

from .views import VaultDeleteView, VaultImportView, VaultInitView, VaultKeysView, VaultSetView

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
        "projects/<slug:project_slug>/vault/import/",
        VaultImportView.as_view(),
        name="vault-import",
    ),
]

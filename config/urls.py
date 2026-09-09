from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("inventario.urls")),
]

# A pasta media NÃO é mais servida por URL pública. Os PDFs saem pelas views
# `contrato_pdf` e `aditivo_pdf`, que conferem a permissão "ver_pdfs" antes de
# entregar o arquivo — servir /media/ direto aqui deixaria qualquer pessoa com
# o link abrir o PDF sem passar pela trava.

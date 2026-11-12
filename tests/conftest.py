"""Configuración común de pytest.

Fuerza la persistencia local para que ninguna prueba escriba en skillfisi-dev,
aunque exista backend/.env con credenciales reales.
"""

import os

os.environ["SKILLFISI_PERSISTENCE"] = "local"

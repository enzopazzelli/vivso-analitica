"""El origen vacío: las 13 tablas sin filas. Es la forma de apagar el simulador sin conectar nada (ANALITICA_ORIGEN=vacio)."""
from analitica.calendario import ahora_local
from analitica.esquema import TABLAS
from analitica.origenes.base import Lectura, tabla_vacia


class OrigenVacio:
    codigo = "vacio"

    def leer(self) -> Lectura:
        return Lectura(origen=self.codigo, leido_en=ahora_local(), tablas={t: tabla_vacia(t) for t in TABLAS})

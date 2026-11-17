"""Límite de corridas por IP y por día, en memoria.

Suficiente para una demo con una sola instancia. Con varias instancias, el conteo
tendría que vivir en un almacén compartido (Redis o la misma base Postgres).
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Rechazo:
    motivo: str
    reintentar_en_segundos: int


class LimitadorDeCorridas:
    VENTANA_IP = 3600  # una hora
    VENTANA_DIA = 86400
    MAX_IPS_EN_MEMORIA = 5000

    def __init__(self, por_ip_por_hora: int, por_dia: int, reloj: Callable[[], float] = time.monotonic):
        self._por_ip = por_ip_por_hora
        self._por_dia = por_dia
        self._reloj = reloj  # inyectable para poder probarlo sin esperar una hora
        self._historial_ip: dict[str, deque[float]] = defaultdict(deque)
        self._historial_dia: deque[float] = deque()

    def intentar(self, ip: str) -> Rechazo | None:
        """Registra la corrida si está permitida; si no, devuelve el motivo."""
        ahora = self._reloj()
        historial_ip = self._historial_ip[ip]
        self._descartar_viejos(historial_ip, ahora - self.VENTANA_IP)
        self._descartar_viejos(self._historial_dia, ahora - self.VENTANA_DIA)

        if len(self._historial_dia) >= self._por_dia:
            espera = self._historial_dia[0] + self.VENTANA_DIA - ahora
            return Rechazo("La demo alcanzó su límite diario de correos procesados.", int(espera) + 1)
        if len(historial_ip) >= self._por_ip:
            espera = historial_ip[0] + self.VENTANA_IP - ahora
            return Rechazo("Procesaste muchos correos en la última hora. Intenta más tarde.", int(espera) + 1)

        historial_ip.append(ahora)
        self._historial_dia.append(ahora)
        if len(self._historial_ip) > self.MAX_IPS_EN_MEMORIA:
            self._olvidar_ips_inactivas(ahora)
        return None

    def _olvidar_ips_inactivas(self, ahora: float) -> None:
        for ip in list(self._historial_ip):
            self._descartar_viejos(self._historial_ip[ip], ahora - self.VENTANA_IP)
            if not self._historial_ip[ip]:
                del self._historial_ip[ip]

    @staticmethod
    def _descartar_viejos(historial: deque[float], limite: float) -> None:
        while historial and historial[0] <= limite:
            historial.popleft()

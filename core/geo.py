"""Coordenadas (lat, lon) de las ciudades de los proveedores, para el mapa del panel.

Tabla fija de 40 filas (centro aproximado de cada ciudad): no depende de ningún servicio externo
y funciona sin internet durante la demo. Lancaster es la de Pensilvania (EE. UU.) y Taizhou la de
Zhejiang, igual que en el diccionario geográfico (core/suppliers.py).
"""
from __future__ import annotations

CITY_COORDS: dict[str, tuple[float, float]] = {
    "Hyderabad": (17.385, 78.487), "Ahmedabad": (23.023, 72.571), "Taizhou": (28.656, 121.421),
    "Basel": (47.560, 7.589), "Wuhan": (30.593, 114.306), "Shanghai": (31.230, 121.474),
    "Cork": (51.899, -8.476), "Ludwigshafen": (49.477, 8.445), "Milan": (45.464, 9.190),
    "Valencia": (39.470, -0.376), "Oslo": (59.914, 10.752), "Kaohsiung": (22.627, 120.301),
    "Vadodara": (22.307, 73.181), "Mainz": (49.993, 8.247), "Bergamo": (45.698, 9.677),
    "Lancaster": (40.038, -76.306), "Barcelona": (41.387, 2.169), "Lodz": (51.759, 19.456),
    "Osaka": (34.694, 135.502), "Monterrey": (25.687, -100.316), "Antwerp": (51.219, 4.403),
    "Dublin": (53.350, -6.260), "Hangzhou": (30.274, 120.155), "San Juan": (18.466, -66.106),
    "Zurich": (47.377, 8.542), "Hsinchu": (24.814, 120.968), "Darmstadt": (49.873, 8.651),
    "Boston": (42.360, -71.059), "Rotterdam": (51.924, 4.478), "Singapore": (1.352, 103.820),
    "Xi'an": (34.342, 108.940), "Bengaluru": (12.972, 77.595), "Madrid": (40.417, -3.704),
    "Sao Paulo": (-23.551, -46.633), "Ho Chi Minh City": (10.823, 106.630), "Cologne": (50.938, 6.960),
    "Tangier": (35.760, -5.834),
}


def coords(city: str) -> tuple[float, float] | None:
    return CITY_COORDS.get(city)

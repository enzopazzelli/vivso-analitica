"""Microservicio de analítica de VIVSO.

Lee el sistema de Desarrollo (o un origen simulado con sus mismas tablas y reglas), conserva la historia que ese sistema
no guarda, calcula indicadores sobre las 6 etapas de obra y los publica.

El núcleo (catálogo, calendario, feriados, esquema y orígenes) no importa fastapi ni streamlit.
"""

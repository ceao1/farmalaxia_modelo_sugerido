#!/bin/bash
# Consulta la base dbventas restaurada en el contenedor farmalaxia-sql.
#
# La contraseña se toma de la variable de entorno MSSQL_SA_PASSWORD.
# NO poner secretos aquí: este archivo está versionado.
#
# Uso:  MSSQL_SA_PASSWORD='...' ./src/00_consultar_bd.sh -Q "SELECT TOP 10 * FROM tblVentas"
set -euo pipefail
if [ -z "${MSSQL_SA_PASSWORD:-}" ]; then
  echo "Falta MSSQL_SA_PASSWORD. Ejemplo:" >&2
  echo "  export MSSQL_SA_PASSWORD='tu-contraseña'" >&2
  exit 1
fi

if [ "$(docker inspect -f '{{.State.Running}}' farmalaxia-sql 2>/dev/null)" != "true" ]; then
  echo "El contenedor no está corriendo. Arráncalo con: docker start farmalaxia-sql" >&2
  exit 1
fi
exec docker exec -i farmalaxia-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -d dbventas "$@"

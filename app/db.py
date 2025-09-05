import oracledb
from . import config

def get_connection():
    dsn = oracledb.makedsn(config.ORACLE_HOST, config.ORACLE_PORT, service_name=config.ORACLE_SERVICE)
    conn = oracledb.connect(user=config.ORACLE_USER, password=config.ORACLE_PASSWORD, dsn=dsn, thin=True)
    return conn

MERGE_SQL = """
MERGE INTO PIZARRAS_PUBLICAS T
USING (
  SELECT TO_DATE(:FECHA,'YYYY-MM-DD') FECHA, :PLAZA PLAZA, :FUENTE FUENTE, :PRODUCTO PRODUCTO FROM DUAL
) S
ON (T.FECHA=S.FECHA AND T.PLAZA=S.PLAZA AND T.FUENTE=S.FUENTE AND T.PRODUCTO=S.PRODUCTO)
WHEN MATCHED THEN UPDATE SET
  T.PRECIO_TN=:PRECIO_TN, T.VAR_ABS=:VAR_ABS, T.VAR_PCT=:VAR_PCT,
  T.TENDENCIA=:TENDENCIA, T.MONEDA=:MONEDA, T.HORA_FUENTE=:HORA_FUENTE, T.URL_FUENTE=:URL_FUENTE
WHEN NOT MATCHED THEN INSERT (
  FECHA, PLAZA, FUENTE, PRODUCTO, MONEDA, PRECIO_TN, VAR_ABS, VAR_PCT, TENDENCIA, HORA_FUENTE, URL_FUENTE
) VALUES (
  TO_DATE(:FECHA,'YYYY-MM-DD'), :PLAZA, :FUENTE, :PRODUCTO, :MONEDA, :PRECIO_TN, :VAR_ABS, :VAR_PCT, :TENDENCIA, :HORA_FUENTE, :URL_FUENTE
)
"""

def bulk_upsert(rows):
    if not rows:
        return {"processed": 0, "message": "No rows to insert"}
    binds = []
    for r in rows:
        binds.append({
            "FECHA": r["fecha"],
            "PLAZA": r["plaza"],
            "FUENTE": r["fuente"],
            "PRODUCTO": r["producto"],
            "MONEDA": r.get("moneda", "ARS"),
            "PRECIO_TN": r["precio_tn"],
            "VAR_ABS": r.get("var_abs"),
            "VAR_PCT": r.get("var_pct"),
            "TENDENCIA": r.get("tendencia"),
            "HORA_FUENTE": r.get("hora_fuente"),
            "URL_FUENTE": r.get("url_fuente"),
        })
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(MERGE_SQL, binds)
        conn.commit()
    return {"processed": len(rows)}

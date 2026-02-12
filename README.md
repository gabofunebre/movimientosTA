# Movdin

Aplicación web basada en FastAPI para registrar movimientos de dinero y facturación.

## Tabla de contenidos

- [Características](#características)
- [Guía rápida de uso](#guía-rápida-de-uso)
- [Notificaciones interoperables](#notificaciones-interoperables)
- [Sincronización incremental de cuenta de facturación](#sincronización-incremental-de-cuenta-de-facturación)
- [Movimientos exportables](#movimientos-exportables)
- [Cálculos de moneda](#cálculos-de-moneda)
- [Desarrollo con Docker](#desarrollo-con-docker)

## Características

- **Cuentas:** Cada cuenta tiene nombre, moneda, saldo inicial, color y puede marcarse como cuenta de facturación.
- **Transacciones:** Se pueden registrar ingresos y egresos asociados a una cuenta.
- **Facturas:** Para la cuenta de facturación se cargan facturas de compra y venta. El sistema calcula automáticamente IVA e IIBB.
- **Transacciones frecuentes:** Plantillas para agilizar carga de movimientos repetitivos.
- **Usuarios y permisos:** Registro de usuarios, inicio de sesión, aprobación por administrador y roles de administrador.
- **Notificaciones:** Recepción y consulta de notificaciones interoperables con una app hermana mediante HMAC y claves de idempotencia.

## Guía rápida de uso

1. Regístrate con tu correo y espera la aprobación de un administrador.
2. Crea tus cuentas indicando nombre, moneda y saldo inicial.
3. Registra ingresos y egresos desde la sección de transacciones.
4. Si corresponde, carga facturas de compra y venta en la cuenta de facturación.
5. Aprovecha las transacciones frecuentes para movimientos repetitivos.

Consulta [USAGE.md](USAGE.md) para una guía más detallada.

## Notificaciones interoperables

La aplicación expone el endpoint `/notificaciones` que implementa el protocolo compartido con la app hermana.

- **POST `/notificaciones`**
  - Con encabezados `X-Timestamp`, `X-Idempotency-Key`, `X-Source-App` y `X-Signature` válidos se aceptan notificaciones entrantes y se guardan como *unread* (respuesta `202`).
  - Con cuerpo `{"action": "ack", "id": "<uuid>"}` marca la notificación como leída y responde `200`.
- **GET `/notificaciones`** permite listar, filtrar por estado/topic/type, paginar mediante cursor y opcionalmente incluir `unread_count`.

Variables de entorno relevantes:

- `NOTIF_SHARED_SECRET`: secreto compartido para firmar y validar notificaciones (obligatorio).
- `NOTIF_SOURCE_APP`: identificador propio (`app-a` o `app-b`, default `app-a`).
- `PEER_BASE_URL`: URL HTTPS base de la app hermana para envíos salientes.

Existe además una tarea en segundo plano que elimina diariamente las notificaciones leídas con más de 90 días de antigüedad.


## Sincronización incremental de cuenta de facturación

El endpoint `GET /movimientos_cuenta_facturada` expone dos vistas del mismo lote, con propósitos distintos:

- `transaction_events`: **fuente de verdad** para sincronización incremental. Incluye `created`, `updated` y `deleted`, por lo que un consumidor event-sourced debe aplicar esta secuencia para reconstruir el estado remoto.
- `transactions` y `active_transactions_in_batch`: campos de **conveniencia** que incluyen solo payloads no eliminados (`created`/`updated`) del lote actual.

Importante: las bajas **solo** se representan en `transaction_events` mediante eventos con `event=deleted` y `transaction=null` + `transaction_id` para purgar entidades en el consumidor. Por diseño, nunca aparecen en `transactions` ni en `active_transactions_in_batch`.

## Movimientos exportables

Los endpoints bajo `/movimientos_exportables` permiten sincronizar un catálogo de movimientos con sistemas externos mediante eventos ordenados e idempotentes.

### GET `/movimientos_exportables/cambios`

Devuelve los eventos pendientes de confirmación desde un checkpoint determinado.

- **Parámetros de consulta**
  - `since` (opcional, `int ≥ 0`): identifica el último evento confirmado por el consumidor. Si se omite se utilizará `last_confirmed_id`, es decir, el último evento confirmado previamente vía `ack`.
  - `limit` (opcional, `1-500`, default `100`): cantidad máxima de eventos a retornar. El servicio internamente consulta `limit + 1` filas para determinar si quedan más eventos disponibles.
- **Respuesta**
  - `last_confirmed_id`: último evento confirmado en el servidor, utilizado como valor por defecto cuando no se envía `since`.
  - `checkpoint_id`: identificador que representa el último evento incluido en la respuesta. Si no hubiera eventos nuevos, repite el `effective_since` aplicado, permitiendo confirmar que no hay novedades.
  - `has_more`: indica si existen eventos adicionales (true cuando se truncó la respuesta por `limit`).
  - `changes`: lista ordenada ascendentemente de eventos con estructura `ExportableMovementChangeEvent`.
    - Cada evento incluye `id`, `movement_id`, `event` (`created`, `updated`, `deleted`), `occurred_at` y un `payload` con la información relevante del cambio.

El campo `payload` describe el estado actual del movimiento exportable asociado al evento, y según el tipo de evento incluye:

- Alta (`created`): `id` y `description` del nuevo movimiento.
- Edición (`updated`): `id`, `description` actualizada y `previous_description` para que el consumidor pueda detectar cambios.
- Baja (`deleted`): `id`, `description` y el indicador `deleted: true` para permitir la purga remota.

**Ejemplo de request**

```http
GET /movimientos_exportables/cambios?since=12&limit=2
```

**Ejemplo de response**

```json
{
  "last_confirmed_id": 10,
  "checkpoint_id": 14,
  "has_more": true,
  "changes": [
    {
      "id": 13,
      "movement_id": 8,
      "event": "created",
      "occurred_at": "2024-01-05T10:15:23.123456",
      "payload": {
        "id": 8,
        "description": "Transferencia bancaria"
      }
    },
    {
      "id": 14,
      "movement_id": 2,
      "event": "updated",
      "occurred_at": "2024-01-05T11:01:02.987654",
      "payload": {
        "id": 2,
        "description": "Pago a proveedor",
        "previous_description": "Pago proveedor"
      }
    }
  ]
}
```

**Ejemplo de baja**

```json
{
  "id": 15,
  "movement_id": 5,
  "event": "deleted",
  "occurred_at": "2024-01-05T12:44:00.000000",
  "payload": {
    "id": 5,
    "description": "Servicio mensual",
    "deleted": true
  }
}
```

### POST `/movimientos_exportables/cambios/ack`

Confirma la recepción de los eventos hasta el `checkpoint_id` indicado y desencadena la purga de los eventos ya procesados.

- **Request**

  ```json
  {
    "checkpoint_id": 14
  }
  ```

- **Validaciones**
  - El `checkpoint_id` debe ser un entero mayor o igual a cero (`conint(ge=0)`).
  - No puede ser menor que `last_change_id`; en caso contrario se devuelve `400` con el mensaje *"El checkpoint es menor al último confirmado"*.
  - No puede superar el máximo `id` existente en `ExportableMovementChange`; si se envía uno inexistente se devuelve `400` con el mensaje *"El checkpoint indicado no existe"*.

Cuando el checkpoint es válido y distinto del último confirmado, se actualiza `last_change_id` y se eliminan de forma permanente todos los eventos `ExportableMovementChange` con `id` menor o igual al checkpoint, evitando reenvíos innecesarios. Si el checkpoint coincide con el último confirmado, simplemente se devuelve el estado actual sin modificar ni borrar eventos.

**Response**

```json
{
  "last_change_id": 14,
  "updated_at": "2024-01-05T11:01:05.000000"
}
```

## Cálculos de moneda

- **Saldo de cuentas:** El saldo de cada cuenta se calcula como `saldo_inicial + suma(transacciones)` para la fecha indicada.
- **Ajustes por facturación:** Si la cuenta es de facturación, el saldo neto descuenta IVA e IIBB de las ventas y suma el IVA de las compras.
- **Facturas:** Al crear o editar una factura se calcula automáticamente el IVA (`monto * porcentaje/100`) y, si es una venta, el IIBB sobre el monto más el IVA (`(monto + iva) * porcentaje/100`).
- Los montos se almacenan usando `Decimal` con dos decimales y no se realiza conversión automática entre monedas; los saldos se informan en la moneda de cada cuenta.

## Desarrollo con Docker

1. Copiar `.env.example` a `.env` y ajustar los valores según sea necesario, incluyendo `POSTGRES_DATA_PATH` que debe apuntar al directorio persistente de la base de datos (por ejemplo `/tuAlmacenamiento/Servicios/tu_app/postgres_data`).
2. Crear la red externa requerida si aún no existe:

   ```bash
   docker network create cloudflared_net
   ```
3. Levantar los servicios:

   ```bash
   docker compose up --build
   ```

Los contenedores no exponen puertos al host y se comunican entre sí por nombre dentro de la red interna de Docker:

- la aplicación escucha en el puerto `8000` del contenedor `movdin-app`
- PostgreSQL lo hace en el puerto `5432` del contenedor `movdin-db`

La aplicación también se une a la red externa `cloudflared_net` para poder ser accesible desde otros servicios. Utiliza `docker compose exec` u otros contenedores para interactuar con los servicios.

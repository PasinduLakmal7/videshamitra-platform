# notification-service (placeholder)

Owned by Person 1. This directory is a placeholder for the internal notification
deployable described in [`docs/architecture/microservices.md`](../../docs/architecture/microservices.md).

Planned responsibilities:

- Owns the `notification` schema and `notification_service_role`.
- Owns device tokens, preferences, quiet hours, delivery records and retries.
- Sends push through Firebase Cloud Messaging (Android, and iOS via FCM's APNs
  bridge) for the Flutter app, and WhatsApp template messages for proactive alerts.
- Consumes `notification.requested.v1` from `vm:notifications:requests`.
- Publishes optional `notification.delivery.updated.v1` to
  `vm:notifications:results`.
- Exposes only internal endpoints (`/internal/v1/devices`,
  `/internal/v1/preferences/{user_id}`, `/internal/v1/health`) verified with a
  service JWT.
- Never exposed through Kong.

`core-api` proxies device registration and preferences to this service; it does
not store tokens or preferences in the `core` schema.

A detailed task plan will be added once the core event and proxy contracts are
frozen. Do not add public routes here.

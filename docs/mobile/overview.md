# VideshaMitra Worker Mobile App

## Purpose

The worker mobile app is the primary product for **normal users** — Sri Lankan migrant workers preparing for, during, and after overseas employment. It is not a caseworker or admin tool; those stay in `admin-frontend/`.

The app source is maintained in a **separate repository** (owner: Person 3). This document defines its scope, behavior, and shared contracts; it does not live in this monorepo.

## Status

Documentation and API contracts are defined in this repository. Mobile implementation happens in the separate app repository.

## Stack

| Concern | Choice |
|---|---|
| Framework | Flutter (Dart), Android first |
| Navigation | `go_router` |
| State | Riverpod |
| HTTP | `dio` with an auth/refresh interceptor and `Idempotency-Key` on queued POSTs |
| Auth | `core-api` `/auth/otp/*` and `/auth/refresh`; tokens in `flutter_secure_storage` |
| Push | Firebase Cloud Messaging (`firebase_messaging`); iOS through FCM's APNs bridge |
| Camera/files | `camera` / `image_picker`, `file_picker` |
| Voice | `record` for capture, `just_audio` for playback; STT/TTS via `core-api` |
| Offline | `drift` (SQLite) cache + a persisted mutation queue |
| i18n | `flutter_localizations` + ARB files (`en`, `si`, `ta`) |
| Builds | Flutter build + Play Console (then App Store) |

## Screens (MVP)

1. Onboarding and language selection
2. Phone/OTP sign-in
3. Home / migration journey dashboard
4. Job offer and agency verification
   - Camera capture or file upload
   - Processing state
   - Risk verdict and supporting evidence
   - Verification history
5. AI assistant
   - Streaming chat
   - Voice input/output
   - Source citations
6. Check-ins (Day 7 / 30 / 90)
7. Documents
8. Complaints and escalation
9. Notifications
10. Profile, consent, and privacy settings

## Mobile-specific behavior

### Offline-first

- Cache the last verification results, guidance, and journey status.
- Queue check-in submissions and complaint drafts; retry with idempotency keys.
- Clearly indicate stale data and pending sync.

### Push notifications

- Register the FCM token after login (`POST /notifications/devices`); unregister on logout (`DELETE /notifications/devices/{token}`).
- Payloads include `type` and `deep_link` (`case`, `checkin`, `verification`).
- Used for check-in reminders, agency license changes, and caseworker replies.

### Document capture

- Compress images client-side before upload.
- Multi-page capture with reorder/delete.
- Upload progress, resumable retries, and offline queue.

### Voice and language

- Detect device language; default to Sinhala, allow Tamil and English.
- Voice input for low-literacy users; TTS for agent replies, with text always shown.
- All safety-critical text available in all three languages.

## Security and privacy

- Tokens in `flutter_secure_storage` (Android Keystore / iOS Keychain), never `SharedPreferences`.
- Optional biometric/PIN app lock (`local_auth`).
- PII redaction before LLM calls happens in `ai-service`.
- No documents cached unencrypted; purge caches on logout.
- Explicit consent for check-ins and data sharing.
- Release builds use code obfuscation (`--obfuscate --split-debug-info`) and HTTPS only.

## API usage

- Base URL from a build-time `--dart-define=API_BASE_URL=...`; the app calls only the public `core-api` surface through Kong.
- Auth via `core-api`, which proxies Supabase Auth; the client refreshes tokens with `/auth/refresh`.
- Push device registration via `/notifications/devices`; `core-api` proxies this to `notification-service`.
- Chat and speech use `core-api` proxy endpoints; the AI service is never called directly.
- Chat streaming: `POST /chat/sessions/{id}/messages` returns SSE; `attachments` must be the caller's own document IDs.
- `Idempotency-Key` header on queued POSTs (`/verification`, `/documents`, `/checkins/{id}/respond`, `/complaints`).

### Push delivery

`notification-service` owns device tokens, preferences, and delivery. It consumes `notification.requested.v1` events from `core-api` and sends FCM push. The mobile app only registers/unregisters tokens through `core-api`.

## Build and release

- Android first (the target audience is Android-dominant).
- Flavors: `dev`, `staging`, `prod`, each with its own Firebase project config.
- Store listing in Sinhala, Tamil, and English.
- Staged rollouts on Play Console, with a rollback plan.

## Out of scope

- Caseworker queues, evidence review, and admin analytics
- Admin-only agency management

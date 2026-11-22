# VideshaMitra Worker Mobile App

## Purpose

The worker mobile app is the primary product for **normal users** — Sri Lankan migrant workers preparing for, during, and after overseas employment. It is not a caseworker or admin tool; those stay in `admin-frontend/`.

The app source is maintained in a **separate repository**. This document defines its scope, behavior, and shared contracts; it does not live in this monorepo.

## Status

Documentation and API contracts are defined in this repository. Mobile implementation happens in the separate app repository.

## Stack

| Concern | Choice |
|---|---|
| Framework | React Native + Expo (managed workflow) |
| Language | TypeScript |
| Navigation | Expo Router |
| Server state | TanStack Query |
| Client state | Zustand |
| Auth | Supabase Auth + `expo-secure-store` |
| Push | Expo Notifications → FCM / APNs |
| Camera/files | `expo-camera`, `expo-document-picker`, `expo-file-system` |
| Voice | `expo-av` recording/playback + backend STT/TTS |
| Offline | AsyncStorage/SQLite + query persistence + mutation queue |
| i18n | `i18next` + `react-i18next` (`en`, `si`, `ta`) |
| Builds | EAS Build / EAS Submit |

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

- Register the device token after login; unregister on logout.
- Payloads include `type` and `deep_link` (`case`, `checkin`, `verification`).
- Used for check-in reminders, agency license changes, and caseworker replies.

### Document capture

- Compress images client-side before upload.
- Multi-page capture with reorder/delete.
- Upload progress, resumable retries, and offline queue.

### Voice and language

- Detect device language; default to Sinhala, allow Tamil and English.
- Voice input for low-literacy users; TTS for agent replies.
- All safety-critical text available in all three languages.

## Security and privacy

- JWTs in `expo-secure-store`, never AsyncStorage.
- Optional biometric/PIN app lock.
- PII redaction before LLM calls (backend guardrail).
- No documents cached unencrypted; purge on logout.
- Explicit consent for check-ins and data sharing.

## API usage

- Base URL from `EXPO_PUBLIC_API_BASE_URL`; the mobile app calls only the public `core-api` surface through Kong.
- Auth via Supabase; refresh tokens handled by the client.
- Push device registration via `/notifications/devices` (planned); `core-api` proxies this to `notification-service`.
- Chat and speech use `core-api` proxy endpoints; the AI service is never called directly.
- Chat streaming: `POST /chat/sessions/{id}/messages` with an SSE response (planned).
- `Idempotency-Key` for queued POSTs (planned).

### Push delivery

`notification-service` owns device tokens, preferences, and delivery. It consumes `notification.requested.v1` events from `core-api` and sends Expo/FCM/APNs push. The mobile app only registers/unregisters tokens through `core-api`.

## Build and release

- Android first (the target audience is Android-dominant).
- EAS profiles: `development`, `preview`, `production`.
- Store listing in Sinhala, Tamil, and English.
- Versioning and OTA updates via EAS Update, with a rollback plan.

## Out of scope

- Caseworker queues, evidence review, and admin analytics
- Admin-only agency management

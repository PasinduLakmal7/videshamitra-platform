#!/usr/bin/env python3
"""Idempotent development seed for core-api.

Creates 1 admin, 2 caseworkers, 3 workers, 4 agencies, 2 verifications,
1 journey with Day 7/30/90 check-ins (one overdue), a complaint with evidence
and a note, and one in-app notification per type.

Run after migrations:
    python scripts/seed_demo_data.py

Auth users are created through the Supabase Admin API when credentials are
configured; otherwise (plain Postgres / auth stub) they are inserted directly.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.db.pool import connect  # noqa: E402
from app.integrations.supabase.auth import SupabaseAuthClient  # noqa: E402

DEMO_PASSWORD = "Demo@12345"
NS = uuid5(NAMESPACE_URL, "videshamitra-demo-seed")


def did(name: str) -> UUID:
    return uuid5(NS, name)


USERS = [
    {
        "key": "admin",
        "email": "admin@videshamitra.lk",
        "phone": "+94770000001",
        "role": "admin",
        "full_name": "Nadeesha Perera",
        "language": "en",
        "country": "LK",
    },
    {
        "key": "caseworker1",
        "email": "caseworker1@videshamitra.lk",
        "phone": "+94770000002",
        "role": "caseworker",
        "full_name": "Ruwan Jayasinghe",
        "language": "si",
        "country": "LK",
    },
    {
        "key": "caseworker2",
        "email": "caseworker2@videshamitra.lk",
        "phone": "+94770000003",
        "role": "caseworker",
        "full_name": "Fathima Rizwan",
        "language": "ta",
        "country": "LK",
    },
    {
        "key": "worker1",
        "email": "worker1@example.com",
        "phone": "+94771110001",
        "role": "worker",
        "full_name": "Amali Fernando",
        "language": "si",
        "country": "SA",
    },
    {
        "key": "worker2",
        "email": "worker2@example.com",
        "phone": "+94771110002",
        "role": "worker",
        "full_name": "Kannan Selvarajah",
        "language": "ta",
        "country": "QA",
    },
    {
        "key": "worker3",
        "email": "worker3@example.com",
        "phone": "+94771110003",
        "role": "worker",
        "full_name": "Dinesh Kumara",
        "language": "en",
        "country": "AE",
    },
]

AGENCIES = [
    {
        "key": "agency-active",
        "registration_no": "SLBFE/1001",
        "name": "Lanka Safe Employment Agency",
        "license_no": "LIC-1001",
        "status": "active",
        "expires": "+2 years",
        "district": "Colombo",
    },
    {
        "key": "agency-suspended",
        "registration_no": "SLBFE/1002",
        "name": "Global Dreams Recruitment",
        "license_no": "LIC-1002",
        "status": "suspended",
        "expires": "+1 year",
        "district": "Gampaha",
    },
    {
        "key": "agency-expired",
        "registration_no": "SLBFE/1003",
        "name": "Sunrise Manpower Services",
        "license_no": "LIC-1003",
        "status": "expired",
        "expires": "-30 days",
        "district": "Kandy",
    },
    {
        "key": "agency-mismatch",
        "registration_no": "SLBFE/1004",
        "name": "Star Overseas Placement",
        "license_no": "LIC-9999",
        "status": "unknown",
        "expires": "+6 months",
        "district": "Jaffna",
    },
]


def _offset_days(value: str) -> int:
    number_text, unit = value.split()
    amount = int(number_text)
    if unit.startswith("year"):
        return amount * 365
    return amount


async def ensure_auth_user(
    client: SupabaseAuthClient,
    conn: asyncpg.Connection,
    *,
    email: str,
    phone: str,
    full_name: str,
    language: str,
) -> UUID:
    metadata = {"full_name": full_name, "preferred_language": language}
    if settings.supabase_admin_configured:
        users = await client.admin_list_users()
        for user in users:
            if (user.get("email") or "").lower() == email.lower():
                return UUID(user["id"])
        created = await client.admin_create_user(
            email=email,
            phone=phone,
            password=DEMO_PASSWORD,
            email_confirm=True,
            phone_confirm=True,
            user_metadata=metadata,
        )
        return UUID(created["id"])

    user_id = did(f"auth:{email}")
    await conn.execute(
        """
        insert into auth.users (id, email, phone, raw_user_meta_data)
        values ($1, $2, $3, $4)
        on conflict (id) do update
        set email = excluded.email, phone = excluded.phone,
            raw_user_meta_data = excluded.raw_user_meta_data
        """,
        user_id,
        email,
        phone,
        metadata,
    )
    return user_id


async def seed_users(conn: asyncpg.Connection, client: SupabaseAuthClient) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for user in USERS:
        user_id = await ensure_auth_user(
            client,
            conn,
            email=user["email"],
            phone=user["phone"],
            full_name=user["full_name"],
            language=user["language"],
        )
        await conn.execute(
            """
            insert into core.users
                (id, role, full_name, phone, preferred_language, country_of_work, is_active)
            values ($1, $2::core.user_role, $3, $4, $5::core.language_code, $6, true)
            on conflict (id) do update
            set role = excluded.role,
                full_name = excluded.full_name,
                phone = excluded.phone,
                preferred_language = excluded.preferred_language,
                country_of_work = excluded.country_of_work,
                is_active = true
            """,
            user_id,
            user["role"],
            user["full_name"],
            user["phone"],
            user["language"],
            user["country"],
        )
        ids[user["key"]] = user_id
    return ids


async def seed_agencies(conn: asyncpg.Connection, admin_id: UUID) -> dict[str, UUID]:
    now = datetime.now(UTC)
    snapshot_date = now.date()
    snapshot_id = did("snapshot:seed")
    await conn.execute(
        """
        insert into core.agency_snapshots
            (id, snapshot_date, source_url, checksum, record_count, imported_by)
        values ($1, $2, 'seed://demo', 'seed-demo-checksum', $3, $4)
        on conflict (id) do update set record_count = excluded.record_count
        """,
        snapshot_id,
        snapshot_date,
        len(AGENCIES),
        admin_id,
    )
    ids: dict[str, UUID] = {}
    for agency in AGENCIES:
        expires = (now + timedelta(days=_offset_days(agency["expires"]))).date()
        row = await conn.fetchrow(
            """
            insert into core.agencies
                (id, registration_no, name, normalized_name, license_no,
                 license_status, license_expires_on, address, district,
                 phone, email, latest_snapshot_id)
            values ($1, $2, $3, lower($3), $4, $5::core.agency_license_status, $6,
                    $7, $8, $9, $10, $11)
            on conflict (registration_no) do update
            set name = excluded.name,
                normalized_name = excluded.normalized_name,
                license_no = excluded.license_no,
                license_status = excluded.license_status,
                license_expires_on = excluded.license_expires_on,
                district = excluded.district,
                latest_snapshot_id = excluded.latest_snapshot_id
            returning id
            """,
            did(agency["key"]),
            agency["registration_no"],
            agency["name"],
            agency["license_no"],
            agency["status"],
            expires,
            f"{agency['district']}, Sri Lanka",
            agency["district"],
            "+94110000000",
            f"{agency['key']}@example.lk",
            snapshot_id,
        )
        agency_id = row["id"]
        ids[agency["key"]] = agency_id
        await conn.execute(
            """
            insert into core.agency_license_history
                (id, agency_id, snapshot_id, license_no, status, issued_on, expires_on,
                 job_categories, raw_data)
            values ($1, $2, $3, $4, $5::core.agency_license_status, $6, $7,
                    $8, $9)
            on conflict (agency_id, snapshot_id, license_no) do nothing
            """,
            did(f"license:{agency['key']}"),
            agency_id,
            snapshot_id,
            agency["license_no"],
            agency["status"],
            (now - timedelta(days=365)).date(),
            expires,
            ["domestic", "hospitality"],
            {"source": "seed"},
        )
    return ids


async def seed_documents(
    conn: asyncpg.Connection, worker_id: UUID, verification_id: UUID, key: str
) -> UUID:
    document_id = did(key)
    await conn.execute(
        """
        insert into core.documents
            (id, user_id, verification_id, type, status, storage_path,
             original_filename, mime_type, size_bytes, page_count, sha256, metadata)
        values ($1, $2, $3, 'job_offer', 'processed', $4, $5,
                'application/pdf', 48213, 2, $6, '{"pages": 2, "seed": true}')
        on conflict (id) do update
        set verification_id = excluded.verification_id,
            status = excluded.status,
            deleted_at = null
        """,
        document_id,
        worker_id,
        verification_id,
        f"{worker_id}/{document_id}/seed-job-offer.pdf",
        f"{key}.pdf",
        f"seed-sha-{key}",
    )
    return document_id


async def seed_verifications(
    conn: asyncpg.Connection,
    workers: dict[str, UUID],
    agencies: dict[str, UUID],
) -> dict[str, UUID]:
    now = datetime.now(UTC)
    ids: dict[str, UUID] = {}
    specs = [
        {
            "key": "verification-low",
            "worker": "worker1",
            "agency": "agency-active",
            "job_title": "Domestic Worker",
            "employer_name": "Al Noor Household",
            "country": "SA",
            "salary": 45000,
            "currency": "LKR",
            "status": "verified",
            "risk_level": "low",
            "risk_score": 12,
            "findings": [{"code": "license_active", "message": "Agency license is active"}],
            "created": now - timedelta(days=2),
        },
        {
            "key": "verification-high",
            "worker": "worker1",
            "agency": "agency-suspended",
            "job_title": "Domestic Worker",
            "employer_name": "Rapid Gulf Recruiters",
            "country": "SA",
            "salary": 30000,
            "currency": "LKR",
            "status": "suspicious",
            "risk_level": "high",
            "risk_score": 82,
            "findings": [
                {
                    "code": "salary_deduction",
                    "message": "Deduction exceeds 20%",
                    "source": "seed-job-offer.pdf#p2",
                },
                {
                    "code": "license_suspended",
                    "message": "Agency license is suspended",
                },
            ],
            "created": now - timedelta(days=1),
        },
    ]
    for spec in specs:
        verification_id = did(spec["key"])
        await conn.execute(
            """
            insert into core.verifications
                (id, user_id, agency_id, agency_name_input, job_title, employer_name,
                 destination_country, offered_salary, currency, status, risk_level,
                 risk_score, findings, evidence, engine_version, analysis_run_id,
                 created_at, completed_at)
            values ($1, $2, $3, null, $4, $5, $6, $7, $8,
                    $9::core.verification_status, $10::core.risk_level, $11, $12,
                    $13, 'seed-ai@1.0.0', $14, $15, $16)
            on conflict (id) do update
            set status = excluded.status,
                risk_level = excluded.risk_level,
                risk_score = excluded.risk_score,
                findings = excluded.findings,
                created_at = excluded.created_at
            """,
            verification_id,
            workers[spec["worker"]],
            agencies[spec["agency"]],
            spec["job_title"],
            spec["employer_name"],
            spec["country"],
            spec["salary"],
            spec["currency"],
            spec["status"],
            spec["risk_level"],
            spec["risk_score"],
            spec["findings"],
            [],
            str(did(f"analysis:{spec['key']}")),
            spec["created"],
            spec["created"],
        )
        await seed_documents(conn, workers[spec["worker"]], verification_id, f"doc:{spec['key']}")
        ids[spec["key"]] = verification_id
    return ids


async def seed_journey(
    conn: asyncpg.Connection,
    workers: dict[str, UUID],
    agencies: dict[str, UUID],
) -> tuple[UUID, UUID]:
    now = datetime.now(UTC)
    journey_id = did("journey:worker1")
    departure = (now - timedelta(days=10)).date()
    await conn.execute(
        """
        insert into core.migration_journeys
            (id, user_id, agency_id, destination_country, employer_name, job_title,
             departure_date, stage, consent_checkins, consent_at, created_at)
        values ($1, $2, $3, 'SA', 'Al Noor Household', 'Domestic Worker', $4,
                'employed_abroad', true, $5, $6)
        on conflict (id) do update
        set consent_checkins = true,
            consent_at = excluded.consent_at,
            stage = 'employed_abroad'
        """,
        journey_id,
        workers["worker1"],
        agencies["agency-active"],
        departure,
        now - timedelta(days=10),
        now - timedelta(days=10),
    )

    expired_due = now - timedelta(days=3)
    checkins = [
        ("checkin-day7", expired_due, "sent", None),
        ("checkin-day30", now + timedelta(days=20), "scheduled", None),
        ("checkin-day90", now + timedelta(days=80), "scheduled", None),
    ]
    checkin_ids: dict[str, UUID] = {}
    for key, due_at, status, response in checkins:
        checkin_id = did(key)
        await conn.execute(
            """
            insert into core.checkins
                (id, journey_id, user_id, due_at, channel, status, sent_at, response)
            values ($1, $2, $3, $4, 'in_app', $5::core.checkin_status, $6, $7)
            on conflict (id) do update
            set journey_id = excluded.journey_id,
                user_id = excluded.user_id,
                due_at = excluded.due_at,
                status = excluded.status,
                sent_at = excluded.sent_at
            """,
            checkin_id,
            journey_id,
            workers["worker1"],
            due_at,
            status,
            due_at if status != "scheduled" else None,
            response,
        )
        checkin_ids[key] = checkin_id
    await conn.execute(
        """
        update core.migration_journeys
        set next_checkin_at = (
            select min(due_at) from core.checkins
            where journey_id = $1 and status in ('scheduled', 'sent')
        )
        where id = $1
        """,
        journey_id,
    )
    return journey_id, checkin_ids["checkin-day7"]


async def seed_complaint(
    conn: asyncpg.Connection,
    workers: dict[str, UUID],
    caseworker_id: UUID,
    journey_id: UUID,
    checkin_id: UUID,
    verification_id: UUID,
    agency_id: UUID,
    document_id: UUID,
) -> UUID:
    now = datetime.now(UTC)
    complaint_id = did("complaint:worker1")
    await conn.execute(
        """
        insert into core.complaints
            (id, user_id, journey_id, verification_id, agency_id, checkin_id,
             title, description, status, triage_tier, assigned_to, evidence,
             submitted_at, created_at)
        values ($1, $2, $3, $4, $5, $6, $7, $8,
                'under_review'::core.complaint_status, 2, $9, $10, $11, $12)
        on conflict (id) do update
        set status = excluded.status,
            triage_tier = excluded.triage_tier,
            assigned_to = excluded.assigned_to,
            submitted_at = excluded.submitted_at
        """,
        complaint_id,
        workers["worker1"],
        journey_id,
        verification_id,
        agency_id,
        checkin_id,
        "Salary deduction and suspended agency",
        "My agency deducted 40% of my salary and their license is suspended.",
        caseworker_id,
        [{"document_id": str(document_id), "note": "job offer"}],
        now - timedelta(days=1),
        now - timedelta(days=1),
    )
    await conn.execute(
        """
        insert into core.complaint_documents (complaint_id, document_id)
        values ($1, $2) on conflict do nothing
        """,
        complaint_id,
        document_id,
    )
    await conn.execute(
        """
        insert into core.case_notes (id, complaint_id, author_id, body, is_internal, created_at)
        values ($1, $2, $3, $4, true, $5)
        on conflict (id) do update set body = excluded.body
        """,
        did("note:complaint1"),
        complaint_id,
        caseworker_id,
        "Initial triage complete; requesting agency license history.",
        now - timedelta(hours=20),
    )
    return complaint_id


async def seed_notifications(conn: asyncpg.Connection, worker_id: UUID) -> int:
    now = datetime.now(UTC)
    specs = [
        ("checkin_due", "Safety check-in", "How are you doing? Tap to complete your check-in."),
        ("checkin_missed", "We missed you", "Please respond to your safety check-in."),
        ("agency_license_changed", "Agency license alert", "Your agency license is suspended."),
        (
            "verification_complete",
            "Verification complete",
            "Your job offer has a high-risk finding.",
        ),
        ("complaint_update", "Case updated", "Your case is under review."),
        ("caseworker_message", "Message from your caseworker", "Please call us when you can."),
        ("system", "Welcome to VideshaMitra", "Your account is ready."),
    ]
    for index, (notification_type, title, body) in enumerate(specs):
        await conn.execute(
            """
            insert into core.notifications
                (id, user_id, type, title, body, data, deep_link, created_at)
            values ($1, $2, $3::core.notification_type, $4, $5, $6, $7, $8)
            on conflict (id) do update
            set title = excluded.title, body = excluded.body
            """,
            did(f"notification:{notification_type}"),
            worker_id,
            notification_type,
            title,
            body,
            {"seed": True},
            "videshamitra://notifications",
            now - timedelta(hours=index),
        )
    return len(specs)


async def run() -> None:
    conn = await connect()
    auth_client = SupabaseAuthClient()
    try:
        async with conn.transaction():
            users = await seed_users(conn, auth_client)
            print(f"Seeded {len(users)} users")
            agencies = await seed_agencies(conn, users["admin"])
            print(f"Seeded {len(agencies)} agencies")
            verifications = await seed_verifications(conn, users, agencies)
            print(f"Seeded {len(verifications)} verifications")
            journey_id, overdue_checkin = await seed_journey(conn, users, agencies)
            print("Seeded journey + Day 7/30/90 check-ins (one overdue)")
            high_document = did("doc:verification-high")
            complaint_id = await seed_complaint(
                conn,
                users,
                users["caseworker1"],
                journey_id,
                overdue_checkin,
                verifications["verification-high"],
                agencies["agency-suspended"],
                high_document,
            )
            print(f"Seeded complaint {complaint_id}")
            count = await seed_notifications(conn, users["worker1"])
            print(f"Seeded {count} notifications")
        print(f"Demo password for all users: {DEMO_PASSWORD}")
    finally:
        await auth_client.aclose()
        await conn.close()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())

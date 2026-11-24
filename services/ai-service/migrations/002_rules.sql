-- 002_rules.sql
-- Deterministic rule tables. Verdicts come from these rows and tool results, never model memory.
-- Every row cites a source; the seed below is DEMO DATA, not official SLBFE figures.

create table if not exists ai.fee_rules (
    id bigint generated always as identity primary key,
    destination text not null,
    job_category text not null,
    max_fee_lkr numeric(12, 2) not null check (max_fee_lkr >= 0),
    source text not null,
    effective_from date not null,
    unique (destination, job_category, effective_from)
);

create table if not exists ai.wage_floors (
    id bigint generated always as identity primary key,
    destination text not null,
    job_category text not null,
    min_monthly numeric(12, 2) not null check (min_monthly >= 0),
    currency char(3) not null,
    source text not null,
    effective_from date not null,
    unique (destination, job_category, effective_from)
);

create table if not exists ai.red_flag_rules (
    code text primary key,
    severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
    description_en text not null,
    description_si text not null,
    description_ta text not null,
    active boolean not null default true,
    source text not null,
    effective_from date not null
);

insert into ai.fee_rules (destination, job_category, max_fee_lkr, source, effective_from) values
    ('Kuwait', 'domestic_worker', 0, 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Saudi Arabia', 'domestic_worker', 0, 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Kuwait', 'driver', 150000, 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Qatar', 'driver', 150000, 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('UAE', 'construction', 175000, 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Saudi Arabia', 'construction', 175000, 'DEMO DATA - not an official SLBFE figure', '2026-01-01')
on conflict do nothing;

insert into ai.wage_floors
    (destination, job_category, min_monthly, currency, source, effective_from) values
    ('Kuwait', 'domestic_worker', 100, 'KWD', 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Saudi Arabia', 'domestic_worker', 1000, 'SAR', 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Qatar', 'domestic_worker', 1000, 'QAR', 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('UAE', 'domestic_worker', 1100, 'AED', 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('Qatar', 'driver', 1800, 'QAR', 'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('UAE', 'construction', 1000, 'AED', 'DEMO DATA - not an official SLBFE figure', '2026-01-01')
on conflict do nothing;

insert into ai.red_flag_rules
    (code, severity, description_en, description_si, description_ta, source, effective_from) values
    ('fee_above_cap', 'high',
     'The agency fee is higher than the allowed limit.',
     'නියෝජිත ආයතන ගාස්තුව අවසර ලත් සීමාවට වඩා වැඩිය.',
     'முகவர் கட்டணம் அனுமதிக்கப்பட்ட வரம்பை விட அதிகமாக உள்ளது.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('wage_below_floor', 'high',
     'The offered salary is below the minimum wage for this job and country.',
     'පිරිනමන වැටුප මෙම රැකියාවට සහ රටට අදාළ අවම වැටුපට වඩා අඩුය.',
     'வழங்கப்படும் சம்பளம் இந்த வேலை மற்றும் நாட்டுக்கான குறைந்தபட்ச ஊதியத்தை விட குறைவாக உள்ளது.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('agency_not_found_in_register', 'critical',
     'This agency was not found in the SLBFE register.',
     'මෙම නියෝජිත ආයතනය SLBFE ලේඛනයේ හමු නොවීය.',
     'இந்த முகவர் நிறுவனம் SLBFE பதிவேட்டில் காணப்படவில்லை.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('license_expired', 'critical',
     'The agency licence has expired.',
     'නියෝජිත ආයතනයේ බලපත්‍රය කල් ඉකුත් වී ඇත.',
     'முகவர் நிறுவனத்தின் உரிமம் காலாவதியாகிவிட்டது.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('license_suspended', 'critical',
     'The agency licence is suspended or cancelled.',
     'නියෝජිත ආයතනයේ බලපත්‍රය අත්හිටුවා හෝ අවලංගු කර ඇත.',
     'முகவர் நிறுவனத்தின் உரிமம் இடைநிறுத்தப்பட்டுள்ளது அல்லது ரத்து செய்யப்பட்டுள்ளது.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('passport_retention', 'high',
     'The document says the employer or agency will keep your passport.',
     'සේවා යෝජකයා හෝ නියෝජිත ආයතනය ඔබේ ගමන් බලපත්‍රය තබා ගන්නා බව ලේඛනයේ සඳහන් වේ.',
     'முதலாளி அல்லது முகவர் உங்கள் கடவுச்சீட்டை வைத்திருப்பார்கள் என்று ஆவணத்தில் கூறப்பட்டுள்ளது.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('payment_to_personal_account', 'high',
     'You are asked to pay money into a personal bank account.',
     'පුද්ගලික බැංකු ගිණුමකට මුදල් ගෙවන ලෙස ඔබෙන් ඉල්ලා ඇත.',
     'தனிப்பட்ட வங்கிக் கணக்கில் பணம் செலுத்துமாறு உங்களிடம் கேட்கப்படுகிறது.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01'),
    ('unable_to_verify', 'medium',
     'We could not verify this offer with official sources.',
     'නිල මූලාශ්‍ර සමඟ මෙම රැකියා දීමනාව තහවුරු කිරීමට අපට නොහැකි විය.',
     'அதிகாரப்பூர்வ ஆதாரங்களுடன் இந்த வேலை வாய்ப்பை எங்களால் சரிபார்க்க முடியவில்லை.',
     'DEMO DATA - not an official SLBFE figure', '2026-01-01')
on conflict do nothing;

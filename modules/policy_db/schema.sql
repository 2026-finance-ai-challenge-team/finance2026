PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS banks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name_ko TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL REFERENCES banks(id),
    policy_key TEXT NOT NULL,
    label_ko TEXT NOT NULL,
    customer_type TEXT NOT NULL,
    account_type TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'retired')),
    verified_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE (bank_id, policy_key, version)
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_version_id INTEGER NOT NULL
        REFERENCES policy_versions(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    scope TEXT NOT NULL,
    publisher TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    UNIQUE (policy_version_id, source_key)
);

CREATE TABLE IF NOT EXISTS requirement_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_version_id INTEGER NOT NULL
        REFERENCES policy_versions(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    requirement_code TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('branch', 'non_face_to_face')),
    visitor_type TEXT NOT NULL CHECK (
        visitor_type IN ('representative', 'agent', 'representative_or_agent')
    ),
    requirement_level TEXT NOT NULL CHECK (
        requirement_level IN (
            'official_minimum',
            'official_required',
            'recommended_additional'
        )
    ),
    eligibility_notes TEXT,
    notes TEXT,
    UNIQUE (policy_version_id, requirement_code)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name_ko TEXT NOT NULL,
    issuer TEXT,
    issuer_aliases_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(issuer_aliases_json)),
    title_patterns_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(title_patterns_json)),
    required_anchors_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(required_anchors_json)),
    negative_anchors_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(negative_anchors_json)),
    doc_number_label TEXT,
    issued_at_labels_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(issued_at_labels_json)),
    validity_days INTEGER CHECK (validity_days IS NULL OR validity_days >= 0),
    source_url TEXT,
    as_of TEXT NOT NULL,
    last_checked TEXT NOT NULL,
    signature_verified INTEGER NOT NULL DEFAULT 0 CHECK (signature_verified IN (0, 1)),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS requirement_documents (
    requirement_set_id INTEGER NOT NULL
        REFERENCES requirement_sets(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    original_required INTEGER CHECK (
        original_required IS NULL OR original_required IN (0, 1)
    ),
    issued_within_days INTEGER CHECK (
        issued_within_days IS NULL OR issued_within_days >= 0
    ),
    submission_method TEXT NOT NULL CHECK (
        submission_method IN ('original', 'original_or_copy', 'photo_or_pdf', 'auto_submit')
    ),
    choice_group TEXT,
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (requirement_set_id, document_id)
);

CREATE TABLE IF NOT EXISTS preparations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_set_id INTEGER NOT NULL
        REFERENCES requirement_sets(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name_ko TEXT NOT NULL,
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (requirement_set_id, code)
);

CREATE TABLE IF NOT EXISTS policy_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_version_id INTEGER NOT NULL
        REFERENCES policy_versions(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    condition_code TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('branch', 'non_face_to_face', 'all')),
    expression_json TEXT NOT NULL CHECK (json_valid(expression_json)),
    result_code TEXT NOT NULL,
    description TEXT NOT NULL,
    UNIQUE (policy_version_id, condition_code)
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_lookup
    ON policy_versions (bank_id, policy_key, status, version);

CREATE INDEX IF NOT EXISTS idx_requirement_sets_lookup
    ON requirement_sets (policy_version_id, channel, visitor_type, requirement_level);

CREATE INDEX IF NOT EXISTS idx_policy_conditions_lookup
    ON policy_conditions (policy_version_id, channel);

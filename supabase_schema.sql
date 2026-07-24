-- Users table
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    credits INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Transactions table
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id),
    amount INTEGER,
    type TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tasks table
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id),
    status TEXT DEFAULT 'pending',
    image_data TEXT,
    result_image TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_tasks_status ON tasks(status);

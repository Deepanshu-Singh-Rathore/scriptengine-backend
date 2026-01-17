# Supabase Database Setup Guide

## 1. Enable pgvector Extension

In your Supabase dashboard:
1. Go to **Database** → **Extensions**
2. Search for `vector`
3. Enable the **pgvector** extension

## 2. Configure Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Update the `.env` file with your Supabase credentials:
```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.dyqtjusjewimrmoetxet.supabase.co:5432/postgres
POSTGRES_PASSWORD=YOUR_PASSWORD
GEMINI_API_KEY=YOUR_GEMINI_KEY
```

## 3. Test Connection

Run the test script:
```bash
cd backend
python test_db_connection.py
```

Expected output:
```
✓ Connection successful!
✓ Current Time: 2026-01-16 ...
✓ pgvector extension is installed
✓ Existing tables: []
✓ Connection closed successfully
```

## 4. Initialize Database

Start the backend server to auto-create tables:
```bash
python3 run.py
```

The application will automatically:
- Create the `scripts` table
- Set up pgvector for embeddings
- Initialize the database schema

## 5. Verify Setup

Check that tables were created:
```bash
python test_db_connection.py
```

You should see the `scripts` table listed.

## Troubleshooting

**pgvector not found:**
- Enable it in Supabase Dashboard → Database → Extensions

**Connection timeout:**
- Check your Supabase project is not paused
- Verify the connection string is correct

**Authentication failed:**
- Double-check your password in `.env`
- Ensure you're using the correct database user (usually `postgres`)

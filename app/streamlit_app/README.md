# Clinexus Streamlit App

**AI-Powered Clinical Trial Intelligence Platform**

Multi-page Streamlit application for researchers to upload clinical trials and reviewers to approve AI-generated signals.

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r ../../requirements_streamlit.txt
```

### 2. Set Environment Variables

Create a `.env` file or export:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=clinical_trial_db
export DB_USER=postgres
export DB_PASSWORD=yourpassword
export API_BASE_URL=http://localhost:8000
```

### 3. Run the App

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

---

## Architecture

### Pages

- **Home** (`pages/home.py`) - Dashboard with metrics
- **Upload & Analyze** (`pages/upload_analyze.py`) - Upload trials, trigger pipeline
- **Signal Review** (`pages/signal_review.py`) - HITL approval workflow
- **Analytics** (`pages/analytics.py`) - Data visualization
- **Sponsor Profiles** (`pages/sponsor_profiles.py`) - Credibility tracking
- **Search** (`pages/search.py`) - Global search
- **Analysis History** (`pages/analysis_history.py`) - Past analyses
- **Settings** (`pages/settings.py`) - Admin configuration

### Modules

- **`config.py`** - Constants, roles, styling
- **`auth.py`** - Authentication & authorization
- **`database.py`** - Database queries (async)
- **`api_client.py`** - FastAPI backend client
- **`components/`** - Reusable UI components (coming soon)

---

## User Roles

### Researcher
- Upload clinical trials
- Trigger AI analysis
- View their own results
- Search analyses

### Reviewer
- Review AI-generated signals
- Approve/reject with comments
- View sponsor profiles
- Access analytics

### Admin
- All permissions
- User management
- System logs
- Data export

---

## Database Requirements

Ensure these tables exist in PostgreSQL:

```sql
CREATE TABLE users (
    email VARCHAR(255) PRIMARY KEY,
    role VARCHAR(50),
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE analyses (
    analysis_id UUID PRIMARY KEY,
    nct_id VARCHAR(50),
    researcher_id VARCHAR(255),
    status VARCHAR(20),
    total_signals INTEGER,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE signals (
    signal_id UUID PRIMARY KEY,
    analysis_id UUID REFERENCES analyses,
    nct_id VARCHAR(50),
    agent_name VARCHAR(100),
    signal_type VARCHAR(100),
    summary TEXT,
    confidence FLOAT,
    evidence JSONB,
    status VARCHAR(20),
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,
    reviewer_comment TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE sponsor_profiles (
    sponsor_name VARCHAR(255) PRIMARY KEY,
    credibility_score FLOAT,
    total_trials INTEGER,
    results_posted_rate FLOAT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

## Features

### ✅ Implemented (Phase 1 & 2)

- [x] Multi-page navigation
- [x] Role-based access control
- [x] Login system (email-based MVP)
- [x] Home dashboard with metrics
- [x] Upload & analyze trials
- [x] Signal review workflow (HITL gate)
- [x] Analytics charts
- [x] Global search
- [x] Analysis history
- [x] Sponsor profiles (basic)
- [x] Admin settings

### 🚀 Coming Soon (Phase 3)

- [ ] Real-time pipeline progress tracking
- [ ] Advanced analytics (trends, forecasts)
- [ ] Sponsor comparison view
- [ ] Custom report generation
- [ ] Batch signal approval
- [ ] User management interface
- [ ] System logs viewer
- [ ] Data export tools
- [ ] Mobile responsiveness optimization

---

## Deployment

### Streamlit Cloud (Recommended for Demo)

```bash
# Push to GitHub
git push origin streamlit-app

# Create app at https://share.streamlit.io
# Connect GitHub repo and deploy
```

### Docker (Cloud Run)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements_streamlit.txt
EXPOSE 8501
CMD ["streamlit", "run", "app/streamlit_app/app.py", "--server.port=8501"]
```

### Local Development

```bash
streamlit run app.py --logger.level=debug --client.showErrorDetails=true
```

---

## Configuration

Edit `config.py` to customize:

- Agent names & colors
- Signal types & labels
- User roles & permissions
- Pagination limits
- Cache TTL

---

## Troubleshooting

### "Database connection failed"
- Ensure PostgreSQL is running
- Check DB_HOST, DB_PORT, DB_USER environment variables
- Verify pgvector extension is installed

### "API backend not responding"
- Ensure FastAPI is running on API_BASE_URL
- Check network connectivity
- Review API logs

### "Login not working"
- Clear browser cache
- Check that users table exists in database
- Verify email format

---

## Development

### Adding a New Page

1. Create file in `pages/new_page.py`
2. Implement `render_new_page()` function
3. Add to navigation in `app.py`
4. Import the render function

### Adding Database Queries

1. Add async method to `Database` class in `database.py`
2. Use `run_async()` wrapper in pages
3. Add error handling

### Styling

Streamlit styling is configured in `config.py`:
- Primary color: #4ECDC4 (teal)
- Page layout: wide
- Icons: emoji

---

## Testing

```bash
# Install test dependencies
pip install pytest pytest-streamlit

# Run tests
pytest tests/
```

---

## Performance Tips

- Use `@st.cache_data` for expensive queries
- Limit dataframe size to <10,000 rows
- Use pagination for large result sets
- Pre-load common data (agents, roles)

---

## Support

Questions? Check:
- `/docs/` (API documentation)
- GitHub issues
- Streamlit documentation: https://docs.streamlit.io

---

**Last updated:** 2026-07-26  
**Version:** 1.0.0 (MVP)  
**Status:** Production Ready ✅

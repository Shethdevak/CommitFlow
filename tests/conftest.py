import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.connection import Base
from app.config.settings import Settings
from app.models.domain import Commit, RedmineProject, RedmineFeature

@pytest.fixture(scope="function")
def db_session():
    """Provides a transactional in-memory SQLite database session for isolated testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def mock_settings():
    """Provides mock settings configuration."""
    return Settings(
        GITHUB_TOKEN="gh_mock_token",
        GITLAB_TOKEN="gl_mock_token",
        GITLAB_API_URL="https://gitlab.mock.com",
        AUTHOR_NAME="Test Author",
        REDMINE_URL="https://redmine.mock.com",
        REDMINE_API_KEY="rm_mock_key",
        DB_PATH=":memory:",
        MAPPINGS_PATH="configs/repo_mappings.yaml",
        TIMEZONE="UTC",
        AI_PROVIDER="openai",
        AI_CONFIDENCE_THRESHOLD=80,
        DEFAULT_FEATURE="General Development",
        OPENAI_API_KEY="sk_mock_openai"
    )

@pytest.fixture
def mock_commits():
    """Provides a list of sample mock git commits."""
    return [
        Commit(
            hash="c1b2a3d4e5f6g7h8",
            message="Fixed invoice calculation issue",
            description="Adjusted tax values in payment processor",
            author="Test Author",
            repository="digiflux-ezytix/be-api",
            committed_date=datetime(2026, 7, 6, 12, 0, 0),
            url="https://github.com/digiflux-ezytix/be-api/commit/c1b2a3d4e5f6g7h8",
            changed_files=["payment/calculator.py", "tests/test_calculator.py"],
            additions=12,
            deletions=2
        ),
        Commit(
            hash="h8g7f6e5d4c3b2a1",
            message="Updated dashboard layout for mobile devices",
            description="Applied responsive grids to navigation page",
            author="Test Author",
            repository="digiflux-ezytix/web-app",
            committed_date=datetime(2026, 7, 6, 14, 30, 0),
            url="https://github.com/digiflux-ezytix/web-app/commit/h8g7f6e5d4c3b2a1",
            changed_files=["src/components/Dashboard.jsx", "src/styles/grid.css"],
            additions=45,
            deletions=10
        )
    ]

@pytest.fixture
def mock_redmine_project():
    """Provides a mock Redmine Project."""
    return RedmineProject(
        id=101,
        name="Ezytix Tech",
        identifier="ezytix-tech",
        description="Core tech project"
    )

@pytest.fixture
def mock_redmine_features():
    """Provides a list of mock Redmine Features (parent issues)."""
    return [
        RedmineFeature(id=2001, subject="Payment", description="Integrations for payment systems", project_id=101),
        RedmineFeature(id=2002, subject="UI Design", description="Frontend interfaces", project_id=101),
        RedmineFeature(id=2003, subject="General Development", description="Generic issues tracker", project_id=101),
    ]

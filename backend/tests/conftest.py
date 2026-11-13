import os, tempfile
os.environ["DATABASE_URL"] = "sqlite:///./test_resqnet.db"
os.environ["SEED_DEMO_DATA"] = "true"
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, engine
@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client: yield test_client
    Base.metadata.drop_all(bind=engine)

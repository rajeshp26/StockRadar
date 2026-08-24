from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_financial_repo():
    repo = MagicMock()
    repo.client = MagicMock()
    repo.client.table.return_value = repo.client
    for m in ["select", "eq", "lte", "update", "insert", "delete"]:
        getattr(repo.client, m).return_value = repo.client
    return repo


@pytest.fixture
def mock_scheduler_repo():
    return MagicMock()


class TestLockManager:
    @pytest.fixture
    def lock_manager(self, mock_financial_repo, mock_scheduler_repo):
        from application.locks.lock_manager import LockManager
        return LockManager(
            financial_repo=mock_financial_repo,
            scheduler_repo=mock_scheduler_repo,
        )

    async def test_acquire_company_lock_success(self, lock_manager, mock_financial_repo):
        # Stale takeover returns data
        mock_financial_repo.client.execute.return_value = MagicMock(data=[{"id": 1}])
        token = await lock_manager.acquire_company_lock(
            company_id=1, owner_id="worker1",
        )
        assert token is not None
        assert isinstance(token, str)

    async def test_acquire_company_lock_insert(self, lock_manager, mock_financial_repo):
        # Stale takeover fails (no expired lock), then insert succeeds
        mock_financial_repo.client.execute.side_effect = [
            MagicMock(data=[]),           # update returns empty
            MagicMock(data=[{"id": 1}]),  # insert returns data
        ]
        token = await lock_manager.acquire_company_lock(
            company_id=1, owner_id="worker1",
        )
        assert token is not None

    async def test_acquire_company_lock_fails(self, lock_manager, mock_financial_repo):
        mock_financial_repo.client.execute.side_effect = [
            MagicMock(data=[]),  # update empty
        ]
        mock_financial_repo.client.insert.side_effect = Exception("duplicate")
        token = await lock_manager.acquire_company_lock(
            company_id=1, owner_id="worker1",
        )
        assert token is None

    async def test_release_company_lock(self, lock_manager, mock_financial_repo):
        mock_financial_repo.client.execute.return_value = MagicMock(data=[{"id": 1}])
        result = await lock_manager.release_company_lock(
            company_id=1, owner_id="worker1", lease_token="tok-123",
        )
        assert result is True

    async def test_release_company_lock_fails_wrong_token(self, lock_manager, mock_financial_repo):
        mock_financial_repo.client.execute.return_value = MagicMock(data=[])
        result = await lock_manager.release_company_lock(
            company_id=1, owner_id="worker1", lease_token="wrong-token",
        )
        assert result is False

    async def test_renew_company_lock(self, lock_manager, mock_financial_repo):
        mock_financial_repo.client.execute.return_value = MagicMock(data=[{"id": 1}])
        result = await lock_manager.renew_company_lock(
            company_id=1, owner_id="worker1", lease_token="tok-123",
        )
        assert result is True

    async def test_renew_company_lock_fails(self, lock_manager, mock_financial_repo):
        mock_financial_repo.client.execute.return_value = MagicMock(data=[])
        result = await lock_manager.renew_company_lock(
            company_id=1, owner_id="worker1", lease_token="wrong-token",
        )
        assert result is False


class TestResourceLockManager:
    @pytest.fixture
    def lock_manager(self, mock_financial_repo, mock_scheduler_repo):
        from application.locks.lock_manager import LockManager
        return LockManager(
            financial_repo=mock_financial_repo,
            scheduler_repo=mock_scheduler_repo,
        )

    def test_acquire_resource_lock(self, lock_manager, mock_scheduler_repo):
        mock_scheduler_repo.acquire_resource_lock.return_value = "tok-456"
        token = lock_manager.acquire_resource_lock(
            resource_type="company", resource_id="123",
            lock_type="admin", owner_id="worker1",
        )
        assert token == "tok-456"

    def test_release_resource_lock(self, lock_manager, mock_scheduler_repo):
        mock_scheduler_repo.release_resource_lock.return_value = True
        result = lock_manager.release_resource_lock(
            resource_type="company", resource_id="123",
            lock_type="admin", owner_id="worker1",
            lease_token="tok-456",
        )
        assert result is True

    def test_renew_resource_lock(self, lock_manager, mock_scheduler_repo):
        mock_scheduler_repo.renew_resource_lock.return_value = True
        result = lock_manager.renew_resource_lock(
            resource_type="company", resource_id="123",
            lock_type="admin", owner_id="worker1",
            lease_token="tok-456",
        )
        assert result is True


class TestLockManagerEdgeCases:
    def test_init_with_default_scheduler_repo(self, mock_financial_repo):
        from application.locks.lock_manager import LockManager
        lm = LockManager(financial_repo=mock_financial_repo)
        assert lm._financial_repo is mock_financial_repo
        assert lm._scheduler_repo is not None

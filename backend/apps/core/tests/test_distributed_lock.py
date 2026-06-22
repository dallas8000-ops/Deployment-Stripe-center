from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.distributed_lock import distributed_lock

_REDIS_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": ["redis://127.0.0.1:6379/0"]},
    }
}


@override_settings(CHANNEL_LAYERS=_REDIS_LAYERS, CELERY_TASK_ALWAYS_EAGER=False)
class DistributedLockTests(SimpleTestCase):
    @patch("apps.core.distributed_lock._redis_client")
    def test_acquire_and_release(self, mock_client_factory):
        client = MagicMock()
        mock_client_factory.return_value = client
        client.set.return_value = True
        client.get.return_value = b"token"

        with patch("apps.core.distributed_lock.secrets.token_hex", return_value="token"):
            with distributed_lock("test-job", ttl_seconds=60) as acquired:
                self.assertTrue(acquired)

        client.set.assert_called_once()

    @patch("apps.core.distributed_lock._redis_client")
    def test_skip_when_lock_held(self, mock_client_factory):
        client = MagicMock()
        mock_client_factory.return_value = client
        client.set.return_value = False

        with distributed_lock("busy-job", blocking=False) as acquired:
            self.assertFalse(acquired)

import pytest

from common.models import Brokers
from users.models import BybitApiToken, OKXApiToken


@pytest.fixture
def crypto_broker(user):
    return Brokers.objects.create(investor=user, name="Bybit", country="Crypto")


@pytest.fixture
def okx_broker(user):
    return Brokers.objects.create(investor=user, name="OKX", country="Crypto")


def _assert_safe_token_payload(payload):
    assert "api_secret" not in payload
    assert "passphrase" not in payload
    assert "encrypted_token" not in payload
    assert "encrypted_passphrase" not in payload


@pytest.mark.django_db
def test_bybit_token_post_encrypts_secret_and_omits_secret_fields(
    user, authenticated_client, crypto_broker
):
    response = authenticated_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": crypto_broker.id,
            "api_key": "bybit-key",
            "api_secret": "bybit-secret",
            "testnet": True,
        },
        format="json",
    )

    assert response.status_code == 201
    token = BybitApiToken.objects.get(user=user, broker=crypto_broker)
    assert token.api_key == "bybit-key"
    assert token.get_api_secret(user) == "bybit-secret"
    assert token.encrypted_token != b"bybit-secret"
    assert token.testnet is True
    assert token.is_active is True
    assert response.data["api_key"] == "bybit-key"
    assert response.data["testnet"] is True
    _assert_safe_token_payload(response.data)


@pytest.mark.django_db
def test_bybit_token_post_rejects_broker_owned_by_another_user(
    django_user_model, authenticated_client
):
    other_user = django_user_model.objects.create_user(username="other", password="pw")
    other_broker = Brokers.objects.create(investor=other_user, name="Bybit", country="Crypto")

    response = authenticated_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": other_broker.id,
            "api_key": "bybit-key",
            "api_secret": "bybit-secret",
            "testnet": False,
        },
        format="json",
    )

    assert response.status_code == 400
    assert BybitApiToken.objects.count() == 0


@pytest.mark.django_db
def test_okx_token_post_encrypts_secret_and_passphrase_and_omits_secret_fields(
    user, authenticated_client, okx_broker
):
    response = authenticated_client.post(
        "/users/api/okx-tokens/",
        {
            "broker": okx_broker.id,
            "api_key": "okx-key",
            "api_secret": "okx-secret",
            "passphrase": "okx-passphrase",
            "simulated_trading": True,
        },
        format="json",
    )

    assert response.status_code == 201
    token = OKXApiToken.objects.get(user=user, broker=okx_broker)
    assert token.api_key == "okx-key"
    assert token.get_api_secret(user) == "okx-secret"
    assert token.get_passphrase(user) == "okx-passphrase"
    assert token.encrypted_token != b"okx-secret"
    assert token.encrypted_passphrase != b"okx-passphrase"
    assert token.simulated_trading is True
    assert token.is_active is True
    assert response.data["api_key"] == "okx-key"
    assert response.data["simulated_trading"] is True
    _assert_safe_token_payload(response.data)


@pytest.mark.django_db
def test_bybit_token_patch_encrypts_replaced_secret(
    user, authenticated_client, crypto_broker
):
    token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="bybit-key",
        testnet=False,
    )
    token.set_api_secret("old-secret", user)

    response = authenticated_client.patch(
        f"/users/api/bybit-tokens/{token.id}/",
        {"api_secret": "new-secret"},
        format="json",
    )

    assert response.status_code == 200
    token.refresh_from_db()
    assert token.get_api_secret(user) == "new-secret"
    assert token.encrypted_token != b"new-secret"
    _assert_safe_token_payload(response.data)


@pytest.mark.django_db
def test_okx_token_patch_encrypts_replaced_secret_and_passphrase(
    user, authenticated_client, okx_broker
):
    token = OKXApiToken(
        user=user,
        broker=okx_broker,
        api_key="okx-key",
        simulated_trading=False,
    )
    token.set_credentials("old-secret", "old-passphrase", user)

    response = authenticated_client.patch(
        f"/users/api/okx-tokens/{token.id}/",
        {
            "api_secret": "new-secret",
            "passphrase": "new-passphrase",
        },
        format="json",
    )

    assert response.status_code == 200
    token.refresh_from_db()
    assert token.get_api_secret(user) == "new-secret"
    assert token.get_passphrase(user) == "new-passphrase"
    assert token.encrypted_token != b"new-secret"
    assert token.encrypted_passphrase != b"new-passphrase"
    _assert_safe_token_payload(response.data)


@pytest.mark.django_db
def test_replacement_active_token_deactivates_previous_token_for_same_environment(
    user, authenticated_client, crypto_broker, okx_broker
):
    first_bybit = authenticated_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": crypto_broker.id,
            "api_key": "same-key",
            "api_secret": "first-secret",
            "testnet": False,
        },
        format="json",
    )
    second_bybit = authenticated_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": crypto_broker.id,
            "api_key": "same-key",
            "api_secret": "second-secret",
            "testnet": False,
        },
        format="json",
    )
    first_okx = authenticated_client.post(
        "/users/api/okx-tokens/",
        {
            "broker": okx_broker.id,
            "api_key": "same-okx-key",
            "api_secret": "first-okx-secret",
            "passphrase": "first-passphrase",
            "simulated_trading": False,
        },
        format="json",
    )
    second_okx = authenticated_client.post(
        "/users/api/okx-tokens/",
        {
            "broker": okx_broker.id,
            "api_key": "same-okx-key",
            "api_secret": "second-okx-secret",
            "passphrase": "second-passphrase",
            "simulated_trading": False,
        },
        format="json",
    )

    assert first_bybit.status_code == 201
    assert second_bybit.status_code == 201
    assert first_okx.status_code == 201
    assert second_okx.status_code == 201
    assert BybitApiToken.objects.get(id=first_bybit.data["id"]).is_active is False
    assert BybitApiToken.objects.get(id=second_bybit.data["id"]).is_active is True
    assert OKXApiToken.objects.get(id=first_okx.data["id"]).is_active is False
    assert OKXApiToken.objects.get(id=second_okx.data["id"]).is_active is True


@pytest.mark.django_db
def test_replacement_active_token_deactivates_previous_token_with_different_api_key(
    authenticated_client, crypto_broker, okx_broker
):
    first_bybit = authenticated_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": crypto_broker.id,
            "api_key": "first-key",
            "api_secret": "first-secret",
            "testnet": False,
        },
        format="json",
    )
    second_bybit = authenticated_client.post(
        "/users/api/bybit-tokens/",
        {
            "broker": crypto_broker.id,
            "api_key": "second-key",
            "api_secret": "second-secret",
            "testnet": False,
        },
        format="json",
    )
    first_okx = authenticated_client.post(
        "/users/api/okx-tokens/",
        {
            "broker": okx_broker.id,
            "api_key": "first-okx-key",
            "api_secret": "first-okx-secret",
            "passphrase": "first-passphrase",
            "simulated_trading": False,
        },
        format="json",
    )
    second_okx = authenticated_client.post(
        "/users/api/okx-tokens/",
        {
            "broker": okx_broker.id,
            "api_key": "second-okx-key",
            "api_secret": "second-okx-secret",
            "passphrase": "second-passphrase",
            "simulated_trading": False,
        },
        format="json",
    )

    assert first_bybit.status_code == 201
    assert second_bybit.status_code == 201
    assert first_okx.status_code == 201
    assert second_okx.status_code == 201
    assert BybitApiToken.objects.get(id=first_bybit.data["id"]).is_active is False
    assert BybitApiToken.objects.get(id=second_bybit.data["id"]).is_active is True
    assert OKXApiToken.objects.get(id=first_okx.data["id"]).is_active is False
    assert OKXApiToken.objects.get(id=second_okx.data["id"]).is_active is True


@pytest.mark.django_db
def test_crypto_token_update_deactivates_conflicting_token_in_target_environment(
    user, authenticated_client, crypto_broker
):
    live_token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="live-key",
        testnet=False,
    )
    live_token.set_api_secret("live-secret", user)
    testnet_token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="testnet-key",
        testnet=True,
    )
    testnet_token.set_api_secret("testnet-secret", user)

    response = authenticated_client.patch(
        f"/users/api/bybit-tokens/{testnet_token.id}/",
        {"testnet": False},
        format="json",
    )

    assert response.status_code == 200
    live_token.refresh_from_db()
    testnet_token.refresh_from_db()
    assert live_token.is_active is False
    assert testnet_token.is_active is True
    assert testnet_token.testnet is False


@pytest.mark.django_db
def test_crypto_verify_and_test_connection_do_not_mark_tokens_active(
    user, authenticated_client, crypto_broker, okx_broker
):
    bybit_token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="bybit-key",
        testnet=False,
        is_active=False,
    )
    bybit_token.set_api_secret("bybit-secret", user)
    bybit_token.is_active = False
    bybit_token.save()
    okx_token = OKXApiToken(
        user=user,
        broker=okx_broker,
        api_key="okx-key",
        simulated_trading=False,
        is_active=False,
    )
    okx_token.set_credentials("okx-secret", "okx-passphrase", user)
    okx_token.is_active = False
    okx_token.save()

    verify_response = authenticated_client.post(
        "/users/api/bybit-tokens/verify_token/",
        {
            "api_key": "anything",
            "api_secret": "anything",
        },
        format="json",
    )
    bybit_test_response = authenticated_client.post(
        f"/users/api/bybit-tokens/{bybit_token.id}/test_connection/",
        {},
        format="json",
    )
    okx_test_response = authenticated_client.post(
        f"/users/api/okx-tokens/{okx_token.id}/test_connection/",
        {},
        format="json",
    )

    assert verify_response.status_code == 501
    assert bybit_test_response.status_code == 501
    assert okx_test_response.status_code == 501
    bybit_token.refresh_from_db()
    okx_token.refresh_from_db()
    assert bybit_token.is_active is False
    assert okx_token.is_active is False
    _assert_safe_token_payload(bybit_test_response.data["token"])
    _assert_safe_token_payload(okx_test_response.data["token"])


@pytest.mark.django_db
def test_broker_tokens_includes_bybit_and_okx_without_secrets(
    user, authenticated_client, crypto_broker, okx_broker
):
    bybit_token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="bybit-key",
        testnet=True,
    )
    bybit_token.set_api_secret("bybit-secret", user)
    okx_token = OKXApiToken(
        user=user,
        broker=okx_broker,
        api_key="okx-key",
        simulated_trading=False,
    )
    okx_token.set_credentials("okx-secret", "okx-passphrase", user)

    response = authenticated_client.get("/users/api/broker_tokens/")

    assert response.status_code == 200
    assert response.data["bybit_tokens"][0]["api_key"] == "bybit-key"
    assert response.data["okx_tokens"][0]["api_key"] == "okx-key"
    _assert_safe_token_payload(response.data["bybit_tokens"][0])
    _assert_safe_token_payload(response.data["okx_tokens"][0])


@pytest.mark.django_db
def test_brokers_with_active_tokens_includes_active_bybit_and_okx_tokens(
    user, authenticated_client, crypto_broker, okx_broker
):
    inactive_broker = Brokers.objects.create(investor=user, name="Inactive", country="Crypto")
    bybit_token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="bybit-key",
        testnet=False,
    )
    bybit_token.set_api_secret("bybit-secret", user)
    okx_token = OKXApiToken(
        user=user,
        broker=okx_broker,
        api_key="okx-key",
        simulated_trading=False,
    )
    okx_token.set_credentials("okx-secret", "okx-passphrase", user)
    inactive_token = BybitApiToken(
        user=user,
        broker=inactive_broker,
        api_key="inactive-key",
        testnet=False,
        is_active=False,
    )
    inactive_token.set_api_secret("inactive-secret", user)
    inactive_token.is_active = False
    inactive_token.save()

    response = authenticated_client.get("/database/api/brokers/", {"with_active_tokens": "1"})

    assert response.status_code == 200
    names = {item["name"] for item in response.data}
    assert names == {"Bybit", "OKX"}


@pytest.mark.django_db
def test_revoke_token_supports_bybit_and_okx(
    user, authenticated_client, crypto_broker, okx_broker
):
    bybit_token = BybitApiToken(
        user=user,
        broker=crypto_broker,
        api_key="bybit-key",
        testnet=False,
    )
    bybit_token.set_api_secret("bybit-secret", user)
    okx_token = OKXApiToken(
        user=user,
        broker=okx_broker,
        api_key="okx-key",
        simulated_trading=False,
    )
    okx_token.set_credentials("okx-secret", "okx-passphrase", user)

    bybit_response = authenticated_client.post(
        "/users/api/revoke_token/",
        {"token_type": "bybit", "token_id": bybit_token.id},
        format="json",
    )
    okx_response = authenticated_client.post(
        "/users/api/revoke_token/",
        {"token_type": "okx", "token_id": okx_token.id},
        format="json",
    )

    assert bybit_response.status_code == 200
    assert okx_response.status_code == 200
    assert BybitApiToken.objects.get(id=bybit_token.id).is_active is False
    assert OKXApiToken.objects.get(id=okx_token.id).is_active is False

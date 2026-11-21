import traceback

import httpx
import pytest
import respx
from apiReading.exceptions import ApiAuthError, ApiConnectionError, ApiHttpError, ApiResponseError
from articleScraping.diffbot import DIFFBOT_URL, DiffbotArticleClient


@pytest.mark.asyncio
async def test_diffbot_request_uses_query_params_and_whitelists_response() -> None:
    token = "secret-token-value"
    requested_url = "https://news.example/a?x=1&token=attacker#fragment"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL).respond(
            200,
            json={
                "objects": [
                    {
                        "type": "article",
                        "title": "News",
                        "text": "Article body",
                        "author": "Reporter",
                        "date": "Wed, 18 Nov 2026 08:00:00 GMT",
                        "html": "must not be retained",
                        "links": ["must not be retained"],
                    }
                ]
            },
        )
        article = await DiffbotArticleClient(api_key=token).extract(requested_url)

    params = route.calls[0].request.url.params
    assert params["token"] == token
    assert params["url"] == requested_url
    assert params["discussion"] == "false"
    assert params["timeout"] == "29000"
    assert article.text == "Article body"
    assert "html" not in article.__dict__


@pytest.mark.asyncio
async def test_missing_token_fails_without_request() -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(DIFFBOT_URL)
        with pytest.raises(ApiAuthError):
            await DiffbotArticleClient().extract("https://news.example/article")
    assert router.calls.call_count == 0


@pytest.mark.asyncio
async def test_diffbot_retries_429_with_retry_after_then_extracts() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL)
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"objects": [{"type": "article", "text": "body"}]}),
        ]
        article = await DiffbotArticleClient(api_key="token", retry_backoff=0).extract(
            "https://news.example/article"
        )

    assert route.call_count == 2
    assert article.text == "body"


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "error_type"), [(401, ApiAuthError), (404, ApiHttpError)])
async def test_diffbot_http_auth_and_not_found_statuses_are_not_retried(status, error_type) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get(DIFFBOT_URL).respond(status_code=status)
        with pytest.raises(error_type) as error:
            await DiffbotArticleClient(api_key="token").extract("https://news.example/article")

    assert route.call_count == 1
    assert error.value.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"errorCode": 401, "error": "private response text"}, ApiAuthError),
        ({"code": 502, "message": "private response text"}, ApiResponseError),
        ({"objects": []}, ApiResponseError),
        ({"objects": [{"type": "page", "text": "body"}]}, ApiResponseError),
    ],
)
async def test_diffbot_maps_error_shapes_without_returning_provider_messages(
    payload, error_type
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(DIFFBOT_URL).respond(200, json=payload)
        with pytest.raises(error_type) as error:
            await DiffbotArticleClient(api_key="secret-token", max_retries=0).extract(
                "https://news.example/article"
            )

    assert "private response" not in str(error.value)
    assert error.value.cause is None


@pytest.mark.asyncio
async def test_diffbot_transport_errors_do_not_expose_token_in_exception_chain() -> None:
    token = "top-secret-token"

    async def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection failed for {request.url}", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
    scraper = DiffbotArticleClient(client=client, api_key=token, max_retries=0)
    try:
        with pytest.raises(ApiConnectionError) as error:
            await scraper.extract("https://news.example/article")
        formatted = "".join(traceback.format_exception(error.value))
        assert token not in str(error.value)
        assert token not in repr(error.value)
        assert token not in formatted
        assert error.value.cause is None
        assert error.value.__cause__ is None
        assert error.value.__context__ is None
        assert token not in repr(scraper)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_diffbot_enforces_streamed_response_size_limit() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(DIFFBOT_URL).respond(200, content=b"x" * 64)
        with pytest.raises(ApiResponseError):
            await DiffbotArticleClient(api_key="token", max_response_bytes=16).extract(
                "https://news.example/article"
            )


@pytest.mark.asyncio
async def test_diffbot_never_follows_redirects_even_if_injected_client_would() -> None:
    requests: list[httpx.Request] = []

    async def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(redirect),
        follow_redirects=True,
    )
    try:
        with pytest.raises(ApiHttpError):
            await DiffbotArticleClient(client=client, api_key="token", max_retries=0).extract(
                "https://news.example/article"
            )
    finally:
        await client.aclose()
    assert len(requests) == 1

import asyncio
import functools
import json
import logging
import os
import time
from functools import lru_cache
from typing import Callable, Dict, Iterator, List, Tuple, Type

import diskcache  # type: ignore

# https://github.com/prius/python-leetcode
import leetcode.api.default_api  # type: ignore
import leetcode.api_client  # type: ignore
import leetcode.auth  # type: ignore
import leetcode.configuration  # type: ignore
import leetcode.models.graphql_query  # type: ignore
import leetcode.models.graphql_query_get_question_detail_variables  # type: ignore
import urllib3  # type: ignore

CACHE_DIR = "cache"


leetcode_api_access_lock = asyncio.Lock()


@lru_cache(None)
def _get_leetcode_api_client() -> leetcode.api.default_api.DefaultApi:
    """
    Leetcode API instance constructor.

    This is a singleton, because we don't need to create a separate client
    each time
    """
    configuration = leetcode.configuration.Configuration()

    session_id = os.environ["LEETCODE_SESSION_ID"]
    csrf_token = leetcode.auth.get_csrf_cookie(session_id)

    configuration.api_key["x-csrftoken"] = csrf_token
    configuration.api_key["csrftoken"] = csrf_token
    configuration.api_key["LEETCODE_SESSION"] = session_id
    configuration.api_key["Referer"] = "https://leetcode.com"
    configuration.debug = False
    api_instance = leetcode.api.default_api.DefaultApi(
        leetcode.api_client.ApiClient(configuration)
    )

    return api_instance


def get_leetcode_task_handles() -> Iterator[Tuple[str, str, str]]:
    """
    Get task handles for all the leetcode problems.
    """
    api_instance = _get_leetcode_api_client()

    for topic in ["algorithms", "database", "shell", "concurrency"]:
        api_response = api_instance.api_problems_topic_get(topic=topic)
        for stat_status_pair in api_response.stat_status_pairs:
            stat = stat_status_pair.stat

            yield (topic, stat.question__title, stat.question__title_slug)


def retry(times: int, exceptions: Tuple[Type[Exception]], delay: float) -> Callable:
    """
    Retry Decorator
    Retries the wrapped function/method `times` times if the exceptions listed
    in `exceptions` are thrown
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(times - 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions:
                    logging.exception(
                        "Exception occured, try %s/%s", attempt + 1, times
                    )
                    time.sleep(delay)

            logging.error("Last try")
            return await func(*args, **kwargs)

        return wrapper

    return decorator


class LeetcodeData:
    """
    Retrieves and caches the data for problems, acquired from the leetcode API.

    This data can be later accessed using provided methods with corresponding
    names.
    """

    def __init__(self) -> None:
        """
        Initialize leetcode API and disk cache for API responses
        """
        self._api_instance = _get_leetcode_api_client()

        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)
        self._cache = diskcache.Cache(CACHE_DIR)

    @retry(times=3, exceptions=(urllib3.exceptions.ProtocolError,), delay=5)
    async def _get_problem_data(self, problem_slug: str) -> Dict[str, str]:
        """
        Get data about a specific problem (method output if cached to reduce
        the load on the leetcode API)
        """
        if problem_slug in self._cache:
            return self._cache[problem_slug]

        api_instance = self._api_instance

        graphql_request = leetcode.models.graphql_query.GraphqlQuery(
            query="""
                query getQuestionDetail($titleSlug: String!) {
                  question(titleSlug: $titleSlug) {
                    freqBar
                    questionId
                    questionFrontendId
                    boundTopicId
                    title
                    content
                    translatedTitle
                    translatedContent
                    isPaidOnly
                    difficulty
                    likes
                    dislikes
                    isLiked
                    similarQuestions
                    contributors {
                      username
                      profileUrl
                      avatarUrl
                      __typename
                    }
                    langToValidPlayground
                    topicTags {
                      name
                      slug
                      translatedName
                      __typename
                    }
                    companyTagStats
                    codeSnippets {
                      lang
                      langSlug
                      code
                      __typename
                    }
                    stats
                    hints
                    solution {
                      id
                      canSeeDetail
                      __typename
                    }
                    status
                    sampleTestCase
                    metaData
                    judgerAvailable
                    judgeType
                    mysqlSchemas
                    enableRunCode
                    enableTestMode
                    envInfo
                    __typename
                  }
                }
            """,
            variables=leetcode.models.graphql_query_get_question_detail_variables.GraphqlQueryGetQuestionDetailVariables(  # noqa: E501
                title_slug=problem_slug
            ),
            operation_name="getQuestionDetail",
        )

        # Critical section. Don't allow more than one parallel request to
        # the Leetcode API
        async with leetcode_api_access_lock:
            time.sleep(2)  # Leetcode has a rate limiter
            data = api_instance.graphql_post(body=graphql_request).data.question

        # Save data in the cache
        self._cache[problem_slug] = data

        return data

    async def _get_description(self, problem_slug: str) -> str:
        """
        Problem description
        """
        data = await self._get_problem_data(problem_slug)
        return data.content or "No content"

    async def _stats(self, problem_slug: str) -> Dict[str, str]:
        """
        Various stats about problem. Such as number of accepted solutions, etc.
        """
        data = await self._get_problem_data(problem_slug)
        return json.loads(data.stats)

    async def submissions_total(self, problem_slug: str) -> int:
        """
        Total number of submissions of the problem
        """
        return int((await self._stats(problem_slug))["totalSubmissionRaw"])

    async def submissions_accepted(self, problem_slug: str) -> int:
        """
        Number of accepted submissions of the problem
        """
        return int((await self._stats(problem_slug))["totalAcceptedRaw"])

    async def description(self, problem_slug: str) -> str:
        """
        Problem description
        """
        return await self._get_description(problem_slug)

    async def difficulty(self, problem_slug: str) -> str:
        """
        Problem difficulty. Returns colored HTML version, so it can be used
        directly in Anki
        """
        data = await self._get_problem_data(problem_slug)
        diff = data.difficulty

        if diff == "Easy":
            return "<font color='green'>Easy</font>"

        if diff == "Medium":
            return "<font color='orange'>Medium</font>"

        if diff == "Hard":
            return "<font color='red'>Hard</font>"

        raise ValueError(f"Incorrect difficulty: {diff}")

    async def paid(self, problem_slug: str) -> str:
        """
        Problem's "available for paid subsribers" status
        """
        data = await self._get_problem_data(problem_slug)
        return data.is_paid_only

    async def problem_id(self, problem_slug: str) -> str:
        """
        Numerical id of the problem
        """
        data = await self._get_problem_data(problem_slug)
        return data.question_frontend_id

    async def likes(self, problem_slug: str) -> int:
        """
        Number of likes for the problem
        """
        data = await self._get_problem_data(problem_slug)
        likes = data.likes

        if not isinstance(likes, int):
            raise ValueError(f"Likes should be int: {likes}")

        return likes

    async def dislikes(self, problem_slug: str) -> int:
        """
        Number of dislikes for the problem
        """
        data = await self._get_problem_data(problem_slug)
        dislikes = data.dislikes

        if not isinstance(dislikes, int):
            raise ValueError(f"Dislikes should be int: {dislikes}")

        return dislikes

    async def tags(self, problem_slug: str) -> List[str]:
        """
        List of the tags for this problem (string slugs)
        """
        data = await self._get_problem_data(problem_slug)
        return list(map(lambda x: x.slug, data.topic_tags))

    async def freq_bar(self, problem_slug: str) -> float:
        """
        Returns percentage for frequency bar
        """
        data = await self._get_problem_data(problem_slug)
        return data.freq_bar or 0

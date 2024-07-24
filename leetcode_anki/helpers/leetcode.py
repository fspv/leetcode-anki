# pylint: disable=missing-module-docstring
import functools
import json
import logging
import math
import os
import time
from functools import cached_property
from typing import Any, Callable, Dict, List, Tuple, Type, TypeVar

# https://github.com/prius/python-leetcode
import leetcode.api.default_api  # type: ignore
import leetcode.api_client  # type: ignore
import leetcode.auth  # type: ignore
import leetcode.configuration  # type: ignore
import leetcode.models.graphql_query  # type: ignore
import leetcode.models.graphql_query_get_question_detail_variables  # type: ignore
import leetcode.models.graphql_query_problemset_question_list_variables  # type: ignore
import leetcode.models.graphql_query_problemset_question_list_variables_filter_input  # type: ignore
import leetcode.models.graphql_question_detail  # type: ignore
import urllib3  # type: ignore
from tqdm import tqdm  # type: ignore

CACHE_DIR = "cache"


def _get_leetcode_api_client() -> leetcode.api.default_api.DefaultApi:
    """
    Leetcode API instance constructor.

    This is a singleton, because we don't need to create a separate client
    each time
    """

    configuration = leetcode.configuration.Configuration()

    session_id = os.environ["LEETCODE_SESSION_ID"]
    csrf_token = os.environ.get("LEETCODE_CSRF_TOKEN", None)
    # Probably method is deprecated since ~24.07.2024,
    #  ref to https://github.com/fspv/leetcode-anki/issues/39.
    # TODO: check new versions for smooth integration of csrf_cookie.
    csrf_token = leetcode.auth.get_csrf_cookie(session_id) if csrf_token is None else csrf_token

    configuration.api_key["x-csrftoken"] = csrf_token
    configuration.api_key["csrftoken"] = csrf_token
    configuration.api_key["LEETCODE_SESSION"] = session_id
    configuration.api_key["Referer"] = "https://leetcode.com"
    configuration.debug = False
    api_instance = leetcode.api.default_api.DefaultApi(
        leetcode.api_client.ApiClient(configuration)
    )

    return api_instance


_T = TypeVar("_T")


class _RetryDecorator:
    _times: int
    _exceptions: Tuple[Type[Exception]]
    _delay: float

    def __init__(
            self, times: int, exceptions: Tuple[Type[Exception]], delay: float
    ) -> None:
        self._times = times
        self._exceptions = exceptions
        self._delay = delay

    def __call__(self, func: Callable[..., _T]) -> Callable[..., _T]:
        times: int = self._times
        exceptions: Tuple[Type[Exception]] = self._exceptions
        delay: float = self._delay

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> _T:
            for attempt in range(times - 1):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    logging.exception(
                        "Exception occured, try %s/%s", attempt + 1, times
                    )
                    time.sleep(delay)

            logging.error("Last try")
            return func(*args, **kwargs)

        return wrapper


def retry(
        times: int, exceptions: Tuple[Type[Exception]], delay: float
) -> _RetryDecorator:
    """
    Retry Decorator
    Retries the wrapped function/method `times` times if the exceptions listed
    in `exceptions` are thrown
    """

    return _RetryDecorator(times, exceptions, delay)


class LeetcodeData:
    """
    Retrieves and caches the data for problems, acquired from the leetcode API.

    This data can be later accessed using provided methods with corresponding
    names.
    """
    # Leetcode has a rate limiter.
    LEETCODE_API_REQUEST_DELAY = 2
    SUBMISSION_STATUS_ACCEPTED = 10

    def __init__(
            self, start: int, stop: int, page_size: int = 1000, list_id: str = "", status: str = "", include_last_submission: bool = False
    ) -> None:
        """
        Initialize leetcode API and disk cache for API responses
        @param status: if status is "AC" then only accepted solutions will be fetched.
        @param include_last_submission: if True, then last accepted submission will be fetched for each problem.
         Note, that this is very heavy operation as it add 2 additional requests per problem.
        """
        if start < 0:
            raise ValueError(f"Start must be non-negative: {start}")

        if stop < 0:
            raise ValueError(f"Stop must be non-negative: {start}")

        if page_size < 0:
            raise ValueError(f"Page size must be greater than 0: {page_size}")

        if start > stop:
            raise ValueError(f"Start (){start}) must be not greater than stop ({stop})")

        self._start = start
        self._stop = stop
        self._page_size = page_size
        self._list_id = list_id
        self.status = status if status != "" else None
        self.include_last_submission = include_last_submission

    @cached_property
    def _api_instance(self) -> leetcode.api.default_api.DefaultApi:
        return _get_leetcode_api_client()

    @cached_property
    def _cache(
            self,
    ) -> Dict[str, leetcode.models.graphql_question_detail.GraphqlQuestionDetail]:
        """
        Cached method to return dict (problem_slug -> question details)
        """
        problems = self._get_problems_data()
        return {problem.title_slug: problem for problem in problems}

    @cached_property
    def _cache_user_submissions(
            self,
    ) -> Dict[str, str]:
        """
        Cached method to return dict (problem_slug -> last submitted accepted user solution)
        """
        problem_to_submission = self._get_submissions_codes_data()
        return {problem_slug: code_data for problem_slug, code_data in problem_to_submission.items()}

    @retry(times=3, exceptions=(urllib3.exceptions.ProtocolError,), delay=5)
    def _get_problems_count(self) -> int:
        api_instance = self._api_instance

        graphql_request = leetcode.models.graphql_query.GraphqlQuery(
            query="""
            query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
              problemsetQuestionList: questionList(
                categorySlug: $categorySlug
                limit: $limit
                skip: $skip
                filters: $filters
              ) {
                totalNum
              }
            }
            """,
            variables=leetcode.models.graphql_query_problemset_question_list_variables.GraphqlQueryProblemsetQuestionListVariables(
                category_slug="",
                limit=1,
                skip=0,
                filters=leetcode.models.graphql_query_problemset_question_list_variables_filter_input.GraphqlQueryProblemsetQuestionListVariablesFilterInput(
                    tags=[],
                    list_id=self._list_id,
                    status=self.status,
                    # difficulty="MEDIUM",
                    # list_id="7p5x763",  # Top Amazon Questions
                    # premium_only=False,
                ),
            ),
            operation_name="problemsetQuestionList",
        )

        time.sleep(self.LEETCODE_API_REQUEST_DELAY)  # Leetcode has a rate limiter
        data = api_instance.graphql_post(body=graphql_request).data

        return data.problemset_question_list.total_num or 0

    @retry(times=3, exceptions=(urllib3.exceptions.ProtocolError,), delay=5)
    def _get_problems_data_page(
            self, offset: int, page_size: int, page: int
    ) -> List[leetcode.models.graphql_question_detail.GraphqlQuestionDetail]:
        api_instance = self._api_instance
        graphql_request = leetcode.models.graphql_query.GraphqlQuery(
            query="""
            query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
              problemsetQuestionList: questionList(
                categorySlug: $categorySlug
                limit: $limit
                skip: $skip
                filters: $filters
              ) {
                questions: data {
                    questionFrontendId
                    title
                    titleSlug
                    categoryTitle
                    freqBar
                    content
                    isPaidOnly
                    difficulty
                    likes
                    dislikes
                    topicTags {
                      name
                      slug
                    }
                    stats
                    hints
                }
              }
            }
            """,
            variables=leetcode.models.graphql_query_problemset_question_list_variables.GraphqlQueryProblemsetQuestionListVariables(
                category_slug="",
                limit=page_size,
                skip=offset + page * page_size,
                filters=leetcode.models.graphql_query_problemset_question_list_variables_filter_input.GraphqlQueryProblemsetQuestionListVariablesFilterInput(
                    list_id=self._list_id,
                    status=self.status,
                ),
            ),
            operation_name="problemsetQuestionList",
        )

        time.sleep(self.LEETCODE_API_REQUEST_DELAY)  # Leetcode has a rate limiter
        data = api_instance.graphql_post(
            body=graphql_request
        ).data.problemset_question_list.questions

        return data

    def _get_problems_data(
            self,
    ) -> List[leetcode.models.graphql_question_detail.GraphqlQuestionDetail]:
        problem_count = self._get_problems_count()

        if self._start > problem_count:
            raise ValueError(
                "Start ({self._start}) is greater than problems count ({problem_count})"
            )

        start = self._start
        stop = min(self._stop, problem_count)

        page_size = min(self._page_size, stop - start + 1)

        problems: List[
            leetcode.models.graphql_question_detail.GraphqlQuestionDetail
        ] = []

        logging.info("Fetching %s problems %s per page", stop - start + 1, page_size)

        for page in tqdm(
                range(math.ceil((stop - start + 1) / page_size)),
                unit="problem",
                unit_scale=page_size,
        ):
            data = self._get_problems_data_page(start, page_size, page)
            problems.extend(data)

        return problems

    @retry(times=3, exceptions=(urllib3.exceptions.ProtocolError,), delay=5)
    def _get_submissions_codes_data(self) -> Dict[str, str]:
        """It collects all submissions for the cached problems of the current class object."""
        all_fetched_problems = self._cache.keys()
        problem_to_submission: Dict[str, str] = {}

        for problem_slug in tqdm(
                all_fetched_problems,
                unit="Problem",
        ):
            logging.info("Fetching submission for problem: %s ", problem_slug)
            try:
                data = self.get_submission_code(problem_slug)
            except Exception as e:
                # Log only if submission was expected to be found.
                if self.status and self.include_last_submission:
                    logging.error("Error fetching submission for problem: %s", problem_slug)
                    logging.exception(e)
                data = ""
            problem_to_submission[problem_slug] = data
        return problem_to_submission

    def get_submission_code(self, problem_slug: str) -> str:
        """
        [Experimental feature, 24.07.24] Get user (depends on session cookies) last submitted code 
        that was accepted for the given problem.
        
        Note:
        - it is sync request.
        - it uses 2 raw requests under the hood to leetcode graphQL endpoints.
        """
        LIMIT = 500  # Max number of submissions to fetch.

        data = self._api_instance.graphql_post(
            body={
                "query": """
            query submissionList($offset: Int!, $limit: Int!, $lastKey: String, $questionSlug: String!, $lang: Int, $status: Int) {
            questionSubmissionList(
                offset: $offset
                limit: $limit
                lastKey: $lastKey
                questionSlug: $questionSlug
                lang: $lang
                status: $status
            ) {
                lastKey
                hasNext
                submissions {
                    id
                }
            }
        }
        """,
                "variables": {
                    "questionSlug": problem_slug,
                    "offset": 0,
                    "limit": LIMIT,
                    "lastKey": None,
                    "status": self.SUBMISSION_STATUS_ACCEPTED,
                },
                "operationName": "submissionList"
            },
            _preload_content=False,  # The key to make it works and return raw content.
        )
        # Reponse format: {'data': {'questionSubmissionList':
        #  {'lastKey': None, 'hasNext': False, 'submissions': [{'id': '969483658', <...>}]}}}
        payload = data.json()

        # Check that somthing returnd and remember the first id.
        accepted_submissions = payload.get("data", {}).get("questionSubmissionList", {}).get("submissions", {})
        if not accepted_submissions:
            raise Exception("No accepted submissions found")
        first_submission_id = accepted_submissions[0]["id"]

        time.sleep(self.LEETCODE_API_REQUEST_DELAY)

        # Get Submission details (we want to get code part).
        data = self._api_instance.graphql_post(
            body={
                "query": """
        query submissionDetails($submissionId: Int!) {
            submissionDetails(submissionId: $submissionId) {
                code
                lang {
                    name
                    verboseName
                }
            }
        }
        """,
                "variables": {
                    "submissionId": first_submission_id
                },
                "operationName": "submissionDetails"
            },
            _preload_content=False,  # The key to make it work and return raw content.
        )
        # E.g. repspons: { "data": { "submissionDetails": { <...> "code": "<...>", <...>} } }
        payload = data.json()
        # Get code if possible.
        code = payload.get("data", {}).get("submissionDetails", {}).get("code", "")
        if not code:
            raise Exception("No code found")

        return code

    async def all_problems_handles(self) -> List[str]:
        """
        Get all problem handles known.
        This method is used to initiate fetching of all data needed from Leetcode, and via blocking call.

        Example: ["two-sum", "three-sum"]
        """
        # Fetch problems if not yet fetched.
        problem_slugs = list(self._cache.keys())

        # Fetch submissions if not yet fetched and needed.
        if self.include_last_submission:
            _ = self._cache_user_submissions

        return problem_slugs

    def _get_problem_data(
            self, problem_slug: str
    ) -> leetcode.models.graphql_question_detail.GraphqlQuestionDetail:
        """
        TODO: Legacy method. Needed in the old architecture. Can be replaced
        with direct cache calls later.
        """
        cache = self._cache
        if problem_slug in cache:
            return cache[problem_slug]

        raise ValueError(f"Problem {problem_slug} is not in cache")

    async def last_submission_code(self, problem_slug: str) -> str:
        """
        Last accepted submission code.
        """
        return self._cache_user_submissions.get(problem_slug, "No code found.")

    async def _get_description(self, problem_slug: str) -> str:
        """
        Problem description
        """
        data = self._get_problem_data(problem_slug)
        return data.content or "No content"

    async def _stats(self, problem_slug: str) -> Dict[str, str]:
        """
        Various stats about problem. Such as number of accepted solutions, etc.
        """
        data = self._get_problem_data(problem_slug)
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
        data = self._get_problem_data(problem_slug)
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
        data = self._get_problem_data(problem_slug)
        return data.is_paid_only

    async def problem_id(self, problem_slug: str) -> str:
        """
        Numerical id of the problem
        """
        data = self._get_problem_data(problem_slug)
        return data.question_frontend_id

    async def likes(self, problem_slug: str) -> int:
        """
        Number of likes for the problem
        """
        data = self._get_problem_data(problem_slug)
        likes = data.likes

        if not isinstance(likes, int):
            raise ValueError(f"Likes should be int: {likes}")

        return likes

    async def dislikes(self, problem_slug: str) -> int:
        """
        Number of dislikes for the problem
        """
        data = self._get_problem_data(problem_slug)
        dislikes = data.dislikes

        if not isinstance(dislikes, int):
            raise ValueError(f"Dislikes should be int: {dislikes}")

        return dislikes

    async def tags(self, problem_slug: str) -> List[str]:
        """
        List of the tags for this problem (string slugs)
        """
        data = self._get_problem_data(problem_slug)
        tags = list(map(lambda x: x.slug, data.topic_tags))
        tags.append(f"difficulty-{data.difficulty.lower()}-tag")
        return tags

    async def freq_bar(self, problem_slug: str) -> float:
        """
        Returns percentage for frequency bar
        """
        data = self._get_problem_data(problem_slug)
        return data.freq_bar or 0

    async def title(self, problem_slug: str) -> float:
        """
        Returns problem title
        """
        data = self._get_problem_data(problem_slug)
        return data.title

    async def category(self, problem_slug: str) -> float:
        """
        Returns problem category title
        """
        data = self._get_problem_data(problem_slug)
        return data.category_title

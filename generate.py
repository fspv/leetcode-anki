#!/usr/bin/env python3
"""
This script generates an Anki deck with all the leetcode problems currently
known.
"""

import argparse
import asyncio
import functools
import json
import logging
import os
import time
from functools import lru_cache
from typing import Any, Callable, Coroutine, Dict, Iterator, List, Tuple

import diskcache  # type: ignore

# https://github.com/kerrickstaley/genanki
import genanki  # type: ignore

# https://github.com/prius/python-leetcode
import leetcode.api.default_api  # type: ignore
import leetcode.api_client  # type: ignore
import leetcode.auth  # type: ignore
import leetcode.configuration  # type: ignore
import leetcode.models.graphql_query  # type: ignore
import leetcode.models.graphql_query_variables  # type: ignore
import urllib3  # type: ignore
from tqdm import tqdm  # type: ignore

LEETCODE_ANKI_MODEL_ID = 4567610856
LEETCODE_ANKI_DECK_ID = 8589798175
OUTPUT_FILE = "leetcode.apkg"
CACHE_DIR = "cache"
ALLOWED_EXTENSIONS = {".py", ".go"}

leetcode_api_access_lock = asyncio.Lock()


logging.getLogger().setLevel(logging.INFO)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments for the script
    """
    parser = argparse.ArgumentParser(description="Generate Anki cards for leetcode")
    parser.add_argument(
        "--start", type=int, help="Start generation from this problem", default=0
    )
    parser.add_argument(
        "--stop", type=int, help="Stop generation on this problem", default=2 ** 64
    )

    args = parser.parse_args()

    return args


def retry(times: int, exceptions: Tuple[Exception], delay: float) -> Callable:
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
        self._api_instance = get_leetcode_api_client()

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
            variables=leetcode.models.graphql_query_variables.GraphqlQueryVariables(
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


class LeetcodeNote(genanki.Note):
    """
    Extended base class for the Anki note, that correctly sets the unique
    identifier of the note.
    """

    @property
    def guid(self):
        # Hash by leetcode task handle
        return genanki.guid_for(self.fields[0])


@lru_cache(None)
def get_leetcode_api_client() -> leetcode.api.default_api.DefaultApi:
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
    api_instance = get_leetcode_api_client()

    for topic in ["algorithms", "database", "shell", "concurrency"]:
        api_response = api_instance.api_problems_topic_get(topic=topic)
        for stat_status_pair in api_response.stat_status_pairs:
            stat = stat_status_pair.stat

            yield (topic, stat.question__title, stat.question__title_slug)


async def generate_anki_note(
    leetcode_data: LeetcodeData,
    leetcode_model: genanki.Model,
    leetcode_task_handle: str,
    leetcode_task_title: str,
    topic: str,
) -> LeetcodeNote:
    """
    Generate a single Anki flashcard
    """
    return LeetcodeNote(
        model=leetcode_model,
        fields=[
            leetcode_task_handle,
            str(await leetcode_data.problem_id(leetcode_task_handle)),
            leetcode_task_title,
            topic,
            await leetcode_data.description(leetcode_task_handle),
            await leetcode_data.difficulty(leetcode_task_handle),
            "yes" if await leetcode_data.paid(leetcode_task_handle) else "no",
            str(await leetcode_data.likes(leetcode_task_handle)),
            str(await leetcode_data.dislikes(leetcode_task_handle)),
            str(await leetcode_data.submissions_total(leetcode_task_handle)),
            str(await leetcode_data.submissions_accepted(leetcode_task_handle)),
            str(
                int(
                    await leetcode_data.submissions_accepted(leetcode_task_handle)
                    / await leetcode_data.submissions_total(leetcode_task_handle)
                    * 100
                )
            ),
            str(await leetcode_data.freq_bar(leetcode_task_handle)),
        ],
        tags=await leetcode_data.tags(leetcode_task_handle),
        # FIXME: sort field doesn't work doesn't work
        sort_field=str(await leetcode_data.freq_bar(leetcode_task_handle)).zfill(3),
    )


async def generate(start: int, stop: int) -> None:
    """
    Generate an Anki deck
    """
    leetcode_model = genanki.Model(
        LEETCODE_ANKI_MODEL_ID,
        "Leetcode model",
        fields=[
            {"name": "Slug"},
            {"name": "Id"},
            {"name": "Title"},
            {"name": "Topic"},
            {"name": "Content"},
            {"name": "Difficulty"},
            {"name": "Paid"},
            {"name": "Likes"},
            {"name": "Dislikes"},
            {"name": "SubmissionsTotal"},
            {"name": "SubmissionsAccepted"},
            {"name": "SumissionAcceptRate"},
            {"name": "Frequency"},
            # TODO: add hints
        ],
        templates=[
            {
                "name": "Leetcode",
                "qfmt": """
                <h2>{{Id}}. {{Title}}</h2>
                <b>Difficulty:</b> {{Difficulty}}<br/>
                &#128077; {{Likes}} &#128078; {{Dislikes}}<br/>
                <b>Submissions (total/accepted):</b>
                {{SubmissionsTotal}}/{{SubmissionsAccepted}}
                ({{SumissionAcceptRate}}%)
                <br/>
                <b>Topic:</b> {{Topic}}<br/>
                <b>Frequency:</b>
                <progress value="{{Frequency}}" max="100">
                {{Frequency}}%
                </progress>
                <br/>
                <b>URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/'>
                    https://leetcode.com/problems/{{Slug}}/
                </a>
                <br/>
                <h3>Description</h3>
                {{Content}}
                """,
                "afmt": """
                {{FrontSide}}
                <hr id="answer">
                <b>Discuss URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/discuss/'>
                    https://leetcode.com/problems/{{Slug}}/discuss/
                </a>
                <br/>
                <b>Solution URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/solution/'>
                    https://leetcode.com/problems/{{Slug}}/solution/
                </a>
                <br/>
                """,
            },
        ],
    )
    leetcode_deck = genanki.Deck(LEETCODE_ANKI_DECK_ID, "leetcode")
    leetcode_data = LeetcodeData()

    note_generators: List[Coroutine[Any, Any, LeetcodeNote]] = []

    for topic, leetcode_task_title, leetcode_task_handle in list(
        get_leetcode_task_handles()
    )[start:stop]:
        note_generators.append(
            generate_anki_note(
                leetcode_data,
                leetcode_model,
                leetcode_task_handle,
                leetcode_task_title,
                topic,
            )
        )

    for leetcode_note in tqdm(note_generators):
        leetcode_deck.add_note(await leetcode_note)

    genanki.Package(leetcode_deck).write_to_file(OUTPUT_FILE)


async def main() -> None:
    """
    The main script logic
    """
    args = parse_args()

    start, stop = args.start, args.stop
    await generate(start, stop)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

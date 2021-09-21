#!/usr/bin/env python3
import json
import logging
import os
import time
from functools import lru_cache
from typing import Dict, Iterator, List, Tuple

import diskcache
# https://github.com/kerrickstaley/genanki
import genanki  # type: ignore
# https://github.com/prius/python-leetcode
import leetcode  # type: ignore
from tqdm import tqdm

cookies = {
    "csrftoken": os.environ["LEETCODE_CSRF_TOKEN"],
    "LEETCODE_SESSION": os.environ["LEETCODE_SESSION_ID"],
}

LEETCODE_ANKI_MODEL_ID = 4567610856
LEETCODE_ANKI_DECK_ID = 8589798175
OUTPUT_FILE = "leetcode.apkg"
CACHE_DIR = "cache"
ALLOWED_EXTENSIONS = {".py", ".go"}


logging.getLogger().setLevel(logging.INFO)


class LeetcodeData:
    def __init__(self) -> None:
        # Initialize leetcode API client
        cookies = {
            "csrftoken": os.environ["LEETCODE_CSRF_TOKEN"],
            "LEETCODE_SESSION": os.environ["LEETCODE_SESSION_ID"],
        }

        configuration = leetcode.Configuration()

        configuration.api_key["x-csrftoken"] = cookies["csrftoken"]
        configuration.api_key["csrftoken"] = cookies["csrftoken"]
        configuration.api_key["LEETCODE_SESSION"] = cookies["LEETCODE_SESSION"]
        configuration.api_key["Referer"] = "https://leetcode.com"
        configuration.debug = False
        self._api_instance = leetcode.DefaultApi(leetcode.ApiClient(configuration))

        # Init problem data cache
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)
        self._cache = diskcache.Cache(CACHE_DIR)

    def _get_problem_data(self, problem_slug: str) -> Dict[str, str]:
        if problem_slug in self._cache:
            return self._cache[problem_slug]

        time.sleep(2)  # Leetcode has a rate limiter

        api_instance = self._api_instance

        graphql_request = leetcode.GraphqlQuery(
            query="""
                query getQuestionDetail($titleSlug: String!) {
                  question(titleSlug: $titleSlug) {
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
            variables=leetcode.GraphqlQueryVariables(title_slug=problem_slug),
            operation_name="getQuestionDetail",
        )

        data = api_instance.graphql_post(body=graphql_request).data["question"]

        # Save data in the cache
        self._cache[problem_slug] = data

        return data

    def _get_description(self, problem_slug: str) -> str:
        data = self._get_problem_data(problem_slug)
        return data["content"]

    def _stats(self, problem_slug: str) -> Dict[str, str]:
        data = self._get_problem_data(problem_slug)
        return json.loads(data["stats"])

    def submissions_total(self, problem_slug: str) -> int:
        return self._stats(problem_slug)["totalSubmissionRaw"]

    def submissions_accepted(self, problem_slug: str) -> int:
        return self._stats(problem_slug)["totalAcceptedRaw"]

    def description(self, problem_slug: str) -> str:
        return self._get_description(problem_slug)

    def solution(self, problem_slug: str) -> str:
        return ""

    def difficulty(self, problem_slug: str) -> str:
        data = self._get_problem_data(problem_slug)
        diff = data["difficulty"]

        if diff == "Easy":
            return "<font color='green'>Easy</font>"
        elif diff == "Medium":
            return "<font color='orange'>Medium</font>"
        elif diff == "Hard":
            return "<font color='red'>Hard</font>"
        else:
            raise ValueError(f"Incorrect difficulty: {diff}")

    def paid(self, problem_slug: str) -> str:
        data = self._get_problem_data(problem_slug)
        return data["isPaidOnly"]

    def problem_id(self, problem_slug: str) -> str:
        data = self._get_problem_data(problem_slug)
        return data["questionFrontendId"]

    def likes(self, problem_slug: str) -> int:
        data = self._get_problem_data(problem_slug)
        likes = data["likes"]

        if not isinstance(likes, int):
            raise ValueError(f"Likes should be int: {likes}")

        return likes

    def dislikes(self, problem_slug: str) -> int:
        data = self._get_problem_data(problem_slug)
        dislikes = data["dislikes"]

        if not isinstance(dislikes, int):
            raise ValueError(f"Dislikes should be int: {dislikes}")

        return dislikes

    def tags(self, problem_slug: str) -> List[str]:
        data = self._get_problem_data(problem_slug)
        return list(map(lambda x: x["slug"], data["topicTags"]))


class LeetcodeNote(genanki.Note):
    @property
    def guid(self):
        # Hash by leetcode task handle
        return genanki.guid_for(self.fields[0])


@lru_cache(None)
def get_leetcode_api_client() -> leetcode.DefaultApi:
    configuration = leetcode.Configuration()

    configuration.api_key["x-csrftoken"] = cookies["csrftoken"]
    configuration.api_key["csrftoken"] = cookies["csrftoken"]
    configuration.api_key["LEETCODE_SESSION"] = cookies["LEETCODE_SESSION"]
    configuration.api_key["Referer"] = "https://leetcode.com"
    configuration.debug = False
    api_instance = leetcode.DefaultApi(leetcode.ApiClient(configuration))

    return api_instance


def get_leetcode_task_handles() -> Iterator[Tuple[str, str, str]]:
    api_instance = get_leetcode_api_client()

    for topic in ["algorithms", "database", "shell", "concurrency"]:
        api_response = api_instance.api_problems_topic_get(topic=topic)
        for stat_status_pair in api_response.stat_status_pairs:
            stat = stat_status_pair.stat

            yield (topic, stat.question__title, stat.question__title_slug)


def generate() -> None:
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
    for topic, leetcode_task_title, leetcode_task_handle in tqdm(
        list(get_leetcode_task_handles())
    ):

        leetcode_note = LeetcodeNote(
            model=leetcode_model,
            fields=[
                leetcode_task_handle,
                str(leetcode_data.problem_id(leetcode_task_handle)),
                leetcode_task_title,
                topic,
                leetcode_data.description(leetcode_task_handle),
                leetcode_data.difficulty(leetcode_task_handle),
                "yes" if leetcode_data.paid(leetcode_task_handle) else "no",
                str(leetcode_data.likes(leetcode_task_handle)),
                str(leetcode_data.dislikes(leetcode_task_handle)),
                str(leetcode_data.submissions_total(leetcode_task_handle)),
                str(leetcode_data.submissions_accepted(leetcode_task_handle)),
                str(
                    int(
                        leetcode_data.submissions_accepted(leetcode_task_handle)
                        / leetcode_data.submissions_total(leetcode_task_handle)
                        * 100
                    )
                ),
            ],
            tags=leetcode_data.tags(leetcode_task_handle),
        )
        leetcode_deck.add_note(leetcode_note)

        # Write each time due to swagger bug causing the app hang indefinitely
        genanki.Package(leetcode_deck).write_to_file(OUTPUT_FILE)


if __name__ == "__main__":
    generate()
